from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from edge_sr_action_request import build_edge_sr_action_request
from edge_event_bus import recent_edge_sr_directive_events
from edge_sr_execution import build_edge_sr_execution_plan


router = APIRouter(prefix="/edge/sr", tags=["Edge S/R Watch"])
db = None
executor = None
EXECUTION_CONFIRMATION = "EXECUTE EDGE SR DIRECTIVE"
EXECUTION_CONFIRMATION_HEADER = "X-Edge-SR-Execution-Confirm"


class EdgeSrDirectivePreviewRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    positions: list[dict[str, Any]] | None = None
    source_config: dict[str, Any] = Field(default_factory=dict)


def set_db(database):
    global db
    db = database


def set_executor(callback):
    global executor
    executor = callback


@router.get("/events")
async def get_edge_sr_events(limit: int = Query(100, ge=1, le=1000)):
    """Return recent Edge S/R directive events targeted to Consolidation."""
    return {"events": recent_edge_sr_directive_events(limit=limit, target_bot="consolidation")}


@router.post("/directives/preview")
async def preview_edge_sr_directive(request: EdgeSrDirectivePreviewRequest):
    """Preview a guarded S/R directive execution plan without placing orders."""
    positions = request.positions
    if positions is None:
        positions = await _load_open_positions()
    plan = build_edge_sr_execution_plan(
        request.payload,
        positions=positions,
        source_config=request.source_config,
    )
    return {"plan": plan}


@router.post("/directives/execute")
async def execute_edge_sr_directive(
    request: EdgeSrDirectivePreviewRequest,
    x_edge_sr_execution_confirm: str = Header(default=""),
):
    """Submit a confirmed Edge S/R directive through the existing trade path."""
    if x_edge_sr_execution_confirm != EXECUTION_CONFIRMATION:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "edge_sr_execution_confirmation_required",
                "required_confirmation": EXECUTION_CONFIRMATION,
                "header": EXECUTION_CONFIRMATION_HEADER,
            },
        )

    positions = request.positions
    if positions is None:
        positions = await _load_open_positions()
    plan = build_support_resistance_plan(
        payload=request.payload,
        positions=positions,
        source_config=request.source_config,
    )
    if plan.get("status") != "ready":
        return {"status": "not_submitted", "plan": plan}
    if executor is None:
        raise HTTPException(status_code=503, detail="Edge S/R executor is not configured")

    action_request = build_edge_sr_action_request(plan, source_config=request.source_config)
    result = executor(action_request["alert"], action_request["parsed"])
    if inspect.isawaitable(result):
        await result
    return {
        "status": "submitted",
        "alert_id": action_request["alert"].id,
        "plan": plan,
    }


def build_support_resistance_plan(
    *,
    payload: dict[str, Any],
    positions: list[dict[str, Any]],
    source_config: dict[str, Any],
) -> dict[str, Any]:
    return build_edge_sr_execution_plan(
        payload,
        positions=positions,
        source_config=source_config,
    )


async def _load_open_positions() -> list[dict[str, Any]]:
    if db is None:
        return []
    open_positions = await db.get_positions("open")
    partial_positions = await db.get_positions("partial")
    return list(open_positions) + list(partial_positions)
