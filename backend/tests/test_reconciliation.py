import asyncio
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeReconciliationDb:
    async def get_operator_events(self, limit=100):
        return [
            {
                "id": "event-accepted",
                "timestamp": "2026-06-22T14:26:00Z",
                "action": "bridge_alert_decision",
                "details": {
                    "event_id": "bridge-accepted",
                    "parsed": {"ticker": "SPY"},
                    "decision": {
                        "status": "accepted",
                        "alert_inserted": True,
                        "alert_id": "alert-1",
                        "trade_requested": True,
                        "trade_request_reason": "auto trading enabled",
                    },
                    "source": {
                        "key": "chrome-alerts",
                        "override_matched": True,
                        "min_parser_confidence": "medium",
                    },
                    "parser": {
                        "confidence": "medium",
                    },
                },
            },
            {
                "id": "event-skipped",
                "timestamp": "2026-06-22T14:23:00Z",
                "action": "bridge_alert_decision",
                "details": {
                    "event_id": "bridge-skipped",
                    "parsed": {"ticker": "QQQ"},
                    "decision": {
                        "status": "skipped",
                        "alert_inserted": False,
                        "alert_id": "",
                        "trade_requested": False,
                        "skip_reason": "parser confidence low below required medium",
                    },
                },
            },
            {
                "id": "event-other",
                "timestamp": "2026-06-22T14:20:00Z",
                "action": "test_alert_created",
                "details": {},
            },
        ]

    async def get_alerts(self, limit=100):
        return [
            {
                "id": "alert-1",
                "ticker": "SPY",
                "alert_type": "buy",
                "trade_executed": True,
                "processed": True,
            },
            {
                "id": "alert-2",
                "ticker": "QQQ",
                "alert_type": "buy",
                "trade_executed": False,
                "processed": True,
            },
        ]

    async def get_trades(self, limit=100):
        return [
            {
                "id": "trade-1",
                "alert_id": "alert-1",
                "ticker": "SPY",
                "status": "pending",
                "order_id": "order-1",
                "simulated": False,
            }
        ]

    async def get_positions(self, status=None):
        return [
            {
                "id": "position-1",
                "ticker": "SPY",
                "status": "open",
                "trade_ids": ["trade-1"],
                "simulated": False,
            }
        ]


class FakeSerializedDecisionDb:
    async def get_alerts(self, limit=100):
        return []

    async def get_trades(self, limit=100):
        return []

    async def get_positions(self, status=None):
        return []

    async def get_operator_events(self, limit=100):
        return [
            {
                "id": "event-string-bools",
                "timestamp": "2026-06-22T14:23:00Z",
                "action": "bridge_alert_decision",
                "details": {
                    "event_id": "bridge-string-bools",
                    "parsed": {"ticker": "SPY"},
                    "decision": {
                        "status": "skipped",
                        "alert_inserted": "false",
                        "trade_requested": "false",
                        "skip_reason": "source override required for chrome bridge",
                    },
                },
            }
        ]


class FakeAcceptedBridgeMissingSourceProofDb:
    async def get_alerts(self, limit=100):
        return [
            {
                "id": "alert-accepted-without-source-proof",
                "ticker": "SPY",
                "alert_type": "buy",
                "trade_executed": True,
                "processed": True,
            }
        ]

    async def get_trades(self, limit=100):
        return [
            {
                "id": "trade-accepted-without-source-proof",
                "alert_id": "alert-accepted-without-source-proof",
                "ticker": "SPY",
                "status": "filled",
                "order_id": "order-accepted-without-source-proof",
                "simulated": False,
            }
        ]

    async def get_positions(self, status=None):
        return [
            {
                "id": "position-accepted-without-source-proof",
                "ticker": "SPY",
                "status": "open",
                "trade_ids": ["trade-accepted-without-source-proof"],
                "simulated": False,
            }
        ]

    async def get_operator_events(self, limit=100):
        return [
            {
                "id": "event-accepted-without-source-proof",
                "timestamp": "2026-06-22T14:30:00Z",
                "action": "bridge_alert_decision",
                "details": {
                    "contract_version": "chrome.discord.message.v1",
                    "event_id": "bridge-accepted-without-source-proof",
                    "channel": {
                        "id": "chrome-alerts",
                        "url": "https://discord.com/channels/1/chrome-alerts",
                    },
                    "author": {
                        "id": "mike",
                        "name": "MikeInvesting",
                    },
                    "parsed": {"ticker": "SPY"},
                    "decision": {
                        "status": "accepted",
                        "alert_inserted": True,
                        "alert_id": "alert-accepted-without-source-proof",
                        "trade_requested": True,
                    },
                },
            }
        ]


