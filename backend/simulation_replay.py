from __future__ import annotations

import os
from typing import Any

from source_config import resolve_source_config, source_skip_reason
from utils import parse_alert


DEFAULT_REPLAY_URL = "http://127.0.0.1:9200/api/consolidation/replay/events"


class SimulationReplayError(RuntimeError):
    pass


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
    settings = settings or {}
    events = replay.get("events") or []
    results = []
    parsed_count = 0
    would_request_trade_count = 0
    drift_alert_count = 0

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

        would_insert_alert = bool(parsed and not skip_reason)
        would_request_trade = bool(
            would_insert_alert
            and settings.get("auto_trading_enabled", False)
            and not settings.get("shutdown_triggered", False)
            and not source_config.get("require_manual_confirm")
        )
        if would_request_trade:
            would_request_trade_count += 1

        results.append(
            {
                "engine_event_id": event.get("event_id"),
                "timestamp": event.get("timestamp"),
                "channel_id": event.get("channel_id"),
                "raw_text": raw_text,
                "parsed": parsed,
                "source_config": source_config,
                "skip_reason": skip_reason,
                "would_insert_alert": would_insert_alert,
                "would_request_trade": would_request_trade,
                "market_context": {
                    "snapshot": market_snapshot,
                    "price_drift": price_drift or None,
                },
            }
        )

    return {
        "contract_version": "consolidation.simulation_replay_preview.v1",
        "engine_contract_version": replay.get("contract_version"),
        "execution_mode": "preview_only_no_trades",
        "event_count": len(events),
        "parsed_count": parsed_count,
        "would_request_trade_count": would_request_trade_count,
        "drift_alert_count": drift_alert_count,
        "results": results,
    }
