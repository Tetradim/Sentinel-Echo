"""Live trading readiness checks shared by diagnostics, arming, and execution."""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

from broker_capabilities import get_broker_capabilities
from source_config import normalize_source_overrides


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


def _auto_live_source_count(source_overrides: Dict[str, Any]) -> tuple[int, bool, str]:
    try:
        normalized = normalize_source_overrides(source_overrides or {})
    except ValueError as exc:
        return 0, False, str(exc)
    count = sum(
        1
        for config in normalized.values()
        if config.get("enabled", True)
        and not config.get("paper_only")
        and not config.get("require_manual_confirm")
    )
    return count, True, ""


def _configured_discord_channel_count(
    settings: Dict[str, Any],
    status: Dict[str, Any],
    env: Dict[str, str] | None,
) -> int:
    settings_channels = settings.get("discord_channel_ids") or []
    if isinstance(settings_channels, str):
        settings_channels = settings_channels.split(",")
    explicit_env_channels = _env_value(env, "DISCORD_CHANNEL_IDS")
    env_channels = explicit_env_channels.split(",") if explicit_env_channels else []
    status_count = int(status.get("discord_channel_count") or status.get("channel_count") or 0)
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
        or bool(status.get("discord_token_configured", False))
    )
    return token_configured and _configured_discord_channel_count(settings, status, env) > 0


def _positive_float(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return float(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _codes(issues: Iterable[Dict[str, str]]) -> set[str]:
    return {issue["code"] for issue in issues}


def evaluate_live_readiness(
    settings: Dict[str, Any] | None,
    runtime_state: Dict[str, Any] | None = None,
    *,
    status: Dict[str, Any] | None = None,
    env: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Return live-trading readiness with machine-readable blockers."""
    settings = settings or {}
    runtime_state = runtime_state or {}
    status = status or {}
    blocking: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    active_broker = str(settings.get("active_broker") or "ibkr").lower()
    broker_configs = settings.get("broker_configs") or {}
    capabilities = get_broker_capabilities(active_broker)
    auto_live_sources, source_config_valid, source_error = _auto_live_source_count(
        settings.get("source_overrides") or {}
    )

    if not _env_value(env, "API_KEY") and not _authless_desktop_mode(env):
        blocking.append(_issue("api_key_missing", "API_KEY is required before exposing live trading controls."))
    if not _env_value(env, "CREDENTIAL_KEY"):
        blocking.append(_issue("credential_key_missing", "CREDENTIAL_KEY is required so broker secrets are encrypted."))
    if bool(settings.get("simulation_mode", True)):
        blocking.append(_issue("simulation_mode_enabled", "Simulation mode must be disabled before live trading."))
    if not bool(settings.get("auto_trading_enabled", False)):
        blocking.append(_issue("auto_trading_disabled", "Auto trading must be enabled before live arming."))
    max_position_size_valid = _positive_float(settings.get("max_position_size"))
    if not max_position_size_valid:
        blocking.append(_issue("max_position_size_invalid", "Max position size must be greater than zero."))
    if active_broker not in broker_configs:
        blocking.append(_issue("active_broker_not_configured", "Active broker has no saved configuration."))
    if not capabilities.get("supports_live_trading"):
        blocking.append(_issue("broker_live_unsupported", "Active broker is not enabled for automated live trading."))
    if not capabilities.get("supports_options"):
        blocking.append(_issue("broker_options_unsupported", "Active broker does not support options trading."))
    if not capabilities.get("supports_order_status"):
        blocking.append(_issue("broker_order_status_unsupported", "Active broker lacks fill status polling."))
    if status.get("broker_connected") is False:
        blocking.append(_issue("broker_not_connected", "Broker connection is not healthy."))
    discord_configured = _discord_configured(settings, status, env)
    discord_connected = bool(status.get("discord_connected", False)) and discord_configured
    chrome_bridge_healthy = bool(status.get("chrome_bridge_healthy", False))
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
    if bool(runtime_state.get("shutdown_triggered", False)):
        blocking.append(_issue("runtime_shutdown_active", "Runtime shutdown is active."))

    checks = {
        "api_auth": {"configured": bool(_env_value(env, "API_KEY")), "authless_desktop_mode": _authless_desktop_mode(env)},
        "credential_key": {"configured": bool(_env_value(env, "CREDENTIAL_KEY"))},
        "broker": {
            "active_broker": active_broker,
            "configured": active_broker in broker_configs,
            "connected": status.get("broker_connected"),
            "capabilities": capabilities,
        },
        "source_policy": {
            "valid": source_config_valid,
            "auto_live_sources": auto_live_sources,
            "error": source_error,
        },
        "signal_ingestion": {
            "discord_connected": discord_connected,
            "discord_configured": discord_configured,
            "discord_channel_count": _configured_discord_channel_count(settings, status, env),
            "chrome_bridge_healthy": chrome_bridge_healthy,
        },
        "trading": {
            "auto_trading_enabled": bool(settings.get("auto_trading_enabled", False)),
            "simulation_mode": bool(settings.get("simulation_mode", True)),
            "max_position_size": settings.get("max_position_size"),
            "max_position_size_valid": max_position_size_valid,
        },
        "runtime": {
            "shutdown_triggered": bool(runtime_state.get("shutdown_triggered", False)),
            "live_trading_armed": bool(runtime_state.get("live_trading_armed", False)),
            "live_trading_armed_until": runtime_state.get("live_trading_armed_until", ""),
        },
    }

    return {
        "ready_for_live": not blocking,
        "blocking_issues": blocking,
        "blocking_codes": sorted(_codes(blocking)),
        "warnings": warnings,
        "checks": checks,
    }
