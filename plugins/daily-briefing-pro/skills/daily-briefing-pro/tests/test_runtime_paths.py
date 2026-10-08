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
            (legacy / "nested" / "shared.json").write_text("legacy", encoding="utf-8")
            (legacy / "legacy-only.csv").write_text("old", encoding="utf-8")
            (package / "data" / "nested" / "shared.json").write_text("package", encoding="utf-8")
            (package / "data" / "package-only.csv").write_text("new", encoding="utf-8")

            result = get_data_dir(package, home=home, env={})
            expected = home / ".codex" / "daily-briefing-pro" / "data"

            self.assertEqual(result, expected)
            self.assertEqual((expected / "nested" / "shared.json").read_text(encoding="utf-8"), "legacy")
            self.assertEqual((expected / "legacy-only.csv").read_text(encoding="utf-8"), "old")
            self.assertEqual((expected / "package-only.csv").read_text(encoding="utf-8"), "new")
            self.assertEqual((legacy / "legacy-only.csv").read_text(encoding="utf-8"), "old")
            self.assertEqual((package / "data" / "package-only.csv").read_text(encoding="utf-8"), "new")

    def test_existing_persistent_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            package = Path(temp) / "package"
            persistent = home / ".codex" / "daily-briefing-pro" / "data"
            persistent.mkdir(parents=True)
            (persistent / "history.csv").write_text("new-state", encoding="utf-8")
            (package / "data").mkdir(parents=True)
            (package / "data" / "history.csv").write_text("stale-state", encoding="utf-8")

            result = get_data_dir(package, home=home, env={})

            self.assertEqual(result, persistent)
            self.assertEqual((persistent / "history.csv").read_text(encoding="utf-8"), "new-state")
            self.assertEqual((package / "data" / "history.csv").read_text(encoding="utf-8"), "stale-state")

    def test_environment_override_is_the_shared_runtime_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            package = Path(temp) / "package"
            override = Path(temp) / "custom-state"
            (package / "data").mkdir(parents=True)
            (package / "data" / "settings.json").write_text("configured", encoding="utf-8")

            result = get_data_dir(package, home=home, env={"DAILY_BRIEFING_DATA_DIR": str(override)})

            self.assertEqual(result, override)
            self.assertEqual((override / "settings.json").read_text(encoding="utf-8"), "configured")
            self.assertFalse((home / ".codex" / "daily-briefing-pro" / "data").exists())


if __name__ == "__main__":
    unittest.main()
