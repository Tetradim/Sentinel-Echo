from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
from typing import Any, Awaitable, Callable, Mapping

from settings_flags import coerce_bool


ClientFactory = Callable[[Mapping[str, Any], str], Any | Awaitable[Any]]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _check(status: str, detail: str, *, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "detail": detail,
        "evidence": evidence or {},
    }


async def _default_client_factory(settings: Mapping[str, Any], broker_id: str) -> Any:
    from order_execution import get_configured_broker_client

    return get_configured_broker_client(settings, broker_id)


async def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        await _maybe_await(close())


async def run_broker_readiness_preflight(
    settings: Mapping[str, Any],
    *,
    broker_id: str | None = None,
    client_factory: ClientFactory | None = None,
) -> dict[str, Any]:
    broker = str(broker_id or settings.get("active_broker") or "").strip().lower()
    simulation_mode = coerce_bool(settings.get("simulation_mode"), default=True)
    auto_trading_enabled = coerce_bool(settings.get("auto_trading_enabled"), default=True)
    checks: dict[str, dict[str, Any]] = {
        "execution_flags": _check(
            "pass" if simulation_mode else "blocked",
            "Settings remain safe for read-only paper broker preflight."
            if simulation_mode
            else "Read-only broker preflight requires simulation_mode=true.",
            evidence={
                "simulation_mode": simulation_mode,
                "auto_trading_enabled": auto_trading_enabled,
            },
        )
    }

    if checks["execution_flags"]["status"] != "pass":
        return {"status": "blocked", "broker": broker, "checks": checks}

    if not broker:
        checks["broker_config"] = _check("blocked", "No active broker configured.")
        return {"status": "blocked", "broker": broker, "checks": checks}

    factory = client_factory or _default_client_factory
    client = None
    try:
        client = await _maybe_await(factory(settings, broker))
        checks["broker_capabilities"] = _check(
            "pass",
            "Broker client exposes read-only preflight hooks.",
            evidence={
                "has_check_connection": callable(getattr(client, "check_connection", None)),
                "has_list_open_orders": callable(getattr(client, "list_open_orders", None)),
                "has_place_order": callable(getattr(client, "place_order", None)),
            },
        )

        check_connection = getattr(client, "check_connection", None)
        if not callable(check_connection):
            checks["connection"] = _check("blocked", "Broker client does not expose check_connection().")
            return {"status": "blocked", "broker": broker, "checks": checks}
        connected = bool(await _maybe_await(check_connection()))
        checks["connection"] = _check(
            "pass" if connected else "blocked",
            "Broker connection check succeeded." if connected else "Broker connection check failed.",
            evidence={"connected": connected},
        )
        if not connected:
            return {"status": "blocked", "broker": broker, "checks": checks}

        list_open_orders = getattr(client, "list_open_orders", None)
        if not callable(list_open_orders):
            checks["open_orders"] = _check("blocked", "Broker client does not expose list_open_orders().")
            return {"status": "blocked", "broker": broker, "checks": checks}
        open_orders = await _maybe_await(list_open_orders())
        open_order_count = len(open_orders) if isinstance(open_orders, list) else 0
        if open_order_count > 0:
            checks["open_orders"] = _check(
                "blocked",
                "Open broker orders must be reconciled or cancelled before readiness preflight can pass.",
                evidence={"open_order_count": open_order_count},
            )
            return {"status": "blocked", "broker": broker, "checks": checks}
        checks["open_orders"] = _check(
            "pass",
            "Open orders listed without submitting or cancelling orders.",
            evidence={"open_order_count": open_order_count},
        )
        return {"status": "pass", "broker": broker, "checks": checks}
    except Exception as exc:
        checks["preflight_error"] = _check(
            "blocked",
            "Broker preflight failed before any order submission.",
            evidence={"error_type": exc.__class__.__name__, "message": str(exc)},
        )
        return {"status": "blocked", "broker": broker, "checks": checks}
    finally:
        if client is not None:
            await _close_client(client)


def _load_runtime_settings(env_file: str) -> dict[str, Any]:
    from alpaca_paper_settings import load_paper_env
    from database_sqlite import get_settings

    env = load_paper_env(env_file)
    credential_key = str(env.get("CREDENTIAL_KEY") or "").strip()
    if credential_key:
        os.environ["CREDENTIAL_KEY"] = credential_key
    return get_settings()


async def _main_async(env_file: str, broker_id: str | None) -> int:
    settings = _load_runtime_settings(env_file)
    report = await run_broker_readiness_preflight(settings, broker_id=broker_id)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a read-only configured-broker preflight.")
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--broker", default=None)
    args = parser.parse_args()
    return asyncio.run(_main_async(args.env_file, args.broker))


if __name__ == "__main__":
    raise SystemExit(main())
