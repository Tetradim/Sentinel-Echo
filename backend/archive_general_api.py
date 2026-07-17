from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_ARCHIVE_GENERAL_URL = "http://127.0.0.1:9200/api/general"
_ALLOWED_ROLES = {"trader", "observer", "risk_controller"}
_ALLOWED_SETTINGS = {
    "enabled",
    "base_url",
    "run_id",
    "participant_id",
    "bot_id",
    "display_name",
    "roles",
    "subscribed_symbols",
    "api_token",
    "timeout_seconds",
    "starting_cash",
    "commission_per_order",
    "slippage_bps",
}


class ArchiveGeneralApiError(RuntimeError):
    """Archive rejected a request or returned an invalid response."""


@dataclass(frozen=True)
class GeneralApiDefaults:
    bot_id: str
    display_name: str
    roles: tuple[str, ...] = ("trader",)
    participant_id: str | None = None


def _bot_env_prefix(bot_id: str) -> str:
    name = re.sub(r"[^A-Z0-9]+", "_", bot_id.upper()).strip("_")
    if name.startswith("SENTINEL_"):
        name = name[len("SENTINEL_") :]
    return f"SENTINEL_{name}_ARCHIVE"


def _normalize_base_url(value: Any) -> str:
    value = str(value or DEFAULT_ARCHIVE_GENERAL_URL).strip().rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute http or https URL")
    return value


def _normalize_roles(value: Any) -> list[str]:
    roles = value if isinstance(value, (list, tuple)) else str(value or "").split(",")
    normalized = list(dict.fromkeys(str(role).strip().lower() for role in roles if str(role).strip()))
    if not normalized:
        normalized = ["trader"]
    invalid = sorted(set(normalized) - _ALLOWED_ROLES)
    if invalid:
        raise ValueError(f"unsupported General API roles: {', '.join(invalid)}")
    return normalized


def _normalize_symbols(value: Any) -> list[str]:
    symbols = value if isinstance(value, (list, tuple)) else str(value or "").split(",")
    return list(dict.fromkeys(str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()))


