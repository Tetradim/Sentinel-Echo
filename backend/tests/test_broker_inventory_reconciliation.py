import asyncio

from live_order_journal import LiveOrderJournal
import broker_inventory_reconciliation as reconciliation
from option_contracts import parse_occ_symbol


def test_occ_parser_round_trips_broker_symbol():
    parsed = parse_occ_symbol("AAPL260918C00150000")
    assert parsed == {
        "occ_symbol": "AAPL260918C00150000",
        "ticker": "AAPL",
        "expiration": "2026-09-18",
        "option_type": "CALL",
        "strike": 150.0,
    }


class _DB:
    def __init__(self, positions=None):
        self.positions = list(positions or [])
        self.position_updates = []

    async def get_positions(self, status=None):
        return [
            dict(position)
            for position in self.positions
            if status is None or position.get("status") == status
        ]

    async def insert_position(self, position):
        self.positions.append(dict(position))
        return position["id"]

    async def update_position(self, position_id, update):
        self.position_updates.append((position_id, update))
        for position in self.positions:
            if position.get("id") != position_id:
                continue
            if "$set" in update:
                position.update(update["$set"])
            else:
                position.update(update)


class _Client:
    routed_broker_id = "alpaca"
    routed_account_id = "acct-1"

    async def get_option_positions(self):
        return [
            {
                "broker": "alpaca",
                "account_id": "acct-1",
                "occ_symbol": "AAPL260918C00150000",
                "ticker": "AAPL",
                "expiration": "2026-09-18",
                "option_type": "CALL",
                "strike": 150.0,
                "quantity": 2,
                "avg_entry_price": 1.25,
                "current_price": 1.40,
                "unrealized_pnl": 30.0,
            }
        ]

    async def get_open_orders(self):
        return [
            {
                "broker": "alpaca",
                "account_id": "acct-1",
                "order_id": "broker-sell-1",
                "client_order_id": "manual-close-1",
                "status": "submitted",
                "side": "SELL",
                "quantity": 1,
                "filled_qty": 0,
                "avg_fill_price": 0,
                "limit_price": 1.50,
                "occ_symbol": "AAPL260918C00150000",
                "ticker": "AAPL",
                "expiration": "2026-09-18",
                "option_type": "CALL",
                "strike": 150.0,
            }
        ]

    async def close(self):
        return None


def test_inventory_imports_position_before_recovering_open_sell(tmp_path, monkeypatch):
    db = _DB()
    journal = LiveOrderJournal(tmp_path / "journal.json")
    monkeypatch.setattr(reconciliation, "journal", journal)
    monkeypatch.setattr(
        reconciliation,
        "get_configured_broker_client",
        lambda *_args, **_kwargs: _Client(),
    )

    result = asyncio.run(
        reconciliation.reconcile_broker_inventory(
            db,
            {
                "active_broker": "alpaca",
                "broker_configs": {"alpaca": {}},
            },
        )
    )

    assert result["brokers_checked"] == 1
    assert result["positions_imported"] == 1
    assert result["orders_recovered"] == 1
    assert result["errors"] == []

    position = db.positions[0]
    assert position["remaining_quantity"] == 2
    assert position["entry_price"] == 1.25
    assert position["broker"] == "alpaca"
    assert position["simulated"] is False

    order = journal.get("manual-close-1")
    assert order["broker_order_id"] == "broker-sell-1"
    assert order["position_id"] == position["id"]
    assert order["side"] == "SELL"


def test_successful_empty_broker_inventory_closes_stale_local_position(tmp_path, monkeypatch):
    db = _DB(
        positions=[
            {
                "id": "position-stale",
                "ticker": "AAPL",
                "strike": 150.0,
                "option_type": "CALL",
                "expiration": "2026-09-18",
                "entry_price": 1.25,
                "remaining_quantity": 2,
                "original_quantity": 2,
                "broker": "alpaca",
                "status": "open",
                "simulated": False,
            }
        ]
    )

    class EmptyClient(_Client):
        async def get_option_positions(self):
            return []

        async def get_open_orders(self):
            return []

    monkeypatch.setattr(reconciliation, "journal", LiveOrderJournal(tmp_path / "journal.json"))
    monkeypatch.setattr(
        reconciliation,
        "get_configured_broker_client",
        lambda *_args, **_kwargs: EmptyClient(),
    )

    result = asyncio.run(
        reconciliation.reconcile_broker_inventory(
            db,
            {
                "active_broker": "alpaca",
                "broker_configs": {"alpaca": {}},
            },
        )
    )
    assert result["positions_closed"] == 1
    assert db.positions[0]["remaining_quantity"] == 0
    assert db.positions[0]["status"] == "closed"
    assert db.positions[0]["broker_reconciliation_reason"] == "position_absent_at_broker"
