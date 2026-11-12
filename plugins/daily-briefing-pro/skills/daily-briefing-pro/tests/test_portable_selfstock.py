import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import news_screener  # noqa: E402
import parse_selfstock  # noqa: E402
import parse_stockblock  # noqa: E402


class PortableSelfstockTests(unittest.TestCase):
    def test_selfstock_environment_path_drives_source_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SelfStockInfo.json"
            path.write_text(
                json.dumps([{"C": "600519", "M": "17"}, {"C": "000001", "M": "33"}]),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"THS_SELFSTOCK_PATH": str(path)}):
                source = parse_selfstock.get_selfstock_source_info()
                health = news_screener.cmd_health()
                stocks = news_screener.cmd_stocks(
                    SimpleNamespace(codes=False, full_codes=False)
                )

        self.assertTrue(source["found"])
        self.assertEqual(source["filepath"], str(path))
        self.assertEqual(source["count"], 2)
        self.assertEqual(health["selfstock"]["path"], str(path))
        self.assertEqual(stocks["source_file"], str(path))
        self.assertEqual(stocks["source_format"], "old_json")

    def test_ths_home_environment_is_a_portable_discovery_root(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"THS_HOME": temp}):
                roots = parse_selfstock._find_ths_base_dirs()

        self.assertIn(temp, roots)

    def test_stockblock_accepts_explicit_path_and_selfstock_json_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stockblock = root / "stockblock.ini"
            stockblock.write_text("[BLOCK_STOCK_CONTEXT]\n1=17:600519\n", encoding="utf-8")
            selfstock = root / "SelfStockInfo.json"
            selfstock.write_text("[]", encoding="utf-8")

            with patch.dict(os.environ, {"THS_STOCKBLOCK_PATH": str(stockblock)}):
                self.assertEqual(parse_stockblock.default_stockblock_file(), str(stockblock))

            with patch.dict(
                os.environ,
                {"THS_SELFSTOCK_PATH": str(selfstock)},
                clear=False,
            ):
                os.environ.pop("THS_STOCKBLOCK_PATH", None)
                self.assertEqual(parse_stockblock.default_stockblock_file(), str(stockblock))


if __name__ == "__main__":
    unittest.main()
