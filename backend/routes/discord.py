"""
Discord bot and alert patterns endpoints
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Body, Request
from pydantic import BaseModel, Field
from models import Settings, DiscordAlertPatterns, DiscordAlertPatternsUpdate
from discord_ingestion import DiscordIngestionDeps, handle_discord_message
from discord_alert_text import build_discord_alert_text
from structured_alert_cards import parse_card
from alert_capture_recorder import record_alert_capture
from bridge_contract import CHROME_BRIDGE_CONTRACT_VERSION
from bot_event_bus import publish_event
from bridge_health import evaluate_bridge_health, record_bridge_heartbeat
from operator_audit import record_operator_event
from risk import is_duplicate_alert
from risk import calculate_position_size
from entry_controls import alert_risk_size_cap
from source_config import (
    apply_source_quantity_limits,
    normalize_source_config,
    resolve_source_config,
    source_metadata_policy_report,
    source_metadata_skip_reason,
    source_skip_reason,
)
from settings_flags import coerce_bool
from types import SimpleNamespace
from typing import Any, Dict, Mapping
from utils import (
    AVG_DOWN_KEYWORDS,
    BUY_KEYWORDS,
    SELL_KEYWORDS,
    is_actionable_average_down_alert,
    normalize_parsed_alert,
    parse_alert,
)
from openclaw_discord_config import DiscordRuntimeConfig, resolve_saved_or_runtime_discord_config
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
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
discord_runtime_loop = None
discord_runtime_token_fingerprint = ""
discord_runtime_channel_ids: list[str] = []
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
    author_raw: str | None = Field(default=None, max_length=240)
    content: str = Field(default="", max_length=12000)
    embeds: list[ChromeBridgeEmbed] = Field(default_factory=list)
    url: str | None = Field(default=None, max_length=2048)
    timestampIso: str | None = Field(default=None, max_length=80)
    revision_hash: str | None = Field(default=None, max_length=80)
    event_type: str = Field(default="created", pattern=r"^(created|updated)$")
    attachment_urls: list[str] = Field(default_factory=list, max_length=20)
    ocr_text: str | None = Field(default=None, max_length=12000)
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    observed_at: str | None = Field(default=None, max_length=80)
    source: str = Field(default="chrome-discord-bridge", max_length=80)
    source_mode: str = Field(default="", pattern=r"^(|listen|listen-only)$")
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


def set_discord_bot(
    bot,
    thread,
    *,
    token: str = "",
    channel_ids: list[str] | str | None = None,
    loop=None,
):
    """Set discord bot references"""
    global discord_bot, discord_bot_thread, discord_runtime_loop, discord_runtime_token_fingerprint, discord_runtime_channel_ids
    discord_bot = bot
    discord_bot_thread = thread
    if bot is None and thread is None:
        discord_runtime_loop = None
        discord_runtime_token_fingerprint = ""
        discord_runtime_channel_ids = []
        return
    if loop is not None:
        discord_runtime_loop = loop
    if token or channel_ids is not None:
        discord_runtime_token_fingerprint = _token_fingerprint(token)
        discord_runtime_channel_ids = _normalize_channel_ids(channel_ids or [])


def get_discord_bot():
    """Get discord bot for external access"""
    return discord_bot, discord_bot_thread


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _source_behavior_enabled(source_config: Dict[str, Any] | None, key: str, *, default: bool) -> bool:
    return coerce_bool((source_config or {}).get(key), default=default)


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


def _token_fingerprint(token: str) -> str:
    normalized = str(token or "").strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _discord_runtime_matches(token: str, channel_ids: list[str] | str) -> bool:
    return (
        discord_runtime_token_fingerprint == _token_fingerprint(token)
        and discord_runtime_channel_ids == _normalize_channel_ids(channel_ids)
    )


async def _close_current_discord_bot() -> None:
    from routes.health import update_bot_status

    global discord_bot, discord_bot_thread
    if discord_bot:
        current_loop = asyncio.get_running_loop()
        if discord_runtime_loop is not None and discord_runtime_loop is not current_loop:
            close_future = asyncio.run_coroutine_threadsafe(
                discord_bot.close(),
                discord_runtime_loop,
            )
            await asyncio.wrap_future(close_future)
        else:
            await discord_bot.close()
    update_bot_status("discord_connected", False)
    set_discord_bot(None, None)


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

    restart_required = False
    with _bot_start_lock:  # FIXED M17: atomic check-and-start
        if discord_bot_thread and discord_bot_thread.is_alive():
            if _discord_runtime_matches(token, channel_ids):
                return {"message": "Discord bot already running"}
            restart_required = True

    if restart_required:
        await _close_current_discord_bot()

    with _bot_start_lock:
        if discord_bot_thread and discord_bot_thread.is_alive():
            if _discord_runtime_matches(token, channel_ids):
                return {"message": "Discord bot already running"}
            return {"message": "Discord bot is stopping before restart"}
        from server import run_discord_bot
        discord_bot_thread = threading.Thread(target=run_discord_bot, args=(token, channel_ids), daemon=True)
        discord_bot_thread.start()

    if restart_required:
        return {"message": "Discord bot restarting with updated configuration..."}
    return {"message": "Discord bot starting..."}


@router.post("/discord/stop")
async def stop_discord_bot():
    """Stop the Discord bot"""
    if discord_bot:
        await _close_current_discord_bot()
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
                "auto_trading_enabled": coerce_bool(settings.get('auto_trading_enabled'), default=True),
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
        raw_text,
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
    freshness_skip_reason = _chrome_bridge_freshness_skip_reason(payload)
    if freshness_skip_reason:
        return _chrome_bridge_skipped_response(payload, skip_reason=freshness_skip_reason)

    synthetic_message = _chrome_bridge_to_message(payload)
    alert_text = build_discord_alert_text(synthetic_message).strip()
    if not alert_text:
        raise HTTPException(status_code=400, detail="message content or embed text is required")

    settings = _dict_or_empty(await db.get_settings() if db else {})
    settings = await _ensure_sentinel_link_source_enrollment(settings, payload)
    stored_patterns = await db.get_discord_patterns() if hasattr(db, "get_discord_patterns") else {}
    patterns = _merge_pattern_overrides(stored_patterns or {}, {})
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

    existing_alert = await _find_existing_chrome_bridge_alert_record(
        payload,
        alert_text,
        source_config,
        patterns=patterns,
    )
    if existing_alert:
        if existing_alert.get("raw_text") != alert_text:
            return await _chrome_bridge_updated_response(
                payload,
                alert_text,
                existing_alert,
                settings=settings,
                patterns=patterns,
                source_config=source_config,
                source_override_matched=source_override_matched,
            )
        return _chrome_bridge_duplicate_response(payload)

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
            target_bots=["sentinel-echo", "sentinel-edge"],
        )
        return _chrome_bridge_duplicate_response(payload)

    alert_fingerprint = _chrome_bridge_alert_fingerprint(payload, alert_text)
    if await _chrome_bridge_alert_already_recorded(alert_fingerprint):
        return _chrome_bridge_duplicate_response(payload, skip_reason="duplicate bridge alert")
    if _mark_chrome_bridge_alert_seen(alert_fingerprint):
        return _chrome_bridge_duplicate_response(payload, skip_reason="duplicate bridge alert")

    parsed_preview, parser_metadata = _parse_alert_for_preview(alert_text, patterns)
    if _exit_alert_uses_context_word_as_ticker(parsed_preview, alert_text):
        parsed_preview = None
    if parsed_preview is None and not parser_metadata.get("card_recognized"):
        inferred_sell = await _infer_single_channel_position_sell(
            payload,
            alert_text,
            source_config,
        )
        if inferred_sell:
            parsed_preview = inferred_sell
            parser_metadata.update(
                {
                    "matched_pattern": "SINGLE CHANNEL POSITION",
                    "matched_pattern_type": "single_position_inferred_sell",
                    "pattern_source": "builtin",
                    "ignored": False,
                    "explicit_action": True,
                    "assumed_action": "sell",
                    "confidence": "high",
                }
            )
    if parsed_preview is None and not parser_metadata.get("ignored"):
        inferred_buy = await _infer_recent_channel_contract_buy(
            payload,
            alert_text,
            source_config,
        )
        if inferred_buy:
            parsed_preview = inferred_buy
            parser_metadata.update(
                {
                    "matched_pattern": "RECENT CHANNEL CONTRACT",
                    "matched_pattern_type": "recent_channel_contract_inferred_buy",
                    "pattern_source": "builtin",
                    "ignored": False,
                    "explicit_action": True,
                    "assumed_action": "buy",
                    "confidence": "high",
                }
            )
    mark_update = {"updated": False}
    if (
        not parser_metadata.get("card_recognized")
        and _source_behavior_enabled(source_config, "process_followup_updates", default=True)
        and not _source_behavior_enabled(source_config, "ignore_followup_messages", default=False)
    ):
        mark_update = await _apply_chrome_bridge_position_mark_update(payload, alert_text)
    if mark_update.get("updated") and not (
        coerce_bool(settings.get("chrome_bridge_require_source_override"), default=True)
        and not source_override_matched
    ):
        ingestion_result = {
            "status": "updated",
            "alert_inserted": False,
            "alert_id": "",
            "trade_requested": False,
            "trade_request_reason": "",
            "skip_reason": "position mark update",
            "position_mark_update": mark_update,
        }
        capture_path = record_alert_capture(
            event_id=payload.event_id,
            channel_id=payload.channel_id,
            channel_name=payload.channel_name,
            author_name=payload.author_name,
            raw_text=alert_text,
            observed_at=payload.observed_at,
            parsed=None,
            ingestion_result=ingestion_result,
            revision_hash=payload.revision_hash,
            event_type=payload.event_type,
            author_raw=payload.author_raw,
            attachment_urls=payload.attachment_urls,
            ocr_confidence=payload.ocr_confidence,
        )
        bus_event = _publish_chrome_bridge_signal(
            payload=payload,
            alert_text=alert_text,
            parsed=None,
            parser_metadata=parser_metadata,
            ingestion_result=ingestion_result,
            capture_path=capture_path,
        )
        audit_event = await _record_chrome_bridge_alert_audit(
            payload=payload,
            raw_text=alert_text,
            capture_path=capture_path,
            parsed=None,
            parser_metadata=parser_metadata,
            source_config=source_config,
            source_override_matched=source_override_matched,
            ingestion_result=ingestion_result,
        )
        return {
            "status": "updated",
            "event_id": payload.event_id,
            "revision_hash": payload.revision_hash,
            "event_type": payload.event_type,
            "source": payload.source,
            "channel_id": payload.channel_id,
            "channel_name": payload.channel_name,
            "channel_url": payload.channel_url,
            "bridge_target_id": payload.bridge_target_id,
            "bridge_target_name": payload.bridge_target_name,
            "url": payload.url,
            "author_name": payload.author_name,
            "author_raw": payload.author_raw,
            "raw_text": alert_text,
            "parsed": None,
            "parser_metadata": parser_metadata,
            "source_config": source_config,
            "alert_inserted": False,
            "alert_id": "",
            "trade_requested": False,
            "trade_request_reason": "",
            "skip_reason": "position mark update",
            "position_mark_update": mark_update,
            "capture_path": str(capture_path),
            "bus_event_id": bus_event.event_id,
            "audit_event_id": audit_event.get("id"),
        }
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
            revision_hash=payload.revision_hash,
            event_type=payload.event_type,
            author_raw=payload.author_raw,
            attachment_urls=payload.attachment_urls,
            ocr_confidence=payload.ocr_confidence,
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
            "revision_hash": payload.revision_hash,
            "event_type": payload.event_type,
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
            card_database=db,
        ),
        bot_user=None,
        parsed_override=parsed_preview,
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
        revision_hash=payload.revision_hash,
        event_type=payload.event_type,
        author_raw=payload.author_raw,
        attachment_urls=payload.attachment_urls,
        ocr_confidence=payload.ocr_confidence,
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
        return parser_metadata.get("card_reason") or "ignored by alert pattern"
    if not parsed:
        return "unparsed"
    return source_skip_reason(parsed, source_config) or source_metadata_skip_reason(
        source_config,
        channel_url=payload.channel_url,
        author_id=_chrome_bridge_author_id(payload),
        parser_confidence=parser_metadata.get("confidence"),
    )


async def _ensure_sentinel_link_source_enrollment(
    settings: Dict[str, Any],
    payload: ChromeBridgeMessage,
) -> Dict[str, Any]:
    if _source_override_matched(settings, payload.channel_id, payload.channel_name):
        return settings

    source_config = _sentinel_link_auto_source_config(payload)
    if source_config is None or not db or not hasattr(db, "update_settings"):
        return settings

    overrides = settings.get("source_overrides")
    updated_overrides = dict(overrides) if isinstance(overrides, dict) else {}
    updated_overrides[str(payload.channel_id)] = normalize_source_config(source_config)
    await db.update_settings({"source_overrides": updated_overrides})

    updated_settings = dict(settings)
    updated_settings["source_overrides"] = updated_overrides
    return updated_settings


def _sentinel_link_auto_source_config(payload: ChromeBridgeMessage) -> Dict[str, Any] | None:
    if str(payload.source or "").strip().lower() != "sentinel-link":
        return None
    mode = str(payload.source_mode or "").strip().lower()
    if mode not in {"listen", "listen-only"}:
        return None
    channel_id = str(payload.channel_id or "").strip()
    if not channel_id.isdigit():
        return None
    channel_url = _normalize_bridge_url(str(payload.channel_url or ""))
    match = re.fullmatch(r"https://discord\.com/channels/(?:\d+|@me)/(\d+)", channel_url)
    if not match or match.group(1) != channel_id:
        return None
    return {
        "name": str(payload.channel_name or channel_id).strip(),
        "enabled": True,
        "parser_format": "default",
        "allowed_channel_urls": [channel_url],
        "min_parser_confidence": "medium",
        "managed_by": "sentinel-link",
        "enrollment_mode": mode,
        "auto_enrolled": True,
        "allow_fresh_entry_after_close": True,
    }


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
            "revision_hash": payload.revision_hash,
            "event_type": payload.event_type,
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
            "author_raw": payload.author_raw or payload.author_name,
            "attachment_urls": payload.attachment_urls,
            "ocr_confidence": payload.ocr_confidence,
            "raw_text": alert_text,
            "parsed": parsed,
            "parser_metadata": parser_metadata,
            "ingestion_result": ingestion_result,
            "capture_path": str(capture_path),
        },
        correlation_id=payload.event_id,
        dedupe_key=f"chrome-discord:{payload.event_id}",
        target_bots=["sentinel-echo", "sentinel-edge", "sentinel-archive"],
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
            "revision_hash": payload.revision_hash,
            "event_type": payload.event_type,
            "channel": {
                "id": payload.channel_id,
                "name": payload.channel_name,
                "url": payload.channel_url,
                "message_url": payload.url,
            },
            "author": {
                "id": _chrome_bridge_author_id(payload),
                "name": payload.author_name,
                "raw_name": payload.author_raw or payload.author_name,
            },
            "bridge_target": {
                "id": payload.bridge_target_id,
                "name": payload.bridge_target_name,
            },
            "raw_text": raw_text,
            "attachment_urls": payload.attachment_urls,
            "ocr_confidence": payload.ocr_confidence,
            "capture_path": str(capture_path),
            "parsed": parsed,
            "parser": parser_metadata,
            "source": {
                "key": source_config.get("key"),
                "name": source_config.get("name"),
                "override_matched": source_override_matched,
                "managed_by": source_config.get("managed_by"),
                "enrollment_mode": source_config.get("enrollment_mode"),
                "auto_enrolled": source_config.get("auto_enrolled", False),
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


async def _find_existing_chrome_bridge_alert_record(
    payload: ChromeBridgeMessage,
    raw_text: str,
    source_config: Dict[str, Any] | None = None,
    *,
    patterns: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    if not db or not hasattr(db, "get_operator_events"):
        return None
    identity = _chrome_bridge_message_identity(payload, source_config)
    try:
        events = await db.get_operator_events(500)
    except Exception as exc:
        logger.warning("Unable to check persisted chrome bridge message identity: %s", exc)
        return None
    if identity:
        for event in events:
            if event.get("action") not in {"bridge_alert_decision", "bridge_alert_update"}:
                continue
            details = event.get("details") if isinstance(event.get("details"), dict) else {}
            if _chrome_bridge_record_identity(details, source_config) != identity:
                continue
            existing = _existing_bridge_alert_from_details(details)
            if existing:
                return existing

    updated_signal_key = _entry_signal_key(raw_text, patterns or {})
    if updated_signal_key:
        for event in events:
            if event.get("action") not in {"bridge_alert_decision", "bridge_alert_update"}:
                continue
            details = event.get("details") if isinstance(event.get("details"), dict) else {}
            channel = details.get("channel") if isinstance(details.get("channel"), dict) else {}
            same_channel = (
                str(channel.get("id") or "").strip()
                == str(payload.channel_id or "").strip()
            )
            previous_raw_text = str(details.get("raw_text") or "")
            if not same_channel and not _same_entry_headline(previous_raw_text, raw_text):
                continue
            if _entry_signal_key(previous_raw_text, patterns or {}) != updated_signal_key:
                continue
            if not _is_appended_entry_update(previous_raw_text, raw_text):
                continue
            existing = _existing_bridge_alert_from_details(details)
            if existing:
                return existing
    return None


def _existing_bridge_alert_from_details(details: Dict[str, Any]) -> Dict[str, Any] | None:
    decision = details.get("decision") if isinstance(details.get("decision"), dict) else {}
    alert_id = str(decision.get("alert_id") or details.get("alert_id") or "").strip()
    if not alert_id:
        return None
    return {
        "alert_id": alert_id,
        "raw_text": str(details.get("raw_text") or ""),
    }


def _is_appended_entry_update(previous_raw_text: str, raw_text: str) -> bool:
    previous = re.sub(r"\s+", " ", str(previous_raw_text or "")).strip().lower()
    current = re.sub(r"\s+", " ", str(raw_text or "")).strip().lower()
    if not previous or previous == current:
        return False
    return (
        "(edited)" in current
        or current.startswith(f"{previous} ")
        or _same_entry_headline(previous_raw_text, raw_text)
    )


def _same_entry_headline(previous_raw_text: str, raw_text: str) -> bool:
    def lines(value: str) -> list[str]:
        return [
            normalized
            for line in str(value or "").splitlines()
            if (normalized := re.sub(r"\s+", " ", line).strip().lower())
        ]

    previous_lines = lines(previous_raw_text)
    current_lines = lines(raw_text)
    if len(current_lines) < 2:
        return False
    previous_headline = previous_lines[0] if previous_lines else ""
    current_headline = current_lines[0]
    return bool(previous_headline and previous_headline == current_headline)


def _entry_signal_key(raw_text: str, patterns: Dict[str, Any]) -> tuple | None:
    parsed, _ = _parse_alert_for_preview(raw_text, patterns)
    if str((parsed or {}).get("alert_type") or "").strip().lower() != "buy":
        return None
    try:
        strike = round(float(parsed.get("strike") or 0.0), 4)
        entry_price = round(float(parsed.get("entry_price") or 0.0), 4)
    except (TypeError, ValueError):
        return None
    if strike <= 0 or entry_price <= 0:
        return None
    return (
        str(parsed.get("ticker") or "").strip().upper(),
        strike,
        str(parsed.get("option_type") or "").strip().upper(),
        str(parsed.get("expiration") or "").strip().upper().replace("-", "/"),
        entry_price,
    )


def _chrome_bridge_message_identity(payload: ChromeBridgeMessage, source_config: Dict[str, Any] | None = None) -> str:
    url = str(payload.url or "").strip()
    if url:
        match = re.search(r"/channels/([^/]+)/([^/]+)/([^/?#]+)", url)
        if match:
            return f"discord-message-url:{match.group(1)}:{match.group(2)}:{match.group(3)}"
        if _source_behavior_enabled(source_config or {}, "dedupe_by_channel_url", default=False):
            return f"discord-channel-url:{_normalize_bridge_url(url)}"
    event_id = _canonical_chrome_bridge_event_id(payload.event_id)
    return f"discord-event:{event_id}" if event_id else ""


def _chrome_bridge_record_identity(details: Dict[str, Any], source_config: Dict[str, Any] | None = None) -> str:
    channel = details.get("channel") if isinstance(details.get("channel"), dict) else {}
    message_url = str(channel.get("message_url") or details.get("url") or "").strip()
    if message_url:
        match = re.search(r"/channels/([^/]+)/([^/]+)/([^/?#]+)", message_url)
        if match:
            return f"discord-message-url:{match.group(1)}:{match.group(2)}:{match.group(3)}"
        if _source_behavior_enabled(source_config or {}, "dedupe_by_channel_url", default=False):
            return f"discord-channel-url:{_normalize_bridge_url(message_url)}"
    channel_url = str(channel.get("url") or "").strip()
    if channel_url and _source_behavior_enabled(source_config or {}, "dedupe_by_channel_url", default=False):
        return f"discord-channel-url:{_normalize_bridge_url(channel_url)}"
    event_id = _canonical_chrome_bridge_event_id(str(details.get("event_id") or ""))
    return f"discord-event:{event_id}" if event_id else ""


def _normalize_bridge_url(url: str) -> str:
    return re.sub(r"[?#].*$", "", str(url or "").strip()).rstrip("/")


async def _chrome_bridge_updated_response(
    payload: ChromeBridgeMessage,
    raw_text: str,
    existing_alert: Dict[str, Any],
    *,
    settings: Dict[str, Any],
    patterns: Dict[str, Any],
    source_config: Dict[str, Any],
    source_override_matched: bool,
) -> dict:
    alert_id = str(existing_alert.get("alert_id") or "").strip()
    if hasattr(db, "update_alert"):
        await db.update_alert(
            alert_id,
            {
                "raw_message": raw_text,
                "bridge_updated_at": datetime.now(timezone.utc).isoformat(),
                "bridge_update_event_id": payload.event_id,
            },
        )
    mark_update = {"updated": False}
    if (
        not parse_card(raw_text).recognized
        and _source_behavior_enabled(source_config, "process_followup_updates", default=True)
        and not _source_behavior_enabled(source_config, "ignore_followup_messages", default=False)
    ):
        mark_update = await _apply_chrome_bridge_position_mark_update(payload, raw_text)
    actionable_result = None
    if _source_behavior_enabled(source_config, "process_actionable_edits", default=True):
        actionable_result = await _process_chrome_bridge_actionable_edit(
            payload,
            raw_text,
            previous_raw_text=str(existing_alert.get("raw_text") or ""),
            settings=settings,
            patterns=patterns,
            source_config=source_config,
            source_override_matched=source_override_matched,
        )
        if actionable_result:
            return actionable_result
    audit_event = await record_operator_event(
        db,
        "alert_ingestion",
        "bridge_alert_update",
        "Chrome bridge alert updated from Discord edit.",
        severity="info",
        details={
            "event_id": payload.event_id,
            "revision_hash": payload.revision_hash,
            "event_type": payload.event_type,
            "channel": {
                "id": payload.channel_id,
                "name": payload.channel_name,
                "url": payload.channel_url,
                "message_url": payload.url,
            },
            "author": {
                "id": _chrome_bridge_author_id(payload),
                "name": payload.author_name,
                "raw_name": payload.author_raw or payload.author_name,
            },
            "raw_text": raw_text,
            "alert_id": alert_id,
            "decision": {
                "status": "updated",
                "alert_inserted": False,
                "alert_id": alert_id,
                "trade_requested": False,
                "trade_request_reason": "discord message edit updated existing alert",
                "skip_reason": "position mark update" if mark_update.get("updated") else "",
                "position_mark_update": mark_update if mark_update.get("updated") else None,
            },
        },
    )
    return {
        "status": "updated",
        "event_id": payload.event_id,
        "source": payload.source,
        "channel_id": payload.channel_id,
        "channel_name": payload.channel_name,
        "channel_url": payload.channel_url,
        "bridge_target_id": payload.bridge_target_id,
        "bridge_target_name": payload.bridge_target_name,
        "url": payload.url,
        "author_name": payload.author_name,
        "raw_text": raw_text,
        "alert_inserted": False,
        "alert_id": alert_id,
        "trade_requested": False,
        "trade_request_reason": "discord message edit updated existing alert",
        "skip_reason": "position mark update" if mark_update.get("updated") else "",
        "position_mark_update": mark_update if mark_update.get("updated") else None,
        "audit_event_id": audit_event.get("id"),
    }


async def _process_chrome_bridge_actionable_edit(
    payload: ChromeBridgeMessage,
    raw_text: str,
    *,
    previous_raw_text: str,
    settings: Dict[str, Any],
    patterns: Dict[str, Any],
    source_config: Dict[str, Any],
    source_override_matched: bool,
) -> dict | None:
    parsed_preview, parser_metadata = _parse_alert_for_preview(raw_text, patterns)
    if not _is_actionable_edit_alert(parsed_preview):
        return None
    previous_parsed, _ = _parse_alert_for_preview(previous_raw_text, patterns)
    if _actionable_alert_key(previous_parsed) == _actionable_alert_key(parsed_preview):
        return None

    preflight_skip_reason = _chrome_bridge_preflight_skip_reason(
        settings=settings,
        parsed=parsed_preview,
        parser_metadata=parser_metadata,
        source_config=source_config,
        source_override_matched=source_override_matched,
        payload=payload,
    )
    if preflight_skip_reason:
        return None

    synthetic_message = _chrome_bridge_to_message(payload)
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
            card_database=db,
        ),
        bot_user=None,
        parsed_override=parsed_preview,
    )
    ingestion_result = {
        "status": "accepted" if result.alert_inserted else "skipped",
        "alert_inserted": result.alert_inserted,
        "alert_id": result.alert_id,
        "trade_requested": result.trade_requested,
        "trade_request_reason": result.trade_request_reason or "discord message edit became actionable",
        "skip_reason": result.skip_reason,
    }
    capture_path = record_alert_capture(
        event_id=payload.event_id,
        channel_id=payload.channel_id,
        channel_name=payload.channel_name,
        author_name=payload.author_name,
        raw_text=raw_text,
        observed_at=payload.observed_at,
        parsed=result.parsed,
        ingestion_result=ingestion_result,
        revision_hash=payload.revision_hash,
        event_type=payload.event_type,
        author_raw=payload.author_raw,
        attachment_urls=payload.attachment_urls,
        ocr_confidence=payload.ocr_confidence,
    )
    bus_event = _publish_chrome_bridge_signal(
        payload=payload,
        alert_text=raw_text,
        parsed=result.parsed,
        parser_metadata=parser_metadata,
        ingestion_result=ingestion_result,
        capture_path=capture_path,
    )
    audit_event = await _record_chrome_bridge_alert_audit(
        payload=payload,
        raw_text=raw_text,
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
        "raw_text": raw_text,
        "parsed": result.parsed,
        "parser_metadata": parser_metadata,
        "source_config": source_config,
        "alert_inserted": result.alert_inserted,
        "alert_id": result.alert_id,
        "trade_requested": result.trade_requested,
        "trade_request_reason": ingestion_result["trade_request_reason"],
        "skip_reason": result.skip_reason,
        "capture_path": str(capture_path),
        "bus_event_id": bus_event.event_id,
        "audit_event_id": audit_event.get("id"),
    }


def _is_actionable_edit_alert(parsed: Dict[str, Any] | None) -> bool:
    alert_type = str((parsed or {}).get("alert_type") or "").strip().lower()
    return alert_type in {"sell", "trim", "close", "average_down"}


def _actionable_alert_key(parsed: Dict[str, Any] | None) -> tuple | None:
    if not _is_actionable_edit_alert(parsed):
        return None
    normalized = normalize_parsed_alert(dict(parsed or {}))
    try:
        strike = round(float(normalized.get("strike") or 0.0), 4)
        entry_price = round(float(normalized.get("entry_price") or 0.0), 4)
        sell_percentage = round(float(normalized.get("sell_percentage") or 0.0), 4)
    except (TypeError, ValueError):
        return None
    return (
        str(normalized.get("alert_type") or "").strip().lower(),
        str(normalized.get("ticker") or "").strip().upper(),
        strike,
        str(normalized.get("option_type") or "").strip().upper(),
        str(normalized.get("expiration") or "").strip().upper().replace("-", "/"),
        entry_price,
        sell_percentage,
    )


async def _apply_chrome_bridge_position_mark_update(
    payload: ChromeBridgeMessage,
    raw_text: str,
) -> dict[str, Any]:
    mark = _parse_position_mark_update(raw_text)
    if not mark or not db or not hasattr(db, "get_positions") or not hasattr(db, "update_position"):
        return {"updated": False}

    open_positions = await db.get_positions("open")
    partial_positions = await db.get_positions("partial")
    positions = list(open_positions or []) + list(partial_positions or [])
    matched = [
        position for position in positions
        if _position_matches_mark_update(position, mark)
    ]
    if len(matched) != 1:
        return {
            "updated": False,
            "reason": "no matching position" if not matched else "ambiguous position mark update",
            "match_count": len(matched),
            "mark": mark,
        }

    position = matched[0]
    position_id = str(position.get("id") or "").strip()
    current_price = round(float(mark["current_price"]), 4)
    highest_price = max(
        _safe_float(position.get("highest_price")),
        _safe_float(position.get("current_price")),
        current_price,
    )
    remaining_quantity = _safe_int(position.get("remaining_quantity") or position.get("quantity"))
    entry_price = _safe_float(position.get("entry_price"))
    updates = {
        "current_price": current_price,
        "highest_price": highest_price,
        "unrealized_pnl": round((current_price - entry_price) * remaining_quantity * 100, 2),
        "mark_updated_from_discord_at": datetime.now(timezone.utc).isoformat(),
        "mark_update_event_id": payload.event_id,
    }
    await db.update_position(position_id, {"$set": updates})
    await record_operator_event(
        db,
        "alert_ingestion",
        "bridge_position_mark_update",
        "Chrome bridge profit update refreshed a local position mark.",
        severity="info",
        details={
            "event_id": payload.event_id,
            "raw_text": raw_text,
            "position_id": position_id,
            "mark": mark,
            "updates": updates,
        },
    )
    return {
        "updated": True,
        "position_id": position_id,
        "current_price": current_price,
        "highest_price": highest_price,
        "mark": mark,
    }


async def _infer_single_channel_position_sell(
    payload: ChromeBridgeMessage,
    raw_text: str,
    source_config: dict[str, Any],
) -> dict[str, Any] | None:
    if not _source_behavior_enabled(source_config, "allow_single_position_inferred_sell", default=True):
        return None
    if not re.search(
        r"^\s*(?:(?:I['\u2019]?M|I\s+AM)\s+(?:GOING\s+TO\s+)?)?"
        r"(?:SOLD|SELL|STC|TRIM|TRIMMING|CLOSE|CLOSING|EXIT|EXITING|OUT|FULLY\s+OUT|STOPPED\s+OUT)\b",
        str(raw_text or ""),
        re.IGNORECASE,
    ):
        return None
    if not db or not hasattr(db, "get_positions") or not hasattr(db, "get_alerts"):
        return None

    open_positions = await db.get_positions("open")
    partial_positions = await db.get_positions("partial")
    positions = list(open_positions or []) + list(partial_positions or [])
    alerts = await db.get_alerts(max(200, len(positions) * 4))
    alert_channel_by_id = {
        str(alert.get("id") or ""): str(alert.get("channel_id") or "")
        for alert in alerts or []
        if isinstance(alert, dict)
    }
    channel_id = str(payload.channel_id or "").strip()
    matched = [
        position
        for position in positions
        if alert_channel_by_id.get(str(position.get("alert_id") or "")) == channel_id
    ]
    if len(matched) != 1:
        return None

    position = matched[0]
    if _newer_channel_contract_conflicts(alerts or [], channel_id, position):
        return None
    try:
        strike = f"{float(position.get('strike')):g}"
    except (TypeError, ValueError):
        return None
    ticker = str(position.get("ticker") or "").strip().upper()
    option_type = str(position.get("option_type") or "").strip().upper()
    expiration = str(position.get("expiration") or "").strip()
    if not ticker or option_type not in {"CALL", "PUT"} or not expiration:
        return None

    canonical = (
        f"{raw_text} ${ticker} ${strike} {option_type}S "
        f"{expiration} @ MARKET"
    )
    parsed = normalize_parsed_alert(parse_alert(canonical))
    if not parsed or str(parsed.get("alert_type") or "").lower() not in {"sell", "trim", "close"}:
        return None
    parsed = dict(parsed)
    parsed.update(
        {
            "ticker": ticker,
            "strike": float(position["strike"]),
            "option_type": option_type,
            "expiration": expiration,
            "entry_price": None,
            "market_price": True,
        }
    )
    parsed["inferred_from_position_id"] = str(position.get("id") or "")
    return parsed


def _newer_channel_contract_conflicts(
    alerts: list[dict[str, Any]],
    channel_id: str,
    position: dict[str, Any],
) -> bool:
    """Do not bind contextual exits across a newer explicit contract conversation."""
    entry_alert_id = str(position.get("alert_id") or "").strip()
    position_ticker = str(position.get("ticker") or "").strip().upper()
    position_type = str(position.get("option_type") or "").strip().upper()
    try:
        position_strike = float(position.get("strike"))
    except (TypeError, ValueError):
        return True

    for alert in alerts:
        if not isinstance(alert, dict) or str(alert.get("channel_id") or "").strip() != channel_id:
            continue
        if entry_alert_id and str(alert.get("id") or "").strip() == entry_alert_id:
            return False
        ticker = str(alert.get("ticker") or "").strip().upper()
        option_type = str(alert.get("option_type") or "").strip().upper()
        try:
            strike = float(alert.get("strike"))
        except (TypeError, ValueError):
            continue
        if not ticker or option_type not in {"CALL", "PUT"} or strike <= 0:
            continue
        if ticker != position_ticker or option_type != position_type or strike != position_strike:
            return True
    return False


_EXIT_CONTEXT_WORDS = {
    "ALL",
    "HALF",
    "FOR",
    "MAJORITY",
    "PART",
    "POSITION",
    "REMAINDER",
    "REST",
    "SOME",
    "SLOWLY",
    "NOW",
}


def _exit_alert_uses_context_word_as_ticker(
    parsed: dict[str, Any] | None,
    raw_text: str,
) -> bool:
    if not parsed or str(parsed.get("alert_type") or "").lower() not in {"sell", "trim", "close"}:
        return False
    ticker = str(parsed.get("ticker") or "").strip().upper()
    if ticker not in _EXIT_CONTEXT_WORDS:
        return False
    return re.search(rf"\${re.escape(ticker)}\b", str(raw_text or ""), re.IGNORECASE) is None


_CONVERSATIONAL_ENTRY_RE = re.compile(
    r"^\s*(?:IN|BOUGHT|BUYING|ENTERED|RE-?ENTER(?:ED|ING)?)\s+"
    r"\$?(?P<ticker>[A-Z]{1,6})\s+"
    r"(?P<option_type>CALLS?|PUTS?)\s+"
    r"(?:AT|@)\s*\$?\s*(?P<price>\d*\.?\d+)\s*"
    r"(?:FILL(?:ED)?)?\b",
    re.IGNORECASE,
)


async def _infer_recent_channel_contract_buy(
    payload: ChromeBridgeMessage,
    raw_text: str,
    source_config: dict[str, Any],
) -> dict[str, Any] | None:
    if not _source_behavior_enabled(source_config, "process_followup_updates", default=True):
        return None
    if _source_behavior_enabled(source_config, "ignore_followup_messages", default=False):
        return None
    text = str(raw_text or "").strip()
    if len([line for line in text.splitlines() if line.strip()]) != 1:
        return None
    match = _CONVERSATIONAL_ENTRY_RE.search(text)
    if not match or not db or not hasattr(db, "get_alerts"):
        return None

    try:
        price = float(match.group("price"))
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None

    ticker = match.group("ticker").upper()
    option_type = "CALL" if match.group("option_type").upper().startswith("CALL") else "PUT"
    channel_id = str(payload.channel_id or "").strip()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    alerts = await db.get_alerts(200)
    for alert in alerts or []:
        if str(alert.get("channel_id") or "").strip() != channel_id:
            continue
        if str(alert.get("alert_type") or "").strip().lower() not in {"buy", "average_down"}:
            continue
        if str(alert.get("ticker") or "").strip().upper() != ticker:
            continue
        if str(alert.get("option_type") or "").strip().upper() != option_type:
            continue
        if alert.get("strike") is None or not alert.get("expiration"):
            continue
        try:
            observed = datetime.fromisoformat(str(alert.get("timestamp") or "").replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            if observed.astimezone(timezone.utc) < cutoff:
                continue
        except (TypeError, ValueError):
            continue
        return {
            "alert_type": "buy",
            "ticker": ticker,
            "strike": float(alert["strike"]),
            "option_type": option_type,
            "expiration": str(alert["expiration"]),
            "entry_price": price,
            "sell_percentage": None,
            "market_price": False,
        }
    return None


def _parse_position_mark_update(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "").strip()
    if not text or _has_builtin_action_keyword(text):
        return None
    if not re.search(r"\b(?:up|here|calls?|puts?)\b", text, re.IGNORECASE):
        return None

    prices = re.findall(r"(?<![A-Z0-9])\$?\s*(\d*\.\d+)(?![A-Z0-9])", text, re.IGNORECASE)
    if not prices:
        return None
    try:
        current_price = float(prices[-1])
    except ValueError:
        return None
    if current_price <= 0:
        return None

    ticker = _extract_mark_update_ticker(text)
    if not ticker:
        return None
    option_type = None
    if re.search(r"\bCALLS?\b", text, re.IGNORECASE):
        option_type = "CALL"
    elif re.search(r"\bPUTS?\b", text, re.IGNORECASE):
        option_type = "PUT"

    strike = None
    strike_match = re.search(r"\$[A-Z]{1,6}\s+\$(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not strike_match:
        strike_match = re.search(r"\b[A-Z]{1,6}\s+(\d+(?:\.\d+)?)\s*[CP]\b", text, re.IGNORECASE)
    if strike_match:
        try:
            strike = float(strike_match.group(1))
        except ValueError:
            strike = None

    profit_pct = None
    profit_match = re.search(r"\bUP\s*\+\s*(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
    if profit_match:
        try:
            profit_pct = float(profit_match.group(1))
        except ValueError:
            profit_pct = None

    return {
        "ticker": ticker,
        "strike": strike,
        "option_type": option_type,
        "current_price": current_price,
        "profit_percentage": profit_pct,
    }


def _extract_mark_update_ticker(text: str) -> str:
    for pattern in (
        r"\bON\s+\$?([A-Z]{1,6})\b",
        r"\bFOR\s+\$?([A-Z]{1,6})\b",
        r"\$([A-Z]{1,6})\b",
        r"\b([A-Z]{1,6})\s+(?:CALLS?|PUTS?)\b",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            ticker = str(match.group(1) or "").strip().upper()
            if ticker not in {"UP", "HERE", "CALL", "CALLS", "PUT", "PUTS"}:
                return ticker
    return ""


def _position_matches_mark_update(position: dict[str, Any], mark: dict[str, Any]) -> bool:
    if str(position.get("status") or "open").strip().lower() not in {"open", "partial"}:
        return False
    if str(position.get("ticker") or "").strip().upper() != str(mark.get("ticker") or "").strip().upper():
        return False
    mark_type = str(mark.get("option_type") or "").strip().upper()
    if mark_type and str(position.get("option_type") or "").strip().upper() != mark_type:
        return False
    mark_strike = mark.get("strike")
    if mark_strike is not None and abs(_safe_float(position.get("strike")) - _safe_float(mark_strike)) >= 0.001:
        return False
    return True


def _safe_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(int(float(value or 0)), 0)
    except (TypeError, ValueError):
        return 0


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


def _chrome_bridge_skipped_response(payload: ChromeBridgeMessage, *, skip_reason: str) -> dict:
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
        "alert_inserted": False,
        "alert_id": "",
        "trade_requested": False,
        "trade_request_reason": "",
        "skip_reason": skip_reason,
    }


def _chrome_bridge_freshness_skip_reason(payload: ChromeBridgeMessage) -> str | None:
    max_age_minutes = _chrome_bridge_max_message_age_minutes()
    if max_age_minutes <= 0:
        return None
    raw_timestamp = str(payload.timestampIso or "").strip()
    if not raw_timestamp:
        return None
    try:
        source_timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return "invalid chrome bridge source timestamp"
    if source_timestamp.tzinfo is None:
        source_timestamp = source_timestamp.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - source_timestamp).total_seconds()
    if age_seconds > max_age_minutes * 60:
        return "stale chrome bridge source timestamp"
    return None


def _chrome_bridge_max_message_age_minutes() -> float:
    raw_value = str(os.environ.get("CHROME_BRIDGE_MAX_MESSAGE_AGE_MINUTES", "10")).strip()
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return 10.0


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

    content = payload.content
    if not content.strip() and not embeds and payload.attachment_urls:
        if payload.ocr_text and (payload.ocr_confidence or 0.0) >= 0.8:
            content = payload.ocr_text
        else:
            confidence = f"{payload.ocr_confidence:.0%}" if payload.ocr_confidence is not None else "unavailable"
            content = f"[Image-only Discord alert; OCR confidence {confidence}; context only]"

    return SimpleNamespace(
        id=payload.event_id,
        content=content,
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
    card = parse_card(raw_text)
    if card.recognized:
        metadata.update({
            "card_recognized": True, "card_reason": card.reason,
            "pattern_source": "structured_card", "matched_pattern_type": "labelled_options",
            "ignored": card.parsed is None, "explicit_action": card.parsed is not None,
            "confidence": "high" if card.parsed else "none",
        })
        return card.parsed, metadata
    explicit_action = _has_builtin_action_keyword(raw_text)
    metadata["explicit_action"] = explicit_action

    followup_exit_pattern = _discord_followup_exit_pattern(raw_text)
    if followup_exit_pattern:
        parsed = normalize_parsed_alert(parse_alert(raw_text))
        if parsed:
            parsed = dict(parsed)
            parsed["alert_type"] = "sell"
            parsed["entry_price"] = None
            parsed["sell_percentage"] = 100.0
            parsed["market_price"] = False
            metadata.update(
                {
                    "matched_pattern": followup_exit_pattern,
                    "matched_pattern_type": "followup_exit",
                    "pattern_source": "builtin",
                    "explicit_action": True,
                    "confidence": "high",
                }
            )
            return parsed, metadata

    followup_average_down = _discord_followup_average_down(raw_text)
    if followup_average_down:
        parsed = normalize_parsed_alert(parse_alert(raw_text))
        if parsed:
            parsed = dict(parsed)
            parsed["alert_type"] = "average_down"
            parsed["entry_price"] = followup_average_down["price"]
            metadata.update(
                {
                    "matched_pattern": followup_average_down["label"],
                    "matched_pattern_type": "followup_average_down",
                    "pattern_source": "builtin",
                    "explicit_action": True,
                    "confidence": "high",
                }
            )
            return parsed, metadata

    followup_pattern = _discord_followup_update_pattern(raw_text)
    if followup_pattern:
        metadata.update(
            {
                "matched_pattern": followup_pattern,
                "matched_pattern_type": "followup_update",
                "pattern_source": "builtin",
                "ignored": True,
                "confidence": "high",
            }
        )
        return None, metadata

    raw_parsed = normalize_parsed_alert(parse_alert(raw_text))
    ignore_match = _first_matching_pattern(
        raw_text,
        patterns.get("ignore_patterns", []),
        case_sensitive=case_sensitive,
    )
    if (
        ignore_match
        and raw_parsed
        and explicit_action
        and _explicit_action_precedes_pattern(raw_text, ignore_match, case_sensitive=case_sensitive)
    ):
        ignore_match = None
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
        if (
            match
            and raw_parsed
            and explicit_action
            and not _parsed_alert_already_matches_pattern(raw_parsed, pattern_type)
            and _explicit_action_precedes_pattern(raw_text, match, case_sensitive=case_sensitive)
        ):
            continue
        if match:
            metadata["matched_pattern"] = match
            metadata["matched_pattern_type"] = pattern_type
            metadata["pattern_source"] = _pattern_source(patterns, pattern_type, match)
            metadata["explicit_action"] = True
            metadata["confidence"] = "high"
            if raw_parsed and _parsed_alert_already_matches_pattern(raw_parsed, pattern_type):
                canonical_text = raw_text
            elif pattern_type != "buy_patterns" or raw_parsed is None:
                canonical_text = _canonicalize_pattern_action(
                    raw_text,
                    match,
                    canonical_action,
                    case_sensitive=case_sensitive,
                )
            break

    parsed = raw_parsed if canonical_text == raw_text else normalize_parsed_alert(parse_alert(canonical_text))
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


def _parsed_alert_already_matches_pattern(parsed: Dict[str, Any], pattern_type: str) -> bool:
    alert_type = str((parsed or {}).get("alert_type") or "").strip().lower()
    if pattern_type == "buy_patterns":
        return alert_type == "buy"
    if pattern_type == "average_down_patterns":
        return alert_type == "average_down"
    if pattern_type in {"sell_patterns", "partial_sell_patterns"}:
        return alert_type in {"sell", "trim", "close"}
    return False


def _has_builtin_action_keyword(raw_text: str) -> bool:
    return any(
        _contains_preview_keyword(raw_text, keyword)
        for keyword in BUY_KEYWORDS + SELL_KEYWORDS + AVG_DOWN_KEYWORDS
    )


def _discord_followup_update_pattern(raw_text: str) -> str | None:
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    if len(lines) < 2:
        return None

    prior_text = " ".join(lines[:-1])
    latest_line = lines[-1]
    if not re.search(r"\bentry\b", prior_text, re.IGNORECASE):
        return None

    actionable_latest = (
        _contains_preview_keyword(latest_line, "entry")
        or any(_contains_preview_keyword(latest_line, keyword) for keyword in BUY_KEYWORDS + SELL_KEYWORDS)
        or is_actionable_average_down_alert(latest_line)
    )
    if actionable_latest:
        return None

    followup_patterns = (
        (r"\bjust\s+filled\b", "JUST FILLED"),
        (r"\bavg(?:erage)?\s+fill\b", "AVG FILL"),
        (r"\bhere\s+on\b.*\bup\s*\+\s*\d+(?:\.\d+)?\s*%", "HERE ON ... UP +%"),
        (r"\bup\s*\+\s*\d+(?:\.\d+)?\s*%", "UP +%"),
        (r"\bon\s+watch\b", "ON WATCH"),
        (r"\bhands\s+off\b", "HANDS OFF"),
        (r"\bwill\s+re-?enter\b", "WILL RE-ENTER"),
        (r"\b(?:looking|waiting)\b.*\b(?:dca|add)\b", "FUTURE DCA"),
        (r"\bdca\s+room\b", "DCA ROOM"),
        (r"\badd\s+on\s+pullbacks?\b", "ADD ON PULLBACKS"),
    )
    for pattern, label in followup_patterns:
        if re.search(pattern, latest_line, re.IGNORECASE):
            return label
    return None


def _discord_followup_exit_pattern(raw_text: str) -> str | None:
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    if len(lines) < 2 or not re.search(r"\bentry\b", " ".join(lines[:-1]), re.IGNORECASE):
        return None

    latest_line = lines[-1]
    stop_reference = re.search(
        r"(?:\bb\s*/?\s*e\b|\bbreak[\s-]*even\b|\bsl\b|\bstop\s*loss\b)",
        latest_line,
        re.IGNORECASE,
    )
    exit_action = re.search(
        r"\b(?:hit|hits|triggered|stopped|stopped\s+out|sold|sell|closed|out)\b",
        latest_line,
        re.IGNORECASE,
    )
    if stop_reference and exit_action:
        return "FOLLOWUP STOP EXIT"
    if re.search(r"\bin\s+cash\b", latest_line, re.IGNORECASE) and re.search(
        r"\b(?:staying|stay|now|hands\s+off|out)\b",
        latest_line,
        re.IGNORECASE,
    ):
        return "FOLLOWUP FLAT EXIT"
    return None


def _discord_followup_average_down(raw_text: str) -> dict[str, Any] | None:
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    if len(lines) < 2 or not re.search(r"\bentry\b", " ".join(lines[:-1]), re.IGNORECASE):
        return None

    latest_line = lines[-1]
    if not is_actionable_average_down_alert(latest_line):
        return None
    fill_price = _discord_followup_fill_price(latest_line)
    if fill_price is None:
        prices = re.findall(r"(?<![A-Z0-9])\$?\s*(\d*\.\d+)(?![A-Z0-9])", latest_line)
        if not prices:
            return None
        fill_price = prices[-1]
    try:
        price = float(fill_price)
    except ValueError:
        return None
    if price <= 0:
        return None
    return {"label": "FOLLOWUP DCA FILL", "price": price}


def _discord_followup_fill_price(latest_line: str) -> str | None:
    for pattern in (
        r"\bfill(?:ed)?(?:\s+adds?)?\s*(?:at|@)?\s*\$?\s*(\d*\.\d+)",
        r"\bre-?add(?:ing|ed)?\b.*?\$?\s*(\d*\.\d+)\s+fill(?:ed)?\b",
    ):
        match = re.search(pattern, latest_line, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _contains_preview_keyword(raw_text: str, keyword: str) -> bool:
    parts = [re.escape(part) for part in str(keyword).strip().split()]
    if not parts:
        return False
    body = r"\s+".join(parts)
    return re.search(rf"(?<![A-Z0-9]){body}(?![A-Z0-9])", raw_text, re.IGNORECASE) is not None


def _explicit_action_precedes_pattern(
    raw_text: str,
    pattern: str,
    *,
    case_sensitive: bool,
) -> bool:
    flags = 0 if case_sensitive else re.IGNORECASE
    action_starts = []
    for keyword in BUY_KEYWORDS + SELL_KEYWORDS + AVG_DOWN_KEYWORDS:
        parts = [re.escape(part) for part in str(keyword).strip().split()]
        if not parts:
            continue
        action_pattern = r"\s+".join(parts)
        match = re.search(rf"(?<![A-Z0-9]){action_pattern}(?![A-Z0-9])", raw_text, flags)
        if match:
            action_starts.append(match.start())
    pattern_parts = [re.escape(part) for part in str(pattern or "").strip().split()]
    if not action_starts or not pattern_parts:
        return False
    ignore_pattern = r"\s+".join(pattern_parts)
    pattern_match = re.search(
        rf"(?<![A-Z0-9]){ignore_pattern}(?![A-Z0-9])",
        raw_text,
        flags,
    )
    return pattern_match is None or min(action_starts) < pattern_match.start()


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
    if not coerce_bool(settings.get("auto_trading_enabled"), default=True):
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
    raw_text: str = "",
) -> Dict[str, Any]:
    auto_trading_enabled = coerce_bool(settings.get("auto_trading_enabled"), default=True)
    shutdown_triggered = coerce_bool(settings.get("shutdown_triggered"), default=False)

    reason = skip_reason
    if reason is None and not auto_trading_enabled:
        reason = "auto trading disabled"
    if reason is None and shutdown_triggered:
        reason = "shutdown triggered"

    quantity = None
    uncapped_quantity = None
    estimated_premium_cost = None
    uncapped_premium_cost = None
    entry_risk_profile = "normal"
    if parsed and str(parsed.get("alert_type", "")).lower() in {"buy", "average_down"}:
        entry_price = parsed.get("entry_price")
        if entry_price:
            entry_price = float(entry_price)
            risk_language_cap, risk_language_reasons = alert_risk_size_cap(
                raw_text,
                cap_percent=float(settings.get("coordinated_high_risk_size_percent", 25.0)),
            )
            entry_risk_profile = "high_risk" if risk_language_reasons else "normal"
            stop_loss_percent = float(
                settings.get(
                    "coordinated_high_risk_stop_loss_percent"
                    if entry_risk_profile == "high_risk"
                    else "coordinated_normal_stop_loss_percent",
                    50.0 if entry_risk_profile == "high_risk" else 35.0,
                )
            )
            uncapped_quantity = calculate_position_size(
                entry_price=entry_price,
                default_quantity=int(settings.get("default_quantity", 1)),
                max_position_size=float(settings.get("max_position_size", 1000.0)),
                risk_multiplier=source_config.get("risk_multiplier", 1.0),
                max_loss_per_trade=(
                    float(settings.get("max_loss_per_trade", 500.0))
                    if coerce_bool(settings.get("risk_budget_sizing_enabled"), default=True)
                    else None
                ),
                stop_loss_percent=(
                    stop_loss_percent
                    if coerce_bool(settings.get("risk_budget_sizing_enabled"), default=True)
                    else None
                ),
            )
            quantity = apply_source_quantity_limits(uncapped_quantity, source_config)
            if risk_language_cap is not None and quantity > 0:
                quantity = max(1, int(quantity * risk_language_cap / 100.0))
            estimated_premium_cost = round(entry_price * quantity * 100, 2)
            uncapped_premium_cost = round(entry_price * uncapped_quantity * 100, 2)
            if quantity <= 0 and reason is None:
                reason = "position size exceeds max_position_size"

    return {
        "would_insert_alert": bool(parsed and skip_reason is None),
        "would_request_trade": bool(parsed and reason is None),
        "reason": reason,
        "auto_trading_enabled": auto_trading_enabled,
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
        "entry_risk_profile": entry_risk_profile,
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
