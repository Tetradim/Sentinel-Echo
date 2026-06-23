"""
Discord bot and alert patterns endpoints
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Body, Request
from pydantic import BaseModel, Field
from models import Settings, DiscordAlertPatterns, DiscordAlertPatternsUpdate
from discord_ingestion import DiscordIngestionDeps, handle_discord_message
from discord_alert_text import build_discord_alert_text
from alert_capture_recorder import record_alert_capture
from bridge_contract import CHROME_BRIDGE_CONTRACT_VERSION
from bot_event_bus import publish_event
from bridge_health import evaluate_bridge_health, record_bridge_heartbeat
from operator_audit import record_operator_event
from risk import is_duplicate_alert
from risk import calculate_position_size
from source_config import (
    apply_source_quantity_limits,
    resolve_source_config,
    source_metadata_policy_report,
    source_metadata_skip_reason,
    source_skip_reason,
)
from settings_flags import coerce_bool
from types import SimpleNamespace
from typing import Any, Dict, Mapping
from utils import AVG_DOWN_KEYWORDS, BUY_KEYWORDS, SELL_KEYWORDS, parse_alert
from openclaw_discord_config import DiscordRuntimeConfig, resolve_saved_or_runtime_discord_config
from datetime import datetime, timezone
import asyncio
import threading
import logging
import os
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
MAX_TICKER_PATTERN_LENGTH = 200
NESTED_QUANTIFIER_PATTERN = re.compile(
    r"\((?:\\.|[^()])*(?:[+*?]|\{\d)(?:\\.|[^()])*\)\s*[+*?{]"
)
BROAD_WILDCARD_PATTERN = re.compile(r"(?<!\\)\.\s*[+*]")

# Database reference
db = None

# Discord bot references (will be set by main server)
discord_bot = None
discord_bot_thread = None
_chrome_bridge_seen_event_ids: set[str] = set()
_chrome_bridge_seen_event_order: list[str] = []
_chrome_bridge_seen_alert_fingerprints: dict[str, datetime] = {}
_chrome_bridge_seen_alert_order: list[str] = []
_CHROME_BRIDGE_MAX_SEEN = 1000
_CHROME_BRIDGE_ALERT_DUPLICATE_WINDOW_SECONDS = 120
_chrome_bridge_ingest_lock = asyncio.Lock()
_LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost"}


class ChromeBridgeEmbed(BaseModel):
    author_name: str | None = None
    title: str | None = None
    description: str | None = None
    fields: list[dict[str, Any]] = Field(default_factory=list)
    footer_text: str | None = None


class ChromeBridgeMessage(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=240)
    channel_id: str = Field(default="chrome-visible-discord", max_length=120)
    channel_name: str = Field(default="chrome-visible-discord", max_length=120)
    channel_url: str | None = Field(default=None, max_length=2048)
    author_id: str | None = Field(default=None, max_length=120)
    author_name: str = Field(default="Discord Chrome", max_length=120)
    content: str = Field(default="", max_length=12000)
    embeds: list[ChromeBridgeEmbed] = Field(default_factory=list)
    url: str | None = Field(default=None, max_length=2048)
    observed_at: str | None = Field(default=None, max_length=80)
    source: str = Field(default="chrome-discord-bridge", max_length=80)
    bridge_target_id: str | None = Field(default=None, max_length=120)
    bridge_target_name: str | None = Field(default=None, max_length=120)


class ChromeBridgeHeartbeat(BaseModel):
    status: str = Field(default="ok", max_length=80)
    bridge_enabled: bool = False
    url: str | None = Field(default=None, max_length=2048)
    channel_id: str | None = Field(default=None, max_length=120)
    channel_name: str | None = Field(default=None, max_length=120)
    channel_url: str | None = Field(default=None, max_length=2048)
    observed_at: str | None = Field(default=None, max_length=80)
    last_forward_at: str | None = Field(default=None, max_length=80)
    last_forward_status: str | None = Field(default=None, max_length=120)
    bridge_target_id: str | None = Field(default=None, max_length=120)
    bridge_target_name: str | None = Field(default=None, max_length=120)
    details: dict[str, Any] = Field(default_factory=dict)


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


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def resolve_discord_start_config(
    settings: dict | None,
    *,
    env: Mapping[str, str] | None = None,
    openclaw_home=None,
) -> DiscordRuntimeConfig:
    """Resolve Discord config for the manual start route without exposing secrets."""
    fallback_env = env if env is not None else os.environ
    return resolve_saved_or_runtime_discord_config(
        _dict_or_empty(settings),
        fallback_env,
        openclaw_home=openclaw_home,
    )


def _normalize_channel_ids(channel_ids: list[str] | str) -> list[str]:
    if isinstance(channel_ids, str):
        raw_ids = channel_ids.split(",")
    else:
        raw_ids = channel_ids

    result = []
    seen = set()
    for channel_id in raw_ids:
        value = str(channel_id).strip()
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


@router.post("/discord/start")
async def start_discord_bot(background_tasks: BackgroundTasks):
    """Start the Discord bot"""
    global discord_bot_thread
    
    settings = _dict_or_empty(await db.get_settings())
    discord_config = resolve_discord_start_config(settings)
    if not discord_config.token:
        raise HTTPException(status_code=400, detail="Discord token not configured")
    if not discord_config.channel_ids:
        raise HTTPException(status_code=400, detail="Discord channel IDs not configured")
    
    token = discord_config.token
    channel_ids = discord_config.channel_ids
    
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
    
    settings = _dict_or_empty(await db.get_settings())
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
                "auto_trading_enabled": coerce_bool(settings.get('auto_trading_enabled'), default=False),
                "alerts_processed": bot_status.get('alerts_processed', 0)
            }
        }


@router.post("/discord/parse-preview")
async def preview_discord_alert(request: Dict[str, Any] = Body(...)):
    """Preview parser and source-policy behavior without mutating trading state."""
    raw_text = str(request.get("raw_text") or request.get("message") or "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text is required")

    settings = _dict_or_empty(await db.get_settings() if db else {})
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


@router.post("/discord/chrome-bridge/message")
async def ingest_chrome_bridge_message(
    payload: ChromeBridgeMessage,
    request: Request,
):
    """Ingest a Discord message observed from the local Chrome UI.

    This endpoint is intentionally local-only. It exists for private servers
    where the operator can view Discord in Chrome but cannot invite a bot.
    """
    _ensure_local_chrome_bridge_request(request)
    if not db:
        raise HTTPException(status_code=503, detail="database not initialized")

    payload.event_id = _canonical_chrome_bridge_event_id(payload.event_id)
    async with _chrome_bridge_ingest_lock:
        return await _ingest_chrome_bridge_message_locked(payload)


async def _ingest_chrome_bridge_message_locked(payload: ChromeBridgeMessage):
    if await _chrome_bridge_event_already_recorded(payload.event_id):
        return _chrome_bridge_duplicate_response(payload)

    if _mark_chrome_bridge_seen(payload.event_id):
        publish_event(
            "signal.duplicate",
            source_bot="chrome-discord-bridge",
            payload={
                "event_id": payload.event_id,
                "source": payload.source,
                "channel_id": payload.channel_id,
                "channel_name": payload.channel_name,
                "channel_url": payload.channel_url,
                "bridge_target_id": payload.bridge_target_id,
                "bridge_target_name": payload.bridge_target_name,
            },
            dedupe_key=f"chrome-discord:{payload.event_id}",
            target_bots=["consolidation", "sentinel-edge"],
        )
        return _chrome_bridge_duplicate_response(payload)

    synthetic_message = _chrome_bridge_to_message(payload)
    alert_text = build_discord_alert_text(synthetic_message).strip()
    if not alert_text:
        raise HTTPException(status_code=400, detail="message content or embed text is required")
    alert_fingerprint = _chrome_bridge_alert_fingerprint(payload, alert_text)
    if await _chrome_bridge_alert_already_recorded(alert_fingerprint):
        return _chrome_bridge_duplicate_response(payload, skip_reason="duplicate bridge alert")
    if _mark_chrome_bridge_alert_seen(alert_fingerprint):
        return _chrome_bridge_duplicate_response(payload, skip_reason="duplicate bridge alert")

    settings = _dict_or_empty(await db.get_settings() if db else {})
    stored_patterns = await db.get_discord_patterns() if hasattr(db, "get_discord_patterns") else {}
    patterns = _merge_pattern_overrides(stored_patterns or {}, {})
    parsed_preview, parser_metadata = _parse_alert_for_preview(alert_text, patterns)
    source_config = resolve_source_config(
        settings,
        channel_id=payload.channel_id,
        channel_name=payload.channel_name,
    )
    source_override_matched = _source_override_matched(
        settings,
        payload.channel_id,
        payload.channel_name,
    )
    preflight_skip_reason = _chrome_bridge_preflight_skip_reason(
        settings=settings,
        parsed=parsed_preview,
        parser_metadata=parser_metadata,
        source_config=source_config,
        source_override_matched=source_override_matched,
        payload=payload,
    )
    if preflight_skip_reason:
        ingestion_result = {
            "status": "skipped",
            "alert_inserted": False,
            "alert_id": "",
            "trade_requested": False,
            "trade_request_reason": "",
            "skip_reason": preflight_skip_reason,
        }
        capture_path = record_alert_capture(
            event_id=payload.event_id,
            channel_id=payload.channel_id,
            channel_name=payload.channel_name,
            author_name=payload.author_name,
            raw_text=alert_text,
            observed_at=payload.observed_at,
            parsed=parsed_preview,
            ingestion_result=ingestion_result,
        )
        bus_event = _publish_chrome_bridge_signal(
            payload=payload,
            alert_text=alert_text,
            parsed=parsed_preview,
            parser_metadata=parser_metadata,
            ingestion_result=ingestion_result,
            capture_path=capture_path,
        )
        audit_event = await _record_chrome_bridge_alert_audit(
            payload=payload,
            raw_text=alert_text,
            capture_path=capture_path,
            parsed=parsed_preview,
            parser_metadata=parser_metadata,
            source_config=source_config,
            source_override_matched=source_override_matched,
            ingestion_result=ingestion_result,
        )
        return {
            "status": "skipped",
            "event_id": payload.event_id,
            "source": payload.source,
            "channel_id": payload.channel_id,
            "channel_name": payload.channel_name,
            "channel_url": payload.channel_url,
            "bridge_target_id": payload.bridge_target_id,
            "bridge_target_name": payload.bridge_target_name,
            "url": payload.url,
            "author_name": payload.author_name,
            "raw_text": alert_text,
            "parsed": parsed_preview,
            "parser_metadata": parser_metadata,
            "source_config": source_config,
            "alert_inserted": False,
            "alert_id": "",
            "trade_requested": False,
            "trade_request_reason": "",
            "skip_reason": preflight_skip_reason,
            "capture_path": str(capture_path),
            "bus_event_id": bus_event.event_id,
            "audit_event_id": audit_event.get("id"),
        }

    channel_ids = _chrome_bridge_channel_ids(settings, payload.channel_id)

    async def process_trade_adapter(alert, parsed):
        from server import process_trade

        await process_trade(alert, parsed)

    async def insert_alert_adapter(alert):
        await db.insert_alert(alert.model_dump(mode="json"))

    def update_status_adapter(key: str, value: Any):
        from routes.health import update_bot_status

        update_bot_status(key, value)

    result = await handle_discord_message(
        synthetic_message,
        channel_ids=channel_ids,
        deps=DiscordIngestionDeps(
            load_settings=lambda: settings,
            insert_alert=insert_alert_adapter,
            process_trade=process_trade_adapter,
            update_status=update_status_adapter,
            is_duplicate_alert=is_duplicate_alert,
            increment_alerts_processed=_increment_chrome_bridge_alert_count,
        ),
        bot_user=None,
    )
    ingestion_result = {
        "status": "accepted" if result.alert_inserted else "skipped",
        "alert_inserted": result.alert_inserted,
        "alert_id": result.alert_id,
        "trade_requested": result.trade_requested,
        "trade_request_reason": result.trade_request_reason,
        "skip_reason": result.skip_reason,
    }
    capture_path = record_alert_capture(
        event_id=payload.event_id,
        channel_id=payload.channel_id,
        channel_name=payload.channel_name,
        author_name=payload.author_name,
        raw_text=alert_text,
        observed_at=payload.observed_at,
        parsed=result.parsed,
        ingestion_result=ingestion_result,
    )
    bus_event = _publish_chrome_bridge_signal(
        payload=payload,
        alert_text=alert_text,
        parsed=result.parsed,
        parser_metadata=parser_metadata,
        ingestion_result=ingestion_result,
        capture_path=capture_path,
    )
    audit_event = await _record_chrome_bridge_alert_audit(
        payload=payload,
        raw_text=alert_text,
        capture_path=capture_path,
        parsed=result.parsed,
        parser_metadata=parser_metadata,
        source_config=source_config,
        source_override_matched=source_override_matched,
        ingestion_result=ingestion_result,
    )

    return {
        "status": "accepted" if result.alert_inserted else "skipped",
        "event_id": payload.event_id,
        "source": payload.source,
        "channel_id": payload.channel_id,
        "channel_name": payload.channel_name,
        "channel_url": payload.channel_url,
        "bridge_target_id": payload.bridge_target_id,
        "bridge_target_name": payload.bridge_target_name,
        "url": payload.url,
        "author_name": payload.author_name,
        "raw_text": alert_text,
        "parsed": result.parsed,
        "parser_metadata": parser_metadata,
        "source_config": source_config,
        "alert_inserted": result.alert_inserted,
        "alert_id": result.alert_id,
        "trade_requested": result.trade_requested,
        "trade_request_reason": result.trade_request_reason,
        "skip_reason": result.skip_reason,
        "capture_path": str(capture_path),
        "bus_event_id": bus_event.event_id,
        "audit_event_id": audit_event.get("id"),
    }


@router.post("/discord/chrome-bridge/heartbeat")
async def ingest_chrome_bridge_heartbeat(
    payload: ChromeBridgeHeartbeat,
    request: Request,
):
    """Record Chrome bridge health and emit OpenClaw attention events on failure."""
    _ensure_local_chrome_bridge_request(request)
    return record_bridge_heartbeat(payload.model_dump(mode="json"))


@router.get("/discord/chrome-bridge/health")
async def get_chrome_bridge_health(request: Request):
    _ensure_local_chrome_bridge_request(request)
    return evaluate_bridge_health()


def _ensure_local_chrome_bridge_request(request: Request) -> None:
    if os.environ.get("CHROME_BRIDGE_ALLOW_REMOTE", "").lower() in {"1", "true", "yes"}:
        return
    host = request.client.host if request.client else ""
    if host not in _LOCAL_CLIENT_HOSTS:
        raise HTTPException(status_code=403, detail="chrome bridge endpoint only accepts local requests")


def _chrome_bridge_preflight_skip_reason(
    *,
    settings: Dict[str, Any],
    parsed: Dict[str, Any] | None,
    parser_metadata: Dict[str, Any],
    source_config: Dict[str, Any],
    source_override_matched: bool,
    payload: ChromeBridgeMessage,
) -> str | None:
    if coerce_bool(settings.get("chrome_bridge_require_source_override"), default=True) and not source_override_matched:
        return "source override required for chrome bridge"
    if parser_metadata.get("ignored"):
        return "ignored by alert pattern"
    if not parsed:
        return "unparsed"
    return source_skip_reason(parsed, source_config) or source_metadata_skip_reason(
        source_config,
        channel_url=payload.channel_url,
        author_id=_chrome_bridge_author_id(payload),
        parser_confidence=parser_metadata.get("confidence"),
    )


def _chrome_bridge_author_id(payload: ChromeBridgeMessage) -> str:
    raw_author_id = str(payload.author_id or "").strip()
    if raw_author_id:
        return raw_author_id
    author_name = str(payload.author_name or "").strip()
    if author_name:
        return f"name:{author_name}"
    return "chrome-observed-user"


def _publish_chrome_bridge_signal(
    *,
    payload: ChromeBridgeMessage,
    alert_text: str,
    parsed: Dict[str, Any] | None,
    parser_metadata: Dict[str, Any],
    ingestion_result: Dict[str, Any],
    capture_path: Any,
):
    return publish_event(
        "signal.observed",
        source_bot="chrome-discord-bridge",
        payload={
            "contract_version": CHROME_BRIDGE_CONTRACT_VERSION,
            "event_id": payload.event_id,
            "source": payload.source,
            "channel_id": payload.channel_id,
            "channel_name": payload.channel_name,
            "channel_url": payload.channel_url,
            "url": payload.url,
            "observed_at": payload.observed_at,
            "bridge_target_id": payload.bridge_target_id,
            "bridge_target_name": payload.bridge_target_name,
            "author_id": _chrome_bridge_author_id(payload),
            "author_name": payload.author_name,
            "raw_text": alert_text,
            "parsed": parsed,
            "parser_metadata": parser_metadata,
            "ingestion_result": ingestion_result,
            "capture_path": str(capture_path),
        },
        correlation_id=payload.event_id,
        dedupe_key=f"chrome-discord:{payload.event_id}",
        target_bots=["consolidation", "sentinel-edge", "simulation-engine"],
    )


async def _record_chrome_bridge_alert_audit(
    *,
    payload: ChromeBridgeMessage,
    raw_text: str,
    capture_path: Any,
    parsed: Dict[str, Any] | None,
    parser_metadata: Dict[str, Any],
    source_config: Dict[str, Any],
    source_override_matched: bool,
    ingestion_result: Dict[str, Any],
) -> Dict[str, Any]:
    if not db:
        return {}
    skipped = ingestion_result.get("status") == "skipped"
    summary = (
        f"Chrome bridge alert skipped: {ingestion_result.get('skip_reason')}"
        if skipped
        else "Chrome bridge alert accepted."
    )
    return await record_operator_event(
        db,
        "alert_ingestion",
        "bridge_alert_decision",
        summary,
        severity="warning" if skipped else "info",
        details={
            "contract_version": CHROME_BRIDGE_CONTRACT_VERSION,
            "event_id": payload.event_id,
            "channel": {
                "id": payload.channel_id,
                "name": payload.channel_name,
                "url": payload.channel_url,
                "message_url": payload.url,
            },
            "author": {
                "id": _chrome_bridge_author_id(payload),
                "name": payload.author_name,
            },
            "bridge_target": {
                "id": payload.bridge_target_id,
                "name": payload.bridge_target_name,
            },
            "raw_text": raw_text,
            "capture_path": str(capture_path),
            "parsed": parsed,
            "parser": parser_metadata,
            "source": {
                "key": source_config.get("key"),
                "name": source_config.get("name"),
                "override_matched": source_override_matched,
                "paper_only": source_config.get("paper_only"),
                "require_manual_confirm": source_config.get("require_manual_confirm"),
                "min_parser_confidence": source_config.get("min_parser_confidence"),
                **source_metadata_policy_report(
                    source_config,
                    channel_url=payload.channel_url,
                    author_id=_chrome_bridge_author_id(payload),
                    parser_confidence=parser_metadata.get("confidence"),
                ),
            },
            "decision": ingestion_result,
        },
    )


def _canonical_chrome_bridge_event_id(event_id: str) -> str:
    raw_event_id = str(event_id or "").strip()
    match = re.search(r"chat-messages-(\d+)-(\d+)", raw_event_id)
    if match:
        return f"chat-messages-{match.group(1)}-{match.group(2)}"
    return raw_event_id


async def _chrome_bridge_event_already_recorded(event_id: str) -> bool:
    if not db or not hasattr(db, "get_operator_events"):
        return False
    try:
        events = await db.get_operator_events(500)
    except Exception as exc:
        logger.warning("Unable to check persisted chrome bridge duplicate event: %s", exc)
        return False
    canonical_event_id = _canonical_chrome_bridge_event_id(event_id)
    for event in events:
        if event.get("action") != "bridge_alert_decision":
            continue
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        if _canonical_chrome_bridge_event_id(str(details.get("event_id") or "")) == canonical_event_id:
            return True
    return False


async def _chrome_bridge_alert_already_recorded(fingerprint: str) -> bool:
    if not fingerprint or not db or not hasattr(db, "get_operator_events"):
        return False
    try:
        events = await db.get_operator_events(500)
    except Exception as exc:
        logger.warning("Unable to check persisted chrome bridge duplicate alert: %s", exc)
        return False
    for event in events:
        if event.get("action") != "bridge_alert_decision":
            continue
        if _operator_event_is_outside_bridge_alert_duplicate_window(event):
            continue
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        channel = details.get("channel") if isinstance(details.get("channel"), dict) else {}
        author = details.get("author") if isinstance(details.get("author"), dict) else {}
        bridge_target = details.get("bridge_target") if isinstance(details.get("bridge_target"), dict) else {}
        candidate = _bridge_alert_fingerprint_from_parts(
            bridge_target_id=str(bridge_target.get("id") or ""),
            channel_key=str(channel.get("url") or channel.get("id") or ""),
            author_key=str(author.get("id") or author.get("name") or ""),
            raw_text=str(details.get("raw_text") or ""),
        )
        if candidate and candidate == fingerprint:
            return True
    return False


def _operator_event_is_outside_bridge_alert_duplicate_window(event: dict[str, Any]) -> bool:
    raw_timestamp = str(event.get("timestamp") or "").strip()
    if not raw_timestamp:
        return False
    try:
        timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()
    return age_seconds > _CHROME_BRIDGE_ALERT_DUPLICATE_WINDOW_SECONDS


def _chrome_bridge_duplicate_response(
    payload: ChromeBridgeMessage,
    *,
    skip_reason: str = "duplicate bridge event",
) -> dict:
    return {
        "status": "duplicate",
        "event_id": payload.event_id,
        "alert_inserted": False,
        "alert_id": "",
        "trade_requested": False,
        "trade_request_reason": "",
        "skip_reason": skip_reason,
    }


def _mark_chrome_bridge_seen(event_id: str) -> bool:
    if event_id in _chrome_bridge_seen_event_ids:
        return True
    _chrome_bridge_seen_event_ids.add(event_id)
    _chrome_bridge_seen_event_order.append(event_id)
    while len(_chrome_bridge_seen_event_order) > _CHROME_BRIDGE_MAX_SEEN:
        old_event_id = _chrome_bridge_seen_event_order.pop(0)
        _chrome_bridge_seen_event_ids.discard(old_event_id)
    return False


def _mark_chrome_bridge_alert_seen(fingerprint: str) -> bool:
    if not fingerprint:
        return False
    _prune_chrome_bridge_alert_fingerprints()
    if fingerprint in _chrome_bridge_seen_alert_fingerprints:
        return True
    _chrome_bridge_seen_alert_fingerprints[fingerprint] = datetime.now(timezone.utc)
    _chrome_bridge_seen_alert_order.append(fingerprint)
    while len(_chrome_bridge_seen_alert_order) > _CHROME_BRIDGE_MAX_SEEN:
        old_fingerprint = _chrome_bridge_seen_alert_order.pop(0)
        _chrome_bridge_seen_alert_fingerprints.pop(old_fingerprint, None)
    return False


def _prune_chrome_bridge_alert_fingerprints() -> None:
    now = datetime.now(timezone.utc)
    while _chrome_bridge_seen_alert_order:
        fingerprint = _chrome_bridge_seen_alert_order[0]
        recorded_at = _chrome_bridge_seen_alert_fingerprints.get(fingerprint)
        if recorded_at is None:
            _chrome_bridge_seen_alert_order.pop(0)
            continue
        if (now - recorded_at).total_seconds() <= _CHROME_BRIDGE_ALERT_DUPLICATE_WINDOW_SECONDS:
            break
        _chrome_bridge_seen_alert_order.pop(0)
        _chrome_bridge_seen_alert_fingerprints.pop(fingerprint, None)


def _chrome_bridge_alert_fingerprint(payload: ChromeBridgeMessage, raw_text: str) -> str:
    return _bridge_alert_fingerprint_from_parts(
        bridge_target_id=str(payload.bridge_target_id or ""),
        channel_key=str(payload.channel_url or payload.channel_id or ""),
        author_key=_chrome_bridge_author_id(payload),
        raw_text=raw_text,
    )


def _bridge_alert_fingerprint_from_parts(
    *,
    bridge_target_id: str,
    channel_key: str,
    author_key: str,
    raw_text: str,
) -> str:
    normalized_text = re.sub(r"\s+", " ", str(raw_text or "")).strip().lower()
    if not normalized_text:
        return ""
    return "|".join(
        [
            str(bridge_target_id or "").strip().lower(),
            str(channel_key or "").strip().lower(),
            str(author_key or "").strip().lower(),
            normalized_text,
        ]
    )


def _chrome_bridge_channel_ids(settings: Dict[str, Any], channel_id: str) -> list[str]:
    configured = settings.get("chrome_bridge_channel_ids")
    if configured is None:
        return [str(channel_id)]
    if isinstance(configured, str):
        configured = configured.split(",")
    normalized = [str(item).strip() for item in configured or [] if str(item).strip()]
    return normalized


def _chrome_bridge_to_message(payload: ChromeBridgeMessage):
    embeds = []
    for embed in payload.embeds:
        embeds.append(
            SimpleNamespace(
                author=SimpleNamespace(name=embed.author_name or ""),
                title=embed.title or "",
                description=embed.description or "",
                fields=[
                    SimpleNamespace(
                        name=str(field.get("name", "")),
                        value=str(field.get("value", "")),
                    )
                    for field in embed.fields
                ],
                footer=SimpleNamespace(text=embed.footer_text or ""),
            )
        )

    return SimpleNamespace(
        id=payload.event_id,
        content=payload.content,
        embeds=embeds,
        author=SimpleNamespace(
            id=_chrome_bridge_author_id(payload),
            name=payload.author_name,
            display_name=payload.author_name,
        ),
        channel=SimpleNamespace(
            id=str(payload.channel_id),
            name=str(payload.channel_name or payload.channel_id),
        ),
        created_at=payload.observed_at,
        jump_url=payload.url,
    )


def _increment_chrome_bridge_alert_count():
    from routes.health import bot_status, update_bot_status

    update_bot_status(
        "alerts_processed",
        bot_status.get("alerts_processed", 0) + 1,
    )


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
        "ticker_pattern_applied": False,
        "matched_ticker_pattern": None,
        "ticker_pattern_source": None,
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

    raw_parsed = parse_alert(raw_text)
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
            if pattern_type != "buy_patterns" or raw_parsed is None:
                canonical_text = _canonicalize_pattern_action(
                    raw_text,
                    match,
                    canonical_action,
                    case_sensitive=case_sensitive,
                )
            break

    parsed = raw_parsed if canonical_text == raw_text else parse_alert(canonical_text)
    ticker_pattern = patterns.get("ticker_pattern")
    ticker_override = _extract_ticker_with_pattern(
        raw_text,
        ticker_pattern,
        case_sensitive=case_sensitive,
    )
    if parsed and ticker_override:
        parsed["ticker"] = ticker_override
        metadata["ticker_pattern_applied"] = True
        metadata["matched_ticker_pattern"] = ticker_pattern
        metadata["ticker_pattern_source"] = _pattern_source(
            patterns,
            "ticker_pattern",
            ticker_pattern,
        )
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
    if "ticker_pattern" in normalized:
        normalized["ticker_pattern"] = _validate_ticker_pattern(
            normalized["ticker_pattern"]
        )
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


def _validate_ticker_pattern(pattern: Any) -> str:
    value = str(pattern or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Ticker pattern cannot be empty")
    if len(value) > MAX_TICKER_PATTERN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Ticker pattern too long (max {MAX_TICKER_PATTERN_LENGTH} chars)",
        )

    try:
        compiled = re.compile(value)
    except re.error as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Ticker pattern is not valid regex: {exc}",
        ) from exc

    if compiled.groups < 1:
        raise HTTPException(
            status_code=400,
            detail="Ticker pattern must include a capture group for the ticker",
        )
    if NESTED_QUANTIFIER_PATTERN.search(value):
        raise HTTPException(
            status_code=400,
            detail="Ticker pattern contains unsafe nested quantifier",
        )
    if BROAD_WILDCARD_PATTERN.search(value):
        raise HTTPException(
            status_code=400,
            detail="Ticker pattern contains unsafe broad wildcard quantifier",
        )
    return value


def _pattern_source(patterns: Dict[str, Any], pattern_type: str, pattern: str) -> str:
    if pattern_type == "ticker_pattern":
        return "request" if pattern_type in patterns.get("_override_keys", set()) else "settings"
    if pattern_type not in patterns.get("_override_keys", set()):
        return "settings"
    override_values = {str(item).strip() for item in patterns.get(pattern_type, []) or []}
    return "request" if pattern in override_values else "settings"


def _extract_ticker_with_pattern(
    raw_text: str,
    pattern: Any,
    *,
    case_sensitive: bool,
) -> str | None:
    if not pattern:
        return None
    flags = 0 if case_sensitive else re.IGNORECASE
    match = re.search(str(pattern), raw_text, flags)
    if not match:
        return None

    ticker = match.groupdict().get("ticker") or match.group(1)
    ticker = str(ticker or "").strip().upper().lstrip("$")
    if not re.fullmatch(r"[A-Z]{1,6}", ticker):
        return None
    return ticker


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
    overrides = settings.get("source_overrides")
    if not isinstance(overrides, dict):
        return False
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
    if source_config.get("paper_shadow"):
        warnings.append("Paper-shadow recording is enabled for this source.")
    if source_config.get("require_manual_confirm"):
        warnings.append("Source requires manual confirmation before trade execution.")
    if not coerce_bool(settings.get("auto_trading_enabled"), default=False):
        warnings.append("Auto trading is disabled; preview will not request a trade.")
    if coerce_bool(settings.get("shutdown_triggered"), default=False):
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
    auto_trading_enabled = coerce_bool(settings.get("auto_trading_enabled"), default=False)
    shutdown_triggered = coerce_bool(settings.get("shutdown_triggered"), default=False)
    simulation_mode = coerce_bool(settings.get("simulation_mode"), default=True) or bool(
        source_config.get("paper_only", False)
    )

    reason = skip_reason
    if reason is None and not auto_trading_enabled:
        reason = "auto trading disabled"
    if reason is None and shutdown_triggered:
        reason = "shutdown triggered"
    if reason is None and source_config.get("require_manual_confirm"):
        reason = "manual confirmation required"

    would_create_paper_shadow = bool(
        parsed
        and reason is None
        and source_config.get("paper_shadow")
        and not simulation_mode
    )

    quantity = None
    uncapped_quantity = None
    estimated_premium_cost = None
    uncapped_premium_cost = None
    if parsed and str(parsed.get("alert_type", "")).lower() in {"buy", "average_down"}:
        entry_price = parsed.get("entry_price")
        if entry_price:
            entry_price = float(entry_price)
            uncapped_quantity = calculate_position_size(
                entry_price=entry_price,
                default_quantity=int(settings.get("default_quantity", 1)),
                max_position_size=float(settings.get("max_position_size", 1000.0)),
                risk_multiplier=source_config.get("risk_multiplier", 1.0),
            )
            quantity = apply_source_quantity_limits(uncapped_quantity, source_config)
            estimated_premium_cost = round(entry_price * quantity * 100, 2)
            uncapped_premium_cost = round(entry_price * uncapped_quantity * 100, 2)
            if quantity <= 0 and reason is None:
                reason = "position size exceeds max_position_size"

    return {
        "would_insert_alert": bool(parsed and skip_reason is None),
        "would_request_trade": bool(parsed and reason is None),
        "would_create_paper_shadow": would_create_paper_shadow,
        "reason": reason,
        "auto_trading_enabled": auto_trading_enabled,
        "simulation_mode": simulation_mode,
        "quantity": quantity,
        "uncapped_quantity": uncapped_quantity,
        "estimated_premium_cost": estimated_premium_cost,
        "uncapped_premium_cost": uncapped_premium_cost,
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
