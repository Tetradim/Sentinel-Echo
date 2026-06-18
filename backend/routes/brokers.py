"""
Broker management endpoints
"""
from fastapi import APIRouter, HTTPException
from models import BrokerType, BrokerInfo

router = APIRouter(tags=["Brokers"])

# Database reference - will be set by main server
db = None


def set_db(database):
    """Set the database reference"""
    global db
    db = database


# Broker info for frontend
BROKERS_INFO = [
    BrokerInfo(id="ibkr", name="Interactive Brokers", description="Professional-grade broker", supports_options=True, requires_gateway=True,
        config_fields=[{"key": "gateway_url", "label": "Gateway URL", "type": "text", "placeholder": "https://localhost:5000"},
            {"key": "account_id", "label": "Account ID", "type": "text", "placeholder": "Your account ID"}]),
    BrokerInfo(id="alpaca", name="Alpaca", description="Commission-free API-first broker", supports_options=True, requires_gateway=False,
        config_fields=[{"key": "api_key", "label": "API Key", "type": "text", "placeholder": "Your Alpaca API key"},
            {"key": "api_secret", "label": "API Secret", "type": "password", "placeholder": "Your API secret"},
            {"key": "base_url", "label": "Base URL", "type": "text", "placeholder": "https://paper-api.alpaca.markets"}]),
    BrokerInfo(id="td_ameritrade", name="TD Ameritrade (Schwab)", description="Now part of Charles Schwab", supports_options=True, requires_gateway=False,
        config_fields=[{"key": "client_id", "label": "Client ID", "type": "text", "placeholder": "Your app client ID"},
            {"key": "refresh_token", "label": "Refresh Token", "type": "password", "placeholder": "OAuth refresh token"}]),
    BrokerInfo(id="tradier", name="Tradier", description="Developer-friendly broker", supports_options=True, requires_gateway=False,
        config_fields=[{"key": "access_token", "label": "Access Token", "type": "password", "placeholder": "Your Tradier access token"},
            {"key": "account_id", "label": "Account ID", "type": "text", "placeholder": "Your account ID"}]),
    BrokerInfo(id="webull", name="Webull", description="Commission-free trading", supports_options=True, requires_gateway=False,
        config_fields=[{"key": "username", "label": "Email/Phone", "type": "text", "placeholder": "Your Webull login"},
            {"key": "password", "label": "Password", "type": "password", "placeholder": "Your password"},
            {"key": "device_id", "label": "Device ID", "type": "text", "placeholder": "Your device ID"},
            {"key": "trade_token", "label": "Trade PIN", "type": "password", "placeholder": "6-digit trading PIN"}]),
    BrokerInfo(id="robinhood", name="Robinhood", description="Commission-free trading app", supports_options=True, requires_gateway=False,
        config_fields=[{"key": "username", "label": "Email", "type": "email", "placeholder": "Your Robinhood email"},
            {"key": "password", "label": "Password", "type": "password", "placeholder": "Your password"},
            {"key": "mfa_code", "label": "MFA Code", "type": "text", "placeholder": "2FA code (if enabled)"}]),
    BrokerInfo(id="tradestation", name="TradeStation", description="Professional trading platform", supports_options=True, requires_gateway=False,
        config_fields=[{"key": "ts_client_id", "label": "Client ID", "type": "text", "placeholder": "TradeStation API Client ID"},
            {"key": "ts_client_secret", "label": "Client Secret", "type": "password", "placeholder": "Client Secret"},
            {"key": "ts_refresh_token", "label": "Refresh Token", "type": "password", "placeholder": "OAuth Refresh Token"}]),
    BrokerInfo(id="thinkorswim", name="Thinkorswim (Schwab)", description="Professional trading platform by Charles Schwab", supports_options=True, requires_gateway=False,
        config_fields=[{"key": "tos_consumer_key", "label": "Consumer Key", "type": "text", "placeholder": "Schwab API Consumer Key"},
            {"key": "tos_refresh_token", "label": "Refresh Token", "type": "password", "placeholder": "OAuth Refresh Token"},
            {"key": "tos_account_id", "label": "Account ID", "type": "text", "placeholder": "Your Account ID"}]),
    BrokerInfo(id="wealthsimple", name="Wealthsimple Trade", description="Canadian commission-free trading (stocks/ETFs)", supports_options=False, requires_gateway=False,
        config_fields=[{"key": "ws_email", "label": "Email", "type": "email", "placeholder": "Your Wealthsimple email"},
            {"key": "ws_password", "label": "Password", "type": "password", "placeholder": "Your password"},
            {"key": "ws_otp_code", "label": "OTP Code (2FA)", "type": "text", "placeholder": "Enter 2FA code"}]),
]


@router.get("/brokers")
async def get_brokers():
    """Get list of supported brokers"""
    return [b.model_dump() for b in BROKERS_INFO]


@router.get("/active-broker")
async def get_active_broker():
    """Get currently active broker"""
    settings = await db.get_settings()
    return {"active_broker": settings.get('active_broker', 'ibkr')}


@router.post("/active-broker/{broker_id}")
async def set_active_broker(broker_id: str):
    """Set the active broker"""
    from routes.health import update_bot_status
    # FIXED C17: validate enum and config exist before switching
    try:
        broker_type = BrokerType(broker_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid broker: {broker_id}")
    settings = await db.get_settings()
    broker_configs = settings.get("broker_configs", {})
    if broker_id not in broker_configs:
        raise HTTPException(
            status_code=400,
            detail=f"Broker '{broker_id}' has no saved configuration. Configure it first."
        )
    await db.update_settings({"active_broker": broker_id})
    update_bot_status("active_broker", broker_type)
    return {"active_broker": broker_id}


@router.post("/broker/switch/{broker_id}")
async def switch_broker_alias(broker_id: str):
    """Compatibility route used by the operator UI to switch brokers."""
    return await set_active_broker(broker_id)


@router.post("/broker/check/{broker_id}")
async def check_broker_alias(broker_id: str):
    """Check a specific broker connection without changing the active broker."""
    from order_execution import close_broker_client, get_configured_broker_client
    from routes.health import update_bot_status

    try:
        BrokerType(broker_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid broker: {broker_id}")

    settings = await db.get_settings()
    broker_configs = settings.get("broker_configs", {}) if settings else {}
    if broker_id not in broker_configs:
        return {
            "connected": False,
            "broker": broker_id,
            "message": f"Broker '{broker_id}' has no saved configuration.",
        }

    broker_client = None
    try:
        broker_client = get_configured_broker_client(settings, broker_id)
        connected = await broker_client.check_connection()
    except Exception as exc:
        import logging as _log

        _log.getLogger(__name__).error("Broker connection check failed for %s: %s", broker_id, exc)
        connected = False
    finally:
        if broker_client is not None:
            await close_broker_client(broker_client)

    active_broker = settings.get("active_broker", "ibkr")
    if hasattr(active_broker, "value"):
        active_broker = active_broker.value
    if str(active_broker) == broker_id:
        update_bot_status("broker_connected", connected)

    return {
        "connected": connected,
        "broker": broker_id,
        "message": "Connection successful" if connected else "Connection check failed",
    }
