import asyncio

from live_order_journal import LiveOrderJournal
import explicit_exit_continuation_patch as continuation


def _record(journal, client_id, *, quantity=3, filled=1, status="cancelled"):
    journal.begin(
        client_id,
        broker="alpaca",
        ticker="AAPL",
        strike=150.0,
        option_type="CALL",
        expiration="2026-09-18",
        side="SELL",
        quantity=quantity,
        price=1.5,
        position_id="position-1",
    )
    journal.acknowledge(client_id, f"broker-{client_id}", status="submitted")
    journal.mark_from_broker(
        client_id,
        {
            "order_id": f"broker-{client_id}",
            "status": status,
            "filled_qty": filled,
            "avg_fill_price": 1.5 if filled else 0,
        },
    )


def test_cancelled_explicit_exit_requests_retry_for_outstanding_quantity(tmp_path, monkeypatch):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    _record(journal, "consolidation-sell-alert-position-1", quantity=3, filled=1)
    monkeypatch.setattr(continuation, "journal", journal)

    pending = continuation._retryable_explicit_exit("position-1")
    assert pending["outstanding_quantity"] == 2
    assert continuation._exit_reason_with_explicit_retry(
        {"id": "position-1", "entry_price": 1.0},
        {},
        mark=1.1,
        highest=1.1,
    ) == "requested_exit_retry"


def test_requested_exit_retry_submits_only_outstanding_quantity(tmp_path, monkeypatch):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    _record(journal, "consolidation-sell-alert-position-1", quantity=3, filled=1)
    captured = {}

    async def submit(_db, _settings, position, reason, quote):
        captured.update({"quantity": position["remaining_quantity"], "reason": reason})
        return True

    monkeypatch.setattr(continuation, "journal", journal)
    monkeypatch.setattr(continuation, "_original_submit_exit", submit)

    result = asyncio.run(
        continuation._submit_exit_with_requested_quantity(
            object(),
            {},
            {"id": "position-1", "remaining_quantity": 5},
            "requested_exit_retry",
            {"mid": 1.2},
        )
    )
    assert result is True
    assert captured == {"quantity": 2, "reason": "requested_exit_retry"}


def test_regular_risk_exit_is_not_retried_as_explicit_request(tmp_path, monkeypatch):
    journal = LiveOrderJournal(tmp_path / "orders.json")
    _record(journal, "echo-risk-stop_loss-position-1-1", quantity=2, filled=0)
    monkeypatch.setattr(continuation, "journal", journal)
    assert continuation._retryable_explicit_exit("position-1") is None
