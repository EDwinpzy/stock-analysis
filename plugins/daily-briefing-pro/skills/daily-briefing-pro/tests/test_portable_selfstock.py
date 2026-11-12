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

    def test_selfstock_codes_environment_avoids_local_file_discovery(self):
        with patch.dict(
            os.environ,
            {"THS_SELFSTOCK_CODES": "600519, 000001；300750.SZ"},
            clear=True,
        ):
            source = parse_selfstock.get_selfstock_source_info()
            stocks = parse_selfstock.parse_selfstock()

        self.assertTrue(source["found"])
        self.assertEqual(source["format"], "env_codes")
        self.assertEqual(source["count"], 3)
        self.assertEqual(
            [stock["full_code"] for stock in stocks],
            ["600519.SH", "000001.SZ", "300750.SZ"],
        )

    def test_selfstock_json_environment_supports_structured_codes(self):
        payload = json.dumps(
            {"stocks": [{"code": "600519", "market": "17"}, {"code": "000001", "market": "33"}]}
        )
        with patch.dict(os.environ, {"THS_SELFSTOCK_JSON": payload}, clear=True):
            source = parse_selfstock.get_selfstock_source_info()
            stocks = parse_selfstock.parse_selfstock()

        self.assertEqual(source["format"], "env_json")
        self.assertEqual(source["count"], 2)
        self.assertEqual([stock["code"] for stock in stocks], ["600519", "000001"])

    def test_stockblock_accepts_explicit_path_and_selfstock_json_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stockblock = root / "stockblock.ini"
            stockblock.write_text("[BLOCK_STOCK_CONTEXT]\n1=17:600519\n", encoding="utf-8")
            with patch.dict(os.environ, {"THS_STOCKBLOCK_PATH": str(stockblock)}):
                self.assertEqual(parse_stockblock.default_stockblock_file(), str(stockblock))

            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(parse_stockblock.default_stockblock_file(), "")


if __name__ == "__main__":
    unittest.main()
