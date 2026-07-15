"""Reconcile Echo's live option ledger from broker positions and open orders."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from typing import Any

from live_order_journal import journal
from live_order_execution_runtime import get_configured_broker_client
from option_contracts import build_occ_symbol


logger = logging.getLogger(__name__)
_SUPPORTED = {"alpaca", "tradier"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _configured_brokers(settings: dict) -> list[str]:
    configured = {
        str(value).lower()
        for value in (settings.get("broker_configs") or {}).keys()
    }
    active = settings.get("active_broker")
    if hasattr(active, "value"):
        active = active.value
    if active:
        configured.add(str(active).lower())
    return sorted(configured & _SUPPORTED)


def _contract_key(position: dict) -> str:
    return build_occ_symbol(
        position.get("ticker"),
        position.get("expiration"),
        position.get("option_type"),
        position.get("strike"),
    )


def _position_id(broker: str, account_id: str, occ_symbol: str) -> str:
    digest = hashlib.sha256(
        f"{broker}|{account_id}|{occ_symbol}".encode("utf-8")
    ).hexdigest()[:24]
    return f"broker-position-{digest}"


def _order_client_id(broker: str, order_id: str) -> str:
    digest = hashlib.sha256(f"{broker}|{order_id}".encode("utf-8")).hexdigest()[:24]
    return f"broker-recovered-{broker}-{digest}"


async def reconcile_broker_inventory(db, settings: dict) -> dict:
    local_positions = await db.get_positions("open")
    local_positions += await db.get_positions("partial")
    local_by_key: dict[tuple[str, str], dict] = {}
    for position in local_positions:
        if position.get("simulated"):
            continue
        broker = str(position.get("broker") or "").lower()
        try:
            local_by_key[(broker, _contract_key(position))] = position
        except Exception:
            continue

    imported_positions = 0
    updated_positions = 0
    closed_positions = 0
    recovered_orders = 0
    brokers_checked = 0
    errors: list[str] = []

    for broker in _configured_brokers(settings):
        client = get_configured_broker_client(
            settings,
            broker,
            require_order_status=True,
        )
        client.routed_broker_id = broker
        try:
            broker_positions = await client.get_option_positions()
            open_orders = await client.get_open_orders()
            brokers_checked += 1
        except Exception as exc:
            errors.append(f"{broker}: {exc}")
            logger.exception("Broker inventory lookup failed for %s: %s", broker, exc)
            await client.close()
            continue

        seen: set[tuple[str, str]] = set()
        for broker_position in broker_positions:
            quantity = abs(_int(broker_position.get("quantity")))
            if quantity <= 0:
                continue
            occ_symbol = str(broker_position.get("occ_symbol") or "")
            key = (broker, occ_symbol)
            seen.add(key)
            existing = local_by_key.get(key)
            avg_entry = _float(broker_position.get("avg_entry_price"))
            current = _float(broker_position.get("current_price")) or avg_entry
            account_id = str(broker_position.get("account_id") or "")
            common = {
                "ticker": broker_position.get("ticker"),
                "strike": _float(broker_position.get("strike")),
                "option_type": broker_position.get("option_type"),
                "expiration": broker_position.get("expiration"),
                "entry_price": avg_entry,
                "current_price": current,
                "remaining_quantity": quantity,
                "total_cost": avg_entry * quantity * 100.0,
                "broker": broker,
                "broker_account_id": account_id,
                "status": "open",
                "simulated": False,
                "unrealized_pnl": _float(broker_position.get("unrealized_pnl")),
                "broker_occ_symbol": occ_symbol,
                "broker_reconciled_at": _now(),
            }
            if existing:
                original = max(_int(existing.get("original_quantity")), quantity)
                await db.update_position(
                    str(existing.get("id")),
                    {
                        "$set": {
                            **common,
                            "original_quantity": original,
                            "highest_price": max(
                                _float(existing.get("highest_price")),
                                current,
                                avg_entry,
                            ),
                        }
                    },
                )
                updated_positions += 1
            else:
                position_id = _position_id(broker, account_id, occ_symbol)
                document = {
                    "id": position_id,
                    **common,
                    "original_quantity": quantity,
                    "opened_at": _now(),
                    "realized_pnl": 0.0,
                    "trade_ids": [],
                    "highest_price": max(current, avg_entry),
                    "broker_inventory_imported": True,
                }
                await db.insert_position(document)
                local_by_key[key] = document
                imported_positions += 1

        # A successful broker inventory response is authoritative for this
        # account. Locally open positions absent at the broker are closed rather
        # than left available for an invalid SELL.
        for key, local in list(local_by_key.items()):
            if key[0] != broker or key in seen:
                continue
            await db.update_position(
                str(local.get("id")),
                {
                    "$set": {
                        "remaining_quantity": 0,
                        "status": "closed",
                        "closed_at": _now(),
                        "broker_reconciled_at": _now(),
                        "broker_reconciliation_reason": "position_absent_at_broker",
                    }
                },
            )
            closed_positions += 1

        # Refresh the local position map after imports so recovered SELL orders
        # can be assigned to the account and position that actually owns them.
        refreshed = await db.get_positions("open")
        refreshed += await db.get_positions("partial")
        refreshed_by_key: dict[tuple[str, str], dict] = {}
        for position in refreshed:
            if position.get("simulated"):
                continue
            try:
                refreshed_by_key[
                    (str(position.get("broker") or "").lower(), _contract_key(position))
                ] = position
            except Exception:
                continue

        for order in open_orders:
            order_id = str(order.get("order_id") or "")
            if not order_id:
                continue
            existing_record = journal.find_by_broker_order_id(order_id, broker)
            if existing_record:
                journal.mark_from_broker(
                    str(existing_record.get("client_order_id") or ""),
                    order,
                )
                continue

            client_id = str(order.get("client_order_id") or "") or _order_client_id(
                broker,
                order_id,
            )
            occ_symbol = str(order.get("occ_symbol") or "")
            position = refreshed_by_key.get((broker, occ_symbol))
            side = str(order.get("side") or "").upper()
            fields = {
                "broker": broker,
                "account_id": str(order.get("account_id") or getattr(client, "routed_account_id", "") or ""),
                "ticker": order.get("ticker"),
                "strike": _float(order.get("strike")),
                "option_type": order.get("option_type"),
                "expiration": order.get("expiration"),
                "occ_symbol": occ_symbol,
                "side": side,
                "quantity": _int(order.get("quantity")),
                "price": _float(order.get("limit_price")) or _float(order.get("avg_fill_price")) or 0.01,
                "position_id": str((position or {}).get("id") or "") or None,
                "position_entry_price": _float((position or {}).get("entry_price")),
                "broker_inventory_recovered": True,
            }
            if side == "SELL" and not fields["position_id"]:
                errors.append(
                    f"{broker} open SELL {order_id} has no matching broker position"
                )
                logger.critical(
                    "Open broker SELL %s at %s has no matching position owner",
                    order_id,
                    broker,
                )
                continue
            try:
                journal.begin(client_id, **fields)
                journal.acknowledge(
                    client_id,
                    order_id,
                    status=order.get("status") or "submitted",
                    **fields,
                )
                journal.mark_from_broker(client_id, order)
                recovered_orders += 1
            except Exception as exc:
                errors.append(f"{broker} order {order_id}: {exc}")
                logger.exception(
                    "Could not reconstruct broker order %s at %s: %s",
                    order_id,
                    broker,
                    exc,
                )

        await client.close()

    return {
        "brokers_checked": brokers_checked,
        "positions_imported": imported_positions,
        "positions_updated": updated_positions,
        "positions_closed": closed_positions,
        "orders_recovered": recovered_orders,
        "errors": errors,
    }
