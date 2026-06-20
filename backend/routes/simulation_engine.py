from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from simulation_replay import SimulationReplayError, build_replay_preview, fetch_engine_replay, normalize_replay_url


router = APIRouter(prefix="/simulation-engine", tags=["Simulation Engine"])
db = None


def set_db(database):
    global db
    db = database


@router.get("/replay-events")
async def get_simulation_engine_replay_events(
    channel_id: str | None = None,
    since: str | None = None,
    limit: int = 1000,
    replay_url: str | None = None,
):
    try:
        return await fetch_engine_replay(
            replay_url=replay_url,
            channel_id=channel_id,
            since=since,
            limit=limit,
        )
    except SimulationReplayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/replay-preview")
async def preview_simulation_engine_replay(body: dict[str, Any] = Body(default_factory=dict)):
    settings = await db.get_settings() if db else {}
    try:
        replay = await fetch_engine_replay(
            replay_url=body.get("replay_url"),
            channel_id=body.get("channel_id"),
            since=body.get("since"),
            limit=int(body.get("limit") or 1000),
        )
    except SimulationReplayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    preview = build_replay_preview(replay, settings or {})
    preview["replay_url"] = normalize_replay_url(body.get("replay_url"))
    return preview
