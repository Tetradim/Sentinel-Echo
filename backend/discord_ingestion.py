from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
from typing import Any, Callable, Optional

from discord_alert_text import build_discord_alert_text
from models import Alert
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
    sr_pre_entry_gate: Optional[Callable[[Alert, dict, dict], Any]] = None


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

    deps.update_status("last_alert_time", datetime.now(timezone.utc).isoformat())
    increment_alerts_processed = getattr(deps, "increment_alerts_processed", None)
    if increment_alerts_processed:
        increment_alerts_processed()

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
    deps.insert_alert(alert)

    trade_requested = False
    skip_reason = ""
    if source_config.get("require_manual_confirm"):
        skip_reason = "manual confirmation required"
    elif _auto_trading_enabled(settings):
        sr_gate = await _run_sr_pre_entry_gate(alert, parsed, source_config, deps)
        if not sr_gate["allowed"]:
            return DiscordIngestionResult(
                parsed=parsed,
                alert_inserted=True,
                trade_requested=False,
                skip_reason=f"sr watch blocked: {sr_gate['reason']}",
            )
        await deps.process_trade(alert, parsed)
        trade_requested = True

    return DiscordIngestionResult(
        parsed=parsed,
        alert_inserted=True,
        trade_requested=trade_requested,
        skip_reason=skip_reason,
    )


def _auto_trading_enabled(settings: dict) -> bool:
    return bool(settings.get("auto_trading_enabled", False)) and not bool(
        settings.get("shutdown_triggered", False)
    )


async def _run_sr_pre_entry_gate(
    alert: Alert,
    parsed: dict,
    source_config: dict,
    deps: DiscordIngestionDeps,
) -> dict:
    if not source_config.get("sr_watch_enabled"):
        return {"allowed": True, "reason": ""}

    if str(parsed.get("alert_type") or "").strip().lower() not in {"buy", "average_down"}:
        return {"allowed": True, "reason": ""}

    gate = getattr(deps, "sr_pre_entry_gate", None)
    if gate is None:
        reason = "sr watch gate unavailable"
        if source_config.get("sr_watch_strict_gating"):
            return {"allowed": False, "reason": reason}
        parsed["_sr_watch_gate_error"] = reason
        return {"allowed": True, "reason": reason}

    try:
        result = gate(alert, parsed, source_config)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        reason = f"sr watch gate error: {exc}"
        if source_config.get("sr_watch_strict_gating"):
            return {"allowed": False, "reason": reason}
        parsed["_sr_watch_gate_error"] = reason
        return {"allowed": True, "reason": reason}

    parsed["_sr_watch_gate"] = result
    if isinstance(result, bool):
        return {"allowed": result, "reason": "gate returned false" if not result else ""}
    if isinstance(result, dict):
        allowed = bool(result.get("allowed", True))
        reason = str(result.get("reason") or "gate returned blocked").strip()
        return {"allowed": allowed, "reason": reason}
    return {"allowed": True, "reason": ""}


def _same_user(left, right) -> bool:
    if left is None or right is None:
        return False
    left_id = getattr(left, "id", None)
    right_id = getattr(right, "id", None)
    if left_id is not None or right_id is not None:
        return left_id == right_id
    return left == right
