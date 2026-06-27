from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import isawaitable
from typing import Any, Callable, Optional

from discord_alert_text import build_discord_alert_text
from models import Alert
from settings_flags import coerce_bool
from source_config import resolve_source_config, source_skip_reason
from utils import parse_alert


EXIT_ALERT_TYPES = {"sell", "trim", "close"}


@dataclass(frozen=True)
class DiscordIngestionResult:
    parsed: Optional[dict] = None
    alert_inserted: bool = False
    trade_requested: bool = False
    skip_reason: str = ""
    alert_id: str = ""
    trade_request_reason: str = ""


@dataclass
class DiscordIngestionDeps:
    load_settings: Callable[[], dict]
    insert_alert: Callable[[Alert], Any]
    process_trade: Callable[[Alert, dict], Any]
    update_status: Callable[[str, Any], Any]
    is_duplicate_alert: Callable[[dict], bool] = lambda parsed: False
    increment_alerts_processed: Optional[Callable[[], Any]] = None


async def handle_discord_message(
    message,
    *,
    channel_ids: list[str],
    deps: DiscordIngestionDeps,
    bot_user=None,
) -> DiscordIngestionResult:
    """Parse and persist a Discord alert, then request trading when settings allow."""
    if _same_user(getattr(message, "author", None), bot_user):
        return DiscordIngestionResult(skip_reason="self message")

    channel = getattr(message, "channel", None)
    channel_id = str(getattr(channel, "id", ""))
    if channel_ids and channel_id not in {str(item) for item in channel_ids}:
        return DiscordIngestionResult(skip_reason="channel not monitored")

    alert_text = build_discord_alert_text(message)
    settings = deps.load_settings() or {}
    source_config = resolve_source_config(
        settings,
        channel_id=channel_id,
        channel_name=getattr(channel, "name", ""),
    )
    metadata = _message_metadata(message, source_config)
    parsed = parse_alert(alert_text)
    if not parsed:
        alert = _build_alert(
            parsed=None,
            raw_message=alert_text,
            metadata=metadata,
            processed=False,
            skip_reason="unparsed",
            trade_request_reason="unparsed",
        )
        await _maybe_await(deps.insert_alert(alert))
        return DiscordIngestionResult(
            alert_inserted=True,
            skip_reason="unparsed",
            alert_id=alert.id,
            trade_request_reason="unparsed",
        )

    skip_reason = source_skip_reason(parsed, source_config)
    if skip_reason:
        alert = _build_alert(
            parsed=parsed,
            raw_message=alert_text,
            metadata=metadata,
            processed=True,
            skip_reason=skip_reason,
            trade_request_reason=skip_reason,
        )
        await _maybe_await(deps.insert_alert(alert))
        return DiscordIngestionResult(
            parsed=parsed,
            alert_inserted=True,
            skip_reason=skip_reason,
            alert_id=alert.id,
            trade_request_reason=skip_reason,
        )

    if source_config.get("paper_only"):
        parsed["_force_simulation"] = True
    parsed["_source_config"] = source_config

    duplicate_check = getattr(deps, "is_duplicate_alert", lambda alert: False)
    if duplicate_check(parsed):
        return DiscordIngestionResult(parsed=parsed, skip_reason="duplicate alert", trade_request_reason="duplicate alert")

    if _is_exit_alert(parsed) and not _sell_alert_listening_enabled(settings):
        alert = _build_alert(
            parsed=parsed,
            raw_message=alert_text,
            metadata=metadata,
            processed=True,
            skip_reason="sell alert listening disabled",
            trade_request_reason="sell alert listening disabled",
        )
        await _maybe_await(deps.insert_alert(alert))
        return DiscordIngestionResult(
            parsed=parsed,
            alert_inserted=True,
            trade_requested=False,
            skip_reason="sell alert listening disabled",
            alert_id=alert.id,
            trade_request_reason="sell alert listening disabled",
        )

    await _maybe_await(deps.update_status("last_alert_time", datetime.now(timezone.utc).isoformat()))
    increment_alerts_processed = getattr(deps, "increment_alerts_processed", None)
    if increment_alerts_processed:
        await _maybe_await(increment_alerts_processed())

    trade_requested = False
    skip_reason = ""
    trade_request_reason = ""
    if source_config.get("require_manual_confirm"):
        skip_reason = "manual confirmation required"
        trade_request_reason = "manual confirmation required"
    elif not _auto_trading_enabled(settings):
        skip_reason = _trade_request_disabled_reason(settings)
        trade_request_reason = skip_reason
    else:
        trade_request_reason = "auto trading enabled"
    alert = _build_alert(
        parsed=parsed,
        raw_message=alert_text,
        metadata=metadata,
        processed=bool(skip_reason),
        skip_reason=skip_reason,
        trade_request_reason=trade_request_reason,
    )
    await _maybe_await(deps.insert_alert(alert))

    if source_config.get("require_manual_confirm"):
        pass
    elif _auto_trading_enabled(settings):
        await deps.process_trade(alert, parsed)
        trade_requested = True
    else:
        trade_request_reason = skip_reason

    return DiscordIngestionResult(
        parsed=parsed,
        alert_inserted=True,
        trade_requested=trade_requested,
        skip_reason=skip_reason,
        alert_id=alert.id,
        trade_request_reason=trade_request_reason,
    )


