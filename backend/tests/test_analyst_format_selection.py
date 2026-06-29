import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeFormat:
    def __init__(self, name, identifiers, result=None):
        self.name = name
        self.identifiers = identifiers
        self.result = result
        self.calls = 0

    def parse(self, message):
        self.calls += 1
        return self.result


class AnalystFormatSelectionTests(unittest.TestCase):
    def test_auto_parse_tries_preferred_format_first(self):
        import analyst_formats

        preferred_result = object()
        preferred = FakeFormat("Preferred", [], preferred_result)
        default = FakeFormat("Default", ["$"], object())
        original_formats = analyst_formats.ANALYST_FORMATS
        try:
            analyst_formats.ANALYST_FORMATS = {
                "default": default,
                "preferred": preferred,
            }

            result = analyst_formats.auto_parse("$SPY 500C", preferred_format="preferred")
        finally:
            analyst_formats.ANALYST_FORMATS = original_formats

        self.assertIs(result, preferred_result)
        self.assertEqual(preferred.calls, 1)
        self.assertEqual(default.calls, 0)

    def test_auto_parse_prioritizes_specific_identifier_match_before_default(self):
        import analyst_formats

        specialist_result = object()
        default = FakeFormat("Default", ["$"], object())
        specialist = FakeFormat("Specialist", ["VIP"], specialist_result)
        original_formats = analyst_formats.ANALYST_FORMATS
        try:
            analyst_formats.ANALYST_FORMATS = {
                "default": default,
                "specialist": specialist,
            }

            result = analyst_formats.auto_parse("$SPY VIP 500C")
        finally:
            analyst_formats.ANALYST_FORMATS = original_formats

        self.assertIs(result, specialist_result)
        self.assertEqual(specialist.calls, 1)
        self.assertEqual(default.calls, 0)


if __name__ == "__main__":
    unittest.main()
