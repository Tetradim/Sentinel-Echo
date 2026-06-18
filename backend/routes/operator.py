"""Operator lab and event log endpoints."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models import OperatorEvent
from routes.trading import create_test_alert_records

router = APIRouter(tags=["Operator"])

db = None


def set_db(database):
    """Set the database reference."""
    global db
    db = database


class OperatorSimulateExitRequest(BaseModel):
    position_id: Optional[str] = None
    sell_percentage: float = Field(default=50, ge=1, le=100)
    exit_price: float = Field(default=1.8, gt=0)


async def _record_event(category: str, action: str, summary: str, *, severity: str = "info", details: Optional[dict] = None):
    event = OperatorEvent(
        category=category,
        action=action,
        summary=summary,
        severity=severity,
        details=details or {},
    ).model_dump(mode="json")
    await db.insert_operator_event(event)
    return event


@router.get("/operator/events")
async def get_operator_events(limit: int = Query(default=100, ge=1, le=500)):
    """Return recent operator-visible events."""
    return await db.get_operator_events(limit)


@router.post("/operator/test-alert")
async def create_operator_test_alert():
    """Create a safe simulated alert/trade/position and log the action."""
    result = await create_test_alert_records(db, message="Operator test alert created")
    event = await _record_event(
        "test_lab",
        "test_alert_created",
        "Created simulated SPY alert, trade, and position.",
        details=result,
    )
    return {**result, "event_id": event["id"]}


@router.post("/operator/simulate-exit")
async def simulate_exit(request: OperatorSimulateExitRequest):
    """Sell a simulated/open position from the operator lab and log the action."""
    position_id = request.position_id
    if not position_id:
        positions = await db.get_positions()
        first_open = next(
            (
                position for position in positions
                if position.get("status") in {"open", "partial"} and int(position.get("remaining_quantity") or 0) > 0
            ),
            None,
        )
        if not first_open:
            raise HTTPException(status_code=404, detail="No open position is available to sell.")
        position_id = first_open["id"]

    from routes import trading as trading_route

    result = await trading_route.sell_position_from_operator(
        position_id,
        sell_percentage=request.sell_percentage,
        exit_price=request.exit_price,
    )
    event = await _record_event(
        "test_lab",
        "simulated_exit",
        f"Sold {result.get('sold_quantity', 0)} contract(s) from a test position.",
        details=result,
    )
    return {**result, "event_id": event["id"]}