class FakeTradeRequestedMissingTradeDb:
    async def get_alerts(self, limit=100):
        return [
            {
                "id": "alert-trade-requested-no-trade",
                "ticker": "SPY",
                "alert_type": "buy",
                "trade_executed": False,
                "processed": False,
            }
        ]

    async def get_trades(self, limit=100):
        return []

    async def get_positions(self, status=None):
        return []

    async def get_operator_events(self, limit=100):
        return [
            {
                "id": "event-trade-requested-no-trade",
                "timestamp": "2026-06-22T14:35:00Z",
                "action": "bridge_alert_decision",
                "details": {
                    "contract_version": "chrome.discord.message.v1",
                    "event_id": "bridge-trade-requested-no-trade",
                    "parsed": {"ticker": "SPY"},
                    "decision": {
                        "status": "accepted",
                        "alert_inserted": True,
                        "alert_id": "alert-trade-requested-no-trade",
                        "trade_requested": True,
                        "trade_request_reason": "auto trading enabled",
                    },
                    "source": {
                        "key": "chrome-alerts",
                        "override_matched": True,
                        "min_parser_confidence": "medium",
                    },
                    "parser": {
                        "confidence": "medium",
                    },
                },
            }
        ]


class FakeAcceptedBridgeMissingParserProofDb:
    async def get_alerts(self, limit=100):
        return [
            {
                "id": "alert-accepted-without-parser-proof",
                "ticker": "SPY",
                "alert_type": "buy",
                "trade_executed": True,
                "processed": True,
            }
        ]

    async def get_trades(self, limit=100):
        return [
            {
                "id": "trade-accepted-without-parser-proof",
                "alert_id": "alert-accepted-without-parser-proof",
                "ticker": "SPY",
                "status": "filled",
                "order_id": "order-accepted-without-parser-proof",
                "simulated": False,
            }
        ]

    async def get_positions(self, status=None):
        return [
            {
                "id": "position-accepted-without-parser-proof",
                "ticker": "SPY",
                "status": "open",
                "trade_ids": ["trade-accepted-without-parser-proof"],
                "simulated": False,
            }
        ]

    async def get_operator_events(self, limit=100):
        return [
            {
                "id": "event-accepted-without-parser-proof",
                "timestamp": "2026-06-22T14:40:00Z",
                "action": "bridge_alert_decision",
                "details": {
                    "contract_version": "chrome.discord.message.v1",
                    "event_id": "bridge-accepted-without-parser-proof",
                    "parsed": {"ticker": "SPY"},
                    "decision": {
                        "status": "accepted",
                        "alert_inserted": True,
                        "alert_id": "alert-accepted-without-parser-proof",
                        "trade_requested": True,
                        "trade_request_reason": "auto trading enabled",
                    },
                    "source": {
                        "key": "chrome-alerts",
                        "override_matched": True,
                        "min_parser_confidence": "medium",
                    },
                },
            }
        ]


