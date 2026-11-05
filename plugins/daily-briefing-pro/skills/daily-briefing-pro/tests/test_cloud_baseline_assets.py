import csv
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from runtime_preflight import PANEL_COLUMNS

PACKAGE = Path(__file__).resolve().parents[1]
ARCHIVE = PACKAGE / "data" / "cloud-baseline" / "models" / "sw_rotation_model.zip"
REQUIRED = {
    "sw_rotation_model/run.py",
    "sw_rotation_model/config.json",
    "sw_rotation_model/RECONSTRUCTED.md",
    "sw_rotation_model/src/data.py",
    "sw_rotation_model/src/features.py",
    "sw_rotation_model/src/engine.py",
    "sw_rotation_model/data/ths_industry_info.csv",
    "sw_rotation_model/data/ths_industry_daily.csv",
    "sw_rotation_model/data/benchmark_csi300.csv",
}


class ShippedCloudBaselineTests(unittest.TestCase):
    def test_model_archive_has_runnable_payload(self):
        self.assertTrue(ARCHIVE.is_file(), ARCHIVE)
        with zipfile.ZipFile(ARCHIVE) as bundle:
            names = set(bundle.namelist())
        self.assertTrue(REQUIRED <= names, REQUIRED - names)
        self.assertFalse(any("/data/ths/" in name for name in names))
        self.assertFalse(any("__pycache__" in name for name in names))

    def test_seed_panel_has_model_columns(self):
        panel = PACKAGE / "data" / "sentiment_panel_v32.csv"
        with panel.open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
        self.assertTrue(set(PANEL_COLUMNS) <= set(header))
        self.assertGreater(len(header), 20)

    def test_history_baselines_are_present(self):
        for name in ("rotation_history.json", "node_cycle_history.json"):
            self.assertTrue((PACKAGE / "data" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
