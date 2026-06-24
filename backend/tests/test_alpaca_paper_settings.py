import pathlib
import os
import sys
import tempfile
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class AlpacaPaperSettingsTests(unittest.TestCase):
    def test_build_update_normalizes_v2_endpoint_and_keeps_auto_trading_enabled(self):
        from alpaca_paper_settings import build_alpaca_paper_settings_update

        update = build_alpaca_paper_settings_update(
            {
                "ALPACA_API_KEY": "paper-key",
                "ALPACA_API_SECRET": "paper-secret",
                "ALPACA_ENDPOINT": "https://paper-api.alpaca.markets/v2",
            }
        )

        self.assertEqual(update["active_broker"], "alpaca")
        self.assertTrue(update["simulation_mode"])
        self.assertTrue(update["auto_trading_enabled"])
        self.assertEqual(update["broker_configs"]["alpaca"]["base_url"], "https://paper-api.alpaca.markets")
        self.assertEqual(update["broker_configs"]["alpaca"]["api_key"], "paper-key")
        self.assertEqual(update["broker_configs"]["alpaca"]["api_secret"], "paper-secret")

    def test_build_update_rejects_live_alpaca_endpoint(self):
        from alpaca_paper_settings import AlpacaPaperSettingsError, build_alpaca_paper_settings_update

        with self.assertRaises(AlpacaPaperSettingsError):
            build_alpaca_paper_settings_update(
                {
                    "ALPACA_API_KEY": "paper-key",
                    "ALPACA_API_SECRET": "paper-secret",
                    "ALPACA_ENDPOINT": "https://api.alpaca.markets/v2",
                }
            )

    def test_apply_initializes_sqlite_and_masks_returned_credentials(self):
        from alpaca_paper_settings import apply_alpaca_paper_settings

        previous_database_path = os.environ.get("DATABASE_PATH")
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "settings.db"
            env_path = pathlib.Path(temp_dir) / ".env.local"
            env_path.write_text(
                "\n".join(
                    [
                        "ALPACA_API_KEY=paper-key",
                        "ALPACA_API_SECRET=paper-secret",
                        "ALPACA_ENDPOINT=https://paper-api.alpaca.markets/v2",
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["DATABASE_PATH"] = str(db_path)
            sys.modules.pop("database_sqlite", None)
            try:
                result = apply_alpaca_paper_settings(str(env_path))
                import database_sqlite

                settings = database_sqlite.get_settings()
            finally:
                try:
                    from utils import credentials

                    credentials._fernet = None
                except Exception:
                    pass
                sys.modules.pop("database_sqlite", None)
                if previous_database_path is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = previous_database_path

        self.assertEqual(result["status"], "configured")
        self.assertEqual(settings["active_broker"], "alpaca")
        self.assertTrue(settings["simulation_mode"])
        self.assertTrue(settings["auto_trading_enabled"])
        self.assertEqual(settings["broker_configs"]["alpaca"]["base_url"], "https://paper-api.alpaca.markets")
        self.assertEqual(result["applied"]["broker_configs"]["alpaca"]["api_key"], "********")
        self.assertNotIn("paper-secret", str(result))

    def test_apply_uses_env_file_credential_key_for_encryption(self):
        from alpaca_paper_settings import apply_alpaca_paper_settings

        previous_database_path = os.environ.get("DATABASE_PATH")
        previous_credential_key = os.environ.get("CREDENTIAL_KEY")
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "settings.db"
            env_path = pathlib.Path(temp_dir) / ".env.local"
            env_path.write_text(
                "\n".join(
                    [
                        "ALPACA_API_KEY=paper-key",
                        "ALPACA_API_SECRET=paper-secret",
                        "ALPACA_ENDPOINT=https://paper-api.alpaca.markets/v2",
                        "CREDENTIAL_KEY=" + ("a" * 64),
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["DATABASE_PATH"] = str(db_path)
            os.environ.pop("CREDENTIAL_KEY", None)
            sys.modules.pop("database_sqlite", None)
            try:
                result = apply_alpaca_paper_settings(str(env_path))
                import database_sqlite

                settings = database_sqlite.get_settings()
            finally:
                try:
                    from utils import credentials

                    credentials._fernet = None
                except Exception:
                    pass
                sys.modules.pop("database_sqlite", None)
                if previous_database_path is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = previous_database_path
                if previous_credential_key is None:
                    os.environ.pop("CREDENTIAL_KEY", None)
                else:
                    os.environ["CREDENTIAL_KEY"] = previous_credential_key

        self.assertEqual(result["status"], "configured")
        self.assertTrue(settings["broker_configs"]["alpaca"]["api_key"].startswith("enc:"))
        self.assertTrue(settings["broker_configs"]["alpaca"]["api_secret"].startswith("enc:"))
        self.assertNotIn("paper-secret", str(result))


if __name__ == "__main__":
    unittest.main()