def _build_alert(
    *,
    parsed: Optional[dict],
    raw_message: str,
    metadata: dict[str, Optional[str]],
    processed: bool = False,
    trade_executed: bool = False,
    skip_reason: str = "",
    trade_request_reason: str = "",
) -> Alert:
    parsed = parsed or {}
    reason = skip_reason or ""
    return Alert(
        ticker=parsed.get("ticker") or "UNKNOWN",
        strike=parsed.get("strike") or 0,
        option_type=parsed.get("option_type") or "",
        expiration=parsed.get("expiration") or "",
        entry_price=parsed.get("entry_price") or 0,
        alert_type=parsed.get("alert_type") or "unparsed",
        sell_percentage=parsed.get("sell_percentage"),
        raw_message=raw_message,
        processed=processed,
        trade_executed=trade_executed,
        trade_result=f"skipped: {reason}" if reason else None,
        skip_reason=reason or None,
        trade_request_reason=trade_request_reason or None,
        exit_trigger="sell_alert" if _is_exit_alert(parsed) else None,
        **metadata,
    )


def _message_metadata(message, source_config: dict) -> dict[str, Optional[str]]:
    author = getattr(message, "author", None)
    channel = getattr(message, "channel", None)
    channel_name = _clean_text(getattr(channel, "name", None))
    source_name = _clean_text(source_config.get("name")) or channel_name
    return {
        "channel_id": _clean_text(getattr(channel, "id", None)),
        "channel_name": channel_name,
        "author_id": _clean_text(getattr(author, "id", None)),
        "author_name": _author_name(author),
        "source_name": source_name,
        "source_label": source_name,
    }


def _author_name(author) -> Optional[str]:
    if author is None:
        return None
    for attr in ("display_name", "global_name", "name"):
        value = _clean_text(getattr(author, attr, None))
        if value:
            return value
    return _clean_text(author)


def _clean_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _is_exit_alert(parsed: dict) -> bool:
    return str((parsed or {}).get("alert_type", "")).strip().lower() in EXIT_ALERT_TYPES


def _sell_alert_listening_enabled(settings: dict) -> bool:
    return coerce_bool(settings.get("sell_alert_listening_enabled"), default=True)


def _auto_trading_enabled(settings: dict) -> bool:
    return coerce_bool(settings.get("auto_trading_enabled"), default=True) and not coerce_bool(
        settings.get("shutdown_triggered"),
        default=False,
    )


def _trade_request_disabled_reason(settings: dict) -> str:
    if coerce_bool(settings.get("shutdown_triggered"), default=False):
        return "shutdown triggered"
    return "auto trading disabled"


def _same_user(left, right) -> bool:
    if left is None or right is None:
        return False
    left_id = getattr(left, "id", None)
    right_id = getattr(right, "id", None)
    if left_id is not None or right_id is not None:
        return left_id == right_id
    return left == right


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value
