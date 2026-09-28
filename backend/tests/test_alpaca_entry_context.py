import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.closed = False

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


class AlpacaEntryContextTests(unittest.TestCase):
    def test_option_quote_still_loads_when_underlying_bars_fail(self):
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        session = FakeSession(
            [
                FakeResponse(503, {"message": "bars unavailable"}),
                FakeResponse(
                    200,
                    {
                        "quotes": {
                            "SPY260901C00765000": {
                                "bp": 0.34,
                                "ap": 0.36,
                                "t": "2026-09-01T14:31:30Z",
                            }
                        }
                    },
                ),
            ]
        )
        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="key",
                api_secret="secret",
                base_url="https://paper-api.alpaca.markets",
            )
        )
        client._session = session

        context = asyncio.run(
            client.get_option_market_context(
                ticker="SPY",
                strike=765.0,
                option_type="CALL",
                expiration="09/01/26",
            )
        )

        self.assertEqual(context["bars"], [])
        self.assertEqual(context["option_bid"], 0.34)
        self.assertEqual(context["option_quote_observed_at"], "2026-09-01T14:31:30Z")

    def test_general_option_context_method_is_available_for_exit_management(self):
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        session = FakeSession(
            [
                FakeResponse(200, {"bars": []}),
                FakeResponse(
                    200,
                    {
                        "quotes": {
                            "SPY260901C00765000": {
                                "bp": 0.34,
                                "ap": 0.36,
                                "t": "2026-09-01T14:31:30Z",
                            }
                        }
                    },
                ),
            ]
        )
        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="key",
                api_secret="secret",
                base_url="https://paper-api.alpaca.markets",
            )
        )
        client._session = session

        context = asyncio.run(
            client.get_option_market_context(
                ticker="SPY",
                strike=765.0,
                option_type="CALL",
                expiration="09/01/26",
            )
        )

        self.assertEqual(context["option_bid"], 0.34)
        self.assertEqual(context["option_ask"], 0.36)
        self.assertEqual(context["option_quote_observed_at"], "2026-09-01T14:31:30Z")

    def test_fetches_normalized_bars_and_latest_option_quote(self):
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        session = FakeSession(
            [
                FakeResponse(
                    200,
                    {
                        "bars": [
                            {"o": 763.0, "h": 763.2, "l": 762.9, "c": 763.1, "v": 1000, "t": "2026-09-01T14:30:00Z"},
                            {"o": 763.1, "h": 763.4, "l": 763.0, "c": 763.3, "v": 1200, "t": "2026-09-01T14:31:00Z"},
                        ]
                    },
                ),
                FakeResponse(
                    200,
                    {
                        "quotes": {
                            "SPY260901C00765000": {
                                "bp": 0.34,
                                "ap": 0.36,
                                "t": "2026-09-01T14:31:30Z",
                            }
                        }
                    },
                ),
            ]
        )
        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="key",
                api_secret="secret",
                base_url="https://paper-api.alpaca.markets",
            )
        )
        client._session = session

        context = asyncio.run(
            client.get_entry_market_context(
                ticker="SPY",
                strike=765.0,
                option_type="CALL",
                expiration="09/01/26",
            )
        )

        self.assertEqual(len(context["bars"]), 2)
        self.assertEqual(context["option_bid"], 0.34)
        self.assertEqual(context["option_ask"], 0.36)
        self.assertEqual(context["option_symbol"], "SPY260901C00765000")
        self.assertEqual(context["source"], "alpaca")
        self.assertEqual(
            session.requests[0][0],
            "https://data.alpaca.markets/v2/stocks/SPY/bars",
        )
        self.assertEqual(session.requests[0][1]["params"]["timeframe"], "1Min")
        self.assertEqual(session.requests[0][1]["params"]["limit"], 30)
        self.assertEqual(
            session.requests[1][0],
            "https://data.alpaca.markets/v1beta1/options/quotes/latest",
        )
        self.assertEqual(session.requests[1][1]["params"]["symbols"], "SPY260901C00765000")

    def test_market_data_failure_returns_empty_context_without_raising(self):
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        session = FakeSession(
            [
                FakeResponse(503, {"message": "unavailable"}),
                FakeResponse(503, {"message": "quote unavailable"}),
            ]
        )
        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="key",
                api_secret="secret",
                base_url="https://paper-api.alpaca.markets",
            )
        )
        client._session = session

        context = asyncio.run(
            client.get_entry_market_context(
                ticker="SPY",
                strike=765.0,
                option_type="CALL",
                expiration="09/01/26",
            )
        )

        self.assertEqual(context["bars"], [])
        self.assertIsNone(context["option_bid"])
        self.assertIsNone(context["option_ask"])


if __name__ == "__main__":
    unittest.main()
