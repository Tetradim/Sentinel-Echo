"""
Trading endpoints - alerts, trades, positions, portfolio
"""
import asyncio
import inspect
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models import Trade, Position
from fill_monitor import monitor_fill
from fill_reconciliation import OrderContext
from order_execution import build_client_order_id, get_configured_broker_client
from operator_audit import record_operator_event
from datetime import datetime, timezone

router = APIRouter(tags=["Trading"])

# Database reference
db = None


def set_db(database):
    """Set the database reference"""
    global db
    db = database


# Helper function
def calculate_pnl(entry_price: float, exit_price: float, quantity: int) -> float:
    """Calculate realized P&L for a trade"""
    return (exit_price - entry_price) * quantity * 100


class CloseTradeRequest(BaseModel):
    exit_price: float = Field(gt=0)


class UpdateTradePriceRequest(BaseModel):
    current_price: float = Field(gt=0)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _get_trade_by_id(trade_id: str) -> Optional[dict]:
    if hasattr(db, "get_trade_by_id"):
        trade = await _maybe_await(db.get_trade_by_id(trade_id))
        if trade:
            return trade

    trades = await db.get_trades(limit=1000)
    return next((trade for trade in trades if trade.get("id") == trade_id), None)


async def _get_open_position_for_trade(trade_id: str) -> Optional[dict]:
    if not hasattr(db, "get_positions"):
        return None

    positions = await db.get_positions()
    for position in positions:
        if position.get("status") == "closed":
            continue
        if trade_id in (position.get("trade_ids") or []):
            return position
    return None


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _exit_reason_label(exit_trigger: str) -> str:
    labels = {
        "sell_alert": "Discord sell alert",
        "trailing_stop": "Trailing stop",
        "support_resistance": "Support/resistance",
        "operator_sell": "Operator sell",
        "operator_trade_close": "Operator trade close",
    }
    return labels.get(str(exit_trigger or "").strip(), "Operator sell")


async def _sell_position_at_price(
    position_id: str,
    percentage: float,
    exit_price: Optional[float],
    exit_trigger: str = "operator_sell",
):
    """Sell a position at a known exit price, shared by legacy and operator routes."""
    resolved_exit_trigger = exit_trigger if isinstance(exit_trigger, str) and exit_trigger.strip() else "operator_sell"
    if percentage <= 0 or percentage > 100:
        raise HTTPException(status_code=400, detail="Sell percentage must be between 1 and 100")

    position_doc = await db.get_position_by_id(position_id)
    if not position_doc:
        raise HTTPException(status_code=404, detail="Position not found")

    position = Position(**position_doc)
    if position.remaining_quantity <= 0:
        raise HTTPException(status_code=400, detail="Position has no remaining contracts to sell")

    resolved_exit_price = exit_price
    if resolved_exit_price is None:
        if position.current_price is None:
            raise HTTPException(
                status_code=400,
                detail="Cannot sell: current_price is not set. Update the position price first.",
            )
        resolved_exit_price = position.current_price
    if resolved_exit_price <= 0:
        raise HTTPException(status_code=400, detail="Exit price must be greater than 0")

    sell_qty = min(
        position.remaining_quantity,
        max(1, int(position.remaining_quantity * (percentage / 100))),
    )

    settings = _dict_or_empty(await db.get_settings())
    active_broker = _enum_value(settings.get("active_broker", "ibkr"))

    trade = Trade(
        ticker=position.ticker,
        strike=position.strike,
        option_type=position.option_type,
        expiration=position.expiration,
        entry_price=position.entry_price,
        exit_price=resolved_exit_price,
        current_price=resolved_exit_price,
        quantity=sell_qty,
        side="SELL",
        status="pending",
        broker=str(active_broker),
        simulated=False,
        sell_percentage=percentage,
        exit_trigger=resolved_exit_trigger,
        exit_reason=_exit_reason_label(resolved_exit_trigger),
    )

    realized_pnl = calculate_pnl(position.entry_price, resolved_exit_price, sell_qty)
    trade.realized_pnl = realized_pnl

    try:
        broker_client = get_configured_broker_client(settings, str(active_broker), require_order_status=True)
        order_result = await broker_client.place_order(
            ticker=position.ticker,
            strike=position.strike,
            option_type=position.option_type,
            expiration=position.expiration,
            side="SELL",
            quantity=sell_qty,
            price=resolved_exit_price,
            client_order_id=build_client_order_id(position_id, "SELL", resolved_exit_trigger),
        )
        order_id = order_result.get("order_id")
        if not order_id:
            raise ValueError(order_result.get("error", "Broker did not return an order id"))
        trade.order_id = order_id
        await db.insert_trade(trade.model_dump(mode="json"))
        asyncio.create_task(
            monitor_fill(
                order_context=OrderContext(
                    trade_id=trade.id,
                    order_id=order_id,
                    side="SELL",
                    ticker=position.ticker,
                    strike=position.strike,
                    option_type=position.option_type,
                    expiration=position.expiration,
                    requested_quantity=sell_qty,
                    broker=str(active_broker),
                    position_id=position.id,
                    alert_price=resolved_exit_price,
                    simulated=False,
                    sell_percentage=percentage,
                    exit_trigger=resolved_exit_trigger,
                ),
                broker_client=broker_client,
                db=db,
                settings=settings,
            )
        )
    except Exception as exc:
        trade.status = "failed"
        trade.error_message = str(exc)
        await db.insert_trade(trade.model_dump(mode="json"))
        raise HTTPException(status_code=502, detail=f"Broker SELL order failed: {exc}") from exc

    result = {
        "position_id": position_id,
        "submitted_quantity": sell_qty,
        "order_id": trade.order_id,
        "trade_id": trade.id,
        "status": trade.status,
        "message": f"Submitted SELL for {sell_qty} contracts",
        "realized_pnl": realized_pnl,
        "exit_trigger": resolved_exit_trigger,
    }

    await record_operator_event(
        db,
        "position",
        "position_sell_submitted",
        f"Submitted SELL for {sell_qty} contract(s) from position {position_id}.",
        severity="warning",
        details={
            "position_id": position_id,
            "sold_quantity": sell_qty,
            "sell_percentage": percentage,
            "exit_trigger": resolved_exit_trigger,
            "exit_price": resolved_exit_price,
            "realized_pnl": realized_pnl,
        },
    )

    return result


