"""Compatibility endpoints used by the Broker Config frontend.

Configuration may exist for several adapters, but only Alpaca and Tradier have
Echo's complete live options submit, quote, status, restart, and inventory
lifecycle.  These routes make that distinction at the action boundary.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from models import BrokerType


router = APIRouter(tags=["Live Broker Operations"])
db = None
LIVE_EXECUTION_BROKERS = {"alpaca", "tradier"}


def set_db(database):
    global db
    db = database


@router.get("/live-brokers")
async def live_broker_capabilities():
    return {
        "live_execution_brokers": sorted(LIVE_EXECUTION_BROKERS),
        "capabilities": {
            "alpaca": {
                "live_execution_supported": True,
                "submit": True,
                "quotes": True,
                "order_status": True,
                "restart_recovery": True,
                "position_inventory": True,
            },
            "tradier": {
                "live_execution_supported": True,
                "submit": True,
                "quotes": True,
                "order_status": True,
                "restart_recovery": True,
                "position_inventory": True,
            },
        },
    }


@router.post("/broker/switch/{broker_id}")
async def switch_broker_from_ui(broker_id: str):
    from routes.health import update_bot_status

    broker_id = str(broker_id or "").lower()
    try:
        broker_type = BrokerType(broker_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid broker: {broker_id}") from exc

    settings = await db.get_settings()
    configs = settings.get("broker_configs") or {}
    if broker_id not in configs:
        raise HTTPException(status_code=400, detail=f"Broker '{broker_id}' has no saved configuration")
    if not settings.get("simulation_mode", True) and broker_id not in LIVE_EXECUTION_BROKERS:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{broker_id} is not available for live options execution. "
                "Select Alpaca or Tradier."
            ),
        )

    await db.update_settings({"active_broker": broker_id})
    update_bot_status("active_broker", broker_type)
    return {
        "active_broker": broker_id,
        "live_execution_supported": broker_id in LIVE_EXECUTION_BROKERS,
    }


@router.post("/broker/check/{broker_id}")
async def check_broker_from_ui(broker_id: str):
    broker_id = str(broker_id or "").lower()
    settings = await db.get_settings()
    configs = settings.get("broker_configs") or {}
    if broker_id not in configs:
        raise HTTPException(status_code=400, detail=f"Broker '{broker_id}' has no saved configuration")

    try:
        from order_execution import get_configured_broker_client

        client = get_configured_broker_client(
            settings,
            broker_id,
            require_order_status=broker_id in LIVE_EXECUTION_BROKERS,
        )
        connected = bool(await client.check_connection())
        close = getattr(client, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result
    except Exception as exc:
        return {
            "connected": False,
            "broker": broker_id,
            "live_execution_supported": broker_id in LIVE_EXECUTION_BROKERS,
            "message": str(exc),
        }

    return {
        "connected": connected,
        "broker": broker_id,
        "live_execution_supported": broker_id in LIVE_EXECUTION_BROKERS,
        "message": (
            "Connected with complete live options lifecycle support"
            if connected and broker_id in LIVE_EXECUTION_BROKERS
            else "Connected, but complete live options execution is unavailable for this adapter"
            if connected
            else "Connection failed"
        ),
    }
