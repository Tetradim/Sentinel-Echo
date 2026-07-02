import os
import pathlib
import sys
import unittest
from unittest.mock import patch


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class PairingRouteTests(unittest.TestCase):
    def test_pairing_status_reports_required_checks_without_exposing_api_key(self):
        from routes import pairing as pairing_route

        with patch.dict(
            os.environ,
            {
                "API_KEY": "mobile-secret-value",
                "HOST": "0.0.0.0",
                "PORT": "8003",
                "CHROME_BRIDGE_ALLOW_REMOTE": "true",
            },
            clear=False,
        ):
            payload = pairing_route.build_pairing_status(now=lambda: "2026-06-27T18:00:00Z")

        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["server_time"], "2026-06-27T18:00:00Z")
        self.assertTrue(payload["api_auth_configured"])
        self.assertTrue(payload["api_key_required"])
        self.assertEqual(payload["remote_bind"]["host"], "0.0.0.0")
        self.assertEqual(payload["remote_bind"]["port"], 8003)
        self.assertTrue(payload["chrome_bridge_remote_enabled"])
        self.assertNotIn("mobile-secret-value", str(payload))
        paths = [check["path"] for check in payload["required_endpoints"]]
        self.assertIn("/health", paths)
        self.assertIn("/operator/live-readiness", paths)
        self.assertIn("/operator/alert-chains", paths)
        self.assertIn("/operator/reconciliation", paths)
        self.assertIn("/discord/chrome-bridge/health", paths)

    def test_pairing_config_returns_import_payload_with_key_when_authorized(self):
        from routes import pairing as pairing_route

        with patch.dict(
            os.environ,
            {
                "API_KEY": "mobile-secret-value",
                "HOST": "0.0.0.0",
                "PORT": "8003",
                "CHROME_BRIDGE_ALLOW_REMOTE": "true",
            },
            clear=False,
        ):
            payload = pairing_route.build_pairing_config(
                base_api_url="http://100.90.10.11:8003/api",
                now=lambda: "2026-06-27T18:01:00Z",
            )

        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["app"], "mobile-sentinel-echo")
        self.assertEqual(payload["created_at"], "2026-06-27T18:01:00Z")
        self.assertEqual(payload["remote_api_url"], "http://100.90.10.11:8003/api")
        self.assertEqual(payload["api_key"], "mobile-secret-value")
        self.assertEqual(payload["transport_hint"], "tailscale")
        self.assertGreater(len(payload["required_endpoints"]), 4)

    def test_remote_bind_without_api_key_is_blocking(self):
        from routes import pairing as pairing_route

        with patch.dict(
            os.environ,
            {
                "API_KEY": "",
                "HOST": "0.0.0.0",
                "PORT": "8003",
                "USE_SQLITE": "true",
            },
            clear=False,
        ):
            payload = pairing_route.build_pairing_status(now=lambda: "2026-06-27T18:02:00Z")

        self.assertFalse(payload["api_auth_configured"])
        self.assertTrue(payload["api_key_required"])
        self.assertIn("api_key_missing_for_remote_bind", [issue["code"] for issue in payload["blocking_issues"]])


if __name__ == "__main__":
    unittest.main()
