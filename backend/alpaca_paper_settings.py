from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
PAPER_HOST = "paper-api.alpaca.markets"


class AlpacaPaperSettingsError(ValueError):
    pass


def _first_env(env: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = str(env.get(name) or "").strip()
        if value:
            return value
    return ""


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


def _normalize_paper_base_url(endpoint: str) -> str:
    endpoint = (endpoint or PAPER_BASE_URL).strip().rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or parsed.netloc != PAPER_HOST:
        raise AlpacaPaperSettingsError("Alpaca paper bootstrap only accepts https://paper-api.alpaca.markets endpoints.")
    path = parsed.path.rstrip("/")
    if path not in {"", "/v2"}:
        raise AlpacaPaperSettingsError("Alpaca paper endpoint must be the paper host root or /v2 endpoint.")
    return PAPER_BASE_URL


def build_alpaca_paper_settings_update(env: Mapping[str, str]) -> dict:
    key = _first_env(env, "ALPACA_API_KEY", "APCA_API_KEY_ID")
    secret = _first_env(env, "ALPACA_API_SECRET", "APCA_API_SECRET_KEY")
    endpoint = _first_env(env, "ALPACA_ENDPOINT", "APCA_API_BASE_URL") or PAPER_BASE_URL
    if not key or not secret:
        raise AlpacaPaperSettingsError("ALPACA_API_KEY/APCA_API_KEY_ID and ALPACA_API_SECRET/APCA_API_SECRET_KEY are required.")
    return {
        "active_broker": "alpaca",
        "broker_configs": {
            "alpaca": {
                "broker_type": "alpaca",
                "api_key": key,
                "api_secret": secret,
                "base_url": _normalize_paper_base_url(endpoint),
            }
        },
        "simulation_mode": True,
        "auto_trading_enabled": True,
        "sell_alert_listening_enabled": True,
        "shutdown_triggered": False,
        "shutdown_reason": "",
    }


def load_paper_env(path: str | None = None, env: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(env or os.environ)
    env_path = Path(path or ".env.local")
    merged.update(_read_env_file(env_path))
    return merged


def apply_alpaca_paper_settings(env_path: str | None = None) -> dict:
    from database_sqlite import init_database, update_settings
    from utils import credentials

    env = load_paper_env(env_path)
    credential_key = str(env.get("CREDENTIAL_KEY") or "").strip()
    if credential_key:
        os.environ["CREDENTIAL_KEY"] = credential_key
        credentials._fernet = None
    update = build_alpaca_paper_settings_update(env)
    update["broker_configs"] = credentials.encrypt_broker_configs(update["broker_configs"])
    init_database()
    settings = update_settings(update)
    safe_update = dict(update)
    safe_update["broker_configs"] = credentials.mask_broker_configs(build_alpaca_paper_settings_update(env)["broker_configs"])
    return {
        "status": "configured",
        "active_broker": settings.get("active_broker"),
        "simulation_mode": bool(settings.get("simulation_mode")),
        "auto_trading_enabled": bool(settings.get("auto_trading_enabled")),
        "sell_alert_listening_enabled": bool(settings.get("sell_alert_listening_enabled", True)),
        "applied": safe_update,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Consolidation for safe Alpaca paper testing.")
    parser.add_argument("--env-file", default=".env.local")
    args = parser.parse_args()
    print(json.dumps(apply_alpaca_paper_settings(args.env_file), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
