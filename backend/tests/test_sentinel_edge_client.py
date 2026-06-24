import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class SentinelEdgeClientTests(unittest.TestCase):
    def test_fallback_analysis_has_no_confidence_when_edge_is_unavailable(self):
        from sentinel_edge_client import ConfidenceLevel, SentinelEdgeClient

        client = SentinelEdgeClient()

        analysis = client._create_fallback_analysis("SPY", "Timeout")

        self.assertEqual(analysis.ticker, "SPY")
        self.assertEqual(analysis.overall_confidence, 0.0)
        self.assertEqual(analysis.confidence_level, ConfidenceLevel.NONE)
        self.assertEqual(analysis.recommendation, "HOLD")
        self.assertFalse(analysis.is_buyable)
        self.assertIn("Edge unavailable", analysis.reason)


class AlertFilterEdgeBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_filter_blocks_execution_when_edge_filter_is_disabled(self):
        from alert_filter import AlertFilter

        alert_filter = AlertFilter(enabled=False)
        alert_filter._parse_message = lambda _message: {"ticker": "SPY", "signal_type": "BTO"}

        result = await alert_filter.process_alert("SPY 600C BTO")

        self.assertEqual(result.ticker, "SPY")
        self.assertFalse(result.should_execute)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.confidence_level, "NONE")
        self.assertEqual(result.recommendation, "HOLD")
        self.assertIn("Edge not connected", result.skip_reason)

    async def test_filter_blocks_execution_when_edge_analysis_errors(self):
        from alert_filter import AlertFilter

        class FailingAnalyzer:
            async def should_execute(self, ticker, signal_type):
                raise RuntimeError(f"Edge unavailable for {ticker}:{signal_type}")

        alert_filter = AlertFilter(enabled=False)
        alert_filter.enabled = True
        alert_filter.analyzer = FailingAnalyzer()
        alert_filter._parse_message = lambda _message: {"ticker": "SPY", "signal_type": "BTO"}

        result = await alert_filter.process_alert("SPY 600C BTO")

        self.assertEqual(result.ticker, "SPY")
        self.assertFalse(result.should_execute)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.confidence_level, "NONE")
        self.assertEqual(result.recommendation, "HOLD")
        self.assertIn("Edge error", result.skip_reason)


if __name__ == "__main__":
    unittest.main()
