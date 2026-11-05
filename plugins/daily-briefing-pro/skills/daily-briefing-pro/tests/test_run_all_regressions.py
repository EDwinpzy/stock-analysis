import io
import hashlib
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Keep importing the orchestrator isolated from the user's real persistent data.
import runtime_paths
_test_data = tempfile.TemporaryDirectory(prefix="daily-briefing-test-")
_original_get_data_dir = runtime_paths.get_data_dir
runtime_paths.get_data_dir = lambda package_dir: Path(_test_data.name)

import run_all
import build_broadsheet
runtime_paths.get_data_dir = _original_get_data_dir
from summary_cache import load_summary_cache, save_summary_cache, set_cached_summary


class RunAllRegressionTests(unittest.TestCase):
    def test_removed_skip_argument_blocks_collection(self):
        with patch.object(run_all.sys, 'argv', ['run_all.py', '--skip-transcription']), \
             patch.object(run_all, 'run_group_a') as collect:
            with self.assertRaises(SystemExit) as raised:
                run_all.main()
        self.assertEqual(raised.exception.code, 2)
        collect.assert_not_called()

    def test_legacy_skip_environment_cannot_bypass_required_douyin_gate(self):
        with patch.dict(os.environ, {'BRIEFING_SKIP_TRANSCRIPTION': '1'}):
            with self.assertRaisesRegex(RuntimeError, '抖音'):
                run_all.required_modules_ready({'fetch_douyin.py': {}}, '2026-10-13')

    def test_scheduled_closed_day_skips_collection(self):
        with patch.object(run_all.sys, 'argv', ['run_all.py', '--scheduled']), \
             patch.object(run_all, 'get_date', return_value='2026-10-11'), \
             patch.object(run_all, 'trade_dates', return_value=['2026-10-09']), \
             patch.object(run_all, 'run_group_a') as collect:
            run_all.main()
        collect.assert_not_called()

    def test_scheduled_calendar_failure_does_not_guess(self):
        with patch.object(run_all.sys, 'argv', ['run_all.py', '--scheduled']), \
             patch.object(run_all, 'get_date', return_value='2026-10-13'), \
             patch.object(run_all, 'trade_dates', side_effect=RuntimeError('calendar unavailable')), \
             patch.object(run_all, 'run_group_a') as collect:
            with self.assertRaises(SystemExit) as raised:
                run_all.main()
        self.assertEqual(raised.exception.code, 2)
        collect.assert_not_called()

    def test_cached_no_opinion_summary_satisfies_tgb_ai_gate(self):
        target_date = "2026-09-24"
        tgb = {
            "bloggers": {
                "博主甲": {"posts": [{"content": "当天原文"}]},
            }
        }
        cache_path = run_all.DATA_DIR / "tgb_ai_summaries.json"
        cache = load_summary_cache(cache_path)
        set_cached_summary(cache, target_date, "tgb", "博主甲", "当天原文", "无明确观点")
        save_summary_cache(cache, cache_path)
        results = {
            "tgb_crawl.py": tgb,
            "fetch_douyin.py": {"bloggers": [{"videos": [{"transcript": "真实转录"}]}]},
        }

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
            self.assertTrue(run_all.required_modules_ready(results, target_date))

    def test_missing_compiler_is_reported_by_preflight(self):
        with tempfile.TemporaryDirectory() as temp:
            reason = run_all.compiler_preflight_error(script_dir=Path(temp))

        self.assertTrue(reason)
        self.assertIn("build_briefing.py", reason)

    def test_compiler_failure_never_emits_success_status(self):
        stderr = io.StringIO()
        with patch.object(run_all, "get_date", return_value="2026-09-24"), \
             patch.object(run_all, "compiler_preflight_error", return_value=""), \
             patch.object(run_all, "run_group_a", return_value={}), \
             patch.object(run_all, "run_script", return_value={}), \
             patch.object(run_all, "save_result"), \
             patch.object(run_all, "run_group_b", return_value={}), \
             patch.object(run_all, "required_modules_ready", return_value=True), \
             patch.object(run_all, "compile_html", return_value={"_rc": 3, "_error": "compiler failed"}), \
             redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                run_all.main()

        self.assertEqual(raised.exception.code, 3)
        self.assertIn('"status": "error"', stderr.getvalue())
        self.assertNotIn('"status": "ok"', stderr.getvalue())

    def test_broadsheet_is_built_and_verified_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            out_dir = Path(temp)
            source = out_dir / "2026-10-10简报.html"
            source.write_text("raw report", encoding="utf-8")

            def fake_run(command, **kwargs):
                if Path(command[1]).name == "build_broadsheet.py":
                    Path(command[command.index("--out") + 1]).write_text("verified style", encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="验收: PASS\n", stderr="")

            with patch.object(run_all, "default_output_dir", return_value=out_dir), \
                 patch.object(run_all.subprocess, "run", side_effect=fake_run) as run:
                result = run_all.compile_broadsheet("2026-10-10")

            self.assertEqual(Path(result).read_text(encoding="utf-8"), "verified style")
            self.assertEqual(run.call_count, 2)

    def test_broadsheet_failure_blocks_delivery_and_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as temp:
            out_dir = Path(temp)
            source = out_dir / "2026-10-10简报.html"
            source.write_text("raw report", encoding="utf-8")
            final = out_dir / "2026-10-10简报-报刊版.html"
            final.write_text("previous verified report", encoding="utf-8")

            def fake_run(command, **kwargs):
                if Path(command[1]).name == "build_broadsheet.py":
                    Path(command[command.index("--out") + 1]).write_text("new report", encoding="utf-8")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=1, stdout="验收: FAIL\n", stderr="")

            with patch.object(run_all, "default_output_dir", return_value=out_dir), \
                 patch.object(run_all.subprocess, "run", side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, "验收失败"):
                    run_all.compile_broadsheet("2026-10-10")

            self.assertEqual(final.read_text(encoding="utf-8"), "previous verified report")
            self.assertEqual(list(out_dir.glob("*.tmp.html")), [])

    def test_delivery_link_targets_broadsheet_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "2026-10-10简报-报刊版.html"
            link = run_all.delivery_button(report)

        self.assertIn("2026-10-10%E7%AE%80%E6%8A%A5-%E6%8A%A5%E5%88%8A%E7%89%88.html", link)
        self.assertIn("打开今日简报", link)

    def test_broadsheet_stylesheet_matches_the_selected_sample(self):
        fingerprint = hashlib.sha256(build_broadsheet.CSS.encode("utf-8")).hexdigest()
        self.assertEqual(fingerprint, "4e49e37c382ad0b318c645888b8c4905c5ce206ab655f9e2aca819ac60a592cd")
        self.assertNotIn("__TEX_", build_broadsheet.CSS)


if __name__ == "__main__":
    unittest.main()
