import asyncio
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeReconciliationDb:
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


if __name__ == "__main__":
    unittest.main()
