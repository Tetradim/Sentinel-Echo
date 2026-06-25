"""Readiness evidence recording and paper monitoring snapshot helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from live_readiness import required_readiness_gate_definitions
from operator_audit import record_operator_event

ALLOWED_GATE_STATUSES = {"passed", "failed", "blocked", "pending"}
MANUAL_PASS_GATES = {"controlled_operator_access_review", "operator_signoff"}


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return None


def bool_value(value: Any, *, default: bool = False) -> bool:
    parsed = optional_bool(value)
    if parsed is None:
        return default
    return parsed


def normalize_gate_status(status: Any) -> str:
    normalized = clean_text(status).lower().replace(" ", "_")
    if normalized not in ALLOWED_GATE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Readiness gate status must be one of: {', '.join(sorted(ALLOWED_GATE_STATUSES))}.",
        )
    return normalized


def readiness_gate_definition(gate_key: str) -> dict[str, str]:
    definitions = required_readiness_gate_definitions()
    normalized_gate_key = clean_text(gate_key)
    gate = definitions.get(normalized_gate_key)
    if not gate:
        raise HTTPException(status_code=404, detail=f"Unknown readiness gate: {gate_key}")
    return gate


def current_market_session() -> str:
    return datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()


def _request_value(request: Any, key: str, default: Any = None) -> Any:
    if isinstance(request, dict):
        return request.get(key, default)
    return getattr(request, key, default)


def validate_gate_recording(gate_key: str, status: str, evidence_source: str) -> None:
    source = clean_text(evidence_source).lower() or "manual"
    if status == "passed" and source == "manual" and gate_key not in MANUAL_PASS_GATES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Readiness gate '{gate_key}' cannot be manually marked passed; "
                "use its drill or monitoring endpoint."
            ),
        )


async def record_readiness_gate_evidence(
    database: Any,
    gate_key: str,
    request: Any,
    *,
    default_summary: str = "",
    evidence_source: str = "manual",
) -> dict[str, Any]:
    normalized_gate_key = clean_text(gate_key)
    gate = readiness_gate_definition(normalized_gate_key)
    status = normalize_gate_status(_request_value(request, "status", "passed"))
    validate_gate_recording(normalized_gate_key, status, evidence_source)
    summary = clean_text(_request_value(request, "summary")) or default_summary or f"{gate['label']}: {status}"
    operator = clean_text(_request_value(request, "operator")) or "local_operator"
    evidence = dict_or_empty(_request_value(request, "evidence"))
    event = await record_operator_event(
        database,
        "readiness_gate",
        "evidence_recorded",
        summary,
        severity="info" if status == "passed" else "warning",
        details={
            "gate_key": normalized_gate_key,
            "status": status,
            "summary": summary,
            "operator": operator,
            "evidence_source": clean_text(evidence_source).lower() or "manual",
            "evidence": evidence,
        },
    )
    return {
        "gate_key": normalized_gate_key,
        "label": gate["label"],
        "status": status,
        "summary": summary,
        "updated_at": event.get("timestamp", ""),
        "event_id": event["id"],
    }


def readiness_gate_event_state(event: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if clean_text(event.get("category")) != "readiness_gate" or clean_text(event.get("action")) != "evidence_recorded":
        return None
    details = dict_or_empty(event.get("details"))
    gate_key = clean_text(details.get("gate_key"))
    if gate_key not in required_readiness_gate_definitions():
        return None
    return gate_key, {
        "status": clean_text(details.get("status")).lower() or "missing",
        "updated_at": clean_text(event.get("timestamp")),
        "summary": clean_text(details.get("summary") or event.get("summary")),
        "operator": clean_text(details.get("operator")),
        "evidence_source": clean_text(details.get("evidence_source")),
        "evidence": dict_or_empty(details.get("evidence")),
    }


async def readiness_gate_states_from_events(database: Any, limit: int = 500) -> dict[str, dict[str, Any]]:
    if not hasattr(database, "get_operator_events"):
        return {}
    events = await database.get_operator_events(limit)
    events = events if isinstance(events, list) else []
    states: dict[str, dict[str, Any]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        state = readiness_gate_event_state(event)
        if not state:
            continue
        gate_key, gate_state = state
        states.setdefault(gate_key, gate_state)
    return states


def paper_session_snapshot_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if clean_text(event.get("category")) != "readiness_monitor" or clean_text(event.get("action")) != "paper_session_snapshot":
        return None
    details = dict_or_empty(event.get("details"))
    market_session = clean_text(details.get("market_session"))
    if not market_session:
        return None
    return {
        "timestamp": clean_text(event.get("timestamp")),
        "market_session": market_session,
        "market_is_open": optional_bool(details.get("market_is_open")),
        "broker_connected": bool_value(details.get("broker_connected")),
        "discord_connected": bool_value(details.get("discord_connected")),
        "auto_trading_enabled": bool_value(details.get("auto_trading_enabled")),
        "simulation_mode": bool_value(details.get("simulation_mode")),
        "active_broker": clean_text(details.get("active_broker")),
        "broker_checked_at": clean_text(details.get("broker_checked_at")),
        "broker_check_error": clean_text(details.get("broker_check_error")),
        "note": clean_text(details.get("note")),
    }


def snapshot_is_healthy(snapshot: dict[str, Any]) -> bool:
    return (
        bool_value(snapshot.get("broker_connected"))
        and bool_value(snapshot.get("discord_connected"))
        and bool_value(snapshot.get("auto_trading_enabled"))
        and not bool_value(snapshot.get("simulation_mode"), default=True)
    )


def snapshot_counts_for_multi_session(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    sessions = sorted({snapshot["market_session"] for snapshot in snapshots if snapshot_is_healthy(snapshot)})
    return {"session_count": len(sessions), "sessions": sessions}


async def paper_session_snapshots(database: Any, limit: int = 500) -> list[dict[str, Any]]:
    if not hasattr(database, "get_operator_events"):
        return []
    events = await database.get_operator_events(limit)
    events = events if isinstance(events, list) else []
    snapshots: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        snapshot = paper_session_snapshot_from_event(event)
        if snapshot:
            snapshots.append(snapshot)
    return snapshots


def transition_snapshot(
    previous_snapshots: list[dict[str, Any]],
    current_snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    current_open = optional_bool(current_snapshot.get("market_is_open"))
    if current_open is None or not snapshot_is_healthy(current_snapshot):
        return None
    for snapshot in previous_snapshots:
        if not snapshot_is_healthy(snapshot):
            continue
        previous_open = optional_bool(snapshot.get("market_is_open"))
        if previous_open is None or previous_open == current_open:
            continue
        return snapshot
    return None
