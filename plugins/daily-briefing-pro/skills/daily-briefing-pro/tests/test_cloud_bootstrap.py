import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cloud_bootstrap


def _write_model(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "config.json").write_text('{"universe": "ths"}', encoding="utf-8")
    (root / "src" / "data.py").write_text("", encoding="utf-8")
    (root / "src" / "features.py").write_text("", encoding="utf-8")
    (root / "src" / "engine.py").write_text("", encoding="utf-8")
    (root / "data" / "ths_industry_info.csv").write_text(
        "code,name\n881001,测试\n", encoding="utf-8")
    (root / "data" / "ths_industry_daily.csv").write_text(
        "date,code,close\n2026-10-19,881001,100\n", encoding="utf-8")
    (root / "data" / "benchmark_csi300.csv").write_text(
        "date,close\n2026-10-19,4500\n", encoding="utf-8")


class CloudBootstrapTests(unittest.TestCase):
    def test_clean_runtime_gets_baseline_and_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "skills" / "daily-briefing-pro"
            package.mkdir(parents=True)
            (package / "data").mkdir()
            panel = package / "data" / "sentiment_panel_v32.csv"
            panel.write_text("date,sh_close\n2026-10-19,3900\n", encoding="utf-8")

            staging = root / "staging"
            _write_model(staging)
            archive = package / "data" / "cloud-baseline" / "models" / "sw_rotation_model.zip"
            archive.parent.mkdir(parents=True)
            with zipfile.ZipFile(archive, "w") as bundle:
                for item in staging.rglob("*"):
                    if item.is_file():
                        bundle.write(item, item.relative_to(staging))

            data_dir = root / "home" / ".codex" / "daily-briefing-pro" / "data"
            data_dir.mkdir(parents=True)
            result = cloud_bootstrap.bootstrap(package, data_dir, env={})

            self.assertEqual(result["errors"], [])
            self.assertTrue((data_dir / "sentiment_panel_v32.csv").is_file())
            model = Path(result["model_dir"])
            self.assertTrue((model / "run.py").is_file())
            self.assertTrue((model / "data" / "ths_industry_daily.csv").is_file())
            self.assertTrue((model / ".bundle-sha256").is_file())

    def test_archive_without_source_tree_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "package"
            package.mkdir()
            staging = root / "staging"
            _write_model(staging)
            (staging / "src" / "features.py").unlink()
            archive = package / "data" / "cloud-baseline" / "models" / "sw_rotation_model.zip"
            archive.parent.mkdir(parents=True)
            with zipfile.ZipFile(archive, "w") as bundle:
                for item in staging.rglob("*"):
                    if item.is_file():
                        bundle.write(item, item.relative_to(staging))

            data_dir = root / "data"
            data_dir.mkdir()
            result = cloud_bootstrap.bootstrap(package, data_dir, env={})

            self.assertTrue(result["errors"])
            self.assertIn("模型包缺少", result["errors"][0])

    def test_existing_runtime_file_and_model_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "plugin" / "skills" / "daily-briefing-pro"
            (package / "data" / "cloud-baseline" / "models").mkdir(parents=True)
            (package / "data" / "sentiment_panel_v32.csv").write_text(
                "date\n2026-10-01\n", encoding="utf-8")

            live_model = root / "plugin" / "models" / "sw_rotation_model"
            _write_model(live_model)
            (live_model / "data" / "local-refresh.marker").write_text("keep", encoding="utf-8")

            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "sentiment_panel_v32.csv").write_text(
                "date\n2026-10-19\n", encoding="utf-8")

            result = cloud_bootstrap.bootstrap(package, data_dir, env={})

            self.assertEqual(
                (data_dir / "sentiment_panel_v32.csv").read_text(encoding="utf-8"),
                "date\n2026-10-19\n",
            )
            self.assertEqual(Path(result["model_dir"]), live_model)
            self.assertTrue((live_model / "data" / "local-refresh.marker").is_file())


if __name__ == "__main__":
    unittest.main()
