from __future__ import annotations

from typing import Any, Dict, Optional


DEFAULT_SOURCE_CONFIG = {
    "name": "",
    "enabled": True,
    "paper_only": False,
    "parser_format": "default",
    "max_premium": None,
    "risk_multiplier": 1.0,
    "notes": "",
}


def resolve_source_config(
    settings: Dict[str, Any],
    *,
    channel_id: str,
    channel_name: str = "",
) -> Dict[str, Any]:
    """Resolve a per-source config by channel id first, then channel name."""
    overrides = settings.get("source_overrides") or {}
    key = _first_existing_key(overrides, str(channel_id), channel_name)
    config = dict(DEFAULT_SOURCE_CONFIG)
    if key:
        config.update(overrides.get(key) or {})
    if not config.get("name"):
        config["name"] = channel_name or str(channel_id)
    config["key"] = key or str(channel_id)
    config["enabled"] = bool(config.get("enabled", True))
    config["paper_only"] = bool(config.get("paper_only", False))
    config["risk_multiplier"] = _positive_float(config.get("risk_multiplier"), default=1.0)
    config["max_premium"] = _optional_positive_float(config.get("max_premium"))
    return config


def source_skip_reason(parsed_alert: Dict[str, Any], source_config: Dict[str, Any]) -> Optional[str]:
    if not source_config.get("enabled", True):
        return "source disabled"

    max_premium = source_config.get("max_premium")
    if (
        max_premium is not None
        and str(parsed_alert.get("alert_type", "")).lower() in {"buy", "average_down"}
    ):
        entry_price = _optional_positive_float(parsed_alert.get("entry_price"))
        if entry_price is not None and entry_price > max_premium:
            return f"premium {entry_price:.2f} exceeds source max {max_premium:.2f}"

    return None


def _first_existing_key(overrides: Dict[str, Any], *candidates: str) -> Optional[str]:
    normalized = {_norm(key): key for key in overrides.keys()}
    for candidate in candidates:
        key = normalized.get(_norm(candidate))
        if key:
            return key
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


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
