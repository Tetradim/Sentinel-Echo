"""Broker registry — all supported brokers ordered LOW risk → HIGH risk."""
from .base import BrokerAdapter, BrokerInfo, BrokerRiskWarning, BrokerRiskLevel

BROKER_REGISTRY: dict[str, BrokerInfo] = {
    # --- LOW RISK ---
    "alpaca": BrokerInfo(
        id="alpaca", name="Alpaca",
        description="Commission-free API-first broker built for algorithmic trading.",
        supported=True,
        auth_fields=["api_key", "api_secret", "base_url"],
        risk_warning=BrokerRiskWarning(BrokerRiskLevel.LOW,
            "Alpaca is designed for algorithmic trading with a robust REST and WebSocket API. Very low risk of restrictions."),
        docs_url="https://docs.alpaca.markets/", color="#22c55e",
    ),
    "ibkr": BrokerInfo(
        id="ibkr", name="Interactive Brokers (IBKR)",
        description="Professional-grade broker with full API support via TWS/Gateway.",
        supported=True,
        auth_fields=["gateway_url", "account_id"],
        risk_warning=BrokerRiskWarning(BrokerRiskLevel.LOW,
            "IBKR is designed for algorithmic trading and provides robust TWS/Gateway APIs. Low risk of restrictions."),
        docs_url="https://interactivebrokers.github.io/", color="#e11d48",
    ),
    "tradier": BrokerInfo(
        id="tradier", name="Tradier",
        description="Developer-friendly broker with a clean REST API and competitive pricing.",
        supported=True,
        auth_fields=["access_token", "account_id"],
        risk_warning=BrokerRiskWarning(BrokerRiskLevel.LOW,
            "Tradier is developer-friendly with an official API designed for automated trading. Low risk of restrictions."),
        docs_url="https://documentation.tradier.com/", color="#8b5cf6",
    ),
    "tradestation": BrokerInfo(
        id="tradestation", name="TradeStation",
        description="Professional trading platform with OAuth REST API.",
        supported=True,
        auth_fields=["ts_client_id", "ts_client_secret", "ts_refresh_token"],
        risk_warning=BrokerRiskWarning(BrokerRiskLevel.LOW,
            "TradeStation provides an official API for algorithmic trading. Low risk of restrictions for API users."),
        docs_url="https://api.tradestation.com/docs/", color="#0066cc",
    ),
    # --- MEDIUM RISK ---
    "td_ameritrade": BrokerInfo(
        id="td_ameritrade", name="TD Ameritrade (Schwab)",
        description="Now part of Charles Schwab. OAuth-based REST API for trading.",
        supported=True,
        auth_fields=["client_id", "refresh_token"],
        risk_warning=BrokerRiskWarning(BrokerRiskLevel.MEDIUM,
            "Schwab permits algorithmic trading through their official API but requires app registration. High-frequency patterns may trigger review."),
        docs_url="https://developer.schwab.com/", color="#3b82f6",
    ),
    "thinkorswim": BrokerInfo(
        id="thinkorswim", name="Thinkorswim (Schwab)",
        description="Professional trading platform by Charles Schwab. Same API as TD Ameritrade.",
        supported=True,
        auth_fields=["tos_consumer_key", "tos_refresh_token", "tos_account_id"],
        risk_warning=BrokerRiskWarning(BrokerRiskLevel.MEDIUM,
            "Thinkorswim uses the Schwab API. App registration required. Moderate risk for high-frequency patterns."),
        docs_url="https://developer.schwab.com/", color="#ff6600",
    ),
    # --- HIGH RISK ---
    "robinhood": BrokerInfo(
        id="robinhood", name="Robinhood",
        description="Commission-free trading app. Uses browser-like session authentication.",
        supported=True,
        auth_fields=["username", "password", "mfa_code"],
        risk_warning=BrokerRiskWarning(BrokerRiskLevel.HIGH,
            "Robinhood actively monitors for automated trading patterns and may restrict or permanently ban accounts. Use at your own risk."),
        docs_url="https://robinhood.com/", color="#00c805",
    ),
    "webull": BrokerInfo(
        id="webull", name="Webull",
        description="Commission-free trading with advanced charting. Unofficial API.",
        supported=True,
        auth_fields=["username", "password", "device_id", "trade_token"],
        risk_warning=BrokerRiskWarning(BrokerRiskLevel.HIGH,
            "Webull does not offer an official public API. Third-party libraries rely on reverse-engineered endpoints. Account bans possible."),
        docs_url="https://www.webull.com/", color="#f59e0b",
    ),
    "wealthsimple": BrokerInfo(
        id="wealthsimple", name="Wealthsimple Trade",
        description="Canadian commission-free trading platform (stocks/ETFs).",
        supported=True,
        auth_fields=["ws_email", "ws_password", "ws_otp_code"],
        risk_warning=BrokerRiskWarning(BrokerRiskLevel.HIGH,
            "Wealthsimple does not offer an official trading API. Relies on undocumented endpoints. Restrictions are highly likely."),
        docs_url="https://www.wealthsimple.com/", color="#f97316",
    ),
}


def get_broker_info(broker_id: str) -> BrokerInfo | None:
    return BROKER_REGISTRY.get(broker_id)


def get_broker_adapter(broker_id: str, credentials: dict) -> BrokerAdapter | None:
    """Factory: instantiate the correct adapter for a given broker."""
    if broker_id == "alpaca":
        from .alpaca_adapter import AlpacaAdapter
        return AlpacaAdapter(credentials)
    if broker_id == "ibkr":
        from .ibkr_adapter import IBKRAdapter
        return IBKRAdapter(credentials)
    if broker_id == "td_ameritrade":
        from .tda_adapter import TDAmeritradeAdapter
        return TDAmeritradeAdapter(credentials)
    if broker_id == "tradier":
        from .tradier_adapter import TradierAdapter
        return TradierAdapter(credentials)
    if broker_id == "robinhood":
        from .robinhood_adapter import RobinhoodAdapter
        return RobinhoodAdapter(credentials)
    if broker_id == "tradestation":
        from .tradestation_adapter import TradeStationAdapter
        return TradeStationAdapter(credentials)
    if broker_id == "thinkorswim":
        from .thinkorswim_adapter import ThinkorswimAdapter
        return ThinkorswimAdapter(credentials)
    if broker_id == "webull":
        from .webull_adapter import WebullAdapter
        return WebullAdapter(credentials)
    if broker_id == "wealthsimple":
        from .wealthsimple_adapter import WealthsimpleAdapter
        return WealthsimpleAdapter(credentials)
    return None
