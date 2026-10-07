import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class TradeCycleAuditTests(unittest.TestCase):
    def test_builds_cycle_metrics_from_positions_trades_alerts_and_events(self):
        from trade_cycle_audit import build_trade_cycle_audit

        positions = [
            {
                "id": "cycle-2",
                "contract_key": "position-alpaca-spy-260930-p-764",
                "trade_cycle_id": "cycle-2",
                "reentry_of_position_id": "cycle-1",
                "alert_id": "alert-2",
                "ticker": "SPY",
                "strike": 764,
                "option_type": "PUT",
                "expiration": "2026-09-30",
                "entry_price": 0.24,
                "original_quantity": 15,
                "remaining_quantity": 0,
                "realized_pnl": -121,
                "status": "closed",
                "opened_at": "2026-09-30T18:35:03+00:00",
                "closed_at": "2026-09-30T18:44:00+00:00",
                "max_favorable_excursion_percent": 8.3,
                "max_adverse_excursion_percent": -50,
                "post_exit_highest_return_percent": 33.3,
                "entry_strategy_snapshot": {"profile": "Runner Capture"},
                "trade_ids": ["buy-2", "sell-2"],
            }
        ]
        trades = [
            {
                "id": "buy-2",
                "position_id": "cycle-2",
                "alert_id": "alert-2",
                "side": "BUY",
                "status": "executed",
                "quantity": 15,
                "entry_price": 0.24,
                "created_at": "2026-09-30T18:34:57+00:00",
                "executed_at": "2026-09-30T18:35:03+00:00",
                "order_id": "broker-buy",
            },
            {
                "id": "sell-2",
                "position_id": "cycle-2",
                "side": "SELL",
                "status": "executed",
                "quantity": 3,
                "exit_price": 0.20,
                "realized_pnl": -12,
                "exit_trigger": "loss_ladder_2",
                "created_at": "2026-09-30T18:36:39+00:00",
                "executed_at": "2026-09-30T18:36:44+00:00",
                "order_id": "broker-sell",
                "exit_decision_audit": {
                    "decision_bid": 0.18,
                    "return_percent": -25,
                    "selected_step": 2,
                },
            },
        ]
        alerts = [
            {
                "id": "alert-2",
                "source_name": "mike-alerts",
                "channel_name": "alerts",
                "author_name": "Mike",
                "raw_message": "SPY 764P re-entry",
                "timestamp": "2026-09-30T18:34:56+00:00",
            }
        ]
        events = [
            {
                "id": "event-1",
                "timestamp": "2026-09-30T18:36:39+00:00",
                "action": "coordinated_exit_submitted",
                "summary": "Submitted loss ladder exit.",
                "details": {"position_id": "cycle-2", "trade_id": "sell-2"},
            }
        ]

        audit = build_trade_cycle_audit(positions, trades, alerts, events)

        self.assertEqual(audit["summary"]["cycles"], 1)
        self.assertEqual(audit["summary"]["net_pnl"], -121)
        self.assertEqual(audit["summary"]["reentries"], 1)
        cycle = audit["cycles"][0]
        self.assertEqual(cycle["source"]["name"], "mike-alerts")
        self.assertEqual(cycle["weighted_exit_price"], 0.20)
        self.assertEqual(cycle["exit_triggers"], ["loss_ladder_2"])
        self.assertEqual(cycle["decision_evidence"][0]["decision_bid"], 0.18)
        self.assertEqual(cycle["timeline"][0]["kind"], "alert")
        self.assertEqual(cycle["data_quality"]["has_decision_evidence"], True)


if __name__ == "__main__":
    unittest.main()
