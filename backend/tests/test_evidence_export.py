import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_evidence.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_evidence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class EvidenceExportTests(unittest.TestCase):
    def test_recursive_sanitizer_removes_credentials_but_keeps_trading_data(self):
        exporter = load_exporter()

        sanitized = exporter.sanitize_value(
            {
                "ticker": "SPY",
                "api_key": "example-key-value",
                "nested": {"secret_key": "example-secret", "quantity": 3},
            }
        )

        self.assertEqual(sanitized["ticker"], "SPY")
        self.assertEqual(sanitized["api_key"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["secret_key"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["quantity"], 3)

    def test_text_sanitizer_removes_key_shaped_values(self):
        exporter = load_exporter()

        text = exporter.sanitize_text(
            'APCA_API_SECRET_KEY=abcdefghijklmnopqrstuvwxyz123456\n'
            'Authorization: Bearer sk-proj-exampleabcdefghijklmnopqrstuvwxyz\n'
            '{"secret_key": "quoted-example-secret"}\n'
        )

        self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", text)
        self.assertNotIn("sk-proj-example", text)
        self.assertNotIn("quoted-example-secret", text)
        self.assertIn("[REDACTED]", text)


if __name__ == "__main__":
    unittest.main()
