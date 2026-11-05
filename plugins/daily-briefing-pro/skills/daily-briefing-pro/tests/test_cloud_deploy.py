import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]


class CloudDeployContractTests(unittest.TestCase):
    def test_compose_uses_json_cookie_targets_and_writable_model_volume(self):
        compose = (PLUGIN_ROOT / "deploy" / "cloud" / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn("daily-briefing-pro:3.23.14-cloud", compose)
        self.assertIn("ROTATION_MODEL_DIR: /runtime/models/sw_rotation_model", compose)
        self.assertIn("./runtime/models:/runtime/models", compose)
        self.assertIn("target: tgb_cookies.json", compose)
        self.assertIn("target: douyin_cookies.json", compose)
        self.assertIn("target: xueqiu_cookies.json", compose)
        self.assertIn("XUEQIU_COOKIE_PATH: /run/secrets/xueqiu_cookies.json", compose)
        self.assertIn("DAILY_BRIEFING_CLOUD: \"1\"", compose)
        self.assertIn("DOUYIN_TRANSCRIPT_PROVIDER: auto", compose)

    def test_entrypoint_bootstraps_model_into_writable_runtime(self):
        entrypoint = (PLUGIN_ROOT / "deploy" / "cloud" / "entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn("model_template=/opt/daily-briefing-pro/models/sw_rotation_model", entrypoint)
        self.assertIn("model_runtime=/runtime/models/sw_rotation_model", entrypoint)
        self.assertIn('export ROTATION_MODEL_DIR="${ROTATION_MODEL_DIR:-$model_runtime}"', entrypoint)

    def test_seed_script_is_available_and_dry_run_by_default(self):
        seed = (PLUGIN_ROOT / "deploy" / "cloud" / "seed-data.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$Apply", seed)
        self.assertIn("if ($Apply)", seed)
        self.assertIn("runtime_seed.py", seed)
        self.assertIn("[string]$DestinationDataDir = ''", seed)
        self.assertIn("$MyInvocation.MyCommand.Path", seed)
        self.assertNotIn(
            "[string]$DestinationDataDir = (Join-Path $PSScriptRoot",
            seed,
        )


if __name__ == "__main__":
    unittest.main()
