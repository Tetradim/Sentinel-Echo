import pathlib
import sys


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import database_sqlite
import pre_task_order_persistence as persistence
from fill_reconciliation import OrderContext


def _context():
    return OrderContext(
        trade_id="trade-1",
        order_id="order-1",
        side="BUY",
        ticker="SPY",
        strike=500.0,
        option_type="CALL",
        expiration="2026-09-18",
        requested_quantity=2,
        broker="alpaca",
        alert_id="alert-1",
    )


def test_sqlite_recovery_context_is_committed_synchronously(monkeypatch):
    updates = []
    monkeypatch.setattr(persistence.server, "USE_SQLITE", True)
    monkeypatch.setattr(
        database_sqlite,
        "update_trade",
        lambda trade_id, values: updates.append((trade_id, values)),
    )

    persistence._persist_recovery_context_sync(_context())

    assert updates[0][0] == "trade-1"
    values = updates[0][1]
    assert values["order_id"] == "order-1"
    assert values["requested_quantity"] == 2
    assert values["monitor_state"] == "scheduled"
    assert values["reconciliation_context"]["trade_id"] == "trade-1"


def test_wrapper_persists_before_returning_monitor_coroutine(monkeypatch):
    events = []
    context = _context()

    def persist(order_context):
        assert order_context is context
        events.append("persist")

    def original(*args, **kwargs):
        events.append("monitor")
        return "monitor-coroutine"

    monkeypatch.setattr(persistence, "_persist_recovery_context_sync", persist)
    monkeypatch.setattr(persistence, "_original_monitor_fill", original)

    result = persistence.monitor_fill_with_pre_task_persistence(
        order_context=context,
        broker_client=object(),
        db=object(),
        settings={},
    )

    assert result == "monitor-coroutine"
    assert events == ["persist", "monitor"]
