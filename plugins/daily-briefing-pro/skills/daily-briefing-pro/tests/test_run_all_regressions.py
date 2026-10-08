import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Keep importing the orchestrator isolated from the user's real persistent data.
import runtime_paths
_test_data = tempfile.TemporaryDirectory(prefix="daily-briefing-test-")
_original_get_data_dir = runtime_paths.get_data_dir
runtime_paths.get_data_dir = lambda package_dir: Path(_test_data.name)

import run_all
runtime_paths.get_data_dir = _original_get_data_dir
from summary_cache import load_summary_cache, save_summary_cache, set_cached_summary


class RunAllRegressionTests(unittest.TestCase):
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
            "fetch_douyin.py": {"bloggers": [{"videos": [{}]}]},
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


if __name__ == "__main__":
    unittest.main()