def _number(value: Any, *, minimum: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


class GeneralApiConfigStore:
    """Private on-disk configuration with environment overrides and redaction."""

    def __init__(self, path: str | Path, defaults: GeneralApiDefaults):
        self.path = Path(path)
        self.defaults = defaults

    def _base(self) -> dict[str, Any]:
        participant_id = self.defaults.participant_id or self.defaults.bot_id
        return {
            "enabled": False,
            "base_url": DEFAULT_ARCHIVE_GENERAL_URL,
            "run_id": "",
            "participant_id": participant_id,
            "bot_id": self.defaults.bot_id,
            "display_name": self.defaults.display_name,
            "roles": list(self.defaults.roles),
            "subscribed_symbols": [],
            "api_token": "",
            "timeout_seconds": 5.0,
            "starting_cash": 100000.0,
            "commission_per_order": 0.0,
            "slippage_bps": 0.0,
        }

    def load(self) -> dict[str, Any]:
        config = self._base()
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ArchiveGeneralApiError(f"could not read General API settings: {exc}") from exc
            if not isinstance(saved, dict):
                raise ArchiveGeneralApiError("General API settings file must contain an object")
            config.update({key: value for key, value in saved.items() if key in _ALLOWED_SETTINGS})

        prefix = _bot_env_prefix(str(config.get("bot_id") or self.defaults.bot_id))
        env_map = {
            "base_url": (f"{prefix}_BASE_URL", "SENTINEL_ARCHIVE_BASE_URL"),
            "run_id": (f"{prefix}_RUN_ID",),
            "participant_id": (f"{prefix}_PARTICIPANT_ID",),
            "api_token": (f"{prefix}_API_TOKEN",),
        }
        for key, names in env_map.items():
            for name in names:
                if os.getenv(name):
                    config[key] = os.environ[name]
                    break
        enabled_env = os.getenv(f"{prefix}_ENABLED")
        if enabled_env is not None:
            config["enabled"] = enabled_env.strip().lower() in {"1", "true", "yes", "on"}
        return self.validate(config)

    def validate(self, config: Mapping[str, Any]) -> dict[str, Any]:
        normalized = self._base()
        normalized.update({key: value for key, value in config.items() if key in _ALLOWED_SETTINGS})
        normalized["enabled"] = bool(normalized["enabled"])
        normalized["base_url"] = _normalize_base_url(normalized["base_url"])
        for key in ("run_id", "participant_id", "bot_id", "display_name", "api_token"):
            normalized[key] = str(normalized.get(key) or "").strip()
        if not normalized["bot_id"]:
            raise ValueError("bot_id is required")
        if not normalized["participant_id"]:
            raise ValueError("participant_id is required")
        normalized["roles"] = _normalize_roles(normalized["roles"])
        normalized["subscribed_symbols"] = _normalize_symbols(normalized["subscribed_symbols"])
        normalized["timeout_seconds"] = _number(
            normalized["timeout_seconds"], minimum=0.1, name="timeout_seconds"
        )
        normalized["starting_cash"] = _number(
            normalized["starting_cash"], minimum=0.01, name="starting_cash"
        )
        normalized["commission_per_order"] = _number(
            normalized["commission_per_order"], minimum=0.0, name="commission_per_order"
        )
        normalized["slippage_bps"] = _number(
            normalized["slippage_bps"], minimum=0.0, name="slippage_bps"
        )
        return normalized

    def save(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(patch) - _ALLOWED_SETTINGS)
        if unknown:
            raise ValueError(f"unsupported General API settings: {', '.join(unknown)}")
        current = self.load()
        update = dict(patch)
        if "api_token" in update and update["api_token"] in {None, ""}:
            update.pop("api_token")
        current.update(update)
        config = self.validate(current)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".general-api-", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(config, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        return config

    def save_registration(self, registration: Mapping[str, Any]) -> dict[str, Any]:
        participant = registration.get("participant") or {}
        return self.save(
            {
                "participant_id": participant.get("participant_id") or self.load()["participant_id"],
                "api_token": registration.get("api_token") or "",
                "enabled": True,
            }
        )

    @staticmethod
    def public(config: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in config.items()
            if key != "api_token"
        } | {"token_configured": bool(config.get("api_token"))}


class ArchiveGeneralApiClient:
    """Synchronous client for Archive's archive.general.v1 participant contract."""

    def __init__(self, store: GeneralApiConfigStore):
        self.store = store

    def _request(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        authenticated: bool = False,
    ) -> Any:
        config = self.store.load()
        url = f"{config['base_url']}/{path.lstrip('/')}"
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if authenticated:
            token = config.get("api_token")
            if not token:
                raise ArchiveGeneralApiError("Archive participant token is not configured")
            headers["X-Archive-Bot-Token"] = token
        request = urllib.request.Request(
            url,
            method=method,
            headers=headers,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
        )
        try:
            with urllib.request.urlopen(request, timeout=config["timeout_seconds"]) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail")
            except Exception:
                detail = None
            raise ArchiveGeneralApiError(
                f"Archive returned HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ArchiveGeneralApiError(f"Archive connection failed: {exc}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArchiveGeneralApiError("Archive returned invalid JSON") from exc

    def spec(self) -> dict[str, Any]:
        return self._request("GET", "spec")

    def register(self) -> dict[str, Any]:
        config = self.store.load()
        if not config["run_id"]:
            raise ArchiveGeneralApiError("run_id is required before registration")
        registration = self._request(
            "POST",
            f"runs/{config['run_id']}/participants",
            {
                "participant_id": config["participant_id"],
                "bot_id": config["bot_id"],
                "display_name": config["display_name"],
                "roles": config["roles"],
                "subscribed_symbols": config["subscribed_symbols"],
                "starting_cash": config["starting_cash"],
                "commission_per_order": config["commission_per_order"],
                "slippage_bps": config["slippage_bps"],
            },
        )
        self.store.save_registration(registration)
        return {
            "participant": registration.get("participant"),
            "token_header": registration.get("token_header", "X-Archive-Bot-Token"),
            "token_saved": bool(registration.get("api_token")),
        }

    def _participant_path(self, suffix: str) -> str:
        config = self.store.load()
        if not config["run_id"]:
            raise ArchiveGeneralApiError("run_id is not configured")
        return (
            f"runs/{config['run_id']}/participants/"
            f"{urllib.parse.quote(config['participant_id'], safe='')}/{suffix.lstrip('/')}"
        )

    def test_connection(self) -> dict[str, Any]:
        config = self.store.load()
        spec = self.spec()
        result: dict[str, Any] = {
            "ok": True,
            "archive_reachable": True,
            "contract": spec.get("contract", spec.get("contract_version", "archive.general.v1")),
            "participant_authenticated": False,
        }
        if config["run_id"] and config["api_token"]:
            account = self.account()
            result["participant_authenticated"] = True
            result["account"] = account
        return result

    def latest_market(self) -> dict[str, Any]:
        return self._request("GET", self._participant_path("market/latest"), authenticated=True)

    def instruments(self) -> list[dict[str, Any]]:
        return self._request(
            "GET", self._participant_path("instruments"), authenticated=True
        ).get("instruments", [])

    def events(self, *, after: int = 0, limit: int = 1000) -> dict[str, Any]:
        query = urllib.parse.urlencode(
            {
                "participant_id": self.store.load()["participant_id"],
                "after": max(0, int(after)),
                "limit": min(5000, max(1, int(limit))),
            }
        )
        config = self.store.load()
        return self._request(
            "GET", f"runs/{config['run_id']}/events?{query}", authenticated=True
        )

    def submit_order(self, order: Mapping[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", self._participant_path("orders"), dict(order), authenticated=True
        )

    def orders(self) -> list[dict[str, Any]]:
        return self._request(
            "GET", self._participant_path("orders"), authenticated=True
        ).get("orders", [])

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request(
            "DELETE",
            self._participant_path(f"orders/{urllib.parse.quote(order_id, safe='')}"),
            authenticated=True,
        )

    def account(self) -> dict[str, Any]:
        return self._request("GET", self._participant_path("account"), authenticated=True)

    def publish_observation(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            self._participant_path("observations"),
            dict(observation),
            authenticated=True,
        )

    def publish_directive(self, directive: Mapping[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            self._participant_path("directives"),
            dict(directive),
            authenticated=True,
        )

    def directives(self) -> list[dict[str, Any]]:
        return self._request(
            "GET", self._participant_path("directives"), authenticated=True
        ).get("directives", [])

    def acknowledge_directive(self, directive_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            self._participant_path(
                f"directives/{urllib.parse.quote(directive_id, safe='')}/ack"
            ),
            {},
            authenticated=True,
        )


def create_fastapi_router(store: GeneralApiConfigStore):
    """Create the standard local settings/status router for a Sentinel backend."""

    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/general-api", tags=["Archive General API"])
    client = ArchiveGeneralApiClient(store)

    def failure(exc: Exception) -> HTTPException:
        if isinstance(exc, ValueError):
            return HTTPException(status_code=422, detail=str(exc))
        return HTTPException(status_code=502, detail=str(exc))

    @router.get("")
    async def get_general_api_settings():
        try:
            return {
                "settings": store.public(store.load()),
                "contract": "archive.general.v1",
                "boundary": "Archive replays and brokers; this bot alone creates decisions.",
            }
        except Exception as exc:
            raise failure(exc) from exc

    @router.put("")
    async def update_general_api_settings(patch: dict[str, Any]):
        try:
            return {"settings": store.public(store.save(patch))}
        except Exception as exc:
            raise failure(exc) from exc

    @router.post("/test")
    async def test_general_api_connection():
        try:
            return client.test_connection()
        except Exception as exc:
            raise failure(exc) from exc

    @router.post("/register")
    async def register_general_api_participant():
        try:
            return client.register()
        except Exception as exc:
            raise failure(exc) from exc

    @router.get("/account")
    async def get_general_api_account():
        try:
            return client.account()
        except Exception as exc:
            raise failure(exc) from exc

    @router.get("/market/latest")
    async def get_general_api_market():
        try:
            return client.latest_market()
        except Exception as exc:
            raise failure(exc) from exc

    return router

