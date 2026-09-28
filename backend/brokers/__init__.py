"""
Sentinel Pulse — Multi-Broker Adapter Layer

Architecture:
  BrokerAdapter (ABC)  <-- common interface with aiohttp session pooling
     ├── AlpacaAdapter        (official API)
     ├── IBKRAdapter          (TWS/Gateway REST)
     ├── TDAmeritradeAdapter  (Schwab OAuth)
     ├── TradierAdapter       (REST API)
     ├── RobinhoodAdapter     (robin_stocks session)
     ├── TradeStationAdapter  (OAuth REST)
     ├── ThinkorswimAdapter   (Schwab OAuth)
     ├── WebullAdapter        (unofficial)
     ├── WealthsimpleAdapter  (unofficial)
"""
from .base import BrokerAdapter, BrokerOrder, BrokerPosition, BrokerAccountInfo, BrokerRiskWarning, BrokerInfo
from .registry import BROKER_REGISTRY, get_broker_adapter, get_broker_info

__all__ = [
    "BrokerAdapter", "BrokerOrder", "BrokerPosition", "BrokerAccountInfo",
    "BrokerRiskWarning", "BrokerInfo",
    "BROKER_REGISTRY", "get_broker_adapter", "get_broker_info",
]
