from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from edge_event_bus import recent_edge_sr_directive_events
from edge_sr_execution import build_edge_sr_execution_plan


router = APIRouter(prefix="/edge/sr", tags=["Edge S/R Watch"])
db = None


class EdgeSrDirectivePreviewRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    positions: list[dict[str, Any]] | None = None
    source_config: dict[str, Any] = Field(default_factory=dict)


def set_db(database):
    global db
    db = database


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


async def _load_open_positions() -> list[dict[str, Any]]:
    if db is None:
        return []
    open_positions = await db.get_positions("open")
    partial_positions = await db.get_positions("partial")
    return list(open_positions) + list(partial_positions)
