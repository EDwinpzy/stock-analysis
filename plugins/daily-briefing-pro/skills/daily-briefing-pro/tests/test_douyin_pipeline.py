import asyncio
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

# Importing env_config reads the user's credential file. These tests exercise only
# local control flow, so provide an inert module instead.
_prior_env_config = sys.modules.get("env_config")
sys.modules["env_config"] = types.ModuleType("env_config")
try:
    import analyze_douyin
    import fetch_douyin
finally:
    if _prior_env_config is None:
        sys.modules.pop("env_config", None)
    else:
        sys.modules["env_config"] = _prior_env_config


class FakeContext:
    def __init__(self):
        self.cookies = []

    async def add_cookies(self, cookies):
        self.cookies = cookies


class FakeBrowser:
    def __init__(self):
        self.context = FakeContext()

    async def new_context(self, **kwargs):
        return self.context


class DouyinCookieTests(unittest.TestCase):
    def test_analyzer_injects_cookies_from_configured_runtime_path(self):
        with tempfile.TemporaryDirectory() as temp:
            cookie_path = Path(temp) / "douyin_cookies.json"
            cookie_path.write_text(json.dumps({"cookies": [
                {"name": "sessionid", "value": "test-only", "domain": ".douyin.com", "path": "/"}
            ]}), encoding="utf-8")
            browser = FakeBrowser()

            with patch.object(analyze_douyin, "COOKIE_PATH", cookie_path):
                context = asyncio.run(analyze_douyin.new_douyin_context(browser))

            self.assertEqual([cookie["name"] for cookie in context.cookies], ["sessionid"])


class DouyinSubprocessTests(unittest.TestCase):
    def test_transcription_uses_active_python_and_parses_json(self):
        completed = types.SimpleNamespace(
            returncode=0,
            stdout='{"status":"success","transcript":"已转录"}',
            stderr="",
        )
        output_dirs = []

        def run_child(command, **kwargs):
            output_dir = Path(command[command.index("--output-dir") + 1])
            output_dirs.append(output_dir)
            self.assertTrue(output_dir.is_dir())
            return completed

        with patch.object(fetch_douyin.subprocess, "run", side_effect=run_child) as run:
            result = fetch_douyin.transcribe_video("https://www.douyin.com/video/123456789012")

        self.assertEqual(result["transcript"], "已转录")
        self.assertEqual(run.call_args.args[0][0], sys.executable)
        self.assertEqual(run.call_args.kwargs["timeout"], fetch_douyin.TRANSCRIBE_TIMEOUT_SECONDS)
        self.assertFalse(output_dirs[0].exists(), "temporary media should be removed after child exit")
        self.assertEqual(
            run.call_args.kwargs["env"]["DOUYIN_COOKIE_PATH"],
            str(fetch_douyin.COOKIE_PATH.resolve()),
        )

    def test_transcription_preserves_child_failure_when_no_json_is_returned(self):
        completed = types.SimpleNamespace(returncode=1, stdout="", stderr="browser launch failed")
        with patch.object(fetch_douyin.subprocess, "run", return_value=completed):
            result = fetch_douyin.transcribe_video("https://www.douyin.com/video/123456789012")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "browser launch failed")

    def test_timeout_error_keeps_last_child_stage_log(self):
        timeout = subprocess.TimeoutExpired("analyze_douyin.py", fetch_douyin.TRANSCRIBE_TIMEOUT_SECONDS, stderr=b"[4/4] local whisper")
        with patch.object(fetch_douyin.subprocess, "run", side_effect=timeout):
            result = fetch_douyin.transcribe_video("https://www.douyin.com/video/123456789012")

        self.assertEqual(result["status"], "error")
        self.assertIn(f"超过{fetch_douyin.TRANSCRIBE_TIMEOUT_SECONDS}秒", result["error"])
        self.assertIn("local whisper", result["error"])


class DouyinConcurrencyTests(unittest.TestCase):
    def test_transcription_defaults_to_one_analyzer(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(fetch_douyin.resolve_max_concurrent_transcripts(), 1)

    def test_explicit_transcription_concurrency_is_clamped_to_two(self):
        self.assertEqual(fetch_douyin.resolve_max_concurrent_transcripts("2"), 2)
        self.assertEqual(fetch_douyin.resolve_max_concurrent_transcripts("9"), 2)
        self.assertEqual(fetch_douyin.resolve_max_concurrent_transcripts("0"), 1)
        self.assertEqual(fetch_douyin.resolve_max_concurrent_transcripts("invalid"), 1)


class DouyinDownloadTests(unittest.TestCase):
    def test_audio_extraction_passes_a_hard_timeout_to_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "input.mp4"
            video.write_bytes(b"not needed by the command compiler")
            with patch.object(analyze_douyin.subprocess, "run") as run:
                audio = analyze_douyin.extract_audio(video)

        self.assertEqual(audio.name, "input.mp3")
        self.assertEqual(run.call_args.kwargs["timeout"], 90)
        self.assertTrue(run.call_args.kwargs["check"])

    def test_download_has_two_bounded_attempts_for_transient_tls_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []

            def curl(command, **kwargs):
                calls.append((command, kwargs))
                if len(calls) == 1:
                    return types.SimpleNamespace(returncode=35, stdout="", stderr="TLS handshake failed")
                output = Path(command[command.index("-o") + 1])
                output.write_bytes(b"video")
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch.object(analyze_douyin.subprocess, "run", side_effect=curl):
                with patch.object(analyze_douyin.time, "sleep"):
                    path = asyncio.run(analyze_douyin.download_video(
                        "https://example.invalid/video.mp4", Path(temp), "test_video"
                    ))

        self.assertTrue(path.name.endswith(".mp4"))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0][calls[0][0].index("--max-time") + 1], "90")
        self.assertEqual(calls[0][1]["timeout"], 100)


