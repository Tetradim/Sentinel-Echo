"""
Broker management endpoints
"""
from fastapi import APIRouter, HTTPException
from broker_capabilities import (
    broker_config_has_saved_value,
    get_broker_capabilities,
    is_broker_configured,
    missing_broker_config_fields,
    normalize_broker_id,
)
from models import BrokerType, BrokerInfo
from operator_audit import record_operator_event

router = APIRouter(tags=["Brokers"])

# Database reference - will be set by main server
db = None


def set_db(database):
    """Set the database reference"""
    global db
    db = database


def _dict_or_empty(value):
    return value if isinstance(value, dict) else {}


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _active_broker_id(settings):
    active_broker = _enum_value(_dict_or_empty(settings).get("active_broker", "ibkr"))
    return active_broker if isinstance(active_broker, str) and active_broker else "ibkr"


def _broker_config(settings, broker_id):
    config, _ = _broker_config_status(settings, broker_id)
    return config


def _broker_config_status(settings, broker_id):
    broker_configs = _dict_or_empty(_dict_or_empty(settings).get("broker_configs", {}))
    normalized_broker_id = normalize_broker_id(broker_id)
    config = broker_configs.get(normalized_broker_id)
    if is_broker_configured(broker_configs, normalized_broker_id):
        return config, []
    if broker_config_has_saved_value(config):
        return None, list(missing_broker_config_fields(config, normalized_broker_id))
    return None, []


def _broker_config_message(broker_id, missing_fields):
    if missing_fields:
        fields = ", ".join(missing_fields)
        return f"Broker '{broker_id}' config is missing required fields: {fields}."
    return f"Broker '{broker_id}' has no saved configuration."


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
    brokers = []
    for broker in BROKERS_INFO:
        payload = broker.model_dump()
        payload["capabilities"] = get_broker_capabilities(payload["id"])
        brokers.append(payload)
    return brokers


@router.get("/active-broker")
async def get_active_broker():
    """Get currently active broker"""
    settings = _dict_or_empty(await db.get_settings())
    return {"active_broker": _active_broker_id(settings)}


@router.post("/active-broker/{broker_id}")
async def set_active_broker(broker_id: str):
    """Set the active broker"""
    from routes.health import update_bot_status
    # FIXED C17: validate enum and config exist before switching
    try:
        broker_type = BrokerType(broker_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid broker: {broker_id}")
    settings = _dict_or_empty(await db.get_settings())
    config, missing_fields = _broker_config_status(settings, broker_id)
    if config is None:
        raise HTTPException(
            status_code=400,
            detail=_broker_config_message(broker_id, missing_fields)
        )
    await db.update_settings({"active_broker": broker_id})
    update_bot_status("active_broker", broker_type)
    await record_operator_event(
        db,
        "broker",
        "active_broker_switched",
        f"Active broker switched to {broker_id}.",
        severity="warning",
        details={"active_broker": broker_id},
    )
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

    settings = _dict_or_empty(await db.get_settings())
    config, missing_fields = _broker_config_status(settings, broker_id)
    if config is None:
        response = {
            "connected": False,
            "broker": broker_id,
            "capabilities": get_broker_capabilities(broker_id),
            "message": _broker_config_message(broker_id, missing_fields),
        }
        if missing_fields:
            response["missing_required_fields"] = missing_fields
        return response

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

    active_broker = _active_broker_id(settings)
    if str(active_broker) == broker_id:
        update_bot_status("broker_connected", connected)

    return {
        "connected": connected,
        "broker": broker_id,
        "capabilities": get_broker_capabilities(broker_id),
        "message": "Connection successful" if connected else "Connection check failed",
    }
