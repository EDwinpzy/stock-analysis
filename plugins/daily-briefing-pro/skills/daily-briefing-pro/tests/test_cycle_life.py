import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import cycle_life


class FetchDailyTests(unittest.TestCase):
    def setUp(self):
        cycle_life._FETCHED_THIS_RUN.clear()

    def test_partial_rows_stop_after_one_source_round(self):
        calls = []

        def fake_fetch(ak, source, code, prefix, start, end):
            calls.append(source)
            if source == "eastmoney":
                return [["2026-11-01", 10.0], ["2026-11-10", 11.0]]
            return []

        with patch.object(cycle_life, "_fetch_one", side_effect=fake_fetch), \
                patch.object(cycle_life, "_throttle", lambda: None), \
                patch.dict(sys.modules, {"akshare": object()}):
            rows = cycle_life.fetch_daily(
                "600000", "2026-10-01", "2026-11-12", {}, "2026-11-12")

        self.assertEqual(rows[-1][0], "2026-11-10")
        self.assertEqual(calls, ["eastmoney", "sina", "tencent"])

    def test_same_run_reuses_partial_cache(self):
        cache = {
            "600000": {
                "fetched_at": "2026-11-12",
                "rows": [["2026-11-10", 11.0]],
                "source": "eastmoney",
                "complete": False,
            }
        }
        cycle_life._FETCHED_THIS_RUN.add("600000")

        with patch.object(
                cycle_life, "_fetch_one",
                side_effect=AssertionError("partial same-run cache must not refetch")):
            rows = cycle_life.fetch_daily(
                "600000", "2026-10-01", "2026-11-12", cache, "2026-11-12")

        self.assertEqual(rows[-1][0], "2026-11-10")


if __name__ == "__main__":
    unittest.main()
