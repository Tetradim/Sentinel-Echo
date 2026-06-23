"""Live trading readiness checks shared by diagnostics, arming, and execution."""
from __future__ import annotations

import os
import math
import json
from typing import Any, Dict, Iterable, List

from broker_capabilities import (
    broker_config_has_saved_value,
    get_broker_capabilities,
    is_broker_configured,
    missing_broker_config_fields,
    normalize_broker_id,
)
from readiness_status import optional_status_flag, status_flag
from settings_flags import coerce_bool
from source_config import summarize_source_policy


LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _issue(code: str, summary: str) -> Dict[str, str]:
    return {"code": code, "summary": summary}


def _env_value(env: Dict[str, str] | None, key: str, default: str = "") -> str:
    source = env if env is not None else os.environ
    return str(source.get(key, default) or "").strip()


def _authless_desktop_mode(env: Dict[str, str] | None) -> bool:
    return (
        not _env_value(env, "API_KEY")
        and _env_value(env, "USE_SQLITE", "false").lower() == "true"
        and _env_value(env, "HOST", "127.0.0.1").lower() in LOCAL_BIND_HOSTS
    )


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _configured_discord_channel_count(
    settings: Dict[str, Any],
    status: Dict[str, Any],
    env: Dict[str, str] | None,
) -> int:
    settings_channels = _channel_id_values(settings.get("discord_channel_ids"))
    explicit_env_channels = _env_value(env, "DISCORD_CHANNEL_IDS")
    env_channels = _channel_id_values(explicit_env_channels)
    status_count = max(
        _nonnegative_int(status.get("discord_channel_count")),
        _nonnegative_int(status.get("channel_count")),
    )
    configured_channels = [
        str(channel_id).strip()
        for channel_id in [*settings_channels, *env_channels]
        if str(channel_id).strip()
    ]
    return max(len(set(configured_channels)), status_count)


def _discord_configured(settings: Dict[str, Any], status: Dict[str, Any], env: Dict[str, str] | None) -> bool:
    token_configured = (
        bool(str(settings.get("discord_token") or "").strip())
        or bool(_env_value(env, "DISCORD_BOT_TOKEN"))
        or status_flag(status, "discord_token_configured")
    )
    return token_configured and _configured_discord_channel_count(settings, status, env) > 0


def _channel_id_values(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, str):
        return value.split(",")
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return []


def _positive_float(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed) and parsed > 0


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _codes(issues: Iterable[Dict[str, str]]) -> set[str]:
    return {issue["code"] for issue in issues}


def _status_or_runtime(
    status: Dict[str, Any],
    runtime_state: Dict[str, Any],
    key: str,
    default: Any = "",
) -> Any:
    value = status.get(key)
    if value is None or value == "":
        return runtime_state.get(key, default)
    return value


