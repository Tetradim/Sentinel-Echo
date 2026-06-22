import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeSettingsDb:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.updated = []
        self.runtime_updates = []
        self.loss_counters_reset = 0
        self.operator_events = []

    async def get_settings(self):
        return dict(self.settings)

    async def update_settings(self, update):
        self.updated.append(update)
        self.settings.update(update)
        return dict(self.settings)

    async def update_runtime_state(self, update):
        self.runtime_updates.append(update)
        return dict(update)

    async def get_runtime_state(self):
        return {
            "shutdown_triggered": False,
            "live_trading_armed": False,
            "live_trading_armed_until": "",
        }

    async def reset_loss_counters(self):
        self.loss_counters_reset += 1

    async def insert_operator_event(self, event):
        self.operator_events.append(event)
        return event["id"]


class FakeRawSettingsDb(FakeSettingsDb):
    async def get_settings(self):
        return self.settings


class SourceOverrideRouteTests(unittest.TestCase):
    def test_update_premium_buffer_settings_persists_enabled_flag_and_amount(self):
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {"premium_buffer_enabled": False, "premium_buffer_amount": 10.0}
        )
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_premium_buffer_settings(
                premium_buffer_amount=25.0,
                premium_buffer_enabled=True,
            )
        )

        self.assertEqual(
            fake_db.updated,
            [{"premium_buffer_amount": 25.0, "premium_buffer_enabled": True}],
        )
        self.assertEqual(
            response,
            {"premium_buffer_amount": 25.0, "premium_buffer_enabled": True},
        )

    def test_update_settings_merges_partial_broker_config_payloads(self):
        from models import SettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "broker_configs": {
                    "ibkr": {"gateway_url": "https://localhost:5000", "account_id": "DU123"},
                    "alpaca": {"api_key": "old-key", "account_id": "paper-1"},
                }
            }
        )
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_settings(
                SettingsUpdate(
                    broker_configs={
                        "alpaca": {"api_key": "new-key", "account_id": "paper-2"}
                    }
                )
            )
        )

        self.assertEqual(
            response["broker_configs"],
            {
                "ibkr": {"gateway_url": "https://localhost:5000", "account_id": "DU123"},
                "alpaca": {
                    "api_key": "********",
                    "account_id": "paper-2",
                    "configured_fields": {"api_key": True},
                },
            },
        )
        self.assertEqual(
            fake_db.updated[0]["broker_configs"],
            {
                "ibkr": {"gateway_url": "https://localhost:5000", "account_id": "DU123"},
                "alpaca": {"api_key": "new-key", "account_id": "paper-2"},
            },
        )

    def test_update_settings_preserves_masked_existing_broker_secret(self):
        from models import SettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "broker_configs": {
                    "alpaca": {"api_key": "old-key", "api_secret": "old-secret", "account_id": "paper-1"},
                }
            }
        )
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_settings(
                SettingsUpdate(
                    broker_configs={
                        "alpaca": {"api_key": "********", "account_id": "paper-2"}
                    }
                )
            )
        )

        self.assertEqual(
            fake_db.updated[0]["broker_configs"]["alpaca"],
            {"api_key": "old-key", "api_secret": "old-secret", "account_id": "paper-2"},
        )
        self.assertEqual(
            response["broker_configs"]["alpaca"],
            {
                "api_key": "********",
                "api_secret": "********",
                "account_id": "paper-2",
                "configured_fields": {"api_key": True, "api_secret": True},
            },
        )

    def test_correlation_settings_round_trip_on_active_settings_route(self):
        from routes import settings as settings_route

        fake_db = FakeSettingsDb({"max_positions_per_ticker": 2})
        settings_route.set_db(fake_db)

        current = asyncio.run(settings_route.get_correlation_settings())
        updated = asyncio.run(settings_route.update_correlation_settings(4))

        self.assertEqual(current, {"max_positions_per_ticker": 2})
        self.assertEqual(updated, {"max_positions_per_ticker": 4})
        self.assertEqual(fake_db.updated, [{"max_positions_per_ticker": 4}])

    def test_toggle_trading_uses_persisted_setting_as_source_of_truth(self):
        from routes import settings as settings_route
        from routes.health import update_bot_status

        fake_db = FakeSettingsDb({"auto_trading_enabled": True})
        settings_route.set_db(fake_db)
        update_bot_status("auto_trading_enabled", False)

        response = asyncio.run(settings_route.toggle_trading())

        self.assertEqual(response, {"auto_trading_enabled": False})
        self.assertEqual(fake_db.updated, [{"auto_trading_enabled": False}])
        self.assertEqual(fake_db.runtime_updates, [{"auto_trading_enabled": False}])

    def test_toggle_trading_blocks_malformed_settings(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(settings_route.toggle_trading())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.runtime_updates, [])
        self.assertEqual(fake_db.operator_events[-1]["action"], "auto_trading_enable_blocked")

    def test_toggle_trading_blocks_live_enable_when_readiness_fails(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "auto_trading_enabled": False,
                "simulation_mode": False,
                "active_broker": "alpaca",
                "broker_configs": {},
                "source_overrides": {},
            }
        )
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(settings_route.toggle_trading())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.updated, [])

    def test_toggle_trading_block_audit_normalizes_malformed_blocking_issues(self):
        from fastapi import HTTPException
        from unittest.mock import patch
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "auto_trading_enabled": False,
                "simulation_mode": False,
                "active_broker": "alpaca",
                "broker_configs": {},
                "source_overrides": {},
            }
        )
        settings_route.set_db(fake_db)

        with patch(
            "live_readiness.evaluate_live_readiness",
            return_value={"ready_for_live": False, "blocking_issues": "blocked"},
        ):
            with self.assertRaises(HTTPException):
                asyncio.run(settings_route.toggle_trading())

        self.assertEqual(fake_db.operator_events[-1]["details"]["blocking_issues"], [])

    def test_toggle_trading_treats_malformed_readiness_payload_as_blocked(self):
        from fastapi import HTTPException
        from unittest.mock import patch
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "auto_trading_enabled": False,
                "simulation_mode": False,
                "active_broker": "alpaca",
                "broker_configs": {},
                "source_overrides": {},
            }
        )
        settings_route.set_db(fake_db)

        with patch("live_readiness.evaluate_live_readiness", return_value="readiness"):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(settings_route.toggle_trading())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.operator_events[-1]["action"], "auto_trading_enable_blocked")

    def test_reset_loss_counters_blocks_live_reenable_when_readiness_fails(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "auto_trading_enabled": False,
                "simulation_mode": False,
                "active_broker": "alpaca",
                "broker_configs": {},
                "source_overrides": {},
            }
        )
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(settings_route.reset_loss_counters())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.loss_counters_reset, 0)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.runtime_updates, [])

    def test_reset_loss_counters_block_audit_normalizes_malformed_blocking_issues(self):
        from fastapi import HTTPException
        from unittest.mock import patch
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "auto_trading_enabled": False,
                "simulation_mode": False,
                "active_broker": "alpaca",
                "broker_configs": {},
                "source_overrides": {},
            }
        )
        settings_route.set_db(fake_db)

        with patch(
            "live_readiness.evaluate_live_readiness",
            return_value={"ready_for_live": False, "blocking_issues": "blocked"},
        ):
            with self.assertRaises(HTTPException):
                asyncio.run(settings_route.reset_loss_counters())

        self.assertEqual(fake_db.operator_events[-1]["details"]["blocking_issues"], [])

    def test_reset_loss_counters_treats_malformed_readiness_payload_as_blocked(self):
        from fastapi import HTTPException
        from unittest.mock import patch
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "auto_trading_enabled": False,
                "simulation_mode": False,
                "active_broker": "alpaca",
                "broker_configs": {},
                "source_overrides": {},
            }
        )
        settings_route.set_db(fake_db)

        with patch("live_readiness.evaluate_live_readiness", return_value="readiness"):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(settings_route.reset_loss_counters())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.loss_counters_reset, 0)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.runtime_updates, [])
        self.assertEqual(fake_db.operator_events[-1]["action"], "loss_counter_reset_blocked")

    def test_settings_update_rejects_invalid_risk_numbers(self):
        from pydantic import ValidationError
        from models import SettingsUpdate

        invalid_payloads = [
            {"max_position_size": 0},
            {"default_quantity": 0},
            {"risk_per_trade": -0.1},
            {"max_drawdown_percent": 0},
            {"max_positions_per_sector": -1},
            {"trailing_hours": 0},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    SettingsUpdate(**payload)

    def test_notification_settings_round_trip_on_active_settings_route(self):
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "sms_enabled": True,
                "sms_phone_number": "+15551234567",
                "twilio_account_sid": "AC123",
                "twilio_auth_token": "secret-token",
                "twilio_from_number": "+15557654321",
            }
        )
        settings_route.set_db(fake_db)

        current = asyncio.run(settings_route.get_notification_settings())
        updated = asyncio.run(
            settings_route.update_notification_settings(
                sms_enabled=False,
                sms_phone_number=" +15550001111 ",
                twilio_account_sid=" AC999 ",
                twilio_auth_token=" new-secret ",
                twilio_from_number=" +15552223333 ",
            )
        )

        self.assertEqual(
            current,
            {
                "sms_enabled": True,
                "sms_phone_number": "+15551234567",
                "twilio_account_sid": "AC123",
                "twilio_auth_token": "********",
                "twilio_from_number": "+15557654321",
            },
        )
        self.assertEqual(updated, {"message": "Notification settings updated"})
        self.assertEqual(
            fake_db.updated,
            [
                {
                    "sms_enabled": False,
                    "sms_phone_number": "+15550001111",
                    "twilio_account_sid": "AC999",
                    "twilio_auth_token": "new-secret",
                    "twilio_from_number": "+15552223333",
                }
            ],
        )

    def test_update_source_overrides_normalizes_before_saving(self):
        from routes import settings as settings_route

        fake_db = FakeSettingsDb()
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_source_overrides(
                {
                    " Alerts ": {
                        "allowed_actions": ["BUY", "Close"],
                        "ticker_allowlist": [" spy ", "$qqq"],
                        "ticker_blocklist": ["tsla"],
                        "risk_multiplier": "0.5",
                        "max_contracts": "3",
                        "require_manual_confirm": True,
                        "paper_shadow": True,
                    }
                }
            )
        )

        self.assertEqual(
            response,
            {
                "Alerts": {
                    "name": "",
                    "enabled": True,
                    "paper_only": False,
                    "parser_format": "default",
                    "max_premium": None,
                    "risk_multiplier": 0.5,
                    "notes": "",
                    "allowed_actions": ["buy", "close"],
                    "ticker_allowlist": ["SPY", "QQQ"],
                    "ticker_blocklist": ["TSLA"],
                    "max_contracts": 3,
                    "require_manual_confirm": True,
                    "paper_shadow": True,
                }
            },
        )
        self.assertEqual(fake_db.updated, [{"source_overrides": response}])

    def test_update_source_overrides_rejects_unknown_actions(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        settings_route.set_db(FakeSettingsDb())

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"allowed_actions": ["buy", "moon"]}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("unknown allowed action", caught.exception.detail)

    def test_update_source_overrides_rejects_invalid_risk_numbers(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeSettingsDb()
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"max_premium": "-0.01"}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("max_premium must be greater than 0", caught.exception.detail)
        self.assertEqual(fake_db.updated, [])

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"risk_multiplier": "0"}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("risk_multiplier must be greater than 0", caught.exception.detail)
        self.assertEqual(fake_db.updated, [])

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"max_contracts": "0"}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("max_contracts must be greater than 0", caught.exception.detail)
        self.assertEqual(fake_db.updated, [])

    def test_update_source_overrides_rejects_invalid_tickers(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeSettingsDb()
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"ticker_allowlist": ["SPY1"]}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("ticker_allowlist contains invalid ticker", caught.exception.detail)
        self.assertEqual(fake_db.updated, [])


if __name__ == "__main__":
    unittest.main()
