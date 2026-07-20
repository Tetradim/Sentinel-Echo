import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import types
import unittest

from discord_ingestion import DiscordIngestionDeps, handle_discord_message
from trade_lifecycle import build_exit_plans, is_exit_alert


MONITORED_CHANNEL_ID = "123"


def discord_message(content, *, channel_id=MONITORED_CHANNEL_ID, author_id="analyst"):
    return types.SimpleNamespace(
        content=content,
        embeds=[],
        author=types.SimpleNamespace(id=author_id),
        channel=types.SimpleNamespace(id=channel_id, name="alerts"),
        created_at=datetime(2026, 6, 16, 14, 42, tzinfo=timezone.utc),
    )


class EchoPaperHarness:
    """In-memory paper adapter driven through Echo's real Discord ingestion path."""

    def __init__(self, *, settings=None):
        self.settings = settings or {
            "auto_trading_enabled": True,
            "simulation_mode": True,
            "source_overrides": {
                MONITORED_CHANNEL_ID: {
                    "enabled": True,
                    "paper_only": True,
                }
            },
        }
        self.alerts = []
        self.positions = []
        self.orders = []
        self.events = []
        self._seen = set()
        self._position_sequence = 0
        self._order_sequence = 0

    def deps(self):
        return DiscordIngestionDeps(
            load_settings=lambda: self.settings,
            insert_alert=self.alerts.append,
            process_trade=self.process_trade,
            update_status=lambda key, value: self.events.append(
                {"event": "status", "key": key, "value": value}
            ),
            is_duplicate_alert=self.is_duplicate_alert,
            resolve_contract_context=self.resolve_contract_context,
        )

    def is_duplicate_alert(self, parsed):
        signature = (
            str(parsed.get("alert_type") or "").lower(),
            str(parsed.get("ticker") or "").upper(),
            float(parsed.get("strike") or 0),
            str(parsed.get("option_type") or "").upper(),
            str(parsed.get("expiration") or ""),
            float(parsed.get("entry_price") or 0),
            float(parsed.get("sell_percentage") or 0),
        )
        if signature in self._seen:
            self.events.append({"event": "duplicate_blocked", "signature": signature})
            return True
        self._seen.add(signature)
        return False

    async def resolve_contract_context(self, parsed, *, include_simulated):
        matches = [
            position
            for position in self.positions
            if position["status"] in {"open", "partial"}
            and position["remaining_quantity"] > 0
            and position["ticker"] == parsed["ticker"]
            and abs(float(position["strike"]) - float(parsed["strike"])) < 0.001
            and position["option_type"] == parsed["option_type"]
            and (include_simulated or not position.get("simulated"))
        ]
        expirations = sorted({position["expiration"] for position in matches})
        if len(expirations) != 1:
            return {
                "reason": (
                    "no unique matching open position"
                    if not expirations
                    else f"matching open positions span multiple expirations: {expirations}"
                )
            }
        return {
            "expiration": expirations[0],
            "position_ids": [position["id"] for position in matches],
        }

    async def process_trade(self, alert, parsed):
        if parsed["alert_type"] in {"buy", "average_down"}:
            quantity = 1 if parsed.get("_context_resolved_from_positions") else 2
            order = self._new_order(
                side="BUY",
                ticker=alert.ticker,
                strike=alert.strike,
                option_type=alert.option_type,
                expiration=alert.expiration,
                quantity=quantity,
                price=alert.entry_price,
                forced_paper=bool(parsed.get("_force_simulation")),
            )
            self._position_sequence += 1
            position = {
                "id": f"pos-{self._position_sequence}",
                "ticker": alert.ticker,
                "strike": alert.strike,
                "option_type": alert.option_type,
                "expiration": alert.expiration,
                "entry_price": alert.entry_price,
                "current_price": alert.entry_price,
                "quantity": quantity,
                "original_quantity": quantity,
                "remaining_quantity": quantity,
                "status": "open",
                "simulated": True,
                "broker": "echo:paper_simulator",
                "trade_ids": [order["client_order_id"]],
            }
            self.positions.append(position)
            self.events.append(
                {"event": "position_opened", "position_id": position["id"], "quantity": quantity}
            )
            return True

        if is_exit_alert(parsed):
            try:
                plans = build_exit_plans(self.positions, parsed, include_simulated=True)
            except ValueError as exc:
                self.events.append({"event": "exit_blocked", "reason": str(exc)})
                return False

            for plan in plans:
                position = plan["position"]
                quantity = plan["quantity"]
                order = self._new_order(
                    side="SELL",
                    ticker=position["ticker"],
                    strike=position["strike"],
                    option_type=position["option_type"],
                    expiration=position["expiration"],
                    quantity=quantity,
                    price=plan["exit_price"],
                    forced_paper=bool(parsed.get("_force_simulation")),
                    position_id=position["id"],
                )
                position["remaining_quantity"] -= quantity
                position["current_price"] = plan["exit_price"]
                position["status"] = "closed" if position["remaining_quantity"] <= 0 else "partial"
                position["trade_ids"].append(order["client_order_id"])
                self.events.append(
                    {
                        "event": "position_updated",
                        "position_id": position["id"],
                        "remaining_quantity": position["remaining_quantity"],
                        "status": position["status"],
                    }
                )
            return bool(plans)

        self.events.append({"event": "unsupported_alert", "alert_type": parsed.get("alert_type")})
        return False

    def _new_order(
        self,
        *,
        side,
        ticker,
        strike,
        option_type,
        expiration,
        quantity,
        price,
        forced_paper,
        position_id=None,
    ):
        self._order_sequence += 1
        order = {
            "client_order_id": f"echo-paper-{self._order_sequence:03d}",
            "broker_adapter": "echo-in-memory-paper-adapter",
            "side": side,
            "ticker": ticker,
            "strike": float(strike),
            "option_type": option_type,
            "expiration": expiration,
            "quantity": int(quantity),
            "limit_price": float(price),
            "position_id": position_id,
            "forced_paper": forced_paper,
            "acknowledgement": "accepted",
            "fill_status": "filled",
            "filled_quantity": int(quantity),
            "filled_price": float(price),
        }
        self.orders.append(order)
        self.events.extend(
            [
                {"event": "order_submitted", "client_order_id": order["client_order_id"], "side": side},
                {"event": "broker_acknowledged", "client_order_id": order["client_order_id"]},
                {"event": "fill", "client_order_id": order["client_order_id"], "quantity": int(quantity)},
            ]
        )
        return order


