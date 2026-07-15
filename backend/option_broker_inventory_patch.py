"""Alpaca/Tradier open-order and option-position inventory contracts."""
from __future__ import annotations

from typing import Any

from broker_clients import AlpacaClient, TradierClient, _float_price, _int_quantity
from option_contracts import parse_occ_symbol
import live_order_execution_runtime as routing


def _side(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return "BUY" if raw.startswith("buy") else "SELL" if raw.startswith("sell") else raw.upper()


def _order_payload(data: dict, *, broker: str) -> dict:
    symbol = str(data.get("option_symbol") or data.get("symbol") or "").upper()
    contract = {}
    try:
        contract = parse_occ_symbol(symbol)
    except ValueError:
        pass
    return {
        "broker": broker,
        "account_id": str(data.get("account_id") or ""),
        "order_id": str(data.get("id") or data.get("order_id") or ""),
        "client_order_id": str(data.get("client_order_id") or data.get("tag") or ""),
        "status": str(data.get("status") or "unknown").lower().replace("canceled", "cancelled"),
        "side": _side(data.get("side")),
        "quantity": _int_quantity(data.get("qty") or data.get("quantity")),
        "filled_qty": _int_quantity(
            data.get("filled_qty")
            or data.get("filled_quantity")
            or data.get("exec_quantity")
        ),
        "avg_fill_price": _float_price(
            data.get("filled_avg_price")
            or data.get("avg_fill_price")
            or data.get("last_fill_price")
        ),
        "limit_price": _float_price(data.get("limit_price") or data.get("price")),
        "created_at": data.get("created_at") or data.get("create_date") or data.get("transaction_date"),
        **contract,
    }


def _position_payload(data: dict, *, broker: str, account_id: str) -> dict | None:
    symbol = str(data.get("symbol") or data.get("option_symbol") or "").upper()
    try:
        contract = parse_occ_symbol(symbol)
    except ValueError:
        return None
    quantity = _int_quantity(data.get("qty") or data.get("quantity"))
    if quantity == 0:
        return None
    quantity = abs(quantity)
    avg_entry = _float_price(data.get("avg_entry_price") or data.get("average_price"))
    cost_basis = _float_price(data.get("cost_basis"))
    if avg_entry <= 0 and cost_basis > 0 and quantity > 0:
        avg_entry = cost_basis / (quantity * 100.0)
    current = _float_price(
        data.get("current_price")
        or data.get("last")
        or data.get("close")
        or avg_entry
    )
    return {
        "broker": broker,
        "account_id": account_id,
        "quantity": quantity,
        "avg_entry_price": avg_entry,
        "current_price": current,
        "market_value": _float_price(data.get("market_value")) or current * quantity * 100.0,
        "unrealized_pnl": _float_price(data.get("unrealized_pl") or data.get("unrealized_pnl")),
        **contract,
    }


async def _alpaca_get_open_option_orders(self) -> list[dict]:
    session = await self._get_session()
    async with session.get(
        f"{self.config.base_url}/v2/orders",
        headers=self._get_headers(),
        params={"status": "open", "limit": 500, "direction": "asc"},
    ) as response:
        try:
            data = await response.json()
        except Exception:
            data = []
        if response.status != 200 or not isinstance(data, list):
            return []
        return [
            payload
            for item in data
            if (payload := _order_payload(item, broker="alpaca")).get("ticker")
        ]


async def _alpaca_get_option_positions(self) -> list[dict]:
    session = await self._get_session()
    async with session.get(
        f"{self.config.base_url}/v2/positions",
        headers=self._get_headers(),
    ) as response:
        try:
            data = await response.json()
        except Exception:
            data = []
        if response.status != 200 or not isinstance(data, list):
            raise RuntimeError(f"Alpaca positions lookup failed: HTTP {response.status}")
        account_id = str(getattr(self.config, "account_id", "") or "")
        return [
            payload
            for item in data
            if (payload := _position_payload(item, broker="alpaca", account_id=account_id)) is not None
        ]


async def _tradier_get_open_option_orders(self) -> list[dict]:
    session = await self._get_session()
    async with session.get(
        f"https://api.tradier.com/v1/accounts/{self.config.account_id}/orders",
        headers=self._get_headers(),
        params={"includeTags": "true"},
    ) as response:
        try:
            data = await response.json()
        except Exception:
            data = {}
        if response.status != 200:
            return []
        orders = (data.get("orders") or {}).get("order", []) if isinstance(data, dict) else []
        if isinstance(orders, dict):
            orders = [orders]
        terminal = {"filled", "cancelled", "canceled", "rejected", "expired"}
        return [
            payload
            for item in orders or []
            if str(item.get("status") or "").lower() not in terminal
            and (payload := _order_payload(item, broker="tradier")).get("ticker")
        ]


async def _tradier_get_option_positions(self) -> list[dict]:
    session = await self._get_session()
    async with session.get(
        f"https://api.tradier.com/v1/accounts/{self.config.account_id}/positions",
        headers=self._get_headers(),
    ) as response:
        try:
            data = await response.json()
        except Exception:
            data = {}
        if response.status != 200:
            raise RuntimeError(f"Tradier positions lookup failed: HTTP {response.status}")
        positions = (data.get("positions") or {}).get("position", []) if isinstance(data, dict) else []
        if isinstance(positions, dict):
            positions = [positions]
        account_id = str(self.config.account_id or "")
        return [
            payload
            for item in positions or []
            if (payload := _position_payload(item, broker="tradier", account_id=account_id)) is not None
        ]


async def _routing_get_option_positions(self) -> list[dict]:
    client = self._client or self._client_for(self.routed_broker_id)
    getter = getattr(client, "get_option_positions", None)
    if not callable(getter):
        raise RuntimeError(f"{self.routed_broker_id} lacks option-position inventory support")
    return await getter()


async def _routing_get_open_orders(self) -> list[dict]:
    client = self._client or self._client_for(self.routed_broker_id)
    getter = getattr(client, "get_open_orders", None)
    if not callable(getter):
        raise RuntimeError(f"{self.routed_broker_id} lacks open-order inventory support")
    return await getter()


AlpacaClient.get_open_orders = _alpaca_get_open_option_orders
AlpacaClient.get_option_positions = _alpaca_get_option_positions
TradierClient.get_open_orders = _tradier_get_open_option_orders
TradierClient.get_option_positions = _tradier_get_option_positions
routing.JournalledRoutingBrokerClient.get_option_positions = _routing_get_option_positions
routing.JournalledRoutingBrokerClient.get_open_orders = _routing_get_open_orders
