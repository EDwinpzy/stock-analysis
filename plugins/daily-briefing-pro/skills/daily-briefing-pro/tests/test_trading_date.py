import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from trading_date import get_recent_trade_date


class TradingDateTests(unittest.TestCase):
    def test_same_day_before_five_uses_previous_weekday(self):
        now = datetime(2026, 9, 24, 4, 59)

        self.assertEqual(get_recent_trade_date("2026-09-24", now=now), "2026-09-23")

    def test_same_day_at_five_keeps_current_weekday(self):
        now = datetime(2026, 9, 24, 5, 0)

        self.assertEqual(get_recent_trade_date("2026-09-24", now=now), "2026-09-24")

    def test_early_sunday_rolls_back_to_friday(self):
        now = datetime(2026, 9, 27, 4, 30)

        self.assertEqual(get_recent_trade_date("2026-09-27", now=now), "2026-09-25")

    def test_historical_override_is_not_shifted_by_current_time(self):
        now = datetime(2026, 9, 24, 4, 0)

        self.assertEqual(get_recent_trade_date("2026-09-22", now=now), "2026-09-22")


if __name__ == "__main__":
    unittest.main()
