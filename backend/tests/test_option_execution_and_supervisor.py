import asyncio
import time
from types import SimpleNamespace

import pytest

from live_order_journal import LiveOrderJournal
import live_order_execution_runtime as routing
import option_execution_quote_patch as quotes
import option_position_supervisor as supervisor


def test_quote_validation_rejects_unprofitable_wide_spread(monkeypatch):
    monkeypatch.setenv("ECHO_MAX_OPTION_SPREAD_PCT", "10")
    with pytest.raises(RuntimeError, match="exceeds"):
        quotes._validate_quote(
            {
                "symbol": "AAPL260918C00150000",
                "bid": 1.0,
                "ask": 1.5,
                "received_at_epoch": time.time(),
            }
        )


def test_buy_limit_uses_midpoint_but_respects_alert_slippage_cap(monkeypatch):
    monkeypatch.setenv("ECHO_MAX_ENTRY_SLIPPAGE_PCT", "5")
    quote = {"bid": 1.00, "ask": 1.10}
    assert quotes._limit_price("BUY", 1.05, quote) == 1.05
    with pytest.raises(RuntimeError, match="slippage cap"):
        quotes._limit_price("BUY", 0.90, quote)


def test_routing_client_exposes_live_option_quote_method():
    assert hasattr(routing.JournalledRoutingBrokerClient, "get_option_quote")


def test_exit_reason_uses_stop_trailing_and_profit_thresholds():
    position = {"entry_price": 1.0}
    assert supervisor._exit_reason(
        position,
        {"stop_loss_enabled": True, "stop_loss_percentage": 20},
        mark=0.79,
        highest=1.0,
    ) == "stop_loss"
    assert supervisor._exit_reason(
        position,
        {
            "trailing_stop_enabled": True,
            "trailing_stop_type": "percent",
            "trailing_stop_percent": 10,
        },
        mark=1.30,
        highest=1.50,
    ) == "trailing_stop"
    assert supervisor._exit_reason(
        position,
        {"take_profit_enabled": True, "take_profit_percentage": 25},
        mark=1.30,
        highest=1.30,
    ) == "take_profit"


class _DB:
    def __init__(self):
        self.position_updates = []

    async def get_settings(self):
        return {
            "active_broker": "alpaca",
            "take_profit_enabled": True,
            "take_profit_percentage": 20,
        }

    async def get_positions(self, status=None):
        if status == "open":
            return [
                {
                    "id": "position-1",
                    "ticker": "AAPL",
                    "strike": 150,
                    "option_type": "CALL",
                    "expiration": "2026-09-18",
                    "entry_price": 1.0,
                    "remaining_quantity": 1,
                    "highest_price": 1.1,
                    "broker": "alpaca",
                    "status": "open",
                    "simulated": False,
                }
            ]
        return []

    async def update_position(self, position_id, update):
        self.position_updates.append((position_id, update))


class _QuoteClient:
    routed_broker_id = "alpaca"

    async def get_option_quote(self, *_args):
        return {
            "bid": 1.29,
            "ask": 1.31,
            "mid": 1.30,
            "spread_pct": 1.54,
            "received_at_epoch": time.time(),
        }

    async def close(self):
        return None


def test_supervisor_submits_profitable_live_position_exit(tmp_path, monkeypatch):
    db = _DB()
    captured = []

    async def submit(_db, _settings, position, reason, quote):
        captured.append((position["id"], reason, quote["mid"]))
        return True

    monkeypatch.setattr(supervisor, "journal", LiveOrderJournal(tmp_path / "orders.json"))
    monkeypatch.setattr(
        supervisor,
        "get_configured_broker_client",
        lambda *_args, **_kwargs: _QuoteClient(),
    )
    monkeypatch.setattr(supervisor, "_submit_exit", submit)

    result = asyncio.run(supervisor.supervise_once(db))
    assert result == {"checked": 1, "submitted": 1}
    assert captured == [("position-1", "take_profit", 1.30)]
    position_update = db.position_updates[0][1]["$set"]
    assert position_update["current_price"] == 1.30
    assert position_update["highest_price"] == 1.30
    assert position_update["unrealized_pnl"] == pytest.approx(30.0)
