"""Trading endpoints - alerts, trades, positions, portfolio.

Manual position exits use the same durable client-id journal, broker-owner
routing, quote validation, and fill monitor as Discord-driven exits.  A UI
request therefore submits an order; it never mutates a live position as if a
fill had already happened.
"""
from fastapi import APIRouter, HTTPException, Query
from models import Trade, Position
from typing import Optional
from datetime import datetime, timezone
import asyncio


router = APIRouter(tags=["Trading"])

# Database reference
db = None


def set_db(database):
    """Set the database reference."""
    global db
    db = database


def calculate_pnl(entry_price: float, exit_price: float, quantity: int) -> float:
    """Calculate realized P&L for a confirmed options fill."""
    return (exit_price - entry_price) * quantity * 100


@router.get("/alerts")
async def get_alerts(limit: int = 50):
    return await db.get_alerts(limit)


@router.get("/trades")
async def get_trades(limit: int = 50):
    return await db.get_trades(limit)


@router.get("/positions")
async def get_positions(status: Optional[str] = None):
    return await db.get_positions(status)


def _active_exit_for_position(position_id: str) -> Optional[dict]:
    try:
        from live_order_journal import journal
    except ImportError:
        from ..live_order_journal import journal
    active_states = {
        "submitting", "ambiguous", "acknowledged", "submitted", "pending",
        "working", "partial", "working_unconfirmed",
    }
    for record in journal.records(active_only=True):
        if str(record.get("position_id") or "") != str(position_id):
            continue
        if str(record.get("side") or "").upper() != "SELL":
            continue
        if str(record.get("status") or "").lower() in active_states:
            return record
    return None


