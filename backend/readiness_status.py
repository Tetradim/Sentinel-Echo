from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from settings_flags import coerce_bool


def readiness_ready_for_live(readiness: Any) -> bool:
    if not isinstance(readiness, Mapping):
        return False
    return coerce_bool(readiness.get("ready_for_live"), default=False)


def status_flag(status: Any, key: str, *, default: bool = False) -> bool:
    if not isinstance(status, Mapping):
        return default
    return coerce_bool(status.get(key), default=default)


def optional_status_flag(status: Any, key: str) -> bool | None:
    if not isinstance(status, Mapping) or key not in status or status.get(key) is None:
        return None
    return coerce_bool(status.get(key), default=False)
