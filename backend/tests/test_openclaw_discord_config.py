import pathlib
import sys
import tempfile
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class OpenClawDiscordConfigTests(unittest.TestCase):
    def test_loads_token_and_enabled_channel_ids_from_openclaw_home(self):
        from openclaw_discord_config import load_openclaw_discord_config

        with tempfile.TemporaryDirectory() as temp_dir:
            home = pathlib.Path(temp_dir)
            (home / ".env").write_text(
                "OPENCLAW_GATEWAY_TOKEN=gateway-token\n"
                "DISCORD_BOT_TOKEN=discord-super-secret-token\n",
                encoding="utf-8",
            )
            (home / "openclaw.json").write_text(
                """
                {
                  "channels": {
                    "discord": {
                      "guilds": {
                        "1508501048610914406": {
                          "channels": {
                            "1508501050720653535": {"enabled": true},
                            "1508501050720653536": {"enabled": false}
                          }
                        }
                      }
                    }
                  }
                }
                """,
                encoding="utf-8",
            )

            config = load_openclaw_discord_config(home)

        self.assertTrue(config.token_configured)
        self.assertEqual(config.token, "discord-super-secret-token")
        self.assertEqual(config.channel_ids, ["1508501050720653535"])
        self.assertEqual(config.guild_ids, ["1508501048610914406"])
        self.assertEqual(config.source, "openclaw")

    def test_public_summary_does_not_expose_openclaw_token(self):
        from openclaw_discord_config import load_openclaw_discord_config

        with tempfile.TemporaryDirectory() as temp_dir:
            home = pathlib.Path(temp_dir)
            (home / ".env").write_text(
                "DISCORD_BOT_TOKEN=discord-super-secret-token\n",
                encoding="utf-8",
            )
            (home / "openclaw.json").write_text(
                """
                {
                  "channels": {
                    "discord": {
                      "guilds": {
                        "1508501048610914406": {
                          "channels": {
                            "1508501050720653535": {"enabled": true}
                          }
                        }
                      }
                    }
                  }
                }
                """,
                encoding="utf-8",
            )

            summary = load_openclaw_discord_config(home).public_summary()

        self.assertTrue(summary["token_configured"])
        self.assertEqual(summary["channel_count"], 1)
        self.assertNotIn("discord-super-secret-token", str(summary))

    def test_explicit_consolidation_env_wins_over_openclaw_fallback(self):
        from openclaw_discord_config import resolve_discord_runtime_config

        with tempfile.TemporaryDirectory() as temp_dir:
            home = pathlib.Path(temp_dir)
            (home / ".env").write_text(
                "DISCORD_BOT_TOKEN=openclaw-secret\n",
                encoding="utf-8",
            )
            (home / "openclaw.json").write_text(
                """
                {
                  "channels": {
                    "discord": {
                      "guilds": {
                        "1508501048610914406": {
                          "channels": {
                            "1508501050720653535": {"enabled": true}
                          }
                        }
                      }
                    }
                  }
                }
                """,
                encoding="utf-8",
            )

            config = resolve_discord_runtime_config(
                {
                    "DISCORD_BOT_TOKEN": "explicit-secret",
                    "DISCORD_CHANNEL_IDS": "111111111111111111,222222222222222222",
                },
                openclaw_home=home,
            )

        self.assertEqual(config.source, "environment")
        self.assertEqual(config.token, "explicit-secret")
        self.assertEqual(
            config.channel_ids,
            ["111111111111111111", "222222222222222222"],
        )

    def test_discord_start_settings_win_over_openclaw_fallback(self):
        from routes.discord import resolve_discord_start_config

        with tempfile.TemporaryDirectory() as temp_dir:
            home = pathlib.Path(temp_dir)
            (home / ".env").write_text(
                "DISCORD_BOT_TOKEN=openclaw-secret\n",
                encoding="utf-8",
            )
            (home / "openclaw.json").write_text(
                """
                {
                  "channels": {
                    "discord": {
                      "guilds": {
                        "1508501048610914406": {
                          "channels": {
                            "1508501050720653535": {"enabled": true}
                          }
                        }
                      }
                    }
                  }
                }
                """,
                encoding="utf-8",
            )

            config = resolve_discord_start_config(
                {
                    "discord_token": "settings-secret",
                    "discord_channel_ids": ["333333333333333333"],
                },
                env={},
                openclaw_home=home,
            )

        self.assertEqual(config.source, "settings")
        self.assertEqual(config.token, "settings-secret")
        self.assertEqual(config.channel_ids, ["333333333333333333"])

    def test_discord_start_uses_openclaw_when_settings_are_empty(self):
        from routes.discord import resolve_discord_start_config

        with tempfile.TemporaryDirectory() as temp_dir:
            home = pathlib.Path(temp_dir)
            (home / ".env").write_text(
                "DISCORD_BOT_TOKEN=openclaw-secret\n",
                encoding="utf-8",
            )
            (home / "openclaw.json").write_text(
                """
                {
                  "channels": {
                    "discord": {
                      "guilds": {
                        "1508501048610914406": {
                          "channels": {
                            "1508501050720653535": {"enabled": true}
                          }
                        }
                      }
                    }
                  }
                }
                """,
                encoding="utf-8",
            )

            config = resolve_discord_start_config(
                {},
                env={},
                openclaw_home=home,
            )

        self.assertEqual(config.source, "openclaw")
        self.assertEqual(config.token, "openclaw-secret")
        self.assertEqual(config.channel_ids, ["1508501050720653535"])


if __name__ == "__main__":
    unittest.main()
