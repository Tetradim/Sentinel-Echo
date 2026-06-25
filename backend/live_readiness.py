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
from utils.credentials import credential_key_status


LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_CONSOLIDATION_ROLE = "paper_shadow"
LIVE_EXECUTION_ROLE = "live_executioner"
SUPPORTED_CONSOLIDATION_ROLES = {
    "portfolio_ops",
    "paper_shadow",
    "replay_audit",
    LIVE_EXECUTION_ROLE,
}
READINESS_GATE_DEFINITIONS = {
    "paper_mode_burn_in": {
        "label": "Paper-mode burn-in",
        "blocking_code": "paper_burn_in_missing",
        "summary": "Paper-mode burn-in evidence is required before live readiness signoff.",
    },
    "partial_fill_broker_behavior": {
        "label": "Partial-fill broker behavior",
        "blocking_code": "partial_fill_drill_missing",
        "summary": "Broker partial-fill behavior must be drilled and recorded before live readiness signoff.",
    },
    "disconnect_reconnect_drill": {
        "label": "Disconnect/reconnect drill",
        "blocking_code": "reconnect_drill_missing",
        "summary": "Broker disconnect/reconnect behavior must be drilled and recorded before live readiness signoff.",
    },
    "market_transition_validation": {
        "label": "Market-transition validation",
        "blocking_code": "market_transition_validation_missing",
        "summary": "Market open/close transition validation is required before live readiness signoff.",
    },
    "multi_session_paper_monitoring": {
        "label": "Multi-session paper monitoring",
        "blocking_code": "multi_session_monitoring_missing",
        "summary": "Paper monitoring must cover at least two real market sessions before live readiness signoff.",
    },
    "live_monitoring_evidence": {
        "label": "Live monitoring evidence",
        "blocking_code": "live_monitoring_evidence_missing",
        "summary": "Operator-visible monitoring evidence is required before live readiness signoff.",
    },
    "controlled_operator_access_review": {
        "label": "Controlled operator access review",
        "blocking_code": "operator_access_review_missing",
        "summary": "Controlled operator access review evidence is required before live readiness signoff.",
    },
    "operator_signoff": {
        "label": "Operator signoff",
        "blocking_code": "operator_signoff_missing",
        "summary": "A recorded operator signoff is required before live readiness signoff.",
    },
}


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


def _normalize_role(value: Any, *, default: str = DEFAULT_CONSOLIDATION_ROLE) -> str:
    role = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return role or default


def _consolidation_role(env: Dict[str, str] | None) -> str:
    return _normalize_role(_env_value(env, "CONSOLIDATION_BOT_ROLE", DEFAULT_CONSOLIDATION_ROLE))


def live_execution_role_enabled(env: Dict[str, str] | None = None) -> bool:
    """Return True only when Consolidation has explicitly been deployed as a live executioner."""
    return _consolidation_role(env) == LIVE_EXECUTION_ROLE


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


def required_readiness_gate_definitions() -> Dict[str, Dict[str, str]]:
    return {key: dict(definition) for key, definition in READINESS_GATE_DEFINITIONS.items()}