class WhisperThreadTests(unittest.TestCase):
    def test_thread_limit_is_applied_even_when_cuda_is_available(self):
        thread_calls = []
        fake_model = types.SimpleNamespace(
            transcribe=lambda path, language: {"text": "测试转录"}
        )
        fake_whisper = types.SimpleNamespace(load_model=lambda size: fake_model)
        fake_torch = types.SimpleNamespace(set_num_threads=thread_calls.append)

        with patch.dict(sys.modules, {"whisper": fake_whisper, "torch": fake_torch}):
            with patch.dict(os.environ, {"DOUYIN_WHISPER_THREADS": "99"}):
                result = analyze_douyin.extract_text_from_audio_local(Path("unused.mp3"))

        self.assertEqual(result, "测试转录")
        self.assertEqual(thread_calls, [min(4, os.cpu_count() or 4)])


class DouyinOutputStatusTests(unittest.TestCase):
    @staticmethod
    def _output(*transcripts):
        return {"bloggers": [{"videos": [{"transcript": value} for value in transcripts]}]}

    def test_ok_requires_a_transcript_for_every_expected_video(self):
        output = fetch_douyin.finalize_douyin_output(self._output("one", "two"), 2)

        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["transcript_count"], 2)

    def test_partial_status_and_counts_when_a_transcript_is_missing(self):
        output = fetch_douyin.finalize_douyin_output(self._output("one", ""), 2)

        self.assertEqual(output["status"], "partial")
        self.assertEqual(output["expected_video_count"], 2)
        self.assertEqual(output["video_count"], 2)
        self.assertEqual(output["transcript_count"], 1)
        self.assertIn("转录未完整", output["note"])

    def test_error_status_when_no_video_has_a_transcript(self):
        output = fetch_douyin.finalize_douyin_output(self._output("", ""), 2)

        self.assertEqual(output["status"], "error")

    def test_collection_errors_prevent_ok_status(self):
        output = fetch_douyin.finalize_douyin_output(self._output("one"), 1, ["profile fetch failed"])

        self.assertEqual(output["status"], "partial")
        self.assertIn("采集异常", output["note"])

    def test_failed_transcript_warning_is_visible_in_run_note(self):
        output = self._output("")
        output["bloggers"][0]["videos"][0].update({
            "title": "视频标题",
            "warning": "转录失败（原因：下载超过时限）",
        })

        result = fetch_douyin.finalize_douyin_output(output, 1)

        self.assertEqual(result["status"], "error")
        self.assertIn("视频标题：转录失败", result["note"])

    def test_transcript_excerpt_is_not_mislabeled_as_ai_summary(self):
        video = {"url": "https://www.douyin.com/video/123456789012", "title": "财经视频"}
        transcript_data = {
            "transcript": "原始转录文本内容",
            "fallback_text": "",
            "warning": "",
            "_resolved_title": "财经视频",
        }
        with patch.object(fetch_douyin, "get_video_transcript_with_fallback", return_value=transcript_data):
            with patch.object(fetch_douyin, "summarize_with_deepseek", return_value=""):
                result = fetch_douyin.extract_video_info(video)

        self.assertEqual(result["summary_source"], "transcript")


class DouyinTimestampTests(unittest.TestCase):
    def test_known_list_timestamp_skips_detail_page_navigation(self):
        video = {"aweme_id": "123", "create_time": 1_797_000_000}

        async def unexpected_detail_lookup(*args, **kwargs):
            raise AssertionError("known timestamp should not trigger a detail request")

        with patch.object(fetch_douyin, "fetch_video_create_time_playwright", unexpected_detail_lookup):
            result = asyncio.run(fetch_douyin.fill_create_times([video], browser=object()))

        self.assertEqual(result, [video])


class DouyinDetailApiTests(unittest.TestCase):
    def test_detail_api_item_is_selected_by_exact_aweme_id(self):
        payload = {
            "aweme_detail": {
                "aweme_id": "123456789012",
                "desc": "目标视频",
                "video": {"play_addr": {"url_list": ["https://cdn.example/video.mp4"]}},
            },
        }

        item = analyze_douyin._find_aweme_detail(payload, "123456789012")

        self.assertEqual(item["desc"], "目标视频")
        self.assertIsNone(analyze_douyin._find_aweme_detail(payload, "999999999999"))

    def test_detail_api_aweme_item_produces_media_url(self):
        item = {
            "aweme_id": "123456789012",
            "desc": "目标视频",
            "video": {"play_addr": {"url_list": ["https://cdn.example/video.mp4"]}},
        }

        info = analyze_douyin._video_info_from_item(item, "123456789012")

        self.assertEqual(info.title, "目标视频")
        self.assertEqual(info.video_url, "https://cdn.example/video.mp4")


if __name__ == "__main__":
    unittest.main()
