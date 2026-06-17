"""
Discord bot and alert patterns endpoints
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Body
from models import Settings, DiscordAlertPatterns, DiscordAlertPatternsUpdate
from risk import calculate_position_size
from source_config import (
    apply_source_quantity_limits,
    resolve_source_config,
    source_skip_reason,
)
from typing import Any, Dict
from utils import AVG_DOWN_KEYWORDS, BUY_KEYWORDS, SELL_KEYWORDS, parse_alert
import threading
import logging
import re

_bot_start_lock = threading.Lock()  # FIXED M17: prevent double-start race

router = APIRouter(tags=["Discord"])
logger = logging.getLogger(__name__)
PATTERN_LIST_FIELDS = {
    "buy_patterns",
    "sell_patterns",
    "partial_sell_patterns",
    "average_down_patterns",
    "stop_loss_patterns",
    "take_profit_patterns",
    "ignore_patterns",
}
MAX_PATTERN_LENGTH = 200

# Database reference
db = None

# Discord bot references (will be set by main server)
discord_bot = None
discord_bot_thread = None


def set_db(database):
    """Set the database reference"""
    global db
    db = database


def set_discord_bot(bot, thread):
    """Set discord bot references"""
    global discord_bot, discord_bot_thread
    discord_bot = bot
    discord_bot_thread = thread


def get_discord_bot():
    """Get discord bot for external access"""
    return discord_bot, discord_bot_thread


@router.post("/discord/start")
async def start_discord_bot(background_tasks: BackgroundTasks):
    """Start the Discord bot"""
    global discord_bot_thread
    
    settings = await db.get_settings()
    if not settings or not settings.get('discord_token'):
        raise HTTPException(status_code=400, detail="Discord token not configured")
    
    token = settings['discord_token']
    channel_ids = settings.get('discord_channel_ids', [])
    
    with _bot_start_lock:  # FIXED M17: atomic check-and-start
        if discord_bot_thread and discord_bot_thread.is_alive():
            return {"message": "Discord bot already running"}
        from server import run_discord_bot
        discord_bot_thread = threading.Thread(target=run_discord_bot, args=(token, channel_ids), daemon=True)
        discord_bot_thread.start()
    
    return {"message": "Discord bot starting..."}


@router.post("/discord/stop")
async def stop_discord_bot():
    """Stop the Discord bot"""
    from routes.health import update_bot_status
    
    if discord_bot:
        await discord_bot.close()
        update_bot_status('discord_connected', False)
        return {"message": "Discord bot stopped"}
    return {"message": "Discord bot not running"}


@router.post("/discord/test-connection")
async def test_discord_connection():
    """Test Discord bot connection"""
    from routes.health import bot_status
    
    settings = await db.get_settings()
    if not settings:
        return {"success": False, "status": "not_configured", "message": "Discord not configured", "details": None}
    
    if not settings.get('discord_token'):
        return {"success": False, "status": "no_token", "message": "No Discord bot token configured", "details": None}
    
    bot_running = discord_bot_thread and discord_bot_thread.is_alive()
    bot_connected = bot_status.get('discord_connected', False)
    
    if not bot_running:
        return {
            "success": False, 
            "status": "not_running", 
            "message": "Discord bot not running. Click 'Start Discord Bot'",
            "details": {"token_configured": True, "channel_ids": settings.get('discord_channel_ids', []) or ["All channels"]}
        }
    
    if not bot_connected:
        return {
            "success": False, 
            "status": "connecting", 
            "message": "Discord bot starting up...",
            "details": {"token_configured": True, "channel_ids": settings.get('discord_channel_ids', []) or ["All channels"]}
        }
    
    return {
        "success": True, 
        "status": "connected", 
        "message": "Discord bot connected and listening!",
        "details": {
            "bot_running": True, 
            "monitoring_channels": settings.get('discord_channel_ids', []) or ["All channels"],
            "auto_trading_enabled": bot_status.get('auto_trading_enabled', False),
            "alerts_processed": bot_status.get('alerts_processed', 0)
        }
    }


@router.post("/discord/parse-preview")
async def preview_discord_alert(request: Dict[str, Any] = Body(...)):
    """Preview parser and source-policy behavior without mutating trading state."""
    raw_text = str(request.get("raw_text") or request.get("message") or "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text is required")

    settings = await db.get_settings() if db else {}
    settings = settings or {}
    source_key = str(
        request.get("source_key")
        or request.get("channel_id")
        or request.get("channel_name")
        or "preview"
    )
    source_name = str(request.get("source_name") or request.get("channel_name") or "")

    stored_patterns = await db.get_discord_patterns() if db else {}
    patterns = _merge_pattern_overrides(
        stored_patterns or {},
        request.get("pattern_overrides") or {},
    )
    parsed, parser_metadata = _parse_alert_for_preview(raw_text, patterns or {})
    source_config = resolve_source_config(
        settings,
        channel_id=source_key,
        channel_name=source_name,
    )
    source_override_matched = _source_override_matched(settings, source_key, source_name)

    skip_reason = None
    if parser_metadata.get("ignored"):
        skip_reason = "ignored by alert pattern"
    elif parsed:
        skip_reason = source_skip_reason(parsed, source_config)
    else:
        skip_reason = "unparsed"

    execution_preview = _build_execution_preview(
        settings,
        parsed,
        source_config,
        skip_reason,
        parser_metadata,
    )
    warnings = _build_preview_warnings(
        settings,
        source_config,
        source_override_matched,
        skip_reason,
        parser_metadata,
        execution_preview,
    )

    return {
        "raw_text": raw_text,
        "parsed": parsed,
        "source_config": source_config,
        "skip_reason": skip_reason,
        "confidence": parser_metadata.get("confidence", "none"),
        "warnings": warnings,
        "parser_metadata": parser_metadata,
        "execution_preview": execution_preview,
    }


def _parse_alert_for_preview(
    raw_text: str,
    patterns: Dict[str, Any],
) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
    metadata: Dict[str, Any] = {
        "configured_patterns": bool(patterns),
        "matched_pattern": None,
        "matched_pattern_type": None,
        "pattern_source": None,
        "ignored": False,
        "explicit_action": False,
        "assumed_action": None,
        "confidence": "none",
    }
    case_sensitive = bool(patterns.get("case_sensitive", False))
    explicit_action = _has_builtin_action_keyword(raw_text)
    metadata["explicit_action"] = explicit_action

    ignore_match = _first_matching_pattern(
        raw_text,
        patterns.get("ignore_patterns", []),
        case_sensitive=case_sensitive,
    )
    if ignore_match:
        metadata.update(
            {
                "matched_pattern": ignore_match,
                "matched_pattern_type": "ignore_patterns",
                "pattern_source": _pattern_source(patterns, "ignore_patterns", ignore_match),
                "ignored": True,
                "confidence": "high",
            }
        )
        return None, metadata

    canonical_text = raw_text
    for pattern_type, canonical_action in (
        ("average_down_patterns", "AVERAGE DOWN"),
        ("partial_sell_patterns", "SELL"),
        ("sell_patterns", "SELL"),
        ("buy_patterns", "BUY"),
    ):
        match = _first_matching_pattern(
            raw_text,
            patterns.get(pattern_type, []),
            case_sensitive=case_sensitive,
        )
        if match:
            metadata["matched_pattern"] = match
            metadata["matched_pattern_type"] = pattern_type
            metadata["pattern_source"] = _pattern_source(patterns, pattern_type, match)
            metadata["explicit_action"] = True
            metadata["confidence"] = "high"
            canonical_text = _canonicalize_pattern_action(
                raw_text,
                match,
                canonical_action,
                case_sensitive=case_sensitive,
            )
            break

    parsed = parse_alert(canonical_text)
    if parsed and metadata["confidence"] == "none":
        if explicit_action:
            metadata["confidence"] = "medium"
        else:
            metadata["confidence"] = "low"
            metadata["assumed_action"] = parsed.get("alert_type")
    return parsed, metadata


def _has_builtin_action_keyword(raw_text: str) -> bool:
    return any(
        _contains_preview_keyword(raw_text, keyword)
        for keyword in BUY_KEYWORDS + SELL_KEYWORDS + AVG_DOWN_KEYWORDS
    )


def _contains_preview_keyword(raw_text: str, keyword: str) -> bool:
    parts = [re.escape(part) for part in str(keyword).strip().split()]
    if not parts:
        return False
    body = r"\s+".join(parts)
    return re.search(rf"(?<![A-Z0-9]){body}(?![A-Z0-9])", raw_text, re.IGNORECASE) is not None


def _canonicalize_pattern_action(
    raw_text: str,
    matched_pattern: str,
    canonical_action: str,
    *,
    case_sensitive: bool,
) -> str:
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.escape(str(matched_pattern or "").strip())
    if not pattern:
        return f"{canonical_action} {raw_text}"
    canonical_text, replacements = re.subn(
        pattern,
        canonical_action,
        raw_text,
        count=1,
        flags=flags,
    )
    if replacements:
        return canonical_text
    return f"{canonical_action} {raw_text}"


def _merge_pattern_overrides(
    stored_patterns: Dict[str, Any],
    pattern_overrides: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(stored_patterns or {})
    normalized_overrides = _normalize_alert_pattern_lists(pattern_overrides or {})
    for key, value in normalized_overrides.items():
        merged[key] = value
    merged["_override_keys"] = set(normalized_overrides.keys())
    return merged


def _normalize_alert_pattern_lists(patterns: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(patterns or {})
    for key in PATTERN_LIST_FIELDS:
        if key not in normalized:
            continue
        values = normalized[key]
        if not isinstance(values, list):
            raise HTTPException(status_code=400, detail=f"{key} must be a list")
        normalized[key] = [_validate_alert_pattern(pattern) for pattern in values]
    return normalized


def _validate_alert_pattern(pattern: Any) -> str:
    value = str(pattern or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Pattern cannot be empty")
    if len(value) > MAX_PATTERN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Pattern too long (max {MAX_PATTERN_LENGTH} chars)",
        )
    return value


def _pattern_source(patterns: Dict[str, Any], pattern_type: str, pattern: str) -> str:
    if pattern_type not in patterns.get("_override_keys", set()):
        return "settings"
    override_values = {str(item).strip() for item in patterns.get(pattern_type, []) or []}
    return "request" if pattern in override_values else "settings"


def _first_matching_pattern(
    raw_text: str,
    patterns: Any,
    *,
    case_sensitive: bool,
) -> str | None:
    haystack = raw_text if case_sensitive else raw_text.upper()
    for raw_pattern in patterns or []:
        pattern = str(raw_pattern or "").strip()
        if not pattern:
            continue
        needle = pattern if case_sensitive else pattern.upper()
        if needle in haystack:
            return pattern
    return None


def _source_override_matched(
    settings: Dict[str, Any],
    source_key: str,
    source_name: str,
) -> bool:
    overrides = settings.get("source_overrides") or {}
    candidates = {
        str(source_key or "").strip().lower(),
        str(source_name or "").strip().lower(),
    }
    candidates.discard("")
    return any(str(key or "").strip().lower() in candidates for key in overrides.keys())


def _build_preview_warnings(
    settings: Dict[str, Any],
    source_config: Dict[str, Any],
    source_override_matched: bool,
    skip_reason: str | None,
    parser_metadata: Dict[str, Any],
    execution_preview: Dict[str, Any],
) -> list[str]:
    warnings: list[str] = []

    if parser_metadata.get("assumed_action") == "buy":
        warnings.append("No explicit action keyword matched; parser assumed buy.")
    if parser_metadata.get("confidence") == "none" and skip_reason == "unparsed":
        warnings.append("Alert text could not be parsed into a supported options contract.")
    if parser_metadata.get("ignored"):
        warnings.append("Alert matched an ignore pattern; no trade preview will be produced.")
    if not source_override_matched:
        warnings.append("No source override matched; default source policy used.")

    invalid_reason = source_config.get("invalid_reason")
    if invalid_reason:
        warnings.append(f"Source config is invalid: {invalid_reason}.")
    if not source_config.get("enabled", True):
        warnings.append("Source is disabled; preview will not request a trade.")
    if source_config.get("paper_only"):
        warnings.append("Source is paper-only; live order would be simulated.")
    if source_config.get("require_manual_confirm"):
        warnings.append("Source requires manual confirmation before trade execution.")
    if not settings.get("auto_trading_enabled", False):
        warnings.append("Auto trading is disabled; preview will not request a trade.")
    if settings.get("shutdown_triggered", False):
        warnings.append("Runtime shutdown is active; preview will not request a trade.")

    uncapped_quantity = execution_preview.get("uncapped_quantity")
    quantity = execution_preview.get("quantity")
    if (
        uncapped_quantity is not None
        and quantity is not None
        and int(quantity) < int(uncapped_quantity)
    ):
        warnings.append(
            f"Source max_contracts capped quantity from {uncapped_quantity} to {quantity}."
        )

    return warnings


def _build_execution_preview(
    settings: Dict[str, Any],
    parsed: Dict[str, Any] | None,
    source_config: Dict[str, Any],
    skip_reason: str | None,
    parser_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    auto_trading_enabled = bool(settings.get("auto_trading_enabled", False))
    shutdown_triggered = bool(settings.get("shutdown_triggered", False))
    simulation_mode = bool(settings.get("simulation_mode", True)) or bool(
        source_config.get("paper_only", False)
    )

    reason = skip_reason
    if reason is None and not auto_trading_enabled:
        reason = "auto trading disabled"
    if reason is None and shutdown_triggered:
        reason = "shutdown triggered"
    if reason is None and source_config.get("require_manual_confirm"):
        reason = "manual confirmation required"

    quantity = None
    uncapped_quantity = None
    if parsed and str(parsed.get("alert_type", "")).lower() in {"buy", "average_down"}:
        entry_price = parsed.get("entry_price")
        if entry_price:
            uncapped_quantity = calculate_position_size(
                entry_price=float(entry_price),
                default_quantity=int(settings.get("default_quantity", 1)),
                max_position_size=float(settings.get("max_position_size", 1000.0)),
                risk_multiplier=source_config.get("risk_multiplier", 1.0),
            )
            quantity = apply_source_quantity_limits(uncapped_quantity, source_config)

    return {
        "would_insert_alert": bool(parsed and skip_reason is None),
        "would_request_trade": bool(parsed and reason is None),
        "reason": reason,
        "auto_trading_enabled": auto_trading_enabled,
        "simulation_mode": simulation_mode,
        "quantity": quantity,
        "uncapped_quantity": uncapped_quantity,
        "risk_multiplier": source_config.get("risk_multiplier", 1.0),
        "max_contracts": source_config.get("max_contracts"),
        "parser_format": source_config.get("parser_format", "default"),
        "matched_pattern": (parser_metadata or {}).get("matched_pattern"),
        "matched_pattern_type": (parser_metadata or {}).get("matched_pattern_type"),
        "pattern_source": (parser_metadata or {}).get("pattern_source"),
    }


# Alert Patterns
@router.get("/discord/alert-patterns")
async def get_discord_alert_patterns():
    """Get custom Discord alert patterns"""
    patterns = await db.get_discord_patterns()
    if not patterns:
        default_patterns = DiscordAlertPatterns().model_dump()
        await db.update_discord_patterns(default_patterns)
        return default_patterns
    # Remove internal keys
    patterns.pop('id', None)
    return patterns


@router.put("/discord/alert-patterns")
async def update_discord_alert_patterns(update_data: DiscordAlertPatternsUpdate):
    """Update Discord alert patterns"""
    patterns = await db.get_discord_patterns()
    if not patterns:
        patterns = DiscordAlertPatterns().model_dump()
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    update_dict = _normalize_alert_pattern_lists(update_dict)
    patterns.update(update_dict)
    
    await db.update_discord_patterns(patterns)
    
    # Remove internal keys for response
    patterns.pop('id', None)
    return patterns


@router.post("/discord/alert-patterns/reset")
async def reset_discord_alert_patterns():
    """Reset Discord alert patterns to defaults"""
    default_patterns = DiscordAlertPatterns().model_dump()
    await db.update_discord_patterns(default_patterns)
    return default_patterns


@router.post("/discord/alert-patterns/{pattern_type}/add")
async def add_alert_pattern(pattern_type: str, pattern: str):
    # FIXED M18: validate pattern
    if not pattern or not pattern.strip():
        raise HTTPException(status_code=400, detail="Pattern cannot be empty")
    if len(pattern) > 200:
        raise HTTPException(status_code=400, detail="Pattern too long (max 200 chars)")
    """Add a pattern to a specific pattern list"""
    valid_types = ['buy_patterns', 'sell_patterns', 'partial_sell_patterns', 
                   'average_down_patterns', 'stop_loss_patterns', 'take_profit_patterns', 'ignore_patterns']
    
    if pattern_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid pattern type. Valid: {valid_types}")
    
    patterns = await db.get_discord_patterns()
    if not patterns:
        patterns = DiscordAlertPatterns().model_dump()
    
    current_list = patterns.get(pattern_type, [])
    if pattern not in current_list:
        current_list.append(pattern)
        patterns[pattern_type] = current_list
        await db.update_discord_patterns(patterns)
    
    return {pattern_type: current_list}


@router.post("/discord/alert-patterns/{pattern_type}/remove")
async def remove_alert_pattern(pattern_type: str, pattern: str):
    """Remove a pattern from a specific pattern list"""
    valid_types = ['buy_patterns', 'sell_patterns', 'partial_sell_patterns', 
                   'average_down_patterns', 'stop_loss_patterns', 'take_profit_patterns', 'ignore_patterns']
    
    if pattern_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid pattern type. Valid: {valid_types}")
    
    patterns = await db.get_discord_patterns()
    if not patterns:
        return {pattern_type: []}
    
    current_list = patterns.get(pattern_type, [])
    if pattern in current_list:
        current_list.remove(pattern)
        patterns[pattern_type] = current_list
        await db.update_discord_patterns(patterns)
    
    return {pattern_type: current_list}
