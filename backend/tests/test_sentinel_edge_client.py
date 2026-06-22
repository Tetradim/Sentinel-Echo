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


if __name__ == "__main__":
    unittest.main()
