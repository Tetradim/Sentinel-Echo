from __future__ import annotations

from typing import Any, List


def build_discord_alert_text(message: Any) -> str:
    """Return parseable text from Discord message content and embeds."""
    parts: List[str] = []
    _append(parts, _get(message, "content"))

    for embed in _get(message, "embeds", []) or []:
        author = _get(embed, "author")
        footer = _get(embed, "footer")
        _append(parts, _get(author, "name"))
        _append(parts, _get(embed, "title"))
        _append(parts, _get(embed, "description"))

        for field in _get(embed, "fields", []) or []:
            _append(parts, _get(field, "name"))
            _append(parts, _get(field, "value"))

        _append(parts, _get(footer, "text"))

    return "\n".join(parts)


def _append(parts: List[str], value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        parts.append(text)


def _get(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)
