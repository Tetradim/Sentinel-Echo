import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from live_order_journal import LiveOrderJournal
from option_contracts import build_occ_symbol
import live_order_execution_runtime as runtime


def test_occ_symbol_normalizes_all_supported_date_formats():
    expected = "AAPL260918C00150000"
    for expiration in ("09/18/26", "09/18/2026", "2026-09-18", "260918", "20260918"):
        assert build_occ_symbol("AAPL", expiration, "CALL", 150) == expected
    assert build_occ_symbol("SPY", "2026-09-18", "P", 501.25) == "SPY260918P00501250"


class _DB:
    def __init__(self, positions=None, trades=None):
        self.positions = positions or []
        self.trades = trades or []
        self.inserted = []
        self.updated = []

    async def get_positions(self, status=None):
        return [p for p in self.positions if status is None or p.get("status") == status]

    async def get_trades(self, limit=50):
        return list(self.trades)

    async def insert_trade(self, trade):
        self.inserted.append(dict(trade))
        self.trades.append(dict(trade))
        return trade["id"]

    async def update_trade(self, trade_id, updates):
        self.updated.append((trade_id, dict(updates)))
        for trade in self.trades:
            if trade.get("id") == trade_id:
                trade.update(updates)


class _Client:
    def __init__(self, broker, journal_ref=None):
        self.broker = broker
        self.config = SimpleNamespace(account_id=f"{broker}-acct")
        self.place_calls = 0
        self.journal_ref = journal_ref
        self.connected = True

    async def place_order(self, **kwargs):
        self.place_calls += 1
        if self.journal_ref is not None:
            record = self.journal_ref.get(kwargs["client_order_id"])
            assert record is not None
            assert record["status"] == "submitting"
        return {
            "order_id": f"{self.broker}-order-1",
            "status": "submitted",
            "client_order_id": kwargs["client_order_id"],
        }

    async def get_order_status(self, order_id):
        return {"order_id": order_id, "status": "submitted", "filled_qty": 0, "avg_fill_price": 0}

    async def get_order_by_client_id(self, client_order_id):
        return {
            "order_id": f"{self.broker}-recovered",
            "client_order_id": client_order_id,
            "status": "submitted",
        }

    async def get_open_orders(self):
        return []

    async def close(self):
        return None


def test_live_order_is_journalled_before_broker_network_call(tmp_path, monkeypatch):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    db = _DB()
    clients = {}

    def factory(_settings, broker_id, require_order_status=False):
        client = _Client(str(broker_id), journal)
        clients[str(broker_id)] = client
        return client

    monkeypatch.setattr(runtime, "journal", journal)
    monkeypatch.setattr(runtime, "get_db", lambda: db)
    monkeypatch.setattr(runtime, "_original_factory", factory)

    proxy = runtime.JournalledRoutingBrokerClient(
        {"active_broker": "alpaca"}, "alpaca", require_order_status=True
    )
    result = asyncio.run(
        proxy.place_order(
            ticker="AAPL",
            strike=150,
            option_type="CALL",
            expiration="2026-09-18",
            side="BUY",
            quantity=1,
            price=2.5,
            client_order_id="consolidation-buy-alert-1",
        )
    )
    assert result["order_id"] == "alpaca-order-1"
    assert clients["alpaca"].place_calls == 1
    record = journal.get("consolidation-buy-alert-1")
    assert record["status"] == "submitted"
    assert record["broker_order_id"] == "alpaca-order-1"
    assert record["occ_symbol"] == "AAPL260918C00150000"


def test_sell_routes_to_position_owner_not_global_active_broker(tmp_path, monkeypatch):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    position_id = "position-123"
    db = _DB(
        positions=[
            {
                "id": position_id,
                "ticker": "AAPL",
                "strike": 150,
                "option_type": "CALL",
                "expiration": "2026-09-18",
                "remaining_quantity": 2,
                "entry_price": 2.0,
                "broker": "tradier",
                "status": "open",
            }
        ]
    )
    selected = []

    def factory(_settings, broker_id, require_order_status=False):
        selected.append(str(broker_id))
        return _Client(str(broker_id), journal)

    monkeypatch.setattr(runtime, "journal", journal)
    monkeypatch.setattr(runtime, "get_db", lambda: db)
    monkeypatch.setattr(runtime, "_original_factory", factory)

    proxy = runtime.JournalledRoutingBrokerClient(
        {"active_broker": "alpaca"}, "alpaca", require_order_status=True
    )
    result = asyncio.run(
        proxy.place_order(
            ticker="AAPL",
            strike=150,
            option_type="CALL",
            expiration="2026-09-18",
            side="SELL",
            quantity=1,
            price=3.0,
            client_order_id=f"consolidation-sell-alert-{position_id}",
        )
    )
    assert selected == ["tradier"]
    assert proxy.routed_broker_id == "tradier"
    assert proxy.position_id == position_id
    assert result["broker"] == "tradier"
    assert journal.get(f"consolidation-sell-alert-{position_id}")["position_id"] == position_id


def test_ambiguous_existing_client_id_is_resolved_without_second_submission(tmp_path, monkeypatch):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    client_id = "consolidation-buy-alert-2"
    journal.begin(
        client_id,
        broker="alpaca",
        ticker="AAPL",
        strike=150,
        option_type="CALL",
        expiration="2026-09-18",
        side="BUY",
        quantity=1,
        price=2.5,
    )
    journal.ambiguous(client_id, "timeout")
    client = _Client("alpaca", journal)

    monkeypatch.setattr(runtime, "journal", journal)
    monkeypatch.setattr(runtime, "get_db", lambda: _DB())
    monkeypatch.setattr(runtime, "_original_factory", lambda *_args, **_kwargs: client)

    proxy = runtime.JournalledRoutingBrokerClient(
        {"active_broker": "alpaca"}, "alpaca", require_order_status=True
    )
    result = asyncio.run(
        proxy.place_order(
            ticker="AAPL",
            strike=150,
            option_type="CALL",
            expiration="2026-09-18",
            side="BUY",
            quantity=1,
            price=2.5,
            client_order_id=client_id,
        )
    )
    assert result["order_id"] == "alpaca-recovered"
    assert result["replayed_from_journal"] is True
    assert client.place_calls == 0


def test_live_factory_rejects_incomplete_broker():
    with pytest.raises(Exception, match="Live options execution is available only"):
        runtime.get_configured_broker_client(
            {"active_broker": "ibkr"}, "ibkr", require_order_status=True
        )
