"""Broker capability metadata used by readiness checks and operator UI."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


_DEFAULT_CAPABILITIES: Dict[str, Any] = {
    "id": "unknown",
    "name": "Unknown",
    "supports_options": False,
    "supports_order_status": False,
    "supports_cancel_order": False,
    "supports_live_trading": False,
    "supports_paper_trading": False,
    "requires_gateway": False,
    "auth_mode": "unknown",
}


_BROKER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "ibkr": {
        **_DEFAULT_CAPABILITIES,
        "id": "ibkr",
        "name": "Interactive Brokers",
        "supports_options": True,
        "supports_live_trading": True,
        "supports_paper_trading": True,
        "requires_gateway": True,
        "auth_mode": "gateway",
    },
    "alpaca": {
        **_DEFAULT_CAPABILITIES,
        "id": "alpaca",
        "name": "Alpaca",
        "supports_options": True,
        "supports_order_status": True,
        "supports_cancel_order": True,
        "supports_live_trading": True,
        "supports_paper_trading": True,
        "auth_mode": "api_key",
    },
    "tradier": {
        **_DEFAULT_CAPABILITIES,
        "id": "tradier",
        "name": "Tradier",
        "supports_options": True,
        "supports_order_status": True,
        "supports_cancel_order": True,
        "supports_live_trading": True,
        "supports_paper_trading": True,
        "auth_mode": "access_token",
    },
    "tradestation": {
        **_DEFAULT_CAPABILITIES,
        "id": "tradestation",
        "name": "TradeStation",
        "supports_options": True,
        "supports_live_trading": True,
        "supports_paper_trading": True,
        "auth_mode": "oauth",
    },
    "thinkorswim": {
        **_DEFAULT_CAPABILITIES,
        "id": "thinkorswim",
        "name": "Thinkorswim",
        "supports_options": True,
        "supports_live_trading": True,
        "supports_paper_trading": False,
        "auth_mode": "oauth",
    },
    "td_ameritrade": {
        **_DEFAULT_CAPABILITIES,
        "id": "td_ameritrade",
        "name": "TD Ameritrade",
        "supports_options": True,
        "supports_live_trading": True,
        "supports_paper_trading": False,
        "auth_mode": "oauth",
    },
    "webull": {
        **_DEFAULT_CAPABILITIES,
        "id": "webull",
        "name": "Webull",
        "supports_options": True,
        "supports_live_trading": False,
        "supports_paper_trading": False,
        "auth_mode": "interactive",
    },
    "robinhood": {
        **_DEFAULT_CAPABILITIES,
        "id": "robinhood",
        "name": "Robinhood",
        "supports_options": True,
        "supports_live_trading": False,
        "supports_paper_trading": False,
        "auth_mode": "interactive",
    },
    "wealthsimple": {
        **_DEFAULT_CAPABILITIES,
        "id": "wealthsimple",
        "name": "Wealthsimple",
        "supports_options": False,
        "supports_live_trading": False,
        "supports_paper_trading": False,
        "auth_mode": "interactive",
    },
}


def normalize_broker_id(broker_id: Any, default: str = "") -> str:
    """Normalize broker ids from strings or enum-backed settings."""
    value = getattr(broker_id, "value", broker_id)
    return str(value or default).strip().lower()


def _has_config_value(value: Any) -> bool:
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_config_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_config_value(item) for item in value)
    return value is not None


def broker_config_is_usable(config: Any) -> bool:
    """Return true when a broker config has at least one usable configured value."""
    if not isinstance(config, dict):
        return False
    relevant = {
        key: value
        for key, value in config.items()
        if key not in {"broker_type", "configured_fields"}
    }
    return any(_has_config_value(value) for value in relevant.values())


def is_broker_configured(broker_configs: Any, broker_id: Any) -> bool:
    """Return true when the active broker has a non-empty saved configuration."""
    configs = broker_configs if isinstance(broker_configs, dict) else {}
    broker_config = configs.get(normalize_broker_id(broker_id))
    return broker_config_is_usable(broker_config)


def get_broker_capabilities(broker_id: str | None) -> Dict[str, Any]:
    """Return a copy of capability metadata for a broker id."""
    normalized = normalize_broker_id(broker_id)
    capabilities = _BROKER_CAPABILITIES.get(normalized)
    if not capabilities:
        fallback = deepcopy(_DEFAULT_CAPABILITIES)
        fallback["id"] = normalized or "unknown"
        return fallback
    return deepcopy(capabilities)


def all_broker_capabilities() -> Dict[str, Dict[str, Any]]:
    """Return capability metadata for all known brokers."""
    return {broker_id: get_broker_capabilities(broker_id) for broker_id in _BROKER_CAPABILITIES}
