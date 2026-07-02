"""Mobile pairing diagnostics and import payloads."""
from datetime import datetime, timezone
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Request


router = APIRouter(tags=["Pairing"])

_LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}
_REQUIRED_ENDPOINTS = [
    {
        "key": "health",
        "method": "GET",
        "path": "/health",
        "requires_api_key": False,
        "label": "Health",
    },
    {
        "key": "status",
        "method": "GET",
        "path": "/status",
        "requires_api_key": True,
        "label": "Runtime status",
    },
    {
        "key": "setup_diagnostics",
        "method": "GET",
        "path": "/diagnostics/setup",
        "requires_api_key": True,
        "label": "Setup diagnostics",
    },
    {
        "key": "live_readiness",
        "method": "GET",
        "path": "/operator/live-readiness",
        "requires_api_key": True,
        "label": "Live readiness",
    },
    {
        "key": "alert_chains",
        "method": "GET",
        "path": "/operator/alert-chains",
        "requires_api_key": True,
        "label": "Alert audit trail",
    },
    {
        "key": "reconciliation",
        "method": "GET",
        "path": "/operator/reconciliation",
        "requires_api_key": True,
        "label": "Broker reconciliation",
    },
    {
        "key": "bot_bus",
        "method": "GET",
        "path": "/events",
        "requires_api_key": True,
        "label": "Bot event bus",
    },
    {
        "key": "chrome_bridge_health",
        "method": "GET",
        "path": "/discord/chrome-bridge/health",
        "requires_api_key": True,
        "label": "Chrome bridge health",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, *, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _normalized_host() -> str:
    return os.environ.get("HOST", "127.0.0.1").strip().lower() or "127.0.0.1"


def _api_key() -> str:
    return os.environ.get("API_KEY", "").strip()


def _remote_accessible(host: str) -> bool:
    return host not in _LOCAL_BIND_HOSTS


def _authless_desktop_mode(host: str) -> bool:
    return not _api_key() and _env_bool("USE_SQLITE", default=False) and host in _LOCAL_BIND_HOSTS


def _api_key_required(host: str) -> bool:
    return bool(_api_key()) or not _authless_desktop_mode(host)


def _blocking_issues(host: str) -> list[dict[str, str]]:
    issues = []
    if not _remote_accessible(host):
        issues.append(
            {
                "code": "remote_bind_localhost_only",
                "message": "Remote API is bound to localhost; a phone on the network cannot reach it.",
            }
        )
    if _remote_accessible(host) and not _api_key():
        issues.append(
            {
                "code": "api_key_missing_for_remote_bind",
                "message": "Remote API is reachable off-device but API_KEY is not configured.",
            }
        )
    return issues


def _transport_hint(base_api_url: str) -> str:
    try:
        hostname = urlparse(base_api_url).hostname or ""
    except ValueError:
        return "manual"

    parts = hostname.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        octets = [int(part) for part in parts]
        if octets[0] == 100 and 64 <= octets[1] <= 127:
            return "tailscale"
        if (
            octets[0] == 10
            or (octets[0] == 172 and 16 <= octets[1] <= 31)
            or (octets[0] == 192 and octets[1] == 168)
        ):
            return "same_wifi"
    if hostname:
        return "cloud_relay"
    return "manual"


def _request_base_api_url(request: Request) -> str:
    url = request.url
    path = str(url.path)
    prefix = path.split("/pairing/", 1)[0] if "/pairing/" in path else "/api"
    return f"{url.scheme}://{url.netloc}{prefix}".rstrip("/")


def required_pairing_endpoints() -> list[dict[str, object]]:
    return [dict(endpoint) for endpoint in _REQUIRED_ENDPOINTS]


def build_pairing_status(*, now=_now_iso) -> dict[str, object]:
    host = _normalized_host()
    port = _env_int("PORT", default=8001)
    api_key = _api_key()
    return {
        "version": 1,
        "server_time": now(),
        "api_auth_configured": bool(api_key),
        "api_key_required": _api_key_required(host),
        "remote_bind": {
            "host": host,
            "port": port,
            "remote_accessible": _remote_accessible(host),
        },
        "chrome_bridge_remote_enabled": _env_bool("CHROME_BRIDGE_ALLOW_REMOTE", default=False),
        "required_endpoints": required_pairing_endpoints(),
        "blocking_issues": _blocking_issues(host),
    }


def build_pairing_config(*, base_api_url: str, now=_now_iso) -> dict[str, object]:
    return {
        "version": 1,
        "app": "mobile-sentinel-echo",
        "created_at": now(),
        "remote_api_url": base_api_url.rstrip("/"),
        "api_key": _api_key(),
        "transport_hint": _transport_hint(base_api_url),
        "required_endpoints": required_pairing_endpoints(),
    }


@router.get("/pairing/status")
async def pairing_status(request: Request):
    payload = build_pairing_status()
    payload["base_api_url_hint"] = _request_base_api_url(request)
    return payload


@router.get("/pairing/config")
async def pairing_config(request: Request):
    return build_pairing_config(base_api_url=_request_base_api_url(request))
