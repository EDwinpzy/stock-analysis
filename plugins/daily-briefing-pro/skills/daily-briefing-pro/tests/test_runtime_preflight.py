import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import runtime_preflight as preflight
from fetch_rotation import find_model_dir, model_dir_candidates


class RotationModelPathTests(unittest.TestCase):
    def test_package_relative_model_is_found_without_windows_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "plugin" / "skills" / "daily-briefing-pro"
            model = package / "models" / "sw_rotation_model"
            model.mkdir(parents=True)
            (model / "run.py").write_text("", encoding="utf-8")
            (model / "config.json").write_text('{"universe": "ths"}', encoding="utf-8")

            candidates = model_dir_candidates(package, env={})
            self.assertEqual(find_model_dir(candidates), model)

    def test_environment_override_has_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "package"
            package.mkdir()
            model = Path(temp) / "custom-model"
            model.mkdir()
            (model / "run.py").write_text("", encoding="utf-8")
            (model / "config.json").write_text("{}", encoding="utf-8")

            candidates = model_dir_candidates(package, env={"ROTATION_MODEL_DIR": str(model)})
            self.assertEqual(candidates[0], model)
            self.assertEqual(find_model_dir(candidates), model)


class PreflightCheckTests(unittest.TestCase):
    def test_hithink_environment_key_bypasses_local_credential_store(self):
        with patch.object(preflight.shutil, "which", return_value="hithink-finance"), \
             patch.object(preflight.subprocess, "run") as auth_status, \
             patch("_hithink.trade_dates", return_value=["2026-10-19"]):
            check, days = preflight._check_hithink({"HITHINK_FINANCE_API_KEY": "configured"})

        auth_status.assert_not_called()
        self.assertEqual(check.state, "ok")
        self.assertEqual(days, ["2026-10-19"])

    def test_short_panel_is_blocked_and_stale_panel_is_warning(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            panel = data / "sentiment_panel_v32.csv"
            header = ",".join(preflight.PANEL_COLUMNS) + "\n"

            def write_rows(dates):
                rows = []
                for day in dates:
                    values = ["1"] * len(preflight.PANEL_COLUMNS)
                    values[preflight.PANEL_COLUMNS.index("date")] = day
                    values[preflight.PANEL_COLUMNS.index("source")] = "test"
                    rows.append(",".join(values) + "\n")
                panel.write_text(header + "".join(rows), encoding="utf-8")

            write_rows(["2026-10-01"] * 10)
            short = preflight._check_panel(data, "2026-10-20")
            self.assertEqual(short.state, "error")

            write_rows(
                [f"2026-08-{day:02d}" for day in range(1, 29)]
                + ["2026-09-01"] * 32
            )
            stale = preflight._check_panel(data, "2026-10-20")
            self.assertEqual(stale.state, "warning")
            self.assertIn("2026-09-01", stale.detail)

    def test_panel_missing_model_columns_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            panel = data / "sentiment_panel_v32.csv"
            panel.write_text("date,sh_close\n2026-10-01,3900\n" * 100, encoding="utf-8")

            check = preflight._check_panel(data, "2026-10-20")

        self.assertEqual(check.state, "error")
        self.assertIn("limit_up", check.detail)

    def test_cookie_parser_never_echoes_file_content(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cookies.json"
            path.write_text("private-cookie-value", encoding="utf-8")
            count, reason = preflight._cookie_count(path)
            self.assertEqual(count, 0)
            self.assertNotIn("private-cookie-value", reason)

    def test_ths_model_requires_original_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp)
            (model / "run.py").write_text("", encoding="utf-8")
            (model / "config.json").write_text('{"universe": "ths"}', encoding="utf-8")
            for name in ("data.py", "features.py", "engine.py"):
                (model / "src").mkdir(exist_ok=True)
                (model / "src" / name).write_text("", encoding="utf-8")

            checks = preflight._check_model(model, "2026-10-20")
            self.assertTrue(any(item.state == "error" and item.key == "rotation_inputs" for item in checks))

    def test_complete_ths_model_passes_input_check(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp)
            (model / "data").mkdir()
            (model / "run.py").write_text("", encoding="utf-8")
            (model / "config.json").write_text('{"universe": "ths"}', encoding="utf-8")
            for name in ("data.py", "features.py", "engine.py"):
                (model / "src").mkdir(exist_ok=True)
                (model / "src" / name).write_text("", encoding="utf-8")
            (model / "data" / "ths_industry_info.csv").write_text(
                "code,name\n881001,测试行业\n", encoding="utf-8"
            )
            (model / "data" / "ths_industry_daily.csv").write_text(
                "date,code,name,close\n2026-10-20,881001,测试行业,100\n", encoding="utf-8"
            )
            (model / "data" / "benchmark_csi300.csv").write_text(
                "date,close\n2026-10-20,4500\n", encoding="utf-8"
            )

            checks = preflight._check_model(model, "2026-10-20")
            self.assertFalse(any(item.state == "error" for item in checks))
            self.assertTrue(any(item.key == "rotation_inputs" and item.state == "ok" for item in checks))

    def test_non_ths_model_requires_original_input_files(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp)
            (model / "run.py").write_text("", encoding="utf-8")
            (model / "config.json").write_text('{"universe": "sw"}', encoding="utf-8")
            for name in ("data.py", "features.py", "engine.py"):
                (model / "src").mkdir(exist_ok=True)
                (model / "src" / name).write_text("", encoding="utf-8")

            missing = preflight._check_model(model, "2026-10-20")
            self.assertTrue(
                any(item.state == "error" and item.key == "rotation_inputs" for item in missing)
            )

            (model / "data").mkdir()
            (model / "data" / "sw_l1_info.csv").write_text(
                "code,name\n801010,测试行业\n", encoding="utf-8"
            )
            (model / "data" / "sw_l1_daily.csv").write_text(
                "date,code,close\n2026-10-20,801010,100\n", encoding="utf-8"
            )
            (model / "data" / "benchmark_csi300.csv").write_text(
                "date,close\n2026-10-20,4500\n", encoding="utf-8"
            )
            complete = preflight._check_model(model, "2026-10-20")
            self.assertFalse(any(item.state == "error" for item in complete))
            self.assertTrue(
                any(item.key == "rotation_inputs" and item.state == "ok" for item in complete)
            )

    def test_model_config_must_be_an_object(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp)
            (model / "run.py").write_text("", encoding="utf-8")
            (model / "config.json").write_text("[]", encoding="utf-8")

            checks = preflight._check_model(model, "2026-10-20")

        self.assertTrue(
            any(item.key == "rotation_model" and item.state == "error" for item in checks)
        )

    def test_local_transcription_requires_whisper_and_torch(self):
        with patch.object(preflight, "_whisper_ready", return_value=(False, "whisper/torch 未安装")):
            check = preflight._check_transcription(
                {"DOUYIN_TRANSCRIPT_PROVIDER": "local"}
            )

        self.assertEqual(check.state, "error")
        self.assertIn("whisper", check.detail)

    def test_auto_transcription_accepts_configured_api_without_local_modules(self):
        with patch.object(preflight, "_whisper_ready", return_value=(False, "whisper/torch 未安装")):
            check = preflight._check_transcription(
                {
                    "DOUYIN_TRANSCRIPT_PROVIDER": "auto",
                    "GROQ_API_KEY": "configured",
                }
            )

        self.assertEqual(check.state, "ok")
        self.assertIn("groq", check.detail)

    def test_cloud_local_whisper_fallback_is_a_warning(self):
        with patch.object(preflight, "_whisper_ready", return_value=(True, "small 权重已就绪")):
            check = preflight._check_transcription(
                {
                    "DOUYIN_TRANSCRIPT_PROVIDER": "auto",
                    "DAILY_BRIEFING_CLOUD": "1",
                }
            )

        self.assertEqual(check.state, "warning")
        self.assertIn("本地 Whisper", check.detail)

    def test_resume_mode_skips_collection_only_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "package"
            data = root / "data"
            output = root / "output"
            (package / "scripts").mkdir(parents=True)
            for name in preflight.REQUIRED_SCRIPTS:
                (package / "scripts" / name).write_text("", encoding="utf-8")
            data.mkdir()
            output.mkdir()

            with patch.object(preflight, "_check_modules", return_value=preflight._ok("modules", "模块", "ok")), \
                 patch.object(preflight, "_check_browser", return_value=preflight._ok("browser", "浏览器", "ok")), \
                 patch.object(preflight, "_check_hithink") as hithink, \
                 patch.object(preflight, "_check_semantic_summary") as ai, \
                 patch.object(preflight, "_check_cookie") as cookie, \
                 patch.object(
                     preflight,
                     "_check_resume_datasets",
                     return_value=preflight._ok("resume_inputs", "续跑数据", "ok"),
                 ) as resume_check:
                report = preflight.build_preflight(
                    "2026-10-20",
                    "2026-10-20",
                    data_dir=data,
                    package_dir=package,
                    output_dir=output,
                    collecting=False,
                )

            hithink.assert_not_called()
            ai.assert_not_called()
            cookie.assert_not_called()
            resume_check.assert_called_once()
            self.assertTrue(report.ok)

    def test_default_output_uses_briefing_output_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "package"
            data = root / "data"
            output = root / "reports"
            (package / "scripts").mkdir(parents=True)
            for name in preflight.REQUIRED_SCRIPTS:
                (package / "scripts" / name).write_text("", encoding="utf-8")
            data.mkdir()

            with patch.object(preflight, "_check_modules", return_value=preflight._ok("modules", "模块", "ok")), \
                 patch.object(preflight, "_check_browser", return_value=preflight._ok("browser", "浏览器", "ok")), \
                 patch.object(
                     preflight,
                     "_check_resume_datasets",
                     return_value=preflight._ok("resume_inputs", "续跑数据", "ok"),
                 ):
                report = preflight.build_preflight(
                    "2026-10-20",
                    "2026-10-20",
                    data_dir=data,
                    package_dir=package,
                    collecting=False,
                    env={"BRIEFING_OUTPUT_DIR": str(output)},
                )

            self.assertEqual(report.output_dir, str(output))
            self.assertTrue(output.is_dir())

    def test_resume_mode_blocks_missing_datasets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "package"
            data = root / "data"
            output = root / "output"
            (package / "scripts").mkdir(parents=True)
            for name in preflight.REQUIRED_SCRIPTS:
                (package / "scripts" / name).write_text("", encoding="utf-8")
            data.mkdir()
            output.mkdir()

            with patch.object(
                preflight,
                "_check_modules",
                return_value=preflight._ok("modules", "模块", "ok"),
            ), patch.object(
                preflight,
                "_check_browser",
                return_value=preflight._ok("browser", "浏览器", "ok"),
            ):
                report = preflight.build_preflight(
                    "2026-10-20",
                    "2026-10-20",
                    data_dir=data,
                    package_dir=package,
                    output_dir=output,
                    collecting=False,
                )

        self.assertFalse(report.ok)
        self.assertTrue(
            any(item.key == "resume_inputs" and item.state == "error" for item in report.checks)
        )


if __name__ == "__main__":
    unittest.main()
