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


_BROKER_REQUIRED_CONFIG_FIELDS: Dict[str, tuple[str, ...]] = {
    "alpaca": ("api_key", "api_secret"),
    "ibkr": ("gateway_url", "account_id"),
    "tradier": ("access_token", "account_id"),
    "tradestation": ("ts_client_id", "ts_client_secret", "ts_refresh_token"),
    "td_ameritrade": ("client_id", "refresh_token"),
    "thinkorswim": ("tos_consumer_key", "tos_refresh_token", "tos_account_id"),
    "webull": ("username", "password", "device_id", "trade_token"),
    "robinhood": ("username", "password"),
    "wealthsimple": ("ws_email", "ws_password"),
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


def _dict_config(config: Any) -> dict:
    if hasattr(config, "model_dump"):
        config = config.model_dump()
    return config if isinstance(config, dict) else {}


def get_broker_required_config_fields(broker_id: Any) -> tuple[str, ...]:
    """Return the required non-empty config fields for a broker."""
    return _BROKER_REQUIRED_CONFIG_FIELDS.get(normalize_broker_id(broker_id), ())


def missing_broker_config_fields(config: Any, broker_id: Any = None) -> tuple[str, ...]:
    """Return required broker config fields that are missing or blank."""
    config_data = _dict_config(config)
    required_fields = get_broker_required_config_fields(
        broker_id or config_data.get("broker_type")
    )
    return tuple(
        field
        for field in required_fields
        if not _has_config_value(config_data.get(field))
    )


def broker_config_is_usable(config: Any, broker_id: Any = None) -> bool:
    """Return true when a broker config has the broker's required values."""
    config_data = _dict_config(config)
    if not config_data:
        return False
    required_fields = get_broker_required_config_fields(
        broker_id or config_data.get("broker_type")
    )
    if required_fields:
        return not missing_broker_config_fields(config_data, broker_id)

    # Unknown brokers retain the legacy fallback so custom adapters can still be detected.
    relevant = {
        key: value
        for key, value in config_data.items()
        if key not in {"broker_type", "configured_fields"}
    }
    return any(_has_config_value(value) for value in relevant.values())


def is_broker_configured(broker_configs: Any, broker_id: Any) -> bool:
    """Return true when the active broker has a usable saved configuration."""
    configs = broker_configs if isinstance(broker_configs, dict) else {}
    broker_config = configs.get(normalize_broker_id(broker_id))
    return broker_config_is_usable(broker_config, broker_id)


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
