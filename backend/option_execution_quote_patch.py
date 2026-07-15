"""Executable option quotes, spread-aware pricing and broker cancellation."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import os
import time
from typing import Any

from broker_clients import AlpacaClient, TradierClient
from live_order_journal import journal
from option_contracts import build_occ_symbol
import live_order_execution_runtime as routing


_current_alpaca_place = AlpacaClient.place_order
_current_tradier_place = TradierClient.place_order


def _num(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _positive_env(name: str, default: float) -> float:
    value = _num(os.getenv(name, default))
    return value if value > 0 else default


def _timestamp_epoch(value: Any) -> float:
    if isinstance(value, (int, float)):
        number = float(value)
        while number > 10_000_000_000:
            number /= 1000.0
        return number
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        number = float(raw)
        while number > 10_000_000_000:
            number /= 1000.0
        return number
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _validate_quote(snapshot: dict) -> dict:
    bid = _num(snapshot.get("bid"))
    ask = _num(snapshot.get("ask"))
    if bid <= 0 or ask <= 0 or ask < bid:
        raise RuntimeError(
            f"Non-executable option quote for {snapshot.get('symbol')}: bid={bid}, ask={ask}"
        )
    mid = (bid + ask) / 2.0
    spread = ask - bid
    spread_pct = spread / mid * 100.0 if mid > 0 else float("inf")
    max_spread = _positive_env("ECHO_MAX_OPTION_SPREAD_PCT", 20.0)
    if spread_pct > max_spread:
        raise RuntimeError(
            f"Option spread {spread_pct:.2f}% for {snapshot.get('symbol')} exceeds {max_spread:.2f}%"
        )
    quote_epoch = _timestamp_epoch(snapshot.get("quote_timestamp"))
    received = _num(snapshot.get("received_at_epoch")) or time.time()
    age = max(0.0, time.time() - (quote_epoch or received))
    max_age = _positive_env("ECHO_MAX_OPTION_QUOTE_AGE_SECONDS", 5.0)
    if age > max_age:
        raise RuntimeError(
            f"Option quote for {snapshot.get('symbol')} is stale ({age:.2f}s > {max_age:.2f}s)"
        )
    return {
        **snapshot,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "spread_pct": spread_pct,
        "age_seconds": age,
    }


def _limit_price(side: str, requested: float, quote: dict) -> float:
    side = str(side or "").upper()
    midpoint = round((quote["bid"] + quote["ask"]) / 2.0, 2)
    if side == "BUY":
        max_slippage = _positive_env("ECHO_MAX_ENTRY_SLIPPAGE_PCT", 5.0)
        requested = _num(requested)
        cap = requested * (1 + max_slippage / 100.0) if requested > 0 else quote["ask"]
        candidate = min(quote["ask"], max(quote["bid"], midpoint))
        if candidate > cap + 1e-9:
            raise RuntimeError(
                f"Executable option entry ${candidate:.2f} exceeds alert/slippage cap ${cap:.2f}"
            )
        return round(candidate, 2)
    if side == "SELL":
        # A midpoint limit improves price while remaining bounded by the current
        # executable bid. Aged exits are cancelled and re-priced by the position
        # supervisor using a new deterministic attempt id.
        return round(max(quote["bid"], midpoint), 2)
    raise RuntimeError(f"Unsupported option side: {side}")


async def _alpaca_option_quote(self, ticker, strike, option_type, expiration) -> dict:
    symbol = build_occ_symbol(ticker, expiration, option_type, strike)
    session = await self._get_session()
    async with session.get(
        "https://data.alpaca.markets/v1beta1/options/quotes/latest",
        headers=self._get_headers(),
        params={"symbols": symbol},
    ) as response:
        data = await response.json()
        if response.status != 200:
            raise RuntimeError(data.get("message") or f"Alpaca option quote HTTP {response.status}")
        quote = (data.get("quotes") or {}).get(symbol) or {}
        return _validate_quote(
            {
                "broker": "alpaca",
                "symbol": symbol,
                "bid": quote.get("bp"),
                "ask": quote.get("ap"),
                "bid_size": quote.get("bs"),
                "ask_size": quote.get("as"),
                "quote_timestamp": quote.get("t"),
                "received_at_epoch": time.time(),
            }
        )


async def _tradier_option_quote(self, ticker, strike, option_type, expiration) -> dict:
    symbol = build_occ_symbol(ticker, expiration, option_type, strike)
    session = await self._get_session()
    async with session.get(
        "https://api.tradier.com/v1/markets/quotes",
        headers=self._get_headers(),
        params={"symbols": symbol, "greeks": "false"},
    ) as response:
        data = await response.json()
        if response.status != 200:
            raise RuntimeError(f"Tradier option quote HTTP {response.status}: {data}")
        quote = (data.get("quotes") or {}).get("quote") or {}
        if isinstance(quote, list):
            quote = quote[0] if quote else {}
        return _validate_quote(
            {
                "broker": "tradier",
                "symbol": symbol,
                "bid": quote.get("bid"),
                "ask": quote.get("ask"),
                "bid_size": quote.get("bidsize"),
                "ask_size": quote.get("asksize"),
                "quote_timestamp": quote.get("bid_date") or quote.get("ask_date") or quote.get("trade_date"),
                "received_at_epoch": time.time(),
            }
        )


async def _quote_aware_place(current, self, **kwargs):
    # Quote lookup and price validation occur before the broker order POST. Their
    # failure is definitive: no order was submitted, so return a rejected result
    # and let the routing journal mark it failed rather than ambiguous.
    try:
        quote = await self.get_option_quote(
            kwargs["ticker"],
            kwargs["strike"],
            kwargs["option_type"],
            kwargs["expiration"],
        )
        submitted_price = _limit_price(kwargs["side"], kwargs["price"], quote)
    except Exception as exc:
        return {
            "status": "rejected_pre_submit",
            "error": str(exc),
            "pre_submission_rejected": True,
        }

    client_id = str(kwargs.get("client_order_id") or "")
    if client_id and journal.get(client_id):
        journal.update(
            client_id,
            price=submitted_price,
            requested_alert_price=_num(kwargs.get("price")),
            execution_quote=quote,
            quote_checked_at=datetime.now(timezone.utc).isoformat(),
        )
    result = await current(self, **{**kwargs, "price": submitted_price})
    if isinstance(result, dict):
        result["submitted_limit_price"] = submitted_price
        result["execution_quote"] = quote
    return result


async def _alpaca_quote_aware_place(self, **kwargs):
    return await _quote_aware_place(_current_alpaca_place, self, **kwargs)


async def _tradier_quote_aware_place(self, **kwargs):
    return await _quote_aware_place(_current_tradier_place, self, **kwargs)


async def _alpaca_cancel_order(self, order_id: str) -> bool:
    session = await self._get_session()
    async with session.delete(
        f"{self.config.base_url}/v2/orders/{order_id}",
        headers=self._get_headers(),
    ) as response:
        return response.status in {200, 202, 204}


async def _tradier_cancel_order(self, order_id: str) -> bool:
    session = await self._get_session()
    async with session.delete(
        f"https://api.tradier.com/v1/accounts/{self.config.account_id}/orders/{order_id}",
        headers=self._get_headers(),
    ) as response:
        return response.status in {200, 202, 204}


async def _routing_get_option_quote(self, ticker, strike, option_type, expiration) -> dict:
    client = self._client or self._client_for(self.routed_broker_id)
    getter = getattr(client, "get_option_quote", None)
    if not callable(getter):
        raise RuntimeError(f"{self.routed_broker_id} lacks live option quote support")
    return await getter(ticker, strike, option_type, expiration)


async def _routing_cancel_order(self, order_id: str) -> bool:
    client = self._client or self._client_for(self.routed_broker_id)
    cancel = getattr(client, "cancel_order", None)
    if not callable(cancel):
        raise RuntimeError(f"{self.routed_broker_id} lacks order cancellation support")
    return bool(await cancel(order_id))


AlpacaClient.get_option_quote = _alpaca_option_quote
TradierClient.get_option_quote = _tradier_option_quote
AlpacaClient.place_order = _alpaca_quote_aware_place
TradierClient.place_order = _tradier_quote_aware_place
AlpacaClient.cancel_order = _alpaca_cancel_order
TradierClient.cancel_order = _tradier_cancel_order
routing.JournalledRoutingBrokerClient.get_option_quote = _routing_get_option_quote
routing.JournalledRoutingBrokerClient.cancel_order = _routing_cancel_order