class ReconciliationTests(unittest.TestCase):
    def test_reconciliation_links_alert_trade_and_position(self):
        from reconciliation import build_reconciliation_rows

        rows = asyncio.run(build_reconciliation_rows(FakeReconciliationDb()))
        by_alert = {row["alert_id"]: row for row in rows}

        self.assertEqual(by_alert["alert-1"]["trade_id"], "trade-1")
        self.assertEqual(by_alert["alert-1"]["position_id"], "position-1")
        self.assertEqual(by_alert["alert-1"]["attention_reason"], "order pending fill")
        self.assertEqual(by_alert["alert-2"]["attention_reason"], "processed alert has no trade")

    def test_reconciliation_summary_counts_only_unresolved_real_rows(self):
        from reconciliation import summarize_reconciliation_rows

        summary = summarize_reconciliation_rows(
            [
                {"attention_reason": "order pending fill", "simulated": False},
                {"attention_reason": "entry trade has no position", "simulated": True},
                {"attention_reason": "", "simulated": False},
            ]
        )

        self.assertEqual(summary["row_count"], 3)
        self.assertEqual(summary["unresolved_count"], 1)
        self.assertEqual(summary["simulated_unresolved_count"], 1)
        self.assertEqual(summary["unresolved_reasons"], ["order pending fill"])

    def test_alert_chain_report_includes_bridge_decisions_and_stored_alerts(self):
        from reconciliation import build_alert_chain_report

        report = asyncio.run(build_alert_chain_report(FakeReconciliationDb()))
        by_key = {row["chain_key"]: row for row in report["rows"]}

        self.assertEqual(report["summary"]["total"], 3)
        self.assertEqual(report["summary"]["accepted_count"], 2)
        self.assertEqual(report["summary"]["skipped_count"], 1)
        self.assertEqual(report["summary"]["attention_count"], 2)
        self.assertFalse(report["summary"]["deterministic"])

        accepted = by_key["bridge:bridge-accepted"]
        self.assertEqual(accepted["alert_id"], "alert-1")
        self.assertEqual(accepted["trade_id"], "trade-1")
        self.assertEqual(accepted["position_id"], "position-1")
        self.assertEqual(accepted["status"], "attention")
        self.assertEqual(accepted["attention_reason"], "order pending fill")

        skipped = by_key["bridge:bridge-skipped"]
        self.assertEqual(skipped["status"], "blocked")
        self.assertTrue(skipped["deterministic"])
        self.assertEqual(skipped["decision_reason"], "parser confidence low below required medium")

        stored = by_key["alert:alert-2"]
        self.assertEqual(stored["source"], "stored_alert")
        self.assertEqual(stored["status"], "attention")
        self.assertEqual(stored["attention_reason"], "processed alert has no trade")

    def test_alert_chain_report_parses_serialized_bridge_decision_booleans(self):
        from reconciliation import build_alert_chain_report

        report = asyncio.run(build_alert_chain_report(FakeSerializedDecisionDb()))
        row = report["rows"][0]

        self.assertFalse(row["alert_inserted"])
        self.assertFalse(row["trade_requested"])
        self.assertEqual(report["summary"]["alert_inserted_count"], 0)
        self.assertEqual(report["summary"]["trade_requested_count"], 0)

    def test_alert_chain_report_flags_accepted_bridge_alert_without_source_policy_proof(self):
        from reconciliation import build_alert_chain_report

        report = asyncio.run(build_alert_chain_report(FakeAcceptedBridgeMissingSourceProofDb()))
        row = report["rows"][0]

        self.assertEqual(row["status"], "attention")
        self.assertEqual(row["attention_reason"], "accepted bridge alert missing source policy proof")
        self.assertFalse(row["deterministic"])
        self.assertEqual(row["channel_id"], "chrome-alerts")
        self.assertEqual(row["channel_url"], "https://discord.com/channels/1/chrome-alerts")
        self.assertEqual(row["author_id"], "mike")
        self.assertFalse(row["source_override_matched"])
        self.assertEqual(report["summary"]["attention_reasons"], ["accepted bridge alert missing source policy proof"])

    def test_alert_chain_report_flags_trade_request_without_linked_trade(self):
        from reconciliation import build_alert_chain_report

        report = asyncio.run(build_alert_chain_report(FakeTradeRequestedMissingTradeDb()))
        row = report["rows"][0]

        self.assertTrue(row["trade_requested"])
        self.assertEqual(row["trade_id"], "")
        self.assertEqual(row["status"], "attention")
        self.assertEqual(row["attention_reason"], "trade requested but no linked trade")
        self.assertFalse(row["deterministic"])
        self.assertEqual(report["summary"]["attention_reasons"], ["trade requested but no linked trade"])

    def test_alert_chain_report_flags_accepted_bridge_alert_without_parser_confidence_proof(self):
        from reconciliation import build_alert_chain_report

        report = asyncio.run(build_alert_chain_report(FakeAcceptedBridgeMissingParserProofDb()))
        row = report["rows"][0]

        self.assertEqual(row["status"], "attention")
        self.assertEqual(row["attention_reason"], "accepted bridge alert missing parser confidence proof")
        self.assertEqual(row["parser_confidence"], "")
        self.assertFalse(row["deterministic"])
        self.assertEqual(
            report["summary"]["attention_reasons"],
            ["accepted bridge alert missing parser confidence proof"],
        )


if __name__ == "__main__":
    unittest.main()
