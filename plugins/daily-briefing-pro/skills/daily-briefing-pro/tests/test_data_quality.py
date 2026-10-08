import sys
import unittest
from pathlib import Path


def _scripts_directory() -> Path:
    for ancestor in Path(__file__).resolve().parents:
        direct = ancestor / "scripts"
        if (direct / "data_quality.py").is_file():
            return direct
        verification_source = ancestor / "source" / "skills" / "daily-briefing-pro" / "scripts"
        if (verification_source / "data_quality.py").is_file():
            return verification_source
    raise RuntimeError("Could not locate daily-briefing-pro/scripts/data_quality.py")


sys.path.insert(0, str(_scripts_directory()))

from data_quality import dataset_state


class DataQualityActualDateTests(unittest.TestCase):
    def test_asof_overrides_request_date_when_prediction_is_stale(self):
        data = {"date": "2026-09-23", "asof": "2026-09-15", "status": "ok"}

        state, _ = dataset_state(data, "2026-09-23", "2026-09-23")

        self.assertEqual(state, "stale")

    def test_asof_equal_to_target_is_fresh(self):
        data = {"date": "2026-09-23", "asof": "2026-09-23", "status": "ok"}

        state, _ = dataset_state(data, "2026-09-23", "2026-09-23")

        self.assertEqual(state, "ok")

    def test_data_date_overrides_request_date(self):
        data = {"date": "2026-09-23", "data_date": "2026-09-15", "status": "ok"}

        state, _ = dataset_state(data, "2026-09-23", "2026-09-23")

        self.assertEqual(state, "stale")

    def test_request_date_remains_fallback_without_actual_date(self):
        data = {"date": "2026-09-23", "status": "ok"}

        state, _ = dataset_state(data, "2026-09-23", "2026-09-23")

        self.assertEqual(state, "ok")

    def test_target_date_remains_fallback_without_actual_date(self):
        data = {"target_date": "2026-09-23", "status": "ok"}

        state, _ = dataset_state(data, "2026-09-23", "2026-09-23")

        self.assertEqual(state, "ok")


if __name__ == "__main__":
    unittest.main()
