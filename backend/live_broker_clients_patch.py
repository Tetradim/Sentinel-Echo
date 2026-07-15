"""Complete the live Alpaca/Tradier option-order contract.

The original adapters duplicated option-symbol formatting and only exposed
lookup by broker order id. These replacements use one OCC builder, preserve a
client order identifier at the broker, and allow ambiguous submissions to be
resolved without issuing a second order.
"""
from __future__ import annotations

from typing import Any

from broker_clients import (
    AlpacaClient,
    TradierClient,
    OrderValidationError,
    _float_price,
    _int_quantity,
    _tradier_error_reason,
)
from option_contracts import build_occ_symbol


def _order_status_payload(data: dict, *, broker: str) -> dict:
    raw_status = str(data.get("status") or "unknown").lower()
    status = {
        "partially_filled": "partial",
        "canceled": "cancelled",
    }.get(raw_status, raw_status)
    return {
        "order_id": str(data.get("id") or data.get("order_id") or ""),
        "client_order_id": str(
            data.get("client_order_id") or data.get("tag") or ""
        ),
        "status": status,
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
        "reason": str(
            data.get("reject_reason")
            or data.get("cancel_reason")
            or data.get("reason_description")
            or ""
        ),
        "broker": broker,
    }


async def _alpaca_place_order(
    self,
    ticker: str,
    strike: float,
    option_type: str,
    expiration: str,
    side: str,
    quantity: int,
    price: float,
    client_order_id: str | None = None,
) -> dict:
    try:
        params = self._validate_and_normalize(
            ticker, strike, option_type, expiration, side, quantity, price
        )
    except OrderValidationError as exc:
        return {"error": f"Validation failed: {exc}"}

    if not self.connected:
        await self.check_connection()
    if not self.connected:
        return {"error": "Not connected to Alpaca"}

    try:
        symbol = build_occ_symbol(
            params["ticker"],
            params["expiration"],
            params["option_type"],
            params["strike"],
        )
    except ValueError as exc:
        return {"error": str(exc)}

    order_data: dict[str, Any] = {
        "symbol": symbol,
        "qty": params["quantity"],
        "side": params["side"].lower(),
        "type": "limit",
        "limit_price": str(params["price"]),
        "time_in_force": "day",
    }
    if client_order_id:
        order_data["client_order_id"] = client_order_id

    session = await self._get_session()
    async with session.post(
        f"{self.config.base_url}/v2/orders",
        headers=self._get_headers(),
        json=order_data,
    ) as response:
        try:
            data = await response.json()
        except Exception:
            data = {}
        if response.status in (200, 201):
            payload = _order_status_payload(data, broker="alpaca")
            payload["status"] = payload["status"] or "submitted"
            payload["order_id"] = str(data.get("id") or "")
            payload["client_order_id"] = str(
                data.get("client_order_id") or client_order_id or ""
            )
            return payload
        return {"error": str(data.get("message") or f"Order failed: HTTP {response.status}")}


async def _alpaca_get_order_by_client_id(self, client_order_id: str) -> dict:
    session = await self._get_session()
    async with session.get(
        f"{self.config.base_url}/v2/orders:by_client_order_id",
        headers=self._get_headers(),
        params={"client_order_id": client_order_id},
    ) as response:
        try:
            data = await response.json()
        except Exception:
            data = {}
        if response.status == 200 and isinstance(data, dict):
            return _order_status_payload(data, broker="alpaca")
        return {
            "status": "not_found" if response.status == 404 else "error",
            "client_order_id": client_order_id,
            "reason": str(data.get("message") or f"HTTP {response.status}"),
            "broker": "alpaca",
        }


async def _alpaca_get_open_orders(self) -> list[dict]:
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
        return [_order_status_payload(item, broker="alpaca") for item in data]


async def _tradier_place_order(
    self,
    ticker: str,
    strike: float,
    option_type: str,
    expiration: str,
    side: str,
    quantity: int,
    price: float,
    client_order_id: str | None = None,
) -> dict:
    try:
        params = self._validate_and_normalize(
            ticker, strike, option_type, expiration, side, quantity, price
        )
    except OrderValidationError as exc:
        return {"error": f"Validation failed: {exc}"}

    if not self.connected:
        await self.check_connection()
    if not self.connected:
        return {"error": "Not connected to Tradier"}

    try:
        symbol = build_occ_symbol(
            params["ticker"],
            params["expiration"],
            params["option_type"],
            params["strike"],
        )
    except ValueError as exc:
        return {"error": str(exc)}

    order_data: dict[str, Any] = {
        "class": "option",
        "symbol": params["ticker"],
        "option_symbol": symbol,
        "side": "buy_to_open" if params["side"] == "BUY" else "sell_to_close",
        "quantity": params["quantity"],
        "type": "limit",
        "price": params["price"],
        "duration": "day",
    }
    if client_order_id:
        order_data["tag"] = client_order_id

    session = await self._get_session()
    async with session.post(
        f"https://api.tradier.com/v1/accounts/{self.config.account_id}/orders",
        headers=self._get_headers(),
        data=order_data,
    ) as response:
        try:
            data = await response.json()
        except Exception:
            data = {}
        if response.status in (200, 201):
            order = data.get("order") if isinstance(data, dict) else {}
            if not isinstance(order, dict):
                order = {}
            return {
                "order_id": str(order.get("id") or ""),
                "client_order_id": str(order.get("tag") or client_order_id or ""),
                "status": str(order.get("status") or "submitted").lower(),
                "broker": "tradier",
            }
        return {"error": _tradier_error_reason(data, f"Order failed: HTTP {response.status}")}


async def _tradier_get_order_by_client_id(self, client_order_id: str) -> dict:
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
            return {
                "status": "error",
                "client_order_id": client_order_id,
                "reason": _tradier_error_reason(data, f"HTTP {response.status}"),
                "broker": "tradier",
            }
        orders = (data.get("orders") or {}).get("order", []) if isinstance(data, dict) else []
        if isinstance(orders, dict):
            orders = [orders]
        for order in orders or []:
            if str(order.get("tag") or "") == client_order_id:
                return _order_status_payload(order, broker="tradier")
        return {
            "status": "not_found",
            "client_order_id": client_order_id,
            "reason": "No Tradier order matched the client order tag",
            "broker": "tradier",
        }


async def _tradier_get_open_orders(self) -> list[dict]:
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
            _order_status_payload(order, broker="tradier")
            for order in orders or []
            if str(order.get("status") or "").lower() not in terminal
        ]


AlpacaClient.place_order = _alpaca_place_order
AlpacaClient.get_order_by_client_id = _alpaca_get_order_by_client_id
AlpacaClient.get_open_orders = _alpaca_get_open_orders
TradierClient.place_order = _tradier_place_order
TradierClient.get_order_by_client_id = _tradier_get_order_by_client_id
TradierClient.get_open_orders = _tradier_get_open_orders
