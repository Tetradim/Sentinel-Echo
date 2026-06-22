"""Runtime live-trading arming semantics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from operator_audit import record_operator_event
from readiness_status import readiness_ready_for_live


CONFIRMATION_PHRASE = "ARM LIVE TRADING"


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _valid_duration_minutes(value: Any) -> bool:
    return type(value) is int and 1 <= value <= 480


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_live_trading_armed(runtime_state: Dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    """Return True only when runtime live arming is active and not expired."""
    runtime_state = _dict_or_empty(runtime_state)
    if runtime_state.get("live_trading_armed") is not True:
        return False
    expires_at = _parse_timestamp(runtime_state.get("live_trading_armed_until"))
    if not expires_at:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return expires_at > current


async def arm_live_trading(
    db,
    *,
    duration_minutes: int,
    confirmation: str,
    readiness: Dict[str, Any],
    operator: str = "local_operator",
    reason: str = "",
) -> Dict[str, Any]:
    """Arm live trading for a bounded runtime window."""
    if confirmation != CONFIRMATION_PHRASE:
        raise ValueError(f'Confirmation must match "{CONFIRMATION_PHRASE}".')
    if not _valid_duration_minutes(duration_minutes):
        raise ValueError("duration_minutes must be between 1 and 480.")
    readiness = _dict_or_empty(readiness)
    if not readiness_ready_for_live(readiness):
        await record_operator_event(
            db,
            "live_safety",
            "live_trading_arm_blocked",
            "Live trading arm was blocked by readiness checks.",
            severity="warning",
            details={"blocking_issues": _list_or_empty(readiness.get("blocking_issues"))},
        )
        raise RuntimeError("Live readiness has blocking issues.")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
    runtime_updates = {
        "live_trading_armed": True,
        "live_trading_armed_until": expires_at.isoformat(),
        "live_trading_armed_by": operator,
        "live_trading_arm_reason": reason,
        "shutdown_triggered": False,
        "shutdown_reason": "",
    }
    runtime = await db.update_runtime_state(runtime_updates)
    runtime = runtime if isinstance(runtime, dict) else runtime_updates
    await record_operator_event(
        db,
        "live_safety",
        "live_trading_armed",
        f"Live trading armed for {duration_minutes} minute(s).",
        severity="warning",
        details={
            "armed_until": runtime.get("live_trading_armed_until"),
            "armed_by": operator,
            "reason": reason,
        },
    )
    return runtime


async def disarm_live_trading(
    db,
    *,
    operator: str = "local_operator",
    reason: str = "manual disarm",
) -> Dict[str, Any]:
    """Clear runtime live arming."""
    runtime_updates = {
        "live_trading_armed": False,
        "live_trading_armed_until": "",
        "live_trading_armed_by": operator,
        "live_trading_arm_reason": reason,
    }
    runtime = await db.update_runtime_state(runtime_updates)
    runtime = runtime if isinstance(runtime, dict) else runtime_updates
    await record_operator_event(
        db,
        "live_safety",
        "live_trading_disarmed",
        "Live trading disarmed.",
        details={"armed_by": operator, "reason": reason},
    )
    return runtime