def evaluate_live_readiness(
    settings: Dict[str, Any] | None,
    runtime_state: Dict[str, Any] | None = None,
    *,
    status: Dict[str, Any] | None = None,
    env: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Return live-trading readiness with machine-readable blockers."""
    settings = _dict_or_empty(settings)
    runtime_state = _dict_or_empty(runtime_state)
    status = _dict_or_empty(status)
    blocking: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    active_broker = normalize_broker_id(settings.get("active_broker"), default="ibkr")
    broker_configs = _dict_or_empty(settings.get("broker_configs"))
    active_broker_config = broker_configs.get(active_broker)
    broker_configured = is_broker_configured(broker_configs, active_broker)
    missing_broker_fields = []
    if not broker_configured and broker_config_has_saved_value(active_broker_config):
        missing_broker_fields = list(missing_broker_config_fields(active_broker_config, active_broker))
    capabilities = get_broker_capabilities(active_broker)
    source_policy = summarize_source_policy(settings.get("source_overrides"))
    auto_live_sources = int(source_policy.get("auto_live_sources", 0))
    source_config_valid = bool(source_policy.get("valid", False))
    source_error = str(source_policy.get("error") or "")
    auto_trading_enabled = coerce_bool(settings.get("auto_trading_enabled"), default=False)
    simulation_mode = coerce_bool(settings.get("simulation_mode"), default=True)
    take_profit_enabled = coerce_bool(settings.get("take_profit_enabled"), default=False)
    stop_loss_enabled = coerce_bool(settings.get("stop_loss_enabled"), default=False)
    trailing_stop_enabled = coerce_bool(settings.get("trailing_stop_enabled"), default=False)
    bracket_order_enabled = coerce_bool(settings.get("bracket_order_enabled"), default=False)
    oco_exits_configured = take_profit_enabled and stop_loss_enabled
    shutdown_triggered = coerce_bool(runtime_state.get("shutdown_triggered"), default=False)
    live_trading_armed = coerce_bool(runtime_state.get("live_trading_armed"), default=False)
    reconciliation_unresolved_count = _nonnegative_int(status.get("reconciliation_unresolved_count"))
    reconciliation_unresolved_reasons = _list_of_strings(status.get("reconciliation_unresolved_reasons"))
    alert_chain_attention_count = _nonnegative_int(status.get("alert_chain_attention_count"))
    alert_chain_attention_reasons = _list_of_strings(status.get("alert_chain_attention_reasons"))
    position_oco_unprotected_count = _nonnegative_int(status.get("position_oco_unprotected_count"))
    position_oco_unprotected_ids = _list_of_strings(status.get("position_oco_unprotected_ids"))
    position_oco_metadata_only_count = _nonnegative_int(status.get("position_oco_metadata_only_count"))
    position_oco_metadata_only_ids = _list_of_strings(status.get("position_oco_metadata_only_ids"))
    replay_acceptance_status = str(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_status", "not_provided")
        or "not_provided"
    ).strip().lower()
    replay_acceptance_expected_count = _nonnegative_int(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_expected_count")
    )
    replay_acceptance_passed_count = _nonnegative_int(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_passed_count")
    )
    replay_acceptance_failed_count = _nonnegative_int(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_failed_count")
    )
    replay_acceptance_failed_event_count = _nonnegative_int(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_failed_event_count")
    )
    replay_acceptance_failed_event_ids = _list_of_strings(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_failed_event_ids")
    )
    replay_acceptance_missing_event_count = _nonnegative_int(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_missing_event_count")
    )
    replay_acceptance_missing_event_ids = _list_of_strings(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_missing_event_ids")
    )
    replay_acceptance_updated_at = str(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_updated_at")
        or ""
    ).strip()
    replay_acceptance_replay_url = str(
        _status_or_runtime(status, runtime_state, "simulation_replay_acceptance_replay_url")
        or ""
    ).strip()

    if not _env_value(env, "API_KEY") and not _authless_desktop_mode(env):
        blocking.append(_issue("api_key_missing", "API_KEY is required before exposing live trading controls."))
    if not _env_value(env, "CREDENTIAL_KEY"):
        blocking.append(_issue("credential_key_missing", "CREDENTIAL_KEY is required so broker secrets are encrypted."))
    if simulation_mode:
        blocking.append(_issue("simulation_mode_enabled", "Simulation mode must be disabled before live trading."))
    if not auto_trading_enabled:
        blocking.append(_issue("auto_trading_disabled", "Auto trading must be enabled before live arming."))
    max_position_size_valid = _positive_float(settings.get("max_position_size"))
    if not max_position_size_valid:
        blocking.append(_issue("max_position_size_invalid", "Max position size must be greater than zero."))
    if not broker_configured:
        if missing_broker_fields:
            fields = ", ".join(missing_broker_fields)
            blocking.append(
                _issue(
                    "active_broker_not_configured",
                    f"Active broker config is missing required fields: {fields}.",
                )
            )
        else:
            blocking.append(_issue("active_broker_not_configured", "Active broker has no saved configuration."))
    if not capabilities.get("supports_live_trading"):
        blocking.append(_issue("broker_live_unsupported", "Active broker is not enabled for automated live trading."))
    if not capabilities.get("supports_options"):
        blocking.append(_issue("broker_options_unsupported", "Active broker does not support options trading."))
    if not capabilities.get("supports_order_status"):
        blocking.append(_issue("broker_order_status_unsupported", "Active broker lacks fill status polling."))
    if not capabilities.get("supports_cancel_order"):
        blocking.append(_issue("broker_cancel_unsupported", "Active broker lacks cancellation support required for OCO exits."))
    broker_connected = optional_status_flag(status, "broker_connected")
    if broker_connected is False:
        blocking.append(_issue("broker_not_connected", "Broker connection is not healthy."))
    discord_configured = _discord_configured(settings, status, env)
    discord_connected = status_flag(status, "discord_connected") and discord_configured
    chrome_bridge_healthy = status_flag(status, "chrome_bridge_healthy")
    if not discord_connected and not chrome_bridge_healthy:
        blocking.append(
            _issue(
                "no_live_ingestion",
                "No live alert ingestion path is healthy; Discord bot or Chrome bridge must be connected.",
            )
        )
    if not source_config_valid:
        blocking.append(_issue("source_policy_invalid", f"Source policy is invalid: {source_error}"))
    elif auto_live_sources <= 0:
        blocking.append(_issue("no_live_source", "No enabled source can submit live orders automatically."))
    if not oco_exits_configured:
        blocking.append(
            _issue(
                "position_oco_exits_missing",
                "Take-profit and stop-loss guards must both be enabled before live trading.",
            )
        )
    if position_oco_unprotected_count > 0:
        position_oco_summary = (
            "Open live positions have metadata-only OCO; broker child-order IDs are required."
            if position_oco_metadata_only_count > 0 or position_oco_metadata_only_ids
            else "Open live positions are missing position-level OCO exit protection."
        )
        blocking.append(
            _issue(
                "position_oco_unprotected",
                position_oco_summary,
            )
        )
    if shutdown_triggered:
        blocking.append(_issue("runtime_shutdown_active", "Runtime shutdown is active."))
    if reconciliation_unresolved_count > 0:
        blocking.append(
            _issue(
                "reconciliation_unresolved",
                "Broker/order reconciliation has unresolved real-money attention items.",
            )
        )
    if alert_chain_attention_count > 0:
        blocking.append(
            _issue(
                "alert_chain_attention",
                "Alert chain report has nondeterministic attention items.",
            )
        )
    if (
        replay_acceptance_status == "failed"
        or replay_acceptance_failed_count > 0
        or replay_acceptance_failed_event_count > 0
        or bool(replay_acceptance_failed_event_ids)
        or replay_acceptance_missing_event_count > 0
        or bool(replay_acceptance_missing_event_ids)
    ):
        blocking.append(
            _issue(
                "simulation_replay_acceptance_failed",
                "Simulation replay acceptance has failed expected alert outcomes.",
            )
        )
    elif (
        replay_acceptance_status != "passed"
        or replay_acceptance_expected_count <= 0
        or replay_acceptance_passed_count < replay_acceptance_expected_count
        or not replay_acceptance_updated_at
        or not replay_acceptance_replay_url
    ):
        blocking.append(
            _issue(
                "simulation_replay_acceptance_missing",
                "A passing deterministic Simulation Engine replay acceptance proof is required.",
            )
        )

    checks = {
        "api_auth": {"configured": bool(_env_value(env, "API_KEY")), "authless_desktop_mode": _authless_desktop_mode(env)},
        "credential_key": {"configured": bool(_env_value(env, "CREDENTIAL_KEY"))},
        "broker": {
            "active_broker": active_broker,
            "configured": broker_configured,
            "missing_required_fields": missing_broker_fields,
            "connected": broker_connected if broker_connected is not None else status.get("broker_connected"),
            "capabilities": capabilities,
        },
        "source_policy": source_policy,
        "signal_ingestion": {
            "discord_connected": discord_connected,
            "discord_configured": discord_configured,
            "discord_channel_count": _configured_discord_channel_count(settings, status, env),
            "chrome_bridge_healthy": chrome_bridge_healthy,
        },
        "trading": {
            "auto_trading_enabled": auto_trading_enabled,
            "simulation_mode": simulation_mode,
            "max_position_size": settings.get("max_position_size"),
            "max_position_size_valid": max_position_size_valid,
        },
        "exit_automation": {
            "take_profit_enabled": take_profit_enabled,
            "stop_loss_enabled": stop_loss_enabled,
            "trailing_stop_enabled": trailing_stop_enabled,
            "bracket_order_enabled": bracket_order_enabled,
            "oco_exits_configured": oco_exits_configured,
            "broker_order_status_supported": bool(capabilities.get("supports_order_status")),
            "broker_cancel_supported": bool(capabilities.get("supports_cancel_order")),
            "unprotected_open_position_count": position_oco_unprotected_count,
            "unprotected_open_position_ids": position_oco_unprotected_ids,
            "metadata_only_open_position_count": position_oco_metadata_only_count,
            "metadata_only_open_position_ids": position_oco_metadata_only_ids,
        },
        "runtime": {
            "shutdown_triggered": shutdown_triggered,
            "live_trading_armed": live_trading_armed,
            "live_trading_armed_until": runtime_state.get("live_trading_armed_until", ""),
        },
        "reconciliation": {
            "unresolved_count": reconciliation_unresolved_count,
            "unresolved_reasons": reconciliation_unresolved_reasons,
        },
        "alert_chains": {
            "attention_count": alert_chain_attention_count,
            "attention_reasons": alert_chain_attention_reasons,
        },
        "simulation_replay": {
            "proof_required": True,
            "acceptance_status": replay_acceptance_status,
            "expected_count": replay_acceptance_expected_count,
            "passed_count": replay_acceptance_passed_count,
            "failed_count": replay_acceptance_failed_count,
            "failed_event_count": replay_acceptance_failed_event_count,
            "failed_event_ids": replay_acceptance_failed_event_ids,
            "missing_event_count": replay_acceptance_missing_event_count,
            "missing_event_ids": replay_acceptance_missing_event_ids,
            "updated_at": replay_acceptance_updated_at,
            "replay_url": replay_acceptance_replay_url,
        },
    }

    return {
        "ready_for_live": not blocking,
        "blocking_issues": blocking,
        "blocking_codes": sorted(_codes(blocking)),
        "warnings": warnings,
        "checks": checks,
    }


def _list_of_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = []
        value = decoded
    if not isinstance(value, (list, tuple, set)):
        return []
    result = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result
