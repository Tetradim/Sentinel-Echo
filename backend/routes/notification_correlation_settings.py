"""Settings endpoints referenced by the consolidated Echo Settings screen."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query


router = APIRouter(tags=["Notification and Correlation Settings"])
db = None


def set_db(database):
    global db
    db = database


@router.get("/notification-settings")
async def get_notification_settings():
    settings = await db.get_settings()
    token = str(settings.get("twilio_auth_token") or "")
    return {
        "sms_enabled": bool(settings.get("sms_enabled", False)),
        "sms_phone_number": str(settings.get("sms_phone_number") or ""),
        "twilio_account_sid": str(settings.get("twilio_account_sid") or ""),
        "twilio_auth_token": "●●●●●●●●" if token else "",
        "twilio_from_number": str(settings.get("twilio_from_number") or ""),
    }


@router.put("/notification-settings")
async def update_notification_settings(
    sms_enabled: bool = Query(False),
    sms_phone_number: str = Query(""),
    twilio_account_sid: str = Query(""),
    twilio_auth_token: str | None = Query(None),
    twilio_from_number: str = Query(""),
):
    updates = {
        "sms_enabled": sms_enabled,
        "sms_phone_number": sms_phone_number.strip(),
        "twilio_account_sid": twilio_account_sid.strip(),
        "twilio_from_number": twilio_from_number.strip(),
    }
    if twilio_auth_token is not None and twilio_auth_token.strip():
        updates["twilio_auth_token"] = twilio_auth_token.strip()
    settings = await db.update_settings(updates)
    return {
        "sms_enabled": bool(settings.get("sms_enabled", False)),
        "sms_phone_number": str(settings.get("sms_phone_number") or ""),
        "twilio_account_sid": str(settings.get("twilio_account_sid") or ""),
        "twilio_auth_token": "●●●●●●●●" if settings.get("twilio_auth_token") else "",
        "twilio_from_number": str(settings.get("twilio_from_number") or ""),
    }


@router.post("/notification-settings/test")
async def test_notification_settings():
    from notifications import send_notification

    settings = await db.get_settings()
    result = await send_notification(
        "connection_test",
        "Sentinel Echo notification test",
        settings,
    )
    if not result.get("sent_sms"):
        raise HTTPException(
            status_code=409,
            detail=result.get("error") or "SMS was not sent",
        )
    return {"success": True, "notification": result}


@router.get("/correlation-settings")
async def get_correlation_settings():
    settings = await db.get_settings()
    return {
        "max_positions_per_ticker": max(
            1,
            int(settings.get("max_positions_per_ticker", 3) or 3),
        )
    }


@router.put("/correlation-settings")
async def update_correlation_settings(
    max_positions_per_ticker: int = Query(3, ge=1, le=100),
):
    settings = await db.update_settings({
        "max_positions_per_ticker": int(max_positions_per_ticker),
    })
    return {
        "max_positions_per_ticker": int(
            settings.get("max_positions_per_ticker", max_positions_per_ticker)
        )
    }
