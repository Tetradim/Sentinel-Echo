"""Durable live-order routing beneath Echo's entry and exit handlers.

The server's legacy handlers construct useful alert/trade records but historically
called the broker before those records were durable. This runtime wraps the
broker factory so every live call is journalled before network submission,
ambiguous calls are resolved by deterministic client id, and SELL orders route
to the broker that owns the selected position.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import order_execution
from database import get_db
from fill_reconciliation import OrderContext
from live_order_journal import journal
from option_contracts import build_occ_symbol


logger = logging.getLogger(__name__)
_SUPPORTED_LIVE_BROKERS = {"alpaca", "tradier"}
_original_factory = order_execution.get_configured_broker_client


def _safe_token(value: Any) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip())
    return token.strip("-_")


def _broker_name(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip().lower()


def _contract_key(ticker: str, expiration: str, option_type: str, strike: float) -> str:
    return build_occ_symbol(ticker, expiration, option_type, strike)


async def _candidate_positions(
    *,
    ticker: str,
    strike: float,
    option_type: str,
    expiration: str,
) -> list[dict]:
    db = get_db()
    positions = await db.get_positions("open")
    positions += await db.get_positions("partial")
    requested_key = _contract_key(ticker, expiration, option_type, strike)
    matches = []
    for position in positions:
        try:
            position_key = _contract_key(
                position.get("ticker"),
                position.get("expiration"),
                position.get("option_type"),
                position.get("strike"),
            )
        except Exception:
            continue
        if position_key != requested_key:
            continue
        if int(float(position.get("remaining_quantity") or 0)) <= 0:
            continue
        matches.append(position)
    return matches


async def _resolve_position_owner(
    *,
    client_order_id: str,
    ticker: str,
    strike: float,
    option_type: str,
    expiration: str,
    quantity: int,
) -> dict:
    candidates = await _candidate_positions(
        ticker=ticker,
        strike=strike,
        option_type=option_type,
        expiration=expiration,
    )
    for position in candidates:
        token = _safe_token(position.get("id"))
        if token and token in client_order_id:
            if int(float(position.get("remaining_quantity") or 0)) < int(quantity):
                raise RuntimeError(
                    f"Exit quantity {quantity} exceeds position {position.get('id')} "
                    f"remaining quantity {position.get('remaining_quantity')}"
                )
            return position

    eligible = [
        position
        for position in candidates
        if int(float(position.get("remaining_quantity") or 0)) >= int(quantity)
    ]
    if len(eligible) == 1:
        return eligible[0]
    if not eligible:
        raise RuntimeError("No matching broker-owned option position is available to exit")
    raise RuntimeError(
        "Multiple brokers own matching option positions; the exit command must identify position_id"
    )


class JournalledRoutingBrokerClient:
    def __init__(self, settings: Any, requested_broker: str, *, require_order_status: bool):
        self.settings = settings
        self.requested_broker = _broker_name(requested_broker)
        self.routed_broker_id = self.requested_broker
        self.routed_account_id = ""
        self.position_id: str | None = None
        self._require_order_status = require_order_status
        self._client = None

    def _client_for(self, broker_id: str):
        broker_id = _broker_name(broker_id)
        if broker_id not in _SUPPORTED_LIVE_BROKERS:
            raise order_execution.BrokerConfigurationError(
                f"Live options execution is implemented only for {sorted(_SUPPORTED_LIVE_BROKERS)}; "
                f"{broker_id or 'missing broker'} lacks a complete submit/status/recovery contract"
            )
        client = _original_factory(
            self.settings,
            broker_id,
            require_order_status=self._require_order_status,
        )
        self._client = client
        self.routed_broker_id = broker_id
        self.routed_account_id = str(getattr(getattr(client, "config", None), "account_id", "") or "")
        return client

    async def _resolve_existing(self, record: dict, client) -> dict | None:
        broker_order_id = str(record.get("broker_order_id") or "")
        if broker_order_id:
            return {
                "order_id": broker_order_id,
                "client_order_id": record.get("client_order_id"),
                "status": record.get("status") or "submitted",
                "broker": record.get("broker") or self.routed_broker_id,
                "replayed_from_journal": True,
            }
        lookup = getattr(client, "get_order_by_client_id", None)
        if callable(lookup):
            found = await lookup(str(record.get("client_order_id") or ""))
            found_id = str((found or {}).get("order_id") or "")
            if found_id:
                journal.acknowledge(
                    str(record["client_order_id"]),
                    found_id,
                    status=(found or {}).get("status") or "acknowledged",
                    broker=self.routed_broker_id,
                    account_id=self.routed_account_id,
                )
                return {**found, "replayed_from_journal": True}
        return None

    async def place_order(
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
        client_id = str(client_order_id or "").strip()
        if not client_id:
            raise RuntimeError("Live options order requires deterministic client_order_id")

        normalized_side = str(side or "").upper()
        position = None
        broker_id = self.requested_broker
        if normalized_side == "SELL":
            position = await _resolve_position_owner(
                client_order_id=client_id,
                ticker=ticker,
                strike=strike,
                option_type=option_type,
                expiration=expiration,
                quantity=quantity,
            )
            broker_id = _broker_name(position.get("broker"))
            self.position_id = str(position.get("id") or "") or None

        client = self._client_for(broker_id)
        existing = journal.get(client_id)
        if existing and str(existing.get("status") or "").lower() in {
            "submitting",
            "ambiguous",
            "acknowledged",
            "submitted",
            "pending",
            "working",
            "partial",
            "working_unconfirmed",
            "filled",
        }:
            resolved = await self._resolve_existing(existing, client)
            if resolved:
                return resolved
            return {
                "error": (
                    f"Order {client_id} has ambiguous prior delivery; broker lookup did not "
                    "prove absence, so Echo will not submit a duplicate"
                ),
                "client_order_id": client_id,
                "status": "ambiguous",
                "reconciliation_required": True,
                "broker": broker_id,
            }

        record_fields = {
            "broker": broker_id,
            "account_id": self.routed_account_id,
            "ticker": str(ticker).upper(),
            "strike": float(strike),
            "option_type": str(option_type).upper(),
            "expiration": str(expiration),
            "occ_symbol": _contract_key(ticker, expiration, option_type, strike),
            "side": normalized_side,
            "quantity": int(quantity),
            "price": float(price),
            "position_id": self.position_id,
            "position_entry_price": (
                float(position.get("entry_price") or 0) if position else None
            ),
        }
        journal.begin(client_id, **record_fields)

        try:
            result = await client.place_order(
                ticker=ticker,
                strike=strike,
                option_type=option_type,
                expiration=expiration,
                side=normalized_side,
                quantity=int(quantity),
                price=float(price),
                client_order_id=client_id,
            )
        except Exception as exc:
            journal.ambiguous(client_id, str(exc), **record_fields)
            raise

        result = result if isinstance(result, dict) else {"error": "Broker returned non-object order result"}
        broker_order_id = str(result.get("order_id") or "")
        if broker_order_id:
            journal.acknowledge(
                client_id,
                broker_order_id,
                status=result.get("status") or "acknowledged",
                **record_fields,
            )
            return {
                **result,
                "broker": broker_id,
                "account_id": self.routed_account_id,
                "client_order_id": client_id,
            }

        error = str(result.get("error") or "Broker did not return an order id")
        journal.fail(client_id, error, **record_fields)
        return {**result, "error": error, "broker": broker_id, "client_order_id": client_id}

    async def get_order_status(self, order_id: str) -> dict:
        client = self._client or self._client_for(self.routed_broker_id)
        result = await client.get_order_status(order_id)
        if isinstance(result, dict):
            result.setdefault("broker", self.routed_broker_id)
        return result

    async def get_order_by_client_id(self, client_order_id: str) -> dict:
        client = self._client or self._client_for(self.routed_broker_id)
        lookup = getattr(client, "get_order_by_client_id", None)
        if not callable(lookup):
            return {"status": "error", "reason": "Broker lacks client-order-id lookup"}
        return await lookup(client_order_id)

    async def get_open_orders(self) -> list[dict]:
        client = self._client or self._client_for(self.routed_broker_id)
        getter = getattr(client, "get_open_orders", None)
        return await getter() if callable(getter) else []

    async def close(self) -> None:
        if self._client is None:
            return
        result = self._client.close()
        if hasattr(result, "__await__"):
            await result


def get_configured_broker_client(
    settings: Any,
    broker_id: str | None = None,
    *,
    require_order_status: bool = False,
):
    if not require_order_status:
        return _original_factory(settings, broker_id, require_order_status=False)
    selected = _broker_name(broker_id or (settings or {}).get("active_broker"))
    if selected not in _SUPPORTED_LIVE_BROKERS:
        raise order_execution.BrokerConfigurationError(
            f"Live options execution is available only for {sorted(_SUPPORTED_LIVE_BROKERS)}; "
            f"selected broker is {selected or 'missing'}"
        )
    return JournalledRoutingBrokerClient(
        settings,
        selected,
        require_order_status=True,
    )


async def recover_journalled_orders(db, settings: dict) -> int:
    """Reconstruct locally missing pending trades from the pre-submit journal."""
    trades = await db.get_trades(5000)
    by_order_id = {
        str(trade.get("order_id")): trade
        for trade in trades
        if str(trade.get("order_id") or "")
    }
    by_client_id = {
        str(trade.get("client_order_id")): trade
        for trade in trades
        if str(trade.get("client_order_id") or "")
    }
    recovered = 0

    for record in journal.records(active_only=True):
        client_id = str(record.get("client_order_id") or "")
        broker_id = _broker_name(record.get("broker"))
        if not client_id or broker_id not in _SUPPORTED_LIVE_BROKERS:
            continue
        proxy = JournalledRoutingBrokerClient(settings, broker_id, require_order_status=True)
        proxy.routed_broker_id = broker_id
        proxy.position_id = record.get("position_id")
        try:
            broker_order_id = str(record.get("broker_order_id") or "")
            if broker_order_id:
                broker_update = await proxy.get_order_status(broker_order_id)
                broker_update.setdefault("order_id", broker_order_id)
            else:
                broker_update = await proxy.get_order_by_client_id(client_id)
                broker_order_id = str((broker_update or {}).get("order_id") or "")
            if broker_order_id:
                journal.mark_from_broker(client_id, broker_update)
            else:
                journal.ambiguous(
                    client_id,
                    str((broker_update or {}).get("reason") or "Broker order not yet located"),
                )
                continue

            existing = by_order_id.get(broker_order_id) or by_client_id.get(client_id)
            trade_id = str((existing or {}).get("id") or "")
            if not trade_id:
                digest = hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:24]
                trade_id = f"journal-{digest}"

            side = str(record.get("side") or "BUY").upper()
            if side == "SELL" and not record.get("position_id"):
                logger.critical(
                    "Cannot reconstruct SELL %s because position ownership is missing",
                    client_id,
                )
                continue

            context = OrderContext(
                trade_id=trade_id,
                order_id=broker_order_id,
                side=side,
                ticker=str(record.get("ticker") or "").upper(),
                strike=float(record.get("strike") or 0),
                option_type=str(record.get("option_type") or "").upper(),
                expiration=str(record.get("expiration") or ""),
                requested_quantity=int(record.get("quantity") or 0),
                broker=broker_id,
                position_id=record.get("position_id"),
                alert_price=float(record.get("price") or 0),
                simulated=False,
            )
            trade_doc = {
                "id": trade_id,
                "ticker": context.ticker,
                "strike": context.strike,
                "option_type": context.option_type,
                "expiration": context.expiration,
                "entry_price": float(
                    record.get("position_entry_price")
                    or record.get("price")
                    or 0.01
                ),
                "exit_price": float(record.get("price") or 0) if side == "SELL" else None,
                "quantity": context.requested_quantity,
                "side": side,
                "status": "pending",
                "broker": broker_id,
                "order_id": broker_order_id,
                "client_order_id": client_id,
                "simulated": False,
                "reconciliation_context": context.to_dict(),
                "requested_quantity": context.requested_quantity,
                "monitor_state": "scheduled",
                "submission_journal_recovered": True,
            }
            if existing:
                await db.update_trade(trade_id, trade_doc)
            else:
                await db.insert_trade(trade_doc)
                recovered += 1
        except Exception as exc:
            logger.exception("Failed to recover journalled order %s: %s", client_id, exc)
        finally:
            await proxy.close()
    return recovered


order_execution.get_configured_broker_client = get_configured_broker_client
