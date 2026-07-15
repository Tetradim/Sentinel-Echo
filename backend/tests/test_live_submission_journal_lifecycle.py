import asyncio
from types import SimpleNamespace

import pytest

from live_order_journal import LiveOrderJournal
import live_trade_state_patch as trade_state


class _DB:
    def __init__(self):
        self.alert_updates = []

    async def update_alert(self, alert_id, updates):
        self.alert_updates.append((alert_id, dict(updates)))

    async def get_trades(self, limit=50):
        return []

    async def update_trade(self, trade_id, updates):
        return None


def _sell_fields(position_id="position-1"):
    return {
        "broker": "alpaca",
        "account_id": "acct-1",
        "ticker": "AAPL",
        "strike": 150.0,
        "option_type": "CALL",
        "expiration": "2026-09-18",
        "occ_symbol": "AAPL260918C00150000",
        "side": "SELL",
        "quantity": 1,
        "price": 3.0,
        "position_id": position_id,
    }


def test_second_unresolved_exit_for_same_position_is_blocked(tmp_path):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    journal.begin("exit-1", **_sell_fields())

    with pytest.raises(RuntimeError, match="already has unresolved exit order"):
        journal.begin("exit-2", **_sell_fields())


def test_terminal_broker_state_releases_exit_reservation(tmp_path):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    journal.begin("exit-1", **_sell_fields())
    journal.acknowledge("exit-1", "broker-order-1", status="submitted")
    journal.mark_from_broker(
        "exit-1",
        {
            "order_id": "broker-order-1",
            "status": "cancelled",
            "filled_qty": 0,
            "avg_fill_price": 0,
            "reason": "cancelled",
        },
    )

    second = journal.begin("exit-2", **_sell_fields())
    assert second["status"] == "submitting"
    assert journal.get("exit-1")["exit_reserved_quantity"] == 0


def test_duplicate_alert_with_durable_order_does_not_call_legacy_processor(tmp_path, monkeypatch):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    alert_id = "alert-duplicate"
    client_id = f"consolidation-buy-{alert_id}"
    journal.begin(
        client_id,
        broker="alpaca",
        ticker="AAPL",
        strike=150.0,
        option_type="CALL",
        expiration="2026-09-18",
        side="BUY",
        quantity=1,
        price=2.5,
    )
    journal.acknowledge(client_id, "broker-order-1", status="submitted")

    db = _DB()
    calls = {"legacy": 0}

    async def legacy(*_args, **_kwargs):
        calls["legacy"] += 1

    monkeypatch.setattr(trade_state, "journal", journal)
    monkeypatch.setattr(trade_state, "get_db", lambda: db)
    monkeypatch.setattr(trade_state, "_original_process_trade", legacy)

    alert = SimpleNamespace(id=alert_id)
    asyncio.run(
        trade_state.process_trade_with_broker_fill_state(
            alert,
            {"alert_type": "buy"},
        )
    )

    assert calls["legacy"] == 0
    assert db.alert_updates[-1][1]["order_submitted"] is True
    assert db.alert_updates[-1][1]["trade_executed"] is False
