"""Runtime live-trading arming semantics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from operator_audit import record_operator_event


CONFIRMATION_PHRASE = "ARM LIVE TRADING"


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
    runtime_state = runtime_state or {}
    if not bool(runtime_state.get("live_trading_armed", False)):
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
    if duration_minutes < 1 or duration_minutes > 480:
        raise ValueError("duration_minutes must be between 1 and 480.")
    if not readiness.get("ready_for_live", False):
        await record_operator_event(
            db,
            "live_safety",
            "live_trading_arm_blocked",
            "Live trading arm was blocked by readiness checks.",
            severity="warning",
            details={"blocking_issues": readiness.get("blocking_issues", [])},
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
