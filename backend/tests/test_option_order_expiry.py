import asyncio
from datetime import datetime, timedelta, timezone

from live_order_journal import LiveOrderJournal
import option_execution_quote_patch as quote_patch
import option_order_expiry_patch as expiry


class _QuoteRejectedClient:
    async def get_option_quote(self, *_args):
        raise RuntimeError("spread too wide")


def test_quote_rejection_is_definitive_before_broker_post():
    calls = {"broker_post": 0}

    async def broker_post(*_args, **_kwargs):
        calls["broker_post"] += 1
        return {"order_id": "should-not-exist"}

    result = asyncio.run(
        quote_patch._quote_aware_place(
            broker_post,
            _QuoteRejectedClient(),
            ticker="AAPL",
            strike=150,
            option_type="CALL",
            expiration="2026-09-18",
            side="BUY",
            quantity=1,
            price=1.0,
            client_order_id="entry-1",
        )
    )
    assert calls["broker_post"] == 0
    assert result["status"] == "rejected_pre_submit"
    assert result["pre_submission_rejected"] is True


class _Proxy:
    routed_broker_id = "alpaca"

    def __init__(self):
        self.cancel_calls = []

    async def cancel_order(self, order_id):
        self.cancel_calls.append(order_id)
        return True


def test_aged_working_order_is_cancelled_and_refetched(tmp_path, monkeypatch):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    journal.begin(
        "exit-1",
        broker="alpaca",
        ticker="AAPL",
        strike=150,
        option_type="CALL",
        expiration="2026-09-18",
        side="SELL",
        quantity=1,
        price=2.0,
        position_id="position-1",
    )
    journal.acknowledge("exit-1", "broker-order-1", status="submitted")
    journal.update(
        "exit-1",
        acknowledged_at=(datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(),
    )
    statuses = iter(
        [
            {"order_id": "broker-order-1", "broker": "alpaca", "status": "submitted"},
            {"order_id": "broker-order-1", "broker": "alpaca", "status": "cancelled"},
        ]
    )

    async def current(*_args, **_kwargs):
        return next(statuses)

    monkeypatch.setenv("ECHO_EXIT_ORDER_TTL_SECONDS", "10")
    monkeypatch.setattr(expiry, "journal", journal)
    monkeypatch.setattr(expiry, "_current_get_order_status", current)
    proxy = _Proxy()

    result = asyncio.run(expiry._status_with_expiry(proxy, "broker-order-1"))
    assert proxy.cancel_calls == ["broker-order-1"]
    assert result["status"] == "cancelled"
    record = journal.get("exit-1")
    assert record["cancel_request_accepted"] is True
