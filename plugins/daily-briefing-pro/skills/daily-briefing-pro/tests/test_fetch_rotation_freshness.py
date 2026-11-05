import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_rotation
import pandas as pd


class RotationFreshnessTests(unittest.TestCase):
    target_date = "2026-10-13"
    trading_days = [
        "2026-10-08",
        "2026-10-09",
        "2026-10-12",
        "2026-10-13",
    ]

    def run_collector(self, prediction_date):
        with tempfile.TemporaryDirectory() as temp:
            model_dir = Path(temp)
            (model_dir / "config.json").write_text(
                json.dumps({"universe": "ths"}), encoding="utf-8"
            )
            completed = SimpleNamespace(
                returncode=0,
                stdout=f"rotation scores, as of {prediction_date}",
                stderr="",
            )
            output = io.StringIO()
            with (
                patch.object(sys, "argv", ["fetch_rotation.py", "--date", self.target_date]),
                patch.object(fetch_rotation, "find_model_dir", return_value=model_dir),
                patch.object(fetch_rotation, "trade_dates", return_value=self.trading_days),
                patch.object(
                    fetch_rotation,
                    "refresh_industry_data",
                    return_value={
                        "expected_industries": 90,
                        "complete_industries": 90,
                        "data_date": self.target_date,
                        "benchmark_data_date": self.target_date,
                    },
                ) as refresh,
                patch.object(fetch_rotation.subprocess, "run", return_value=completed) as run,
                patch.object(
                    fetch_rotation,
                    "build_result",
                    return_value={
                        "date": self.target_date,
                        "asof": self.target_date,
                        "status": "ok",
                        "entries": [],
                    },
                ) as build,
                patch.object(fetch_rotation, "read_csv_rows", return_value=[{}] * 90),
                redirect_stdout(output),
            ):
                fetch_rotation.main()

        return json.loads(output.getvalue()), refresh, run, build

    def test_stale_prediction_is_reported_as_error_and_not_built_as_current(self):
        result, refresh, run, build = self.run_collector("2026-10-09")

        self.assertEqual(result["date"], self.target_date)
        self.assertEqual(result["asof"], "2026-10-09")
        self.assertEqual(result["status"], "error")
        self.assertIn("要求2026-10-13", result["note"])
        self.assertEqual(refresh.call_args.args[1], self.target_date)
        self.assertIn(self.target_date, run.call_args.args[0])
        build.assert_not_called()

    def test_current_prediction_keeps_the_date_reported_by_this_run(self):
        result, refresh, run, build = self.run_collector(self.target_date)

        self.assertEqual(result["date"], self.target_date)
        self.assertEqual(result["asof"], self.target_date)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["coverage"]["data_date"], self.target_date)
        self.assertEqual(result["coverage"]["benchmark_data_date"], self.target_date)
        refresh.assert_called_once()
        run.assert_called_once()
        build.assert_called_once()
        self.assertEqual(build.call_args.args[0], self.target_date)
        self.assertEqual(build.call_args.args[2], self.target_date)

    def test_benchmark_cache_is_extended_without_losing_training_history(self):
        with tempfile.TemporaryDirectory() as temp:
            model_dir = Path(temp)
            data_dir = model_dir / "data"
            data_dir.mkdir()
            path = data_dir / "benchmark_csi300.csv"
            original = "date,close\n2026-10-09,4500\n"
            path.write_text(original, encoding="utf-8")
            response = pd.DataFrame(
                {"date": ["2026-10-09", "2026-10-12", self.target_date], "close": [4500, 4510, 4520]}
            )

            with patch("akshare.stock_zh_index_daily", return_value=response):
                asof = fetch_rotation.refresh_benchmark_data(model_dir, self.target_date)

            refreshed = pd.read_csv(path, dtype={"date": str})
            self.assertEqual(asof, self.target_date)
            self.assertEqual(refreshed["date"].tolist(), ["2026-10-09", "2026-10-12", self.target_date])
            self.assertEqual(refreshed.iloc[-1]["close"], 4520)
            self.assertEqual(path.with_name("benchmark_csi300.before-2026-10-13.csv").read_text(encoding="utf-8"), original)

    def test_stale_benchmark_response_does_not_replace_cached_file(self):
        with tempfile.TemporaryDirectory() as temp:
            model_dir = Path(temp)
            data_dir = model_dir / "data"
            data_dir.mkdir()
            path = data_dir / "benchmark_csi300.csv"
            original = "date,close\n2026-10-09,4500\n"
            path.write_text(original, encoding="utf-8")
            response = pd.DataFrame({"date": ["2026-10-09"], "close": [4500]})

            with patch("akshare.stock_zh_index_daily", return_value=response), patch(
                "akshare.stock_zh_index_daily_tx", return_value=response
            ):
                with self.assertRaisesRegex(ValueError, "未补齐到 2026-10-13"):
                    fetch_rotation.refresh_benchmark_data(model_dir, self.target_date)

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_industry_refresh_also_advances_the_benchmark_input(self):
        with tempfile.TemporaryDirectory() as temp:
            model_dir = Path(temp)
            data_dir = model_dir / "data"
            data_dir.mkdir()
            (data_dir / "ths_industry_info.csv").write_text(
                "code,name\n881001,测试行业\n", encoding="utf-8"
            )
            (data_dir / "ths_industry_daily.csv").write_text(
                "date,code,name,close\n2026-10-09,881001,测试行业,100\n",
                encoding="utf-8",
            )
            (data_dir / "benchmark_csi300.csv").write_text(
                "date,close\n2026-10-09,4500\n", encoding="utf-8"
            )
            industry = pd.DataFrame({"日期": [self.target_date], "收盘价": [101]})
            benchmark = pd.DataFrame(
                {"date": ["2026-10-09", self.target_date], "close": [4500, 4520]}
            )

            with patch("akshare.stock_board_industry_index_ths", return_value=industry), patch(
                "akshare.stock_zh_index_daily", return_value=benchmark
            ):
                coverage = fetch_rotation.refresh_industry_data(model_dir, self.target_date)

            self.assertEqual(coverage["complete_industries"], 1)
            self.assertEqual(coverage["data_date"], self.target_date)
            self.assertEqual(coverage["benchmark_data_date"], self.target_date)
            self.assertEqual(
                pd.read_csv(data_dir / "ths_industry_daily.csv")["date"].max(),
                self.target_date,
            )
            self.assertEqual(
                pd.read_csv(data_dir / "benchmark_csi300.csv")["date"].max(),
                self.target_date,
            )


if __name__ == "__main__":
    unittest.main()
