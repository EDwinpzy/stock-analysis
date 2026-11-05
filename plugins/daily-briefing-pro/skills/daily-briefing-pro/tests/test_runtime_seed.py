import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from runtime_seed import apply_seed, plan_seed


class RuntimeSeedTests(unittest.TestCase):
    def test_only_durable_files_are_selected_and_secrets_are_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            target = root / "target"
            (source / "douyin_transcripts").mkdir(parents=True)
            (source / "sentiment_panel_v32.csv").write_text("date\n2026-10-19\n", encoding="utf-8")
            (source / "survey_raw_2026-10-19.json").write_text("[]", encoding="utf-8")
            (source / "douyin_transcripts" / "video.json").write_text("{}", encoding="utf-8")
            (source / "news_today.json").write_text("{}", encoding="utf-8")
            (source / "douyin_cookies.json").write_text("[]", encoding="utf-8")
            (source / "quote_today.html").write_text("stale", encoding="utf-8")

            entries = plan_seed(source, target)
            selected = {entry.relative_path for entry in entries}

            self.assertIn("sentiment_panel_v32.csv", selected)
            self.assertIn("survey_raw_2026-10-19.json", selected)
            self.assertIn("douyin_transcripts/video.json", selected)
            self.assertNotIn("news_today.json", selected)
            self.assertNotIn("douyin_cookies.json", selected)
            self.assertNotIn("quote_today.html", selected)
            self.assertFalse(target.exists())

    def test_default_does_not_overwrite_and_refresh_requires_source_not_older(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            source_file = source / "sentiment_panel_v32.csv"
            target_file = target / "sentiment_panel_v32.csv"
            source_file.write_text("new", encoding="utf-8")
            target_file.write_text("old", encoding="utf-8")
            os.utime(target_file, (200, 200))
            os.utime(source_file, (100, 100))

            default_plan = plan_seed(source, target)
            self.assertEqual(default_plan[0].action, "skip")
            self.assertIn("默认不覆盖", default_plan[0].reason)

            older_plan = plan_seed(source, target, refresh_existing=True)
            self.assertEqual(older_plan[0].action, "skip")
            self.assertIn("目标文件更新", older_plan[0].reason)

            os.utime(source_file, (300, 300))
            newer_plan = plan_seed(source, target, refresh_existing=True)
            self.assertEqual(newer_plan[0].action, "copy")
            apply_seed(source, target, newer_plan)
            self.assertEqual(target_file.read_text(encoding="utf-8"), "new")
            self.assertTrue(list(target.glob("sentiment_panel_v32.csv.bak-*")))

    def test_force_overwrites_with_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "rotation_history.json").write_text('{"new": true}', encoding="utf-8")
            (target / "rotation_history.json").write_text('{"old": true}', encoding="utf-8")

            plan = plan_seed(source, target, force=True)
            self.assertEqual(plan[0].action, "copy")
            apply_seed(source, target, plan)

            self.assertIn('"new"', (target / "rotation_history.json").read_text(encoding="utf-8"))
            self.assertTrue(list(target.glob("rotation_history.json.bak-*")))


if __name__ == "__main__":
    unittest.main()
