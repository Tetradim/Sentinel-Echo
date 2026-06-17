import pathlib
import sys
import types
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class DiscordAlertTextTests(unittest.TestCase):
    def test_embed_only_alert_text_can_be_parsed(self):
        from discord_alert_text import build_discord_alert_text
        from utils import parse_alert

        embed = types.SimpleNamespace(
            title="Trade Alert",
            description="BTO SPY 500C 6/21 @ 1.25",
            fields=[
                types.SimpleNamespace(name="Analyst", value="Momentum room"),
                types.SimpleNamespace(name="Notes", value="Starter size"),
            ],
            footer=types.SimpleNamespace(text="risk-managed"),
            author=types.SimpleNamespace(name="Options Desk"),
        )
        message = types.SimpleNamespace(content="", embeds=[embed])

        alert_text = build_discord_alert_text(message)
        parsed = parse_alert(alert_text)

        self.assertIn("Trade Alert", alert_text)
        self.assertIn("Options Desk", alert_text)
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["strike"], 500.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["expiration"], "6/21")
        self.assertEqual(parsed["entry_price"], 1.25)


if __name__ == "__main__":
    unittest.main()
