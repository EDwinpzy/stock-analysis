import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_briefing


class BriefingSectionTests(unittest.TestCase):
    def test_full_briefing_omits_watchlist_news_without_loading_its_snapshot(self):
        loaded_files = []
        load_json = build_briefing.load_json

        def record_load(filename):
            loaded_files.append(filename)
            return load_json(filename)

        with tempfile.TemporaryDirectory(prefix="briefing-sections-") as temp:
            with (
                patch.object(build_briefing, "DATA_DIR", Path(temp)),
                patch.object(build_briefing, "load_json", side_effect=record_load),
                patch.object(build_briefing, "fetch_index_data", return_value={}),
                patch.object(
                    build_briefing,
                    "fetch_sentiment_chart_data",
                    return_value=([], [], []),
                ),
            ):
                html = build_briefing.build_html("2026-09-30", "2026-09-30")

        self.assertNotIn("selfstock_today.json", loaded_files)
        self.assertNotIn("自选股新闻", html)
        self.assertIn("共 <b>12</b> 个板块", html)


if __name__ == "__main__":
    unittest.main()
