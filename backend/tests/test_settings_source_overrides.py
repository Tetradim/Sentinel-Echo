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
        if isinstance(self.settings, dict):
            self.settings.update(update)
            return dict(self.settings)
        return dict(update)

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

    async def increment_loss_counters(self, loss_amount):
        return {
            "consecutive_losses": 1,
            "daily_losses": 1,
            "daily_loss_amount": loss_amount,
        }

    async def insert_operator_event(self, event):
        self.operator_events.append(event)
        return event["id"]


class FakeRawSettingsDb(FakeSettingsDb):
    async def get_settings(self):
        return self.settings


class FakeMalformedRuntimeDb(FakeSettingsDb):
    async def get_runtime_state(self):
        return "runtime"


class FakeRuntimeSettingsDb(FakeSettingsDb):
    def __init__(self, settings=None, runtime=None):
        super().__init__(settings)
        self.runtime = runtime or {}

    async def get_runtime_state(self):
        return dict(self.runtime)


class SourceOverrideRouteTests(unittest.TestCase):
    def test_get_settings_treats_malformed_settings_as_defaults(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_settings())

        self.assertIsInstance(response, dict)
        self.assertTrue(response["auto_trading_enabled"])
        self.assertFalse(response["simulation_mode"])

    def test_get_settings_coerces_known_string_flags_for_clients(self):
        from routes import settings as settings_route

        string_flags = {
            "auto_trading_enabled": "false",
            "premium_buffer_enabled": "false",
            "simulation_mode": "false",
            "averaging_down_enabled": "false",
            "take_profit_enabled": "false",
            "bracket_order_enabled": "false",
            "stop_loss_enabled": "false",
            "trailing_stop_enabled": "false",
            "auto_shutdown_enabled": "false",
            "shutdown_triggered": "false",
            "sms_enabled": "false",
        }
        fake_db = FakeSettingsDb(string_flags)
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_settings())

        for flag_name in string_flags:
            self.assertIs(response[flag_name], False)

    def test_get_settings_backfills_exit_intelligence_defaults(self):
        from routes import settings as settings_route

        settings_route.set_db(FakeSettingsDb({"active_broker": "alpaca"}))

        response = asyncio.run(settings_route.get_settings())

        self.assertTrue(response["reversal_exit_enabled"])
        self.assertEqual(response["reversal_warning_confirmations"], 3)
        self.assertEqual(response["reversal_confirmed_confirmations"], 5)
        self.assertEqual(response["entry_slippage_mode"], "tiered")
        self.assertEqual(response["coordinated_trailing_mode"], "tightening")
        self.assertTrue(response["coordinated_loss_ladder_enabled"])
        self.assertEqual(response["exit_reprice_interval_seconds"], 5)
        self.assertEqual(response["profit_exit_reprice_interval_seconds"], 3)
        self.assertTrue(response["adaptive_trailing_enabled"])
        self.assertEqual(response["adaptive_trailing_max_percent"], 35.0)
        self.assertTrue(response["zero_dte_liquidation_enabled"])
        self.assertEqual(response["zero_dte_liquidation_time"], "15:40")
        self.assertFalse(response["core_runner_enabled"])
        self.assertEqual(response["core_runner_allocation_mode"], "greater_of")
        self.assertEqual(response["core_runner_catastrophic_stop_percent"], 65.0)

    def test_update_settings_normalizes_runner_tiers_and_loss_targets(self):
        from models import SettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeSettingsDb()
        settings_route.set_db(fake_db)

        asyncio.run(
            settings_route.update_settings(
                SettingsUpdate(
                    core_runner_trailing_tiers=[
                        {"mfe_percent": 100, "trail_percent": 35},
                        {"mfe_percent": 300, "trail_percent": 30},
                    ],
                    coordinated_loss_ladder=[
                        {
                            "loss_percent": 20,
                            "quantity_mode": "percent_remaining",
                            "quantity": 100,
                            "confirmations": 1,
                            "allocation_target": "entire_position",
                        }
                    ],
                )
            )
        )

        self.assertEqual(
            fake_db.updated[0]["core_runner_trailing_tiers"],
            [
                {"mfe_percent": 100.0, "trail_percent": 35.0},
                {"mfe_percent": 300.0, "trail_percent": 30.0},
            ],
        )
        self.assertEqual(
            fake_db.updated[0]["coordinated_loss_ladder"][0]["allocation_target"],
            "entire_position",
        )

    def test_update_settings_rejects_unordered_runner_tiers(self):
        from fastapi import HTTPException
        from models import SettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeSettingsDb()
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as error:
            asyncio.run(
                settings_route.update_settings(
                    SettingsUpdate(
                        core_runner_trailing_tiers=[
                            {"mfe_percent": 300, "trail_percent": 30},
                            {"mfe_percent": 100, "trail_percent": 35},
                        ]
                    )
                )
            )

        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(fake_db.updated, [])

    def test_update_settings_rejects_invalid_exit_intelligence_relationships(self):
        from fastapi import HTTPException
        from models import SettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeSettingsDb()
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as reversal_error:
            asyncio.run(
                settings_route.update_settings(
                    SettingsUpdate(
                        reversal_warning_confirmations=4,
                        reversal_confirmed_confirmations=4,
                    )
                )
            )
        self.assertEqual(reversal_error.exception.status_code, 400)

        with self.assertRaises(HTTPException) as trailing_error:
            asyncio.run(
                settings_route.update_settings(
                    SettingsUpdate(
                        adaptive_trailing_min_percent=30,
                        adaptive_trailing_max_percent=20,
                    )
                )
            )
        self.assertEqual(trailing_error.exception.status_code, 400)

        with self.assertRaises(HTTPException) as slippage_error:
            asyncio.run(
                settings_route.update_settings(
                    SettingsUpdate(
                        entry_slippage_warning_percent=20,
                        entry_slippage_severe_percent=10,
                    )
                )
            )
        self.assertEqual(slippage_error.exception.status_code, 400)

        with self.assertRaises(HTTPException) as scalp_error:
            asyncio.run(
                settings_route.update_settings(
                    SettingsUpdate(
                        coordinated_fast_scalp_profit_stage_1_percent=20,
                        coordinated_fast_scalp_profit_stage_2_percent=10,
                    )
                )
            )
        self.assertEqual(scalp_error.exception.status_code, 400)
        self.assertEqual(fake_db.updated, [])

    def test_get_settings_masks_discord_token(self):
        from routes import settings as settings_route

        fake_db = FakeSettingsDb({"discord_token": "discord-secret-token"})
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_settings())

        self.assertEqual(response["discord_token"], "********")
        self.assertTrue(response["discord_token_configured"])
        self.assertNotEqual(response["discord_token"], "discord-secret-token")

    def test_update_settings_preserves_masked_existing_discord_token(self):
        from models import SettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "discord_token": "discord-secret-token",
                "discord_channel_ids": ["111"],
            }
        )
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_settings(
                SettingsUpdate(
                    discord_token="********",
                    discord_channel_ids=["222"],
                )
            )
        )

        self.assertEqual(
            fake_db.updated[0],
            {"discord_channel_ids": ["222"]},
        )
        self.assertEqual(fake_db.settings["discord_token"], "discord-secret-token")
        self.assertEqual(response["discord_token"], "********")
        self.assertTrue(response["discord_token_configured"])

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
        stored_alpaca = fake_db.updated[0]["broker_configs"]["alpaca"]
        self.assertEqual(fake_db.updated[0]["broker_configs"]["ibkr"], {"gateway_url": "https://localhost:5000", "account_id": "DU123"})
        self.assertEqual(stored_alpaca["account_id"], "paper-2")
        self.assertNotEqual(stored_alpaca["api_key"], "new-key")
        self.assertTrue(str(stored_alpaca["api_key"]).startswith("enc:"))

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

        stored_alpaca = fake_db.updated[0]["broker_configs"]["alpaca"]
        self.assertEqual(stored_alpaca["account_id"], "paper-2")
        self.assertNotEqual(stored_alpaca["api_key"], "old-key")
        self.assertNotEqual(stored_alpaca["api_secret"], "old-secret")
        self.assertTrue(str(stored_alpaca["api_key"]).startswith("enc:"))
        self.assertTrue(str(stored_alpaca["api_secret"]).startswith("enc:"))
        self.assertEqual(
            response["broker_configs"]["alpaca"],
            {
                "api_key": "********",
                "api_secret": "********",
                "account_id": "paper-2",
                "configured_fields": {"api_key": True, "api_secret": True},
            },
        )

    def test_update_settings_handles_malformed_existing_broker_configs(self):
        from models import SettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_settings(
                SettingsUpdate(
                    broker_configs={
                        "alpaca": {
                            "api_key": "new-key",
                            "api_secret": "new-secret",
                            "account_id": "paper-1",
                        }
                    }
                )
            )
        )

        stored_alpaca = fake_db.updated[0]["broker_configs"]["alpaca"]
        self.assertEqual(stored_alpaca["account_id"], "paper-1")
        self.assertNotEqual(stored_alpaca["api_key"], "new-key")
        self.assertNotEqual(stored_alpaca["api_secret"], "new-secret")
        self.assertTrue(str(stored_alpaca["api_key"]).startswith("enc:"))
        self.assertTrue(str(stored_alpaca["api_secret"]).startswith("enc:"))
        self.assertEqual(
            response["broker_configs"]["alpaca"],
            {
                "api_key": "********",
                "api_secret": "********",
                "account_id": "paper-1",
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

    def test_correlation_settings_treats_malformed_settings_as_defaults(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_correlation_settings())

        self.assertEqual(response, {"max_positions_per_ticker": 3})

    def test_premium_buffer_settings_treats_malformed_settings_as_defaults(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_premium_buffer_settings())

        self.assertEqual(
            response,
            {"premium_buffer_enabled": False, "premium_buffer_amount": 10.0},
        )

    def test_risk_management_settings_treats_malformed_settings_as_defaults(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_risk_management_settings())

        self.assertEqual(
            response,
            {
                "take_profit_enabled": False,
                "take_profit_percentage": 50.0,
                "take_profit_sell_percentage": 100.0,
                "bracket_order_enabled": False,
                "break_even_enabled": False,
                "break_even_activation_type": "percent",
                "break_even_activation_percentage": 10.0,
                "break_even_activation_cents": 10.0,
                "stop_loss_enabled": False,
                "stop_loss_percentage": 25.0,
                "stop_loss_order_type": "market",
            },
        )

    def test_auto_shutdown_settings_treats_malformed_settings_as_defaults(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_auto_shutdown_settings())

        self.assertFalse(response["auto_shutdown_enabled"])
        self.assertEqual(response["max_consecutive_losses"], 3)
        self.assertEqual(response["max_daily_losses"], 5)
        self.assertEqual(response["max_daily_loss_amount"], 500.0)
        self.assertFalse(response["shutdown_triggered"])
        self.assertEqual(response["shutdown_reason"], "")

    def test_auto_shutdown_settings_coerces_persisted_string_shutdown_flag(self):
        from routes import settings as settings_route

        fake_db = FakeRuntimeSettingsDb(
            {},
            {
                "shutdown_triggered": "false",
                "shutdown_reason": "stored as text",
            },
        )
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_auto_shutdown_settings())

        self.assertIs(response["shutdown_triggered"], False)
        self.assertEqual(response["shutdown_reason"], "stored as text")

    def test_setting_read_endpoints_coerce_string_flags_for_clients(self):
        from routes import settings as settings_route

        cases = [
            (
                "get_premium_buffer_settings",
                {"premium_buffer_enabled": "false"},
                {"premium_buffer_enabled": False},
            ),
            (
                "get_averaging_down_settings",
                {"averaging_down_enabled": "false"},
                {"averaging_down_enabled": False},
            ),
            (
                "get_risk_management_settings",
                {
                    "take_profit_enabled": "false",
                    "bracket_order_enabled": "false",
                    "stop_loss_enabled": "false",
                },
                {
                    "take_profit_enabled": False,
                    "bracket_order_enabled": False,
                    "stop_loss_enabled": False,
                },
            ),
            (
                "get_trailing_stop_settings",
                {"trailing_stop_enabled": "false"},
                {"trailing_stop_enabled": False},
            ),
            (
                "get_auto_shutdown_settings",
                {"auto_shutdown_enabled": "false"},
                {"auto_shutdown_enabled": False},
            ),
            (
                "get_notification_settings",
                {"sms_enabled": "false"},
                {"sms_enabled": False},
            ),
        ]
        for function_name, settings, expected_flags in cases:
            with self.subTest(function_name=function_name):
                fake_db = FakeSettingsDb(settings)
                settings_route.set_db(fake_db)

                response = asyncio.run(getattr(settings_route, function_name)())

                for flag_name, expected in expected_flags.items():
                    self.assertIs(response[flag_name], expected)

    def test_averaging_down_settings_treats_malformed_settings_as_defaults(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_averaging_down_settings())

        self.assertEqual(
            response,
            {
                "averaging_down_enabled": False,
                "averaging_down_threshold": 10.0,
                "averaging_down_percentage": 25.0,
                "averaging_down_max_buys": 3,
            },
        )

    def test_trailing_stop_settings_treats_malformed_settings_as_defaults(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_trailing_stop_settings())

        self.assertEqual(
            response,
            {
                "trailing_stop_enabled": False,
                "trailing_stop_type": "percent",
                "trailing_stop_percent": 10.0,
                "trailing_stop_activation_percent": 10.0,
                "trailing_stop_cents": 50.0,
            },
        )

    def test_notification_settings_treats_malformed_settings_as_defaults(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_notification_settings())

        self.assertEqual(
            response,
            {
                "sms_enabled": False,
                "sms_phone_number": "",
                "twilio_account_sid": "",
                "twilio_auth_token": "",
                "twilio_from_number": "",
            },
        )

    def test_update_premium_buffer_settings_treats_malformed_response_as_defaults(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_premium_buffer_settings(
                premium_buffer_amount=15.0,
                premium_buffer_enabled=True,
            )
        )

        self.assertEqual(
            fake_db.updated,
            [{"premium_buffer_amount": 15.0, "premium_buffer_enabled": True}],
        )
        self.assertEqual(
            response,
            {"premium_buffer_enabled": True, "premium_buffer_amount": 15.0},
        )

    def test_update_risk_management_settings_treats_malformed_response_as_defaults(self):
        from models import RiskManagementSettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_risk_management_settings(
                RiskManagementSettingsUpdate(
                    take_profit_enabled=True,
                    stop_loss_percentage=20.0,
                )
            )
        )

        self.assertEqual(
            fake_db.updated,
            [{"take_profit_enabled": True, "stop_loss_percentage": 20.0}],
        )
        self.assertEqual(
            response,
            {
                "take_profit_enabled": True,
                "take_profit_percentage": 50.0,
                "take_profit_sell_percentage": 100.0,
                "bracket_order_enabled": False,
                "break_even_enabled": False,
                "break_even_activation_type": "percent",
                "break_even_activation_percentage": 10.0,
                "break_even_activation_cents": 10.0,
                "stop_loss_enabled": False,
                "stop_loss_percentage": 20.0,
                "stop_loss_order_type": "market",
            },
        )

    def test_update_averaging_down_settings_treats_malformed_response_as_defaults(self):
        from models import AveragingDownSettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_averaging_down_settings(
                AveragingDownSettingsUpdate(
                    averaging_down_enabled=True,
                    averaging_down_threshold=8.0,
                )
            )
        )

        self.assertEqual(
            fake_db.updated,
            [{"averaging_down_enabled": True, "averaging_down_threshold": 8.0}],
        )
        self.assertEqual(
            response,
            {
                "averaging_down_enabled": True,
                "averaging_down_threshold": 8.0,
                "averaging_down_percentage": 25.0,
                "averaging_down_max_buys": 3,
            },
        )

    def test_update_trailing_stop_settings_treats_malformed_response_as_defaults(self):
        from models import TrailingStopSettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_trailing_stop_settings(
                TrailingStopSettingsUpdate(
                    trailing_stop_enabled=True,
                    trailing_stop_type="premium",
                )
            )
        )

        self.assertEqual(
            fake_db.updated,
            [{"trailing_stop_enabled": True, "trailing_stop_type": "premium"}],
        )
        self.assertEqual(
            response,
            {
                "trailing_stop_enabled": True,
                "trailing_stop_type": "premium",
                "trailing_stop_percent": 10.0,
                "trailing_stop_activation_percent": 10.0,
                "trailing_stop_cents": 50.0,
            },
        )

    def test_update_auto_shutdown_settings_treats_malformed_response_as_defaults(self):
        from models import AutoShutdownSettingsUpdate
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_auto_shutdown_settings(
                AutoShutdownSettingsUpdate(
                    auto_shutdown_enabled=True,
                    max_daily_losses=2,
                )
            )
        )

        self.assertEqual(
            fake_db.updated,
            [{"auto_shutdown_enabled": True, "max_daily_losses": 2}],
        )
        self.assertEqual(
            response,
            {
                "auto_shutdown_enabled": True,
                "max_consecutive_losses": 3,
                "max_daily_losses": 2,
                "max_daily_loss_amount": 500.0,
            },
        )

    def test_setting_update_endpoints_coerce_existing_string_flags_for_clients(self):
        from models import (
            AutoShutdownSettingsUpdate,
            AveragingDownSettingsUpdate,
            RiskManagementSettingsUpdate,
            TrailingStopSettingsUpdate,
        )
        from routes import settings as settings_route

        cases = [
            (
                "update_premium_buffer_settings",
                {"premium_buffer_enabled": "false"},
                {"premium_buffer_amount": 11.0},
                {"premium_buffer_enabled": False},
            ),
            (
                "update_averaging_down_settings",
                {"averaging_down_enabled": "false"},
                {
                    "update": AveragingDownSettingsUpdate(
                        averaging_down_threshold=12.0,
                    )
                },
                {"averaging_down_enabled": False},
            ),
            (
                "update_risk_management_settings",
                {
                    "take_profit_enabled": "false",
                    "bracket_order_enabled": "false",
                    "stop_loss_enabled": "false",
                },
                {
                    "update": RiskManagementSettingsUpdate(
                        take_profit_percentage=55.0,
                    )
                },
                {
                    "take_profit_enabled": False,
                    "bracket_order_enabled": False,
                    "stop_loss_enabled": False,
                },
            ),
            (
                "update_trailing_stop_settings",
                {"trailing_stop_enabled": "false"},
                {
                    "update": TrailingStopSettingsUpdate(
                        trailing_stop_percent=12.0,
                    )
                },
                {"trailing_stop_enabled": False},
            ),
            (
                "update_auto_shutdown_settings",
                {"auto_shutdown_enabled": "false"},
                {
                    "update": AutoShutdownSettingsUpdate(
                        max_daily_losses=4,
                    )
                },
                {"auto_shutdown_enabled": False},
            ),
        ]
        for function_name, existing_settings, kwargs, expected_flags in cases:
            with self.subTest(function_name=function_name):
                fake_db = FakeSettingsDb(existing_settings)
                settings_route.set_db(fake_db)

                response = asyncio.run(getattr(settings_route, function_name)(**kwargs))

                for flag_name, expected in expected_flags.items():
                    self.assertIs(response[flag_name], expected)

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

    def test_get_source_overrides_treats_malformed_settings_as_empty(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.get_source_overrides())

        self.assertEqual(response, {})

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

    def test_toggle_trading_parses_string_simulation_flag_before_live_enable(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeSettingsDb(
            {
                "auto_trading_enabled": "false",
                "simulation_mode": "false",
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

    def test_toggle_trading_blocks_serialized_false_readiness(self):
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
            return_value={"ready_for_live": "false", "blocking_issues": []},
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(settings_route.toggle_trading())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.operator_events[-1]["action"], "auto_trading_enable_blocked")

    def test_secondary_toggles_parse_string_false_before_toggling(self):
        from routes import settings as settings_route

        cases = [
            ("toggle_premium_buffer", "premium_buffer_enabled"),
            ("toggle_averaging_down", "averaging_down_enabled"),
            ("toggle_take_profit", "take_profit_enabled"),
            ("toggle_stop_loss", "stop_loss_enabled"),
            ("toggle_trailing_stop", "trailing_stop_enabled"),
            ("toggle_auto_shutdown", "auto_shutdown_enabled"),
        ]
        for function_name, flag_name in cases:
            with self.subTest(function_name=function_name):
                fake_db = FakeSettingsDb({flag_name: "false"})
                settings_route.set_db(fake_db)

                response = asyncio.run(getattr(settings_route, function_name)())

                self.assertEqual(response, {flag_name: True})
                self.assertEqual(fake_db.updated, [{flag_name: True}])

    def test_toggle_premium_buffer_treats_malformed_settings_as_default(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.toggle_premium_buffer())

        self.assertEqual(response, {"premium_buffer_enabled": True})
        self.assertEqual(fake_db.updated, [{"premium_buffer_enabled": True}])

    def test_toggle_averaging_down_treats_malformed_settings_as_default(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.toggle_averaging_down())

        self.assertEqual(response, {"averaging_down_enabled": True})
        self.assertEqual(fake_db.updated, [{"averaging_down_enabled": True}])

    def test_toggle_take_profit_treats_malformed_settings_as_default(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.toggle_take_profit())

        self.assertEqual(response, {"take_profit_enabled": True})
        self.assertEqual(fake_db.updated, [{"take_profit_enabled": True}])

    def test_toggle_stop_loss_treats_malformed_settings_as_default(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.toggle_stop_loss())

        self.assertEqual(response, {"stop_loss_enabled": True})
        self.assertEqual(fake_db.updated, [{"stop_loss_enabled": True}])

    def test_toggle_trailing_stop_treats_malformed_settings_as_default(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.toggle_trailing_stop())

        self.assertEqual(response, {"trailing_stop_enabled": True})
        self.assertEqual(fake_db.updated, [{"trailing_stop_enabled": True}])

    def test_toggle_auto_shutdown_treats_malformed_settings_as_default(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.toggle_auto_shutdown())

        self.assertEqual(response, {"auto_shutdown_enabled": True})
        self.assertEqual(fake_db.updated, [{"auto_shutdown_enabled": True}])

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

    def test_reset_loss_counters_blocks_serialized_false_readiness(self):
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
            return_value={"ready_for_live": "false", "blocking_issues": []},
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(settings_route.reset_loss_counters())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.loss_counters_reset, 0)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.runtime_updates, [])
        self.assertEqual(fake_db.operator_events[-1]["action"], "loss_counter_reset_blocked")

    def test_reset_loss_counters_blocks_malformed_settings(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(settings_route.reset_loss_counters())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.loss_counters_reset, 0)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.runtime_updates, [])
        self.assertEqual(fake_db.operator_events[-1]["action"], "loss_counter_reset_blocked")

    def test_check_broker_connection_reports_malformed_settings(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        response = asyncio.run(settings_route.check_broker_connection())

        self.assertEqual(
            response,
            {"connected": False, "broker": None, "error": "Settings are malformed"},
        )

    def test_shutdown_check_disables_trading_on_malformed_settings(self):
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        reason = asyncio.run(settings_route.check_and_trigger_shutdown(-125.0))

        self.assertEqual(reason, "Settings are malformed")
        self.assertEqual(
            fake_db.runtime_updates,
            [
                {
                    "shutdown_triggered": True,
                    "shutdown_reason": "Settings are malformed",
                    "auto_trading_enabled": False,
                }
            ],
        )
        self.assertEqual(fake_db.updated, [{"auto_trading_enabled": False}])

    def test_shutdown_check_treats_malformed_runtime_state_as_empty(self):
        from routes import settings as settings_route

        fake_db = FakeMalformedRuntimeDb(
            {
                "auto_shutdown_enabled": True,
                "max_consecutive_losses": 3,
                "max_daily_losses": 5,
                "max_daily_loss_amount": 500.0,
            }
        )
        settings_route.set_db(fake_db)

        reason = asyncio.run(settings_route.check_and_trigger_shutdown(-125.0))

        self.assertIsNone(reason)
        self.assertEqual(len(fake_db.runtime_updates), 1)
        self.assertEqual(fake_db.runtime_updates[0]["daily_losses"], 0)
        self.assertEqual(fake_db.runtime_updates[0]["daily_loss_amount"], 0.0)

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

    def test_sms_notification_treats_malformed_settings_as_disabled(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeRawSettingsDb("settings")
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(settings_route.test_sms_notification())

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "SMS notifications are disabled.")

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
                        "allowed_channel_urls": ["https://discord.com/channels/1/2/"],
                        "allowed_author_ids": [" mike "],
                        "min_parser_confidence": "HIGH",
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
                    "parser_format": "default",
                    "max_premium": None,
                    "risk_multiplier": 0.5,
                    "notes": "",
                    "allowed_actions": ["buy", "close"],
                    "ticker_allowlist": ["SPY", "QQQ"],
                    "ticker_blocklist": ["TSLA"],
                    "allowed_channel_urls": ["https://discord.com/channels/1/2"],
                    "allowed_author_ids": ["mike"],
                    "min_parser_confidence": "high",
                    "max_contracts": 3,
                    "process_followup_updates": True,
                    "process_actionable_edits": True,
                    "allow_single_position_inferred_sell": True,
                    "allow_broad_exit_matching": True,
                    "protect_trailing_armed_from_contextual_exits": True,
                    "trailing_context_exit_override_enabled": True,
                    "trailing_context_exit_override_percent": 80.0,
                    "dedupe_by_channel_url": False,
                    "ignore_followup_messages": False,
                    "allow_fresh_entry_after_close": False,
                    "trim_alert_listening_enabled": None,
                    "exit_profile": "standard",
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
