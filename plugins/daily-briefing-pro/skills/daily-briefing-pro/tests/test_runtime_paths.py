import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from runtime_paths import get_data_dir


class PersistentDataDirectoryTests(unittest.TestCase):
    def test_default_path_migrates_legacy_before_package_data(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            package = Path(temp) / "package"
            legacy = home / ".agents" / "skills" / "daily-briefing-pro" / "data"
            (legacy / "nested").mkdir(parents=True)
            (package / "data" / "nested").mkdir(parents=True)
            (legacy / "nested" / "rotation_history.json").write_text("legacy", encoding="utf-8")
            (legacy / "sentiment_history.json").write_text("old", encoding="utf-8")
            (package / "data" / "nested" / "rotation_history.json").write_text("package", encoding="utf-8")
            (package / "data" / "news_ai_summaries.json").write_text("new", encoding="utf-8")
            (package / "data" / "news_today.json").write_text("stale", encoding="utf-8")
            (package / "data" / "tgb_cookies.json").write_text("secret", encoding="utf-8")

            result = get_data_dir(package, home=home, env={})
            expected = home / ".codex" / "daily-briefing-pro" / "data"

            self.assertEqual(result, expected)
            self.assertEqual((expected / "nested" / "rotation_history.json").read_text(encoding="utf-8"), "legacy")
            self.assertEqual((expected / "sentiment_history.json").read_text(encoding="utf-8"), "old")
            self.assertEqual((expected / "news_ai_summaries.json").read_text(encoding="utf-8"), "new")
            self.assertFalse((expected / "news_today.json").exists())
            self.assertFalse((expected / "tgb_cookies.json").exists())
            self.assertEqual((legacy / "sentiment_history.json").read_text(encoding="utf-8"), "old")
            self.assertEqual((package / "data" / "news_ai_summaries.json").read_text(encoding="utf-8"), "new")

    def test_existing_persistent_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            package = Path(temp) / "package"
            persistent = home / ".codex" / "daily-briefing-pro" / "data"
            persistent.mkdir(parents=True)
            (persistent / "sentiment_panel_v32.csv").write_text("new-state", encoding="utf-8")
            (package / "data").mkdir(parents=True)
            (package / "data" / "sentiment_panel_v32.csv").write_text("stale-state", encoding="utf-8")

            result = get_data_dir(package, home=home, env={})

            self.assertEqual(result, persistent)
            self.assertEqual((persistent / "sentiment_panel_v32.csv").read_text(encoding="utf-8"), "new-state")
            self.assertEqual((package / "data" / "sentiment_panel_v32.csv").read_text(encoding="utf-8"), "stale-state")

    def test_environment_override_is_the_shared_runtime_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            package = Path(temp) / "package"
            override = Path(temp) / "custom-state"
            (package / "data").mkdir(parents=True)
            (package / "data" / "node_cycle_history.json").write_text("configured", encoding="utf-8")

            result = get_data_dir(package, home=home, env={"DAILY_BRIEFING_DATA_DIR": str(override)})

            self.assertEqual(result, override)
            self.assertEqual((override / "node_cycle_history.json").read_text(encoding="utf-8"), "configured")
            self.assertFalse((home / ".codex" / "daily-briefing-pro" / "data").exists())

    def test_cloud_mode_seeds_missing_durable_baseline_but_not_snapshots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            package = root / "package"
            override = root / "cloud-data"
            (package / "data").mkdir(parents=True)
            (package / "data" / "sentiment_panel_v32.csv").write_text(
                "date,value\n2026-09-21,1\n", encoding="utf-8"
            )
            (package / "data" / "node_cycle_history.json").write_text(
                '{"records":[]}', encoding="utf-8"
            )
            (package / "data" / "rotation_today.json").write_text(
                '{"entries": []}', encoding="utf-8"
            )

            result = get_data_dir(
                package,
                home=home,
                env={
                    "DAILY_BRIEFING_DATA_DIR": str(override),
                    "DAILY_BRIEFING_CLOUD": "1",
                },
            )

            self.assertEqual(result, override)
            self.assertTrue((override / "sentiment_panel_v32.csv").exists())
            self.assertTrue((override / "node_cycle_history.json").exists())
            self.assertFalse((override / "rotation_today.json").exists())


if __name__ == "__main__":
    unittest.main()
