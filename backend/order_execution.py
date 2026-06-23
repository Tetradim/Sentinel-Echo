from __future__ import annotations

import hashlib
import inspect
import re
from enum import Enum
from typing import Any, Dict, Optional

from broker_capabilities import missing_broker_config_fields, normalize_broker_id
from models import BrokerConfig, BrokerType
from settings_flags import coerce_bool
from utils.credentials import decrypt_broker_config


class BrokerConfigurationError(ValueError):
    pass


def build_client_order_id(
    alert_id: Any,
    side: str,
    position_id: Any = None,
) -> str:
    """Build a deterministic broker-safe ID for tracking submitted orders."""
    parts = [
        "consolidation",
        _client_order_id_token(side, fallback="order").lower(),
        _client_order_id_token(alert_id, fallback="alert"),
    ]
    position_token = _client_order_id_token(position_id, fallback="")
    if position_token:
        parts.append(position_token)

    client_order_id = "-".join(parts)
    if len(client_order_id) <= 128:
        return client_order_id

    digest = hashlib.sha1(client_order_id.encode("utf-8")).hexdigest()[:12]
    return f"{client_order_id[:115].rstrip('-')}-{digest}"


def _client_order_id_token(value: Any, *, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip())
    token = token.strip("-_")
    return token or fallback


def build_oco_exit_plan(
    settings: Any,
    *,
    alert_id: Any,
    position_id: Any,
    entry_price: Any,
    quantity: Any,
) -> Dict[str, Any]:
    """Build deterministic position-level OCO exit metadata from risk settings."""
    settings_data = settings if isinstance(settings, dict) else {}
    if not (
        coerce_bool(settings_data.get("take_profit_enabled"), default=False)
        and coerce_bool(settings_data.get("stop_loss_enabled"), default=False)
    ):
        return {}

    entry = _positive_float(entry_price)
    contracts = _positive_int(quantity)
    if entry is None or contracts <= 0:
        return {}

    take_profit_pct = _positive_float(settings_data.get("take_profit_percentage")) or 50.0
    stop_loss_pct = _positive_float(settings_data.get("stop_loss_percentage")) or 25.0
    stop_loss_order_type = str(settings_data.get("stop_loss_order_type") or "market").strip().lower()
    if stop_loss_order_type not in {"market", "limit"}:
        stop_loss_order_type = "market"

    trailing_stop_enabled = coerce_bool(settings_data.get("trailing_stop_enabled"), default=False)
    trailing_stop_type = str(settings_data.get("trailing_stop_type") or "percent").strip().lower()
    if trailing_stop_type not in {"percent", "premium"}:
        trailing_stop_type = "percent"

    trailing_percent = None
    trailing_cents = None
    if trailing_stop_enabled:
        if trailing_stop_type == "premium":
            trailing_cents = _positive_float(settings_data.get("trailing_stop_cents")) or 50.0
        else:
            trailing_percent = _positive_float(settings_data.get("trailing_stop_percent")) or 10.0

    oco_group_id = build_client_order_id(alert_id, "oco", position_id)
    return {
        "status": "armed",
        "oco_group_id": oco_group_id,
        "entry_price": entry,
        "quantity": contracts,
        "take_profit": {
            "side": "SELL",
            "order_type": "limit",
            "trigger_price": round(entry * (1 + take_profit_pct / 100), 2),
            "percentage": take_profit_pct,
            "client_order_id": build_client_order_id(alert_id, "take-profit", position_id),
            "oco_group_id": oco_group_id,
        },
        "stop_loss": {
            "side": "SELL",
            "order_type": stop_loss_order_type,
            "trigger_price": round(max(entry * (1 - stop_loss_pct / 100), 0.01), 2),
            "percentage": stop_loss_pct,
            "client_order_id": build_client_order_id(alert_id, "stop-loss", position_id),
            "oco_group_id": oco_group_id,
        },
        "trailing_stop": {
            "enabled": trailing_stop_enabled,
            "type": trailing_stop_type,
            "percent": trailing_percent,
            "cents": trailing_cents,
        },
    }


def _positive_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def materialize_secret_values(value: Any) -> Any:
    """Convert Pydantic/SecretStr broker config values into plain runtime values."""
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return materialize_secret_values(value.model_dump())
    if isinstance(value, dict):
        return {key: materialize_secret_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [materialize_secret_values(item) for item in value]
    return value


def resolve_broker_config(settings: Any, broker_id: Optional[str] = None) -> Dict[str, Any]:
    """Return decrypted, materialized config for the selected broker."""
    settings_data = materialize_secret_values(settings)
    settings_data = settings_data if isinstance(settings_data, dict) else {}
    selected_broker = normalize_broker_id(broker_id or settings_data.get("active_broker"))
    if not selected_broker:
        raise BrokerConfigurationError("No active broker configured")

    broker_configs = settings_data.get("broker_configs") or {}
    broker_configs = broker_configs if isinstance(broker_configs, dict) else {}
    raw_config = broker_configs.get(selected_broker)
    if raw_config is None:
        raise BrokerConfigurationError(f"No broker config for {selected_broker}")

    decrypted = decrypt_broker_config(raw_config)
    config = materialize_secret_values(decrypted)
    if not isinstance(config, dict):
        raise BrokerConfigurationError(f"Broker config for {selected_broker} is malformed")
    config.setdefault("broker_type", selected_broker)
    missing_fields = missing_broker_config_fields(config, selected_broker)
    if missing_fields:
        field_list = ", ".join(missing_fields)
        raise BrokerConfigurationError(
            f"Broker config for {selected_broker} is missing required fields: {field_list}"
        )
    return config


def require_order_status_support(client: Any, *, require: bool) -> None:
    if require and not hasattr(client, "get_order_status"):
        raise BrokerConfigurationError(
            "Live execution requires broker order-status support; use paper mode or a supported broker."
        )


async def close_broker_client(client: Any) -> None:
    """Close a temporary broker client when it exposes a sync or async close hook."""
    close = getattr(client, "close", None)
    if not callable(close):
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def get_configured_broker_client(
    settings: Any,
    broker_id: Optional[str] = None,
    *,
    require_order_status: bool = False,
):
    """Create the legacy broker client with decrypted credentials."""
    from broker_clients import get_broker_client

    config_data = resolve_broker_config(settings, broker_id)
    selected_broker = str(broker_id or config_data.get("broker_type") or "").lower()
    broker_type = BrokerType(selected_broker)
    broker_config_data = dict(config_data)
    broker_config_data.pop("broker_type", None)
    broker_config = BrokerConfig(broker_type=broker_type, **broker_config_data)
    client = get_broker_client(broker_type, broker_config)
    require_order_status_support(client, require=require_order_status)
    return client
