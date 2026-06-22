from __future__ import annotations

import os
from typing import Any

from risk import calculate_position_size
from settings_flags import coerce_bool
from source_config import resolve_source_config, source_skip_reason
from source_config import apply_source_quantity_limits
from utils import parse_alert


DEFAULT_REPLAY_URL = "http://127.0.0.1:9200/api/consolidation/replay/events"


class SimulationReplayError(RuntimeError):
    pass


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_replay_url(value: str | None = None) -> str:
    configured = (value or os.environ.get("SIMULATION_ENGINE_REPLAY_URL") or DEFAULT_REPLAY_URL).strip()
    configured = configured.rstrip("/")
    if not configured:
        return DEFAULT_REPLAY_URL
    if configured.endswith("/api/consolidation/replay/events"):
        return configured
    if "/api/" in configured:
        return configured
    return f"{configured}/api/consolidation/replay/events"


async def fetch_engine_replay(
    *,
    replay_url: str | None = None,
    channel_id: str | None = None,
    since: str | None = None,
    limit: int = 1000,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    import aiohttp

    url = normalize_replay_url(replay_url)
    params = {"limit": str(limit)}
    if channel_id:
        params["channel_id"] = str(channel_id)
    if since:
        params["since"] = str(since)

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            if response.status < 200 or response.status >= 300:
                text = await response.text()
                raise SimulationReplayError(f"Simulation Engine replay returned HTTP {response.status}: {text[:240]}")
            payload = await response.json()

    if payload.get("contract_version") != "simulation.consolidation.replay.v1":
        raise SimulationReplayError("Simulation Engine replay contract version is unsupported")
    return payload


def build_replay_preview(replay: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = _dict_or_empty(settings)
    events = replay.get("events") or []
    expected_results = _dict_or_empty(replay.get("expected_results") or replay.get("expectations"))
    results = []
    parsed_count = 0
    would_request_trade_count = 0
    drift_alert_count = 0
    acceptance_expected_count = 0
    acceptance_passed_count = 0
    acceptance_failed_count = 0

    for event in events:
        payload = event.get("payload") or {}
        message = payload.get("message") or {}
        engine_alert = payload.get("alert") or {}
        market_snapshot = payload.get("market_snapshot")
        price_drift = payload.get("price_drift") or {}
        raw_text = str(engine_alert.get("raw_text") or message.get("content") or "").strip()
        parsed = parse_alert(raw_text) if raw_text else None
        if parsed:
            parsed_count += 1

        source_config = resolve_source_config(
            settings,
            channel_id=str(event.get("channel_id") or message.get("channel_id") or ""),
            channel_name=str(message.get("channel_name") or ""),
        )
        skip_reason = None
        if not parsed:
            skip_reason = "unparsed"
        else:
            skip_reason = source_skip_reason(parsed, source_config)

        if price_drift.get("price_drift_alert"):
            drift_alert_count += 1

        execution_preview = _build_execution_preview(
            settings,
            parsed,
            source_config,
            skip_reason,
        )
        would_insert_alert = bool(execution_preview["would_insert_alert"])
        would_request_trade = bool(execution_preview["would_request_trade"])
        if would_request_trade:
            would_request_trade_count += 1

        result = {
            "engine_event_id": event.get("event_id"),
            "timestamp": event.get("timestamp"),
            "channel_id": event.get("channel_id"),
            "raw_text": raw_text,
            "parsed": parsed,
            "source_config": source_config,
            "skip_reason": skip_reason,
            "would_insert_alert": would_insert_alert,
            "would_request_trade": would_request_trade,
            "execution_preview": execution_preview,
            "market_context": {
                "snapshot": market_snapshot,
                "price_drift": price_drift or None,
            },
        }
        expected = _expected_for_event(event, payload, expected_results)
        result["acceptance"] = _evaluate_expected_result(result, expected)
        if expected:
            acceptance_expected_count += 1
            if result["acceptance"]["passed"]:
                acceptance_passed_count += 1
            else:
                acceptance_failed_count += 1
        results.append(result)

    acceptance_status = "not_provided"
    if acceptance_expected_count:
        acceptance_status = "failed" if acceptance_failed_count else "passed"

    return {
        "contract_version": "consolidation.simulation_replay_preview.v1",
        "engine_contract_version": replay.get("contract_version"),
        "execution_mode": "preview_only_no_trades",
        "event_count": len(events),
        "parsed_count": parsed_count,
        "would_request_trade_count": would_request_trade_count,
        "drift_alert_count": drift_alert_count,
        "acceptance": {
            "status": acceptance_status,
            "expected_count": acceptance_expected_count,
            "passed_count": acceptance_passed_count,
            "failed_count": acceptance_failed_count,
        },
        "results": results,
    }


def _build_execution_preview(
    settings: dict[str, Any],
    parsed: dict[str, Any] | None,
    source_config: dict[str, Any],
    skip_reason: str | None,
) -> dict[str, Any]:
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
    }


def _expected_for_event(
    event: dict[str, Any],
    payload: dict[str, Any],
    expected_results: dict[str, Any],
) -> dict[str, Any]:
    event_id = str(event.get("event_id") or "")
    expected = event.get("expected") or payload.get("expected") or expected_results.get(event_id)
    return expected if isinstance(expected, dict) else {}


def _evaluate_expected_result(
    result: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    if not expected:
        return {"expected": False, "passed": None, "mismatches": []}

    mismatches: list[dict[str, Any]] = []
    for key in ("would_insert_alert", "would_request_trade", "skip_reason"):
        if key in expected:
            _compare_field(mismatches, key, expected.get(key), result.get(key))

    if "execution_reason" in expected:
        _compare_field(
            mismatches,
            "execution_reason",
            expected.get("execution_reason"),
            _dict_or_empty(result.get("execution_preview")).get("reason"),
        )

    expected_parsed = expected.get("parsed")
    if isinstance(expected_parsed, dict):
        actual_parsed = _dict_or_empty(result.get("parsed"))
        for key, value in expected_parsed.items():
            _compare_field(mismatches, f"parsed.{key}", value, actual_parsed.get(key))

    expected_execution = expected.get("execution_preview")
    if isinstance(expected_execution, dict):
        actual_execution = _dict_or_empty(result.get("execution_preview"))
        for key, value in expected_execution.items():
            _compare_field(mismatches, f"execution_preview.{key}", value, actual_execution.get(key))

    return {
        "expected": True,
        "passed": not mismatches,
        "mismatches": mismatches,
    }


def _compare_field(
    mismatches: list[dict[str, Any]],
    field: str,
    expected: Any,
    actual: Any,
) -> None:
    if actual != expected:
        mismatches.append(
            {
                "field": field,
                "expected": expected,
                "actual": actual,
            }
        )
