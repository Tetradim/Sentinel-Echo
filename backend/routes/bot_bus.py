from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from bot_event_bus import BotEvent, event_bus
from routes.discord import _ensure_local_chrome_bridge_request


router = APIRouter(prefix="/bus", tags=["Cross Bot Event Bus"])


@router.post("/events")
async def publish_bot_event(payload: BotEvent, request: Request):
    _ensure_local_chrome_bridge_request(request)
    event = event_bus.publish(payload)
    return {"status": "accepted", "event": event.model_dump(mode="json")}


@router.get("/events")
async def recent_bot_events(
    request: Request,
    limit: int = 100,
    event_type: str | None = None,
):
    _ensure_local_chrome_bridge_request(request)
    return {"events": event_bus.recent(limit=limit, event_type=event_type)}
