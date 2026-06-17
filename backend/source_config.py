from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


DEFAULT_SOURCE_CONFIG = {
    "name": "",
    "enabled": True,
    "paper_only": False,
    "parser_format": "default",
    "max_premium": None,
    "risk_multiplier": 1.0,
    "max_contracts": None,
    "require_manual_confirm": False,
    "notes": "",
    "allowed_actions": [],
    "ticker_allowlist": [],
    "ticker_blocklist": [],
}

ALLOWED_ALERT_ACTIONS = {"buy", "sell", "trim", "close", "average_down"}
ACTION_ALIASES = {
    "add": "average_down",
    "avg_down": "average_down",
    "average": "average_down",
    "average-down": "average_down",
    "entry": "buy",
    "open": "buy",
    "bto": "buy",
    "exit": "sell",
    "stc": "sell",
    "partial": "trim",
}


def normalize_source_overrides(
    source_overrides: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_key, raw_config in (source_overrides or {}).items():
        key = str(raw_key or "").strip()
        if not key:
            raise ValueError("source override key cannot be empty")
        normalized[key] = normalize_source_config(raw_config or {})
    return normalized


def normalize_source_config(source_config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(source_config, dict):
        raise ValueError("source override must be an object")

    config = dict(DEFAULT_SOURCE_CONFIG)
    config.update(
        {key: source_config.get(key) for key in DEFAULT_SOURCE_CONFIG if key in source_config}
    )
    config["name"] = str(config.get("name") or "").strip()
    config["enabled"] = bool(config.get("enabled", True))
    config["paper_only"] = bool(config.get("paper_only", False))
    config["require_manual_confirm"] = bool(config.get("require_manual_confirm", False))
    config["parser_format"] = str(config.get("parser_format") or "default").strip() or "default"
    config["max_premium"] = _optional_positive_float_field(
        config.get("max_premium"),
        "max_premium",
    )
    config["risk_multiplier"] = _positive_float_field(
        config.get("risk_multiplier"),
        "risk_multiplier",
        default=1.0,
    )
    config["max_contracts"] = _optional_positive_int_field(
        config.get("max_contracts"),
        "max_contracts",
    )
    config["notes"] = str(config.get("notes") or "").strip()
    config["allowed_actions"] = _normalize_actions(config.get("allowed_actions"))
    config["ticker_allowlist"] = _normalize_tickers(
        config.get("ticker_allowlist"),
        "ticker_allowlist",
    )
    config["ticker_blocklist"] = _normalize_tickers(
        config.get("ticker_blocklist"),
        "ticker_blocklist",
    )
    return config


def resolve_source_config(
    settings: Dict[str, Any],
    *,
    channel_id: str,
    channel_name: str = "",
) -> Dict[str, Any]:
    """Resolve a per-source config by channel id first, then channel name."""
    overrides = settings.get("source_overrides") or {}
    key = _first_existing_key(overrides, str(channel_id), channel_name)
    try:
        config = normalize_source_config(overrides.get(key) or {})
    except ValueError as exc:
        config = normalize_source_config({"enabled": False})
        config["invalid_reason"] = str(exc)
    if not config.get("name"):
        config["name"] = channel_name or str(channel_id)
    config["key"] = key or str(channel_id)
    return config


def source_skip_reason(parsed_alert: Dict[str, Any], source_config: Dict[str, Any]) -> Optional[str]:
    invalid_reason = source_config.get("invalid_reason")
    if invalid_reason:
        return f"invalid source config: {invalid_reason}"

    if not source_config.get("enabled", True):
        return "source disabled"

    alert_type = str(parsed_alert.get("alert_type", "")).strip().lower()
    allowed_actions = source_config.get("allowed_actions") or []
    if allowed_actions and alert_type not in set(allowed_actions):
        return f"action {alert_type or 'unknown'} not allowed for source"

    ticker = _normalize_ticker(parsed_alert.get("ticker"))
    ticker_blocklist = set(source_config.get("ticker_blocklist") or [])
    if ticker and ticker in ticker_blocklist:
        return f"ticker {ticker} blocked for source"

    ticker_allowlist = set(source_config.get("ticker_allowlist") or [])
    if ticker_allowlist and ticker not in ticker_allowlist:
        return f"ticker {ticker or 'unknown'} not allowed for source"

    max_premium = source_config.get("max_premium")
    if (
        max_premium is not None
        and alert_type in {"buy", "average_down"}
    ):
        entry_price = _optional_positive_float(parsed_alert.get("entry_price"))
        if entry_price is not None and entry_price > max_premium:
            return f"premium {entry_price:.2f} exceeds source max {max_premium:.2f}"

    return None


def apply_source_quantity_limits(quantity: int, source_config: Dict[str, Any]) -> int:
    max_contracts = source_config.get("max_contracts")
    if max_contracts is None:
        return max(1, int(quantity))
    return max(1, min(int(quantity), int(max_contracts)))


def _first_existing_key(overrides: Dict[str, Any], *candidates: str) -> Optional[str]:
    normalized = {_norm(key): key for key in overrides.keys()}
    for candidate in candidates:
        key = normalized.get(_norm(candidate))
        if key:
            return key
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_actions(actions: Any) -> list[str]:
    normalized = []
    for action in _coerce_list(actions):
        action_key = str(action or "").strip().lower().replace(" ", "_")
        if not action_key:
            continue
        if action_key == "all":
            return []
        action_key = ACTION_ALIASES.get(action_key, action_key)
        if action_key not in ALLOWED_ALERT_ACTIONS:
            raise ValueError(f"unknown allowed action: {action}")
        if action_key not in normalized:
            normalized.append(action_key)
    return normalized


def _normalize_tickers(tickers: Any, field_name: str) -> list[str]:
    normalized = []
    for ticker in _coerce_list(tickers):
        ticker_key = _normalize_ticker(ticker)
        if ticker_key and not _is_valid_ticker(ticker_key):
            raise ValueError(f"{field_name} contains invalid ticker: {ticker}")
        if ticker_key and ticker_key not in normalized:
            normalized.append(ticker_key)
    return normalized


def _normalize_ticker(ticker: Any) -> str:
    return str(ticker or "").strip().upper().lstrip("$")


def _is_valid_ticker(ticker: str) -> bool:
    return ticker.isalpha() and 1 <= len(ticker) <= 6


def _coerce_list(value: Any) -> Iterable[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",")]
    if isinstance(value, (list, tuple, set)):
        return value
    return [value]


def _optional_positive_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _positive_float(value: Any, *, default: float) -> float:
    parsed = _optional_positive_float(value)
    return parsed if parsed is not None else default


def _optional_positive_float_field(value: Any, field_name: str) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number")
    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return parsed


def _positive_float_field(value: Any, field_name: str, *, default: float) -> float:
    parsed = _optional_positive_float_field(value, field_name)
    return parsed if parsed is not None else default


def _optional_positive_int_field(value: Any, field_name: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer")
    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return parsed