async def _submit_position_exit(
    position_id: str,
    *,
    percentage: float,
    requested_exit_price: Optional[float],
) -> dict:
    from routes.settings import check_and_trigger_shutdown

    position_doc = await db.get_position_by_id(position_id)
    if not position_doc:
        raise HTTPException(status_code=404, detail="Position not found")

    position = Position(**position_doc)
    remaining = int(position.remaining_quantity)
    if remaining <= 0 or str(position.status).lower() == "closed":
        raise HTTPException(status_code=409, detail="Position is already closed")
    if not 0 < percentage <= 100:
        raise HTTPException(status_code=422, detail="sell_percentage must be between 0 and 100")

    existing = _active_exit_for_position(position.id)
    if existing:
        return {
            "status": "already_working",
            "message": "An exit order is already working for this position",
            "position_id": position.id,
            "client_order_id": existing.get("client_order_id"),
            "order_id": existing.get("broker_order_id"),
            "broker": existing.get("broker") or position.broker,
            "requested_quantity": existing.get("quantity"),
            "filled_quantity": existing.get("filled_qty", 0),
        }

    sell_qty = remaining if percentage >= 100 else max(1, int(remaining * (percentage / 100.0)))
    sell_qty = min(remaining, sell_qty)
    settings = await db.get_settings()
    simulation_mode = bool(settings.get("simulation_mode", True))
    requested_price = float(
        requested_exit_price
        or position.current_price
        or position.entry_price
    )
    if requested_price <= 0:
        raise HTTPException(status_code=422, detail="A positive exit reference price is required")

    trade = Trade(
        ticker=position.ticker,
        strike=position.strike,
        option_type=position.option_type,
        expiration=position.expiration,
        entry_price=position.entry_price,
        exit_price=requested_price,
        quantity=sell_qty,
        side="SELL",
        broker=str(position.broker or "").lower(),
        simulated=simulation_mode,
        realized_pnl=0.0,
        status="submitting" if not simulation_mode else "simulated",
    )

    if simulation_mode:
        trade.executed_at = datetime.now(timezone.utc)
        trade.realized_pnl = calculate_pnl(position.entry_price, requested_price, sell_qty)
        await db.insert_trade(trade.model_dump())
        new_remaining = max(0, remaining - sell_qty)
        update_data = {
            "$set": {
                "remaining_quantity": new_remaining,
                "realized_pnl": position.realized_pnl + trade.realized_pnl,
                "current_price": requested_price,
                "status": "closed" if new_remaining <= 0 else "partial",
            },
            "$push": {"trade_ids": trade.id},
        }
        if new_remaining <= 0:
            update_data["$set"]["closed_at"] = datetime.now(timezone.utc).isoformat()
        await db.update_position(position.id, update_data)
        shutdown_reason = await check_and_trigger_shutdown(trade.realized_pnl)
        return {
            "status": "filled",
            "message": f"Simulated exit filled for {sell_qty} contract(s)",
            "position_id": position.id,
            "trade_id": trade.id,
            "requested_quantity": sell_qty,
            "filled_quantity": sell_qty,
            "realized_pnl": trade.realized_pnl,
            "shutdown_reason": shutdown_reason,
            "simulated": True,
        }

    try:
        from order_execution import build_client_order_id, get_configured_broker_client
        from fill_reconciliation import OrderContext
        import server
    except ImportError:
        from ..order_execution import build_client_order_id, get_configured_broker_client
        from ..fill_reconciliation import OrderContext
        from .. import server

    broker_id = str(position.broker or "").lower()
    if broker_id not in {"alpaca", "tradier"}:
        raise HTTPException(
            status_code=409,
            detail=f"Live exit is not implemented for position broker {broker_id or 'unknown'}; supported brokers are Alpaca and Tradier",
        )

    client_order_id = build_client_order_id(
        f"ui-exit-{position.id}-{remaining}-{sell_qty}",
        "SELL",
        position.id,
    )
    trade_doc = trade.model_dump()
    trade_doc.update({
        "client_order_id": client_order_id,
        "position_id": position.id,
        "requested_exit_price": requested_price,
        "order_submitted": False,
    })
    await db.insert_trade(trade_doc)

    broker_client = get_configured_broker_client(settings, broker_id, require_order_status=True)
    try:
        order_result = await broker_client.place_order(
            ticker=position.ticker,
            strike=position.strike,
            option_type=position.option_type,
            expiration=position.expiration,
            side="SELL",
            quantity=sell_qty,
            price=requested_price,
            client_order_id=client_order_id,
        )
    except Exception as exc:
        await db.update_trade(trade.id, {
            "status": "working_unconfirmed",
            "error_message": str(exc),
            "client_order_id": client_order_id,
            "position_id": position.id,
        })
        raise HTTPException(
            status_code=502,
            detail=(
                "Broker delivery is unresolved. Echo retained the deterministic order intent and will reconcile it before any retry: "
                f"{exc}"
            ),
        ) from exc

    order_id = str(order_result.get("order_id") or "")
    if not order_id:
        status_value = str(order_result.get("status") or "failed")
        detail = str(order_result.get("error") or "Broker did not return an order id")
        await db.update_trade(trade.id, {
            "status": "working_unconfirmed" if status_value == "ambiguous" else "failed",
            "error_message": detail,
            "client_order_id": client_order_id,
            "position_id": position.id,
        })
        raise HTTPException(status_code=502, detail=detail)

    routed_broker = str(getattr(broker_client, "routed_broker_id", "") or broker_id)
    submitted_price = float(order_result.get("submitted_limit_price") or requested_price)
    await db.update_trade(trade.id, {
        "status": "pending",
        "order_id": order_id,
        "broker": routed_broker,
        "client_order_id": client_order_id,
        "position_id": position.id,
        "order_submitted": True,
        "submitted_limit_price": submitted_price,
        "execution_quote": order_result.get("execution_quote"),
    })

    context = OrderContext(
        trade_id=trade.id,
        order_id=order_id,
        side="SELL",
        ticker=position.ticker,
        strike=position.strike,
        option_type=position.option_type,
        expiration=position.expiration,
        requested_quantity=sell_qty,
        broker=routed_broker,
        position_id=position.id,
        alert_price=submitted_price,
        simulated=False,
    )
    asyncio.create_task(
        server.monitor_fill(
            order_context=context,
            broker_client=broker_client,
            db=db,
            settings=settings,
        )
    )
    return {
        "status": "submitted",
        "message": f"Exit submitted for {sell_qty} contract(s); position changes after broker fills",
        "position_id": position.id,
        "trade_id": trade.id,
        "order_id": order_id,
        "client_order_id": client_order_id,
        "broker": routed_broker,
        "requested_quantity": sell_qty,
        "filled_quantity": 0,
        "submitted_limit_price": submitted_price,
        "execution_quote": order_result.get("execution_quote"),
        "simulated": False,
    }


@router.post("/positions/{position_id}/sell")
async def sell_position_from_ui(
    position_id: str,
    sell_percentage: float = Query(100, gt=0, le=100),
    exit_price: Optional[float] = Query(None, gt=0),
):
    """Submit a full or partial exit from the visible Positions screen."""
    return await _submit_position_exit(
        position_id,
        percentage=sell_percentage,
        requested_exit_price=exit_price,
    )


@router.post("/sell-position/{position_id}")
async def sell_position_legacy_alias(
    position_id: str,
    percentage: float = Query(100, gt=0, le=100),
):
    """Compatibility alias routed through the same live broker lifecycle."""
    return await _submit_position_exit(
        position_id,
        percentage=percentage,
        requested_exit_price=None,
    )


@router.get("/portfolio")
async def get_portfolio():
    return await db.get_portfolio_summary()
