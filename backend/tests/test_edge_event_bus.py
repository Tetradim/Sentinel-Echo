from pathlib import Path
import json
import tempfile
import unittest
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class EdgeEventBusTests(unittest.TestCase):
    def test_recent_edge_sr_directive_events_filters_and_orders_newest_first(self):
        from edge_event_bus import recent_edge_sr_directive_events

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "2026-06-23.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "event_id": "evt-1",
                                "event_type": "edge.sr.directive.v1",
                                "target_bots": ["consolidation"],
                                "payload": {"directive_id": "dir-1"},
                            }
                        ),
                        json.dumps(
                            {
                                "event_id": "wrong-target",
                                "event_type": "edge.sr.directive.v1",
                                "target_bots": ["sentinel-pulse"],
                                "payload": {"directive_id": "dir-pulse"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            (root / "2026-06-24.jsonl").write_text(
                "\n".join(
                    [
                        "not valid json",
                        json.dumps(
                            {
                                "event_id": "wrong-type",
                                "event_type": "edge.action",
                                "target_bots": ["consolidation"],
                            }
                        ),
                        json.dumps(
                            {
                                "event_id": "evt-2",
                                "event_type": "edge.sr.directive.v1",
                                "target_bots": ["consolidation"],
                                "payload": {"directive_id": "dir-2"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            events = recent_edge_sr_directive_events(root=root, target_bot="consolidation")

        self.assertEqual([event["event_id"] for event in events], ["evt-2", "evt-1"])

    def test_recent_edge_sr_directive_events_respects_limit(self):
        from edge_event_bus import recent_edge_sr_directive_events

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "2026-06-24.jsonl").write_text(
                "\n".join(
                    json.dumps(
                        {
                            "event_id": f"evt-{index}",
                            "event_type": "edge.sr.directive.v1",
                            "target_bots": ["consolidation"],
                            "payload": {"directive_id": f"dir-{index}"},
                        }
                    )
                    for index in range(3)
                ),
                encoding="utf-8",
            )

            events = recent_edge_sr_directive_events(root=root, limit=2)

        self.assertEqual(len(events), 2)
        self.assertEqual([event["event_id"] for event in events], ["evt-2", "evt-1"])


if __name__ == "__main__":
    unittest.main()
