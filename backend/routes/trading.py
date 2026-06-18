"""
Trading endpoints - alerts, trades, positions, portfolio
"""
import inspect
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models import Trade, Position
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


async def _sell_position_at_price(
    position_id: str,
    percentage: float,
    exit_price: Optional[float],
):
    """Sell a position at a known exit price, shared by legacy and operator routes."""
    from routes.settings import check_and_trigger_shutdown

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

    settings = await db.get_settings()
    active_broker = _enum_value(settings.get("active_broker", "ibkr"))
    simulation_mode = bool(settings.get("simulation_mode", True))

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
        status="simulated" if simulation_mode else "executed",
        broker=str(active_broker),
        simulated=simulation_mode,
        executed_at=datetime.now(timezone.utc),
    )

    realized_pnl = calculate_pnl(position.entry_price, resolved_exit_price, sell_qty)
    trade.realized_pnl = realized_pnl

    await db.insert_trade(trade.model_dump(mode="json"))

    new_remaining = position.remaining_quantity - sell_qty
    remaining_unrealized = (
        calculate_pnl(position.entry_price, resolved_exit_price, new_remaining)
        if new_remaining > 0
        else 0.0
    )
    update_data = {
        "$set": {
            "remaining_quantity": new_remaining,
            "current_price": resolved_exit_price,
            "realized_pnl": position.realized_pnl + realized_pnl,
            "unrealized_pnl": remaining_unrealized,
            "status": "closed" if new_remaining <= 0 else "partial",
        },
        "$push": {"trade_ids": trade.id},
    }
    if new_remaining <= 0:
        update_data["$set"]["closed_at"] = datetime.now(timezone.utc).isoformat()

    await db.update_position(position_id, update_data)

    shutdown_reason = await check_and_trigger_shutdown(realized_pnl)

    result = {
        "position_id": position_id,
        "sold_quantity": sell_qty,
        "message": f"Sold {sell_qty} contracts",
        "realized_pnl": realized_pnl,
    }
    if shutdown_reason:
        result["shutdown_triggered"] = True
        result["shutdown_reason"] = shutdown_reason

    return result


# Alerts
@router.get("/alerts")
async def get_alerts(limit: int = 50):
    """Get recent alerts"""
    return await db.get_alerts(limit)


@router.post("/test-alert")
async def create_test_alert():
    """Create a safe simulated alert/trade/position for local UI testing."""
    settings = await db.get_settings()
    active_broker = str(_enum_value(settings.get("active_broker", "ibkr")))
    now = datetime.now(timezone.utc)

    from models import Alert

    test_alert = Alert(
        ticker="SPY",
        strike=500.0,
        option_type="CALL",
        expiration="2026-06-26",
        entry_price=1.25,
        raw_message="TEST ALERT: BTO SPY 500C 2026-06-26 @ 1.25",
        processed=True,
        trade_executed=True,
        trade_result="filled",
    )
    trade = Trade(
        alert_id=test_alert.id,
        ticker=test_alert.ticker,
        strike=test_alert.strike,
        option_type=test_alert.option_type,
        expiration=test_alert.expiration,
        entry_price=test_alert.entry_price,
        current_price=test_alert.entry_price,
        quantity=1,
        side="BUY",
        status="simulated",
        broker=active_broker,
        executed_at=now,
        simulated=True,
    )
    position = Position(
        ticker=test_alert.ticker,
        strike=test_alert.strike,
        option_type=test_alert.option_type,
        expiration=test_alert.expiration,
        entry_price=test_alert.entry_price,
        current_price=test_alert.entry_price,
        original_quantity=1,
        remaining_quantity=1,
        total_cost=test_alert.entry_price * 100,
        broker=active_broker,
        status="open",
        opened_at=now,
        simulated=True,
        trade_ids=[trade.id],
        highest_price=test_alert.entry_price,
    )

    await db.insert_alert(test_alert.model_dump(mode="json"))
    await db.insert_trade(trade.model_dump(mode="json"))
    await db.insert_position(position.model_dump(mode="json"))

    return {
        "message": "Test alert created",
        "alert_id": test_alert.id,
        "trade_id": trade.id,
        "position_id": position.id,
    }


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
        )
        realized_pnl = float(position_close.get("realized_pnl", realized_pnl))

    updates = {
        "status": "closed",
        "exit_price": request.exit_price,
        "current_price": request.exit_price,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": 0.0,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.update_trade(trade_id, updates)

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
    return await _sell_position_at_price(position_id, percentage, exit_price=None)


@router.post("/positions/{position_id}/sell")
async def sell_position_from_operator(
    position_id: str,
    sell_percentage: float = Query(100, ge=1, le=100),
    exit_price: float = Query(..., gt=0),
):
    """Sell a position using the operator UI's submitted price and percentage."""
    return await _sell_position_at_price(position_id, sell_percentage, exit_price)


# Portfolio
@router.get("/portfolio")
async def get_portfolio():
    """Get portfolio summary"""
    return await db.get_portfolio_summary()