# Alerts
@router.get("/alerts")
async def get_alerts(limit: int = 50):
    """Get recent alerts"""
    return await db.get_alerts(limit)


@router.post("/test-alert")
async def create_test_alert():
    """Reject removed local synthetic alert creation."""
    raise HTTPException(status_code=410, detail="Local test alerts have been removed; broker-routed alerts are required.")


# Trades
@router.get("/trades")
async def get_trades(limit: int = 50):
    """Get recent trades"""
    return await db.get_trades(limit)


@router.post("/trades/{trade_id}/close")
async def close_trade(trade_id: str, request: CloseTradeRequest):
    """Close an open trade at the submitted exit price."""
    trade = await _get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    entry_price = float(trade.get("entry_price") or 0)
    quantity = int(trade.get("quantity") or 0)
    realized_pnl = calculate_pnl(entry_price, request.exit_price, quantity)
    position_close = None
    linked_position = await _get_open_position_for_trade(trade_id)
    if linked_position:
        position_close = await _sell_position_at_price(
            str(linked_position["id"]),
            100,
            request.exit_price,
            exit_trigger="operator_trade_close",
        )
        realized_pnl = float(position_close.get("realized_pnl", realized_pnl))
    else:
        raise HTTPException(
            status_code=409,
            detail="Trade close requires a linked open position so Echo can submit a broker SELL order.",
        )

    updates = {
        "status": "closed",
        "exit_price": request.exit_price,
        "current_price": request.exit_price,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": 0.0,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.update_trade(trade_id, updates)
    await record_operator_event(
        db,
        "trade",
        "trade_closed",
        f"Trade {trade_id} closed.",
        severity="warning",
        details={"trade_id": trade_id, "exit_price": request.exit_price, "realized_pnl": realized_pnl},
    )

    return {
        "trade_id": trade_id,
        "realized_pnl": realized_pnl,
        "message": "Trade closed",
        **(position_close or {}),
    }


@router.put("/trades/{trade_id}/price")
async def update_trade_price(trade_id: str, request: UpdateTradePriceRequest):
    """Update a trade's current mark and unrealized P&L."""
    trade = await _get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    entry_price = float(trade.get("entry_price") or 0)
    quantity = int(trade.get("quantity") or 0)
    status = str(trade.get("status") or "").lower()
    unrealized_pnl = (
        0.0
        if status == "closed"
        else calculate_pnl(entry_price, request.current_price, quantity)
    )
    await db.update_trade(
        trade_id,
        {
            "current_price": request.current_price,
            "unrealized_pnl": unrealized_pnl,
        },
    )
    await record_operator_event(
        db,
        "trade",
        "trade_price_updated",
        f"Trade {trade_id} price updated.",
        details={"trade_id": trade_id, "current_price": request.current_price, "unrealized_pnl": unrealized_pnl},
    )

    return {
        "trade_id": trade_id,
        "current_price": request.current_price,
        "unrealized_pnl": unrealized_pnl,
    }


# Positions
@router.get("/positions")
async def get_positions(status: Optional[str] = None):
    """Get positions, optionally filtered by status"""
    return await db.get_positions(status)


@router.post("/sell-position/{position_id}")
async def sell_position(position_id: str, percentage: float = 100):
    """Sell a position (full or partial)"""
    return await _sell_position_at_price(position_id, percentage, exit_price=None, exit_trigger="operator_sell")


@router.post("/positions/{position_id}/sell")
async def sell_position_from_operator(
    position_id: str,
    sell_percentage: float = Query(100, ge=1, le=100),
    exit_price: float = Query(..., gt=0),
    exit_trigger: str = Query("operator_sell"),
):
    """Sell a position using the operator UI's submitted price and percentage."""
    return await _sell_position_at_price(position_id, sell_percentage, exit_price, exit_trigger=exit_trigger)


# Portfolio
@router.get("/portfolio")
async def get_portfolio():
    """Get portfolio summary"""
    return await db.get_portfolio_summary()
