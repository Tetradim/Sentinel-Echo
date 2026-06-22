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


@dataclass(frozen=True)
class DiscordIngestionResult:
    parsed: Optional[dict] = None
    alert_inserted: bool = False
    trade_requested: bool = False
    skip_reason: str = ""


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
    parsed = parse_alert(alert_text)
    if not parsed:
        return DiscordIngestionResult(skip_reason="unparsed")

    settings = deps.load_settings() or {}
    source_config = resolve_source_config(
        settings,
        channel_id=channel_id,
        channel_name=getattr(channel, "name", ""),
    )
    skip_reason = source_skip_reason(parsed, source_config)
    if skip_reason:
        return DiscordIngestionResult(parsed=parsed, skip_reason=skip_reason)

    if source_config.get("paper_only"):
        parsed["_force_simulation"] = True
    parsed["_source_config"] = source_config

    duplicate_check = getattr(deps, "is_duplicate_alert", lambda alert: False)
    if duplicate_check(parsed):
        return DiscordIngestionResult(parsed=parsed, skip_reason="duplicate alert")

    await _maybe_await(deps.update_status("last_alert_time", datetime.now(timezone.utc).isoformat()))
    increment_alerts_processed = getattr(deps, "increment_alerts_processed", None)
    if increment_alerts_processed:
        await _maybe_await(increment_alerts_processed())

    alert = Alert(
        ticker=parsed.get("ticker", ""),
        strike=parsed.get("strike") or 0,
        option_type=parsed.get("option_type") or "CALL",
        expiration=parsed.get("expiration") or "",
        entry_price=parsed.get("entry_price") or 0,
        alert_type=parsed.get("alert_type", "buy"),
        sell_percentage=parsed.get("sell_percentage"),
        raw_message=alert_text,
    )
    await _maybe_await(deps.insert_alert(alert))

    trade_requested = False
    skip_reason = ""
    if source_config.get("require_manual_confirm"):
        skip_reason = "manual confirmation required"
    elif _auto_trading_enabled(settings):
        await deps.process_trade(alert, parsed)
        trade_requested = True

    return DiscordIngestionResult(
        parsed=parsed,
        alert_inserted=True,
        trade_requested=trade_requested,
        skip_reason=skip_reason,
    )


def _auto_trading_enabled(settings: dict) -> bool:
    return coerce_bool(settings.get("auto_trading_enabled"), default=False) and not coerce_bool(
        settings.get("shutdown_triggered"),
        default=False,
    )


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
