import asyncio
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeAuditDb:
    def __init__(self):
        self.events = []

    async def insert_operator_event(self, event):
        self.events.append(event)
        return event["id"]


class OperatorAuditTests(unittest.TestCase):
    def test_audit_sanitizes_secret_fields(self):
        from operator_audit import sanitize_audit_details

        result = sanitize_audit_details(
            {"api_key": "secret", "nested": {"password": "pw"}, "safe": "ok"}
        )

        self.assertEqual(result["api_key"], "[redacted]")
        self.assertEqual(result["nested"]["password"], "[redacted]")
        self.assertEqual(result["safe"], "ok")

    def test_record_operator_event_appends_sanitized_event(self):
        from operator_audit import record_operator_event

        db = FakeAuditDb()
        event = asyncio.run(
            record_operator_event(
                db,
                "settings",
                "updated",
                "Settings updated.",
                details={"api_secret": "secret", "field": "simulation_mode"},
            )
        )

        self.assertEqual(event["category"], "settings")
        self.assertEqual(event["details"]["api_secret"], "[redacted]")
        self.assertEqual(db.events[0]["id"], event["id"])


if __name__ == "__main__":
    unittest.main()
