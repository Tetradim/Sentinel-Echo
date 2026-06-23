from __future__ import annotations

from datetime import datetime, timezone
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
    if db and hasattr(db, "update_runtime_state"):
        acceptance = preview.get("acceptance") if isinstance(preview.get("acceptance"), dict) else {}
        await db.update_runtime_state(
            {
                "simulation_replay_acceptance_status": str(acceptance.get("status") or "not_provided"),
                "simulation_replay_acceptance_expected_count": int(acceptance.get("expected_count") or 0),
                "simulation_replay_acceptance_passed_count": int(acceptance.get("passed_count") or 0),
                "simulation_replay_acceptance_failed_count": int(acceptance.get("failed_count") or 0),
                "simulation_replay_acceptance_failed_event_count": int(
                    acceptance.get("failed_event_count") or 0
                ),
                "simulation_replay_acceptance_failed_event_ids": (
                    acceptance.get("failed_event_ids")
                    if isinstance(acceptance.get("failed_event_ids"), list)
                    else []
                ),
                "simulation_replay_acceptance_missing_event_count": int(
                    acceptance.get("missing_event_count") or 0
                ),
                "simulation_replay_acceptance_missing_event_ids": (
                    acceptance.get("missing_event_ids")
                    if isinstance(acceptance.get("missing_event_ids"), list)
                    else []
                ),
                "simulation_replay_acceptance_updated_at": datetime.now(timezone.utc).isoformat(),
                "simulation_replay_acceptance_replay_url": preview["replay_url"],
            }
        )
    return preview
