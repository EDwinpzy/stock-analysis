import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]
DEPLOY_ROOT = PLUGIN_ROOT / "deploy" / "cloud"


@unittest.skipUnless(DEPLOY_ROOT.is_dir(), "deploy tree is source-only")
class CloudDeployContractTests(unittest.TestCase):
    def test_plugin_manifests_share_the_release_version(self):
        root_manifest = json.loads(
            (PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8")
        )
        codex_manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        self.assertEqual(root_manifest["version"], "3.23.19")
        self.assertEqual(codex_manifest["version"], root_manifest["version"])

    def test_compose_uses_json_cookie_targets_and_writable_model_volume(self):
        compose = (PLUGIN_ROOT / "deploy" / "cloud" / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn(
            "image: ${DAILY_BRIEFING_IMAGE:-daily-briefing-pro:3.23.19-cloud}",
            compose,
        )
        self.assertIn("ROTATION_MODEL_DIR: /runtime/models/sw_rotation_model", compose)
        self.assertIn("./runtime/models:/runtime/models", compose)
        self.assertIn("target: tgb_cookies.json", compose)
        self.assertIn("target: douyin_cookies.json", compose)
        self.assertIn("target: xueqiu_cookies.json", compose)
        self.assertIn("XUEQIU_COOKIE_PATH: /run/secrets/xueqiu_cookies.json", compose)
        self.assertIn("DAILY_BRIEFING_CLOUD: \"1\"", compose)
        self.assertIn("DOUYIN_TRANSCRIPT_PROVIDER: auto", compose)
        self.assertIn("- fuyao_api_key", compose)
        self.assertIn("file: ./secrets/fuyao_api_key", compose)

    def test_entrypoint_bootstraps_model_into_writable_runtime(self):
        entrypoint = (PLUGIN_ROOT / "deploy" / "cloud" / "entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn("model_template=/opt/daily-briefing-pro/models/sw_rotation_model", entrypoint)
        self.assertIn("model_runtime=/runtime/models/sw_rotation_model", entrypoint)
        self.assertIn('export ROTATION_MODEL_DIR="${ROTATION_MODEL_DIR:-$model_runtime}"', entrypoint)
        self.assertIn('if [ -z "${HITHINK_FINANCE_API_KEY:-}" ]; then', entrypoint)
        self.assertIn('elif [ -n "${FUYAO_API_KEY:-}" ]; then', entrypoint)
        self.assertIn(
            "load_secret HITHINK_FINANCE_API_KEY /run/secrets/fuyao_api_key",
            entrypoint,
        )
        dockerfile = (DEPLOY_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("DAILY_BRIEFING_CLOUD=1", dockerfile)

    def test_cloud_requirements_include_full_report_runtime_helpers(self):
        requirements = (DEPLOY_ROOT / "requirements-cloud.txt").read_text(encoding="utf-8")
        for requirement in ("ffmpeg-python==0.2.0", "Pillow==12.2.0", "zhconv==1.4.3"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, requirements)

    def test_akshare_dependencies_are_installed_without_the_arm64_js_blocker(self):
        requirements = (DEPLOY_ROOT / "requirements-cloud.txt").read_text(encoding="utf-8")
        dockerfile = (DEPLOY_ROOT / "Dockerfile").read_text(encoding="utf-8")
        bootstrap = (DEPLOY_ROOT / "codex-cloud-bootstrap.sh").read_text(encoding="utf-8")

        self.assertNotIn("akshare==", requirements)
        self.assertNotIn("py-mini-racer==", requirements)
        for requirement in (
            "lxml==6.1.3",
            "curl-cffi==0.17.0",
            "html5lib==1.1",
            "xlrd==2.0.2",
            "urllib3==2.8.0",
            "tqdm==4.70.1",
            "openpyxl==3.1.5",
            "jsonpath==0.82.2",
            "tabulate==0.10.0",
            "decorator==5.3.1",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, requirements)

        for source in (dockerfile, bootstrap):
            with self.subTest(source=source.splitlines()[0]):
                self.assertIn('--no-deps "akshare==1.18.46"', source)
                self.assertIn('--no-deps "akracer==0.0.14"', source)
                self.assertIn('--no-deps "py-mini-racer==0.6.0"', source)
                self.assertIn("arm64", source)
                self.assertIn("amd64", source)
                self.assertIn("MiniRacer", source)

    def test_cloud_runtime_bakes_faster_whisper_without_torch(self):
        dockerfile = (DEPLOY_ROOT / "Dockerfile").read_text(encoding="utf-8")
        bootstrap = (DEPLOY_ROOT / "codex-cloud-bootstrap.sh").read_text(encoding="utf-8")
        requirements = (DEPLOY_ROOT / "requirements-cloud.txt").read_text(encoding="utf-8")

        for source in (dockerfile, bootstrap):
            with self.subTest(source=source.splitlines()[0]):
                self.assertIn("faster_whisper", source)
                self.assertIn("small", source)
                self.assertNotIn('"torch==2.7.0+cpu"', source)
        self.assertIn("faster-whisper==1.2.1", requirements)
        self.assertIn("ctranslate2==4.9.0", requirements)
        self.assertNotIn("openai-whisper==", requirements)

    def test_fuyao_secret_is_created_and_loaded(self):
        init_secrets = (DEPLOY_ROOT / "init-secrets.sh").read_text(encoding="utf-8")
        entrypoint = (DEPLOY_ROOT / "entrypoint.sh").read_text(encoding="utf-8")

        self.assertIn("fuyao_api_key", init_secrets)
        self.assertIn("load_secret FUYAO_API_KEY /run/secrets/fuyao_api_key", entrypoint)

    def test_wencai_secret_is_created_and_loaded(self):
        compose = (DEPLOY_ROOT / "compose.yaml").read_text(encoding="utf-8")
        init_secrets = (DEPLOY_ROOT / "init-secrets.sh").read_text(encoding="utf-8")
        entrypoint = (DEPLOY_ROOT / "entrypoint.sh").read_text(encoding="utf-8")

        self.assertIn("iwencai_api_key", init_secrets)
        self.assertIn("file: ./secrets/iwencai_api_key", compose)
        self.assertIn("load_secret IWENCAI_API_KEY /run/secrets/iwencai_api_key", entrypoint)

    def test_generic_asr_secret_is_optional_and_loaded_without_changing_text_relay(self):
        compose = (DEPLOY_ROOT / "compose.yaml").read_text(encoding="utf-8")
        init_secrets = (DEPLOY_ROOT / "init-secrets.sh").read_text(encoding="utf-8")
        entrypoint = (DEPLOY_ROOT / "entrypoint.sh").read_text(encoding="utf-8")

        self.assertIn("douyin_asr_api_key", init_secrets)
        self.assertIn("file: ./secrets/douyin_asr_api_key", compose)
        self.assertIn("DOUYIN_ASR_BASE_URL: ${DOUYIN_ASR_BASE_URL:-}", compose)
        self.assertIn("DOUYIN_ASR_MODEL: ${DOUYIN_ASR_MODEL:-}", compose)
        self.assertIn(
            "load_secret DOUYIN_ASR_API_KEY /run/secrets/douyin_asr_api_key",
            entrypoint,
        )
        self.assertNotIn(
            "load_secret DOUYIN_ASR_API_KEY /run/secrets/deepseek_api_key",
            entrypoint,
        )

    def test_ths_account_secrets_are_created_and_loaded(self):
        compose = (DEPLOY_ROOT / "compose.yaml").read_text(encoding="utf-8")
        init_secrets = (DEPLOY_ROOT / "init-secrets.sh").read_text(encoding="utf-8")
        entrypoint = (DEPLOY_ROOT / "entrypoint.sh").read_text(encoding="utf-8")

        for name in ("ths_username", "ths_password", "ths_mac"):
            with self.subTest(name=name):
                self.assertIn(name, init_secrets)
                self.assertIn(f"file: ./secrets/{name}", compose)
                self.assertIn(f"load_secret THS_{name.removeprefix('ths_').upper()} /run/secrets/{name}", entrypoint)

    def test_init_secrets_assigns_container_uid_and_requires_privileged_compose(self):
        init_secrets = (DEPLOY_ROOT / "init-secrets.sh").read_text(encoding="utf-8")
        readme = (DEPLOY_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn('chown 10001:10001 "$path"', init_secrets)
        self.assertIn("sudo sh ./init-secrets.sh", readme)
        self.assertIn("DOCKER_BUILDKIT=1 docker build", readme)
        self.assertIn("sudo docker compose version", readme)
        self.assertNotIn("\ndocker compose -f compose.yaml", readme)

    def test_cloud_js_runtime_supports_arm64(self):
        dockerfile = (DEPLOY_ROOT / "Dockerfile").read_text(encoding="utf-8")
        bootstrap = (DEPLOY_ROOT / "codex-cloud-bootstrap.sh").read_text(encoding="utf-8")

        for source in (dockerfile, bootstrap):
            with self.subTest(source=source.splitlines()[0]):
                self.assertIn("akracer==0.0.14", source)
                self.assertIn("py-mini-racer==0.6.0", source)
                self.assertIn("MiniRacer", source)
                self.assertIn("arm64", source)

    def test_cloud_bootstrap_defaults_to_main_and_pins_an_explicit_sha(self):
        bootstrap = (DEPLOY_ROOT / "codex-cloud-bootstrap.sh").read_text(encoding="utf-8")

        self.assertIn('BRANCH="${DAILY_BRIEFING_BRANCH:-main}"', bootstrap)
        self.assertIn("EXPECTED_SHA", bootstrap)
        self.assertIn('git -C "$REPO_ROOT" rev-parse HEAD', bootstrap)

    def test_cloud_image_recreates_node_cli_symlinks(self):
        dockerfile = (DEPLOY_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn(
            "ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm",
            dockerfile,
        )
        self.assertIn(
            "ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx",
            dockerfile,
        )
        self.assertIn("ln -sf /usr/local/bin/node /usr/bin/node", dockerfile)
        self.assertNotIn(
            "COPY --from=node-runtime /usr/local/bin /usr/local/bin",
            dockerfile,
        )

    def test_playwright_browsers_live_outside_the_runtime_home_volume(self):
        dockerfile = (DEPLOY_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers", dockerfile)
        self.assertIn("python -m playwright install --with-deps chromium", dockerfile)
        self.assertIn("chmod -R a+rX /opt/playwright-browsers", dockerfile)

    def test_shell_entrypoints_are_normalized_to_lf(self):
        repo_root = PLUGIN_ROOT.parents[1]
        gitattributes_path = repo_root / ".gitattributes"
        if not gitattributes_path.is_file():
            self.skipTest("repository-level .gitattributes is not present in the packaged image")
        gitattributes = gitattributes_path.read_text(encoding="utf-8")
        dockerfile = (DEPLOY_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("*.sh text eol=lf", gitattributes)
        self.assertIn("Dockerfile text eol=lf", gitattributes)
        self.assertIn(
            "find /opt/daily-briefing-pro -type f -name '*.sh' "
            "-exec sed -i 's/\\r$//' {} +",
            dockerfile,
        )

    def test_docs_do_not_pass_unsupported_no_build_to_compose_run(self):
        readme = (DEPLOY_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("run --rm --no-build", readme)

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
