from __future__ import annotations

import hashlib
import inspect
import re
from enum import Enum
from typing import Any, Dict, Optional

from models import BrokerConfig, BrokerType
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
    selected_broker = str(broker_id or settings_data.get("active_broker") or "").lower()
    if not selected_broker:
        raise BrokerConfigurationError("No active broker configured")

    broker_configs = settings_data.get("broker_configs") or {}
    raw_config = broker_configs.get(selected_broker)
    if raw_config is None:
        raise BrokerConfigurationError(f"No broker config for {selected_broker}")

    decrypted = decrypt_broker_config(raw_config)
    config = materialize_secret_values(decrypted)
    config.setdefault("broker_type", selected_broker)
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
