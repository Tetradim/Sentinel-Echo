"""Read Discord runtime settings from an existing OpenClaw install.

This module intentionally keeps the token in memory only. Public summaries must
report presence/counts without returning the secret itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Mapping

from settings_flags import coerce_bool


_DISABLED_VALUES = {"0", "false", "no", "off"}


@dataclass
class DiscordRuntimeConfig:
    token: str = ""
    channel_ids: list[str] = field(default_factory=list)
    guild_ids: list[str] = field(default_factory=list)
    source: str = "empty"
    openclaw_home: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def token_configured(self) -> bool:
        return bool(self.token)

    def public_summary(self) -> dict:
        return {
            "source": self.source,
            "token_configured": self.token_configured,
            "channel_count": len(self.channel_ids),
            "guild_count": len(self.guild_ids),
            "openclaw_home": self.openclaw_home,
            "warnings": list(self.warnings),
        }


def load_openclaw_discord_config(openclaw_home: str | Path | None = None) -> DiscordRuntimeConfig:
    home = Path(openclaw_home or Path.home() / ".openclaw").expanduser()
    warnings: list[str] = []
    env_path = home / ".env"
    config_path = home / "openclaw.json"

    env_values = _read_env_file(env_path)
    if not env_path.exists():
        warnings.append(f"OpenClaw env file not found: {env_path}")

    token = env_values.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        warnings.append("OpenClaw DISCORD_BOT_TOKEN is not configured.")

    guild_ids: list[str] = []
    channel_ids: list[str] = []
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            guild_ids, channel_ids = _extract_discord_ids(data)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"OpenClaw config could not be read: {exc}")
    else:
        warnings.append(f"OpenClaw config file not found: {config_path}")

    if not channel_ids:
        warnings.append("No enabled OpenClaw Discord channel IDs were found.")

    return DiscordRuntimeConfig(
        token=token,
        channel_ids=channel_ids,
        guild_ids=guild_ids,
        source="openclaw",
        openclaw_home=str(home),
        warnings=warnings,
    )


def resolve_discord_runtime_config(
    env: Mapping[str, str] | None = None,
    *,
    openclaw_home: str | Path | None = None,
) -> DiscordRuntimeConfig:
    runtime_env = env if env is not None else os.environ
    explicit_token = str(runtime_env.get("DISCORD_BOT_TOKEN", "")).strip()
    explicit_channels = _normalize_channel_ids(
        str(runtime_env.get("DISCORD_CHANNEL_IDS", ""))
    )
    explicit_guild = str(runtime_env.get("DISCORD_GUILD_ID", "")).strip()

    if explicit_token and explicit_channels:
        return DiscordRuntimeConfig(
            token=explicit_token,
            channel_ids=explicit_channels,
            guild_ids=[explicit_guild] if explicit_guild else [],
            source="environment",
        )

    use_openclaw = str(
        runtime_env.get("SENTINEL_ECHO_USE_OPENCLAW_DISCORD", "true")
    ).strip().lower()
    if use_openclaw in _DISABLED_VALUES:
        return DiscordRuntimeConfig(
            token=explicit_token,
            channel_ids=explicit_channels,
            guild_ids=[explicit_guild] if explicit_guild else [],
            source="environment",
            warnings=["OpenClaw Discord import is disabled."],
        )

    home = openclaw_home or runtime_env.get("OPENCLAW_HOME") or Path.home() / ".openclaw"
    openclaw = load_openclaw_discord_config(home)
    token = explicit_token or openclaw.token
    channel_ids = explicit_channels or openclaw.channel_ids
    guild_ids = [explicit_guild] if explicit_guild else openclaw.guild_ids

    if explicit_token or explicit_channels or explicit_guild:
        source = "environment+openclaw"
    else:
        source = "openclaw"

    return DiscordRuntimeConfig(
        token=token,
        channel_ids=channel_ids,
        guild_ids=guild_ids,
        source=source,
        openclaw_home=openclaw.openclaw_home,
        warnings=openclaw.warnings,
    )


def resolve_saved_or_runtime_discord_config(
    settings: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
    *,
    openclaw_home: str | Path | None = None,
) -> DiscordRuntimeConfig:
    settings = settings or {}
    settings_token = str(settings.get("discord_token") or "").strip()
    settings_channels = _normalize_channel_ids(settings.get("discord_channel_ids") or [])

    if settings_token and settings_channels:
        return DiscordRuntimeConfig(
            token=settings_token,
            channel_ids=settings_channels,
            source="settings",
        )

    fallback = resolve_discord_runtime_config(env, openclaw_home=openclaw_home)
    return DiscordRuntimeConfig(
        token=settings_token or fallback.token,
        channel_ids=settings_channels or fallback.channel_ids,
        guild_ids=fallback.guild_ids,
        source="settings+" + fallback.source if settings_token or settings_channels else fallback.source,
        openclaw_home=fallback.openclaw_home,
        warnings=fallback.warnings,
    )


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _extract_discord_ids(data: dict) -> tuple[list[str], list[str]]:
    discord_config = (
        data.get("channels", {})
        .get("discord", {})
    )
    guilds = discord_config.get("guilds", {}) if isinstance(discord_config, dict) else {}
    if not isinstance(guilds, dict):
        return [], []

    guild_ids: list[str] = []
    channel_ids: list[str] = []
    for guild_id, guild_config in guilds.items():
        guild_ids.append(str(guild_id))
        if not isinstance(guild_config, dict):
            continue
        channels = guild_config.get("channels", {})
        if not isinstance(channels, dict):
            continue
        for channel_id, channel_config in channels.items():
            if _channel_enabled(channel_config):
                channel_ids.append(str(channel_id))
    return _dedupe(guild_ids), _dedupe(channel_ids)


def _channel_enabled(channel_config) -> bool:
    if not isinstance(channel_config, dict):
        return True
    return coerce_bool(channel_config.get("enabled", True), default=True)


def _normalize_channel_ids(raw_ids: str | list[str]) -> list[str]:
    if isinstance(raw_ids, str):
        parts = raw_ids.split(",")
    else:
        parts = raw_ids
    return _dedupe(str(part).strip() for part in parts if str(part).strip())


def _dedupe(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