async def ingest(harness, content, *, channel_id=MONITORED_CHANNEL_ID, author_id="analyst"):
    return await handle_discord_message(
        discord_message(content, channel_id=channel_id, author_id=author_id),
        channel_ids=[MONITORED_CHANNEL_ID],
        deps=harness.deps(),
        bot_user=types.SimpleNamespace(id="echo-bot"),
    )


class EchoDiscordTradeBehaviorTests(unittest.TestCase):
    def test_echo_discord_buy_sell_behavior_and_guards(self):
        report = asyncio.run(self._run_behavior_replay())

        log_path = Path(os.environ.get("ECHO_BEHAVIOR_LOG_PATH", "echo-discord-trade-behavior.json"))
        log_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        self.assertEqual(report["summary"]["buy_orders"], 2)
        self.assertEqual(report["summary"]["sell_orders"], 3)
        self.assertEqual(report["summary"]["contracts_bought"], 3)
        self.assertEqual(report["summary"]["contracts_sold"], 3)
        self.assertEqual(report["summary"]["open_contracts_after_close"], 0)
        self.assertTrue(report["guards"]["duplicate_blocked"])
        self.assertTrue(report["guards"]["wrong_channel_blocked"])
        self.assertTrue(report["guards"]["self_message_blocked"])
        self.assertTrue(report["guards"]["watch_notice_blocked"])
        self.assertTrue(report["guards"]["ambiguous_exit_blocked"])
        self.assertTrue(all(order["forced_paper"] for order in report["orders"]))

    async def _run_behavior_replay(self):
        harness = EchoPaperHarness()

        archive_style_entry = (
            "$SPY\n$756 CALLS\n EXPIRATION 6/16/2026\n"
            "$.37 Entry, $.33 AVG\n@everyone"
        )
        entry = await ingest(harness, archive_style_entry)
        duplicate = await ingest(harness, archive_style_entry)
        readd = await ingest(
            harness,
            "RE-ADDING THE INITIAL SPY $756C ALERT @ $.29",
        )
        trim = await ingest(
            harness,
            "SOLD 50% SPY $756 CALLS HERE AT $.50 FILL\n@everyone",
        )
        close = await ingest(
            harness,
            "SOLD 100% SPY $756 CALLS HERE AT $.65 FILL\n@everyone",
        )

        wrong_channel = await ingest(
            harness,
            archive_style_entry.replace("$.37", "$.38"),
            channel_id="999",
        )
        self_message = await ingest(
            harness,
            archive_style_entry.replace("$.37", "$.39"),
            author_id="echo-bot",
        )
        watch_notice = await ingest(
            harness,
            "QQQ $716C 0DTE ON WATCH NOTICE\n\nENTRY NOT VALID YET\n@everyone",
        )

        ambiguous = EchoPaperHarness()
        ambiguous.positions = [
            {
                "id": "amb-1",
                "ticker": "SPY",
                "strike": 756.0,
                "option_type": "CALL",
                "expiration": "6/16/2026",
                "entry_price": 0.37,
                "current_price": 0.45,
                "quantity": 1,
                "remaining_quantity": 1,
                "status": "open",
                "simulated": True,
                "broker": "echo:paper_simulator",
                "trade_ids": [],
            },
            {
                "id": "amb-2",
                "ticker": "SPY",
                "strike": 756.0,
                "option_type": "CALL",
                "expiration": "6/19/2026",
                "entry_price": 0.40,
                "current_price": 0.45,
                "quantity": 1,
                "remaining_quantity": 1,
                "status": "open",
                "simulated": True,
                "broker": "echo:paper_simulator",
                "trade_ids": [],
            },
        ]
        ambiguous_result = await ingest(
            ambiguous,
            "SOLD 10% SPY $756 CALLS HERE AT $.45 FILL\n@everyone",
        )

        open_contracts = sum(
            position["remaining_quantity"]
            for position in harness.positions
            if position["status"] in {"open", "partial"}
        )
        buy_orders = [order for order in harness.orders if order["side"] == "BUY"]
        sell_orders = [order for order in harness.orders if order["side"] == "SELL"]

        return {
            "test_scope": {
                "execution_path": "Echo handle_discord_message -> parser/context resolver -> process_trade -> build_exit_plans",
                "broker": "Echo in-memory paper adapter; no Alpaca order was submitted",
                "monitored_channel_id": MONITORED_CHANNEL_ID,
            },
            "scenario_results": {
                "initial_entry": entry.__dict__,
                "duplicate_entry": duplicate.__dict__,
                "contextual_readd": readd.__dict__,
                "partial_exit": trim.__dict__,
                "full_exit": close.__dict__,
                "ambiguous_exit_request": ambiguous_result.__dict__,
            },
            "guards": {
                "duplicate_blocked": duplicate.skip_reason == "duplicate alert",
                "wrong_channel_blocked": wrong_channel.skip_reason == "channel not monitored",
                "self_message_blocked": self_message.skip_reason == "self message",
                "watch_notice_blocked": watch_notice.skip_reason == "unparsed",
                "ambiguous_exit_blocked": any(
                    event["event"] == "exit_blocked" for event in ambiguous.events
                ) and not ambiguous.orders,
            },
            "orders": harness.orders,
            "positions": harness.positions,
            "events": harness.events,
            "ambiguous_exit_events": ambiguous.events,
            "summary": {
                "buy_orders": len(buy_orders),
                "sell_orders": len(sell_orders),
                "contracts_bought": sum(order["quantity"] for order in buy_orders),
                "contracts_sold": sum(order["quantity"] for order in sell_orders),
                "open_contracts_after_close": open_contracts,
                "alerts_persisted": len(harness.alerts),
                "paper_orders_only": all(order["forced_paper"] for order in harness.orders),
            },
        }


if __name__ == "__main__":
    unittest.main()
