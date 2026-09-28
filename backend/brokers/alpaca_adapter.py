"""Alpaca broker adapter — API-first broker for algorithmic trading."""
import logging
from .base import BrokerAdapter, BrokerOrder, BrokerPosition, BrokerAccountInfo

logger = logging.getLogger("SentinelPulse")


class AlpacaAdapter(BrokerAdapter):
    broker_id = "alpaca"

    def _headers(self):
        return {
            "APCA-API-KEY-ID": self.config.get("api_key", ""),
            "APCA-API-SECRET-KEY": self.config.get("api_secret", ""),
        }

    def _base_url(self):
        return str(self.config.get("base_url") or self.config.get("endpoint") or "https://paper-api.alpaca.markets").rstrip("/")

    async def check_connection(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(f"{self._base_url()}/v2/account", headers=self._headers()) as resp:
                self.connected = resp.status == 200
                return self.connected
        except Exception as e:
            logger.error(f"Alpaca connection error: {e}")
            return False

    async def get_account(self) -> BrokerAccountInfo:
        session = await self._get_session()
        async with session.get(f"{self._base_url()}/v2/account", headers=self._headers()) as resp:
            data = await resp.json()
            return BrokerAccountInfo(
                balance=float(data.get("cash", 0)),
                buying_power=float(data.get("buying_power", 0)),
                equity=float(data.get("equity", 0)),
            )

    async def get_positions(self) -> list[BrokerPosition]:
        session = await self._get_session()
        async with session.get(f"{self._base_url()}/v2/positions", headers=self._headers()) as resp:
            data = await resp.json()
            return [
                BrokerPosition(
                    symbol=p["symbol"],
                    quantity=float(p["qty"]),
                    avg_entry=float(p["avg_entry_price"]),
                    current_price=float(p["current_price"]),
                    market_value=float(p["market_value"]),
                    unrealized_pnl=float(p["unrealized_pl"]),
                )
                for p in data
            ]

    async def place_order(self, order: BrokerOrder) -> BrokerOrder:
        session = await self._get_session()
        payload = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.value.lower(),
            "type": order.order_type.value.lower(),
            "time_in_force": "day",
        }
        if order.limit_price and order.order_type in ("LIMIT", "STOP_LIMIT"):
            payload["limit_price"] = str(order.limit_price)
        if order.stop_price and order.order_type in ("STOP", "STOP_LIMIT"):
            payload["stop_price"] = str(order.stop_price)

        async with session.post(f"{self._base_url()}/v2/orders", headers=self._headers(), json=payload) as resp:
            data = await resp.json()
            if resp.status in (200, 201):
                order.broker_order_id = data.get("id", "")
                order.status = data.get("status", "submitted")
            else:
                order.status = "rejected"
                order.error = data.get("message", f"HTTP {resp.status}")
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        session = await self._get_session()
        async with session.delete(f"{self._base_url()}/v2/orders/{broker_order_id}", headers=self._headers()) as resp:
            return resp.status in (200, 204)

    async def get_quote(self, symbol: str) -> float:
        session = await self._get_session()
        async with session.get(f"{self._base_url()}/v2/stocks/{symbol}/quotes/latest", headers=self._headers()) as resp:
            data = await resp.json()
            return float(data.get("quote", {}).get("ap", 0) or data.get("quote", {}).get("bp", 0))