def _readiness_gate_source(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _readiness_gate_session_count(evidence: Dict[str, Any]) -> int:
    return max(
        _nonnegative_int(evidence.get("session_count")),
        _nonnegative_int(evidence.get("market_session_count")),
    )


def _optional_bool(value: Any) -> bool | None:
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


def _bool_field(value: Any, *, default: bool = False) -> bool:
    parsed = _optional_bool(value)
    if parsed is None:
        return default
    return parsed


def _nonempty_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _healthy_monitoring_evidence(evidence: Dict[str, Any]) -> bool:
    return (
        _bool_field(evidence.get("broker_connected"))
        and _bool_field(evidence.get("discord_connected"))
        and _bool_field(evidence.get("auto_trading_enabled"))
        and not _bool_field(evidence.get("simulation_mode"), default=True)
    )


def _partial_fill_evidence_passed(evidence: Dict[str, Any]) -> bool:
    broker_update = _dict_or_empty(evidence.get("broker_update"))
    reconciliation = _dict_or_empty(evidence.get("reconciliation"))
    return (
        _nonempty_text(evidence.get("active_broker"))
        and _nonempty_text(evidence.get("trade_id"))
        and _nonempty_text(evidence.get("order_id"))
        and str(broker_update.get("status") or "").strip().lower() == "partial"
        and _nonnegative_int(broker_update.get("filled_qty")) > 0
        and str(reconciliation.get("trade_status") or "").strip().lower() == "partial"
        and str(reconciliation.get("position_status") or "").strip().lower() == "partial"
    )


def _reconnect_evidence_passed(evidence: Dict[str, Any]) -> bool:
    errors = evidence.get("errors")
    return (
        _nonempty_text(evidence.get("active_broker"))
        and _bool_field(evidence.get("before_connected"))
        and _bool_field(evidence.get("after_connected"))
        and (not isinstance(errors, list) or len(errors) == 0)
    )


def _market_transition_evidence_passed(evidence: Dict[str, Any]) -> bool:
    from_open = _optional_bool(evidence.get("from_market_is_open"))
    to_open = _optional_bool(evidence.get("to_market_is_open"))
    if from_open is None or to_open is None or from_open == to_open:
        return False
    return (
        _nonempty_text(evidence.get("from_timestamp"))
        and _nonempty_text(evidence.get("to_timestamp"))
        and _bool_field(evidence.get("from_broker_connected"))
        and _bool_field(evidence.get("to_broker_connected"))
        and _bool_field(evidence.get("from_discord_connected"))
        and _bool_field(evidence.get("to_discord_connected"))
        and _bool_field(evidence.get("from_auto_trading_enabled"))
        and _bool_field(evidence.get("to_auto_trading_enabled"))
        and not _bool_field(evidence.get("from_simulation_mode"), default=True)
        and not _bool_field(evidence.get("to_simulation_mode"), default=True)
    )


def _readiness_gate_passed(gate_key: str, state: Dict[str, Any]) -> bool:
    status = str(state.get("status") or "").strip().lower()
    updated_at = str(state.get("updated_at") or "").strip()
    if status != "passed" or not updated_at:
        return False
    evidence = _dict_or_empty(state.get("evidence"))
    if gate_key == "paper_mode_burn_in":
        return _healthy_monitoring_evidence(evidence) and _nonempty_text(evidence.get("snapshot_event_id"))
    if gate_key == "partial_fill_broker_behavior":
        return _partial_fill_evidence_passed(evidence)
    if gate_key == "disconnect_reconnect_drill":
        return _reconnect_evidence_passed(evidence)
    if gate_key == "market_transition_validation":
        return _market_transition_evidence_passed(evidence)
    if gate_key == "multi_session_paper_monitoring":
        sessions = evidence.get("sessions")
        return _readiness_gate_session_count(evidence) >= 2 and isinstance(sessions, list) and len(sessions) >= 2
    if gate_key == "live_monitoring_evidence":
        return _healthy_monitoring_evidence(evidence) and _nonempty_text(evidence.get("broker_checked_at"))
    return True


def _readiness_gate_checks(raw_gates: Any) -> Dict[str, Any]:
    source = _readiness_gate_source(raw_gates)
    states: Dict[str, Dict[str, Any]] = {}
    missing_gate_keys: list[str] = []
    for gate_key, definition in READINESS_GATE_DEFINITIONS.items():
        raw_state = _dict_or_empty(source.get(gate_key))
        evidence = _dict_or_empty(raw_state.get("evidence"))
        state = {
            "label": definition["label"],
            "status": str(raw_state.get("status") or "missing").strip().lower() or "missing",
            "updated_at": str(raw_state.get("updated_at") or "").strip(),
            "summary": str(raw_state.get("summary") or "").strip(),
            "evidence": evidence,
        }
        if gate_key == "multi_session_paper_monitoring":
            state["session_count"] = _readiness_gate_session_count(evidence)
            state["required_session_count"] = 2
        state["passed"] = _readiness_gate_passed(gate_key, state)
        if not state["passed"]:
            missing_gate_keys.append(gate_key)
        states[gate_key] = state
    return {
        "required": True,
        "definitions": required_readiness_gate_definitions(),
        "states": states,
        "missing_gate_keys": missing_gate_keys,
        "passed_count": len(states) - len(missing_gate_keys),
        "required_count": len(READINESS_GATE_DEFINITIONS),
    }


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
    auto_trading_enabled = coerce_bool(settings.get("auto_trading_enabled"), default=True)
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
    alert_chain_audit_attention_count = _nonnegative_int(status.get("alert_chain_attention_count"))
    alert_chain_audit_attention_reasons = _list_of_strings(status.get("alert_chain_attention_reasons"))
    alert_chain_attention_count = _nonnegative_int(
        status.get("alert_chain_live_blocking_attention_count", status.get("alert_chain_attention_count"))
    )
    alert_chain_attention_reasons = _list_of_strings(
        status.get("alert_chain_live_blocking_attention_reasons", status.get("alert_chain_attention_reasons"))
    )
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
    credential_status = credential_key_status(env)
    active_role = _consolidation_role(env)
    role_valid = active_role in SUPPORTED_CONSOLIDATION_ROLES
    live_execution_allowed = live_execution_role_enabled(env)
    readiness_gates = _readiness_gate_checks(_status_or_runtime(status, runtime_state, "readiness_gates", {}))

    if not _env_value(env, "API_KEY") and not _authless_desktop_mode(env):
        blocking.append(_issue("api_key_missing", "API_KEY is required before exposing live trading controls."))
    if not role_valid:
        blocking.append(
            _issue(
                "consolidation_role_invalid",
                "CONSOLIDATION_BOT_ROLE must be portfolio_ops, paper_shadow, replay_audit, or live_executioner.",
            )
        )
    elif not live_execution_allowed:
        blocking.append(
            _issue(
                "consolidation_role_not_live_executioner",
                "Consolidation is outside the default live path; set CONSOLIDATION_BOT_ROLE=live_executioner only when explicitly reintroduced as an execution bot.",
            )
        )
    if not credential_status["configured"]:
        blocking.append(_issue("credential_key_missing", "CREDENTIAL_KEY is required so broker secrets are encrypted."))
    elif not credential_status["valid"]:
        blocking.append(_issue("credential_key_invalid", "CREDENTIAL_KEY must be a 32-byte hex string."))
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
    if broker_connected is not True:
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
    for gate_key in readiness_gates["missing_gate_keys"]:
        gate = READINESS_GATE_DEFINITIONS[gate_key]
        blocking.append(_issue(gate["blocking_code"], gate["summary"]))

    checks = {
        "role": {
            "active_role": active_role,
            "valid": role_valid,
            "live_execution_allowed": live_execution_allowed,
            "source": "CONSOLIDATION_BOT_ROLE",
            "supported_roles": sorted(SUPPORTED_CONSOLIDATION_ROLES),
        },
        "api_auth": {"configured": bool(_env_value(env, "API_KEY")), "authless_desktop_mode": _authless_desktop_mode(env)},
        "credential_key": credential_status,
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
            "attention_count": alert_chain_audit_attention_count,
            "attention_reasons": alert_chain_audit_attention_reasons,
            "live_blocking_attention_count": alert_chain_attention_count,
            "live_blocking_attention_reasons": alert_chain_attention_reasons,
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
        "readiness_gates": readiness_gates,
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
