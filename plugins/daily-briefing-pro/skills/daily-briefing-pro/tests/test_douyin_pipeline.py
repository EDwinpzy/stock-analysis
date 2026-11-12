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

    def test_transcription_forwards_homepage_media_urls_to_analyzer(self):
        completed = types.SimpleNamespace(
            returncode=0,
            stdout='{"status":"success","transcript":"已转录"}',
            stderr="",
        )
        video = {
            "url": "https://www.douyin.com/video/123456789012",
            "title": "财经视频",
            "media_urls": [
                "https://v1.example/video.mp4",
                "https://v2.example/video.mp4",
            ],
            "subtitle_urls": ["https://cdn.example/subtitle.vtt"],
        }
        with patch.object(fetch_douyin.subprocess, "run", return_value=completed) as run:
            fetch_douyin.transcribe_video(video)

        command = run.call_args.args[0]
        offsets = [index for index, value in enumerate(command) if value == "--media-url"]
        self.assertEqual(
            [command[index + 1] for index in offsets],
            video["media_urls"],
        )
        self.assertIn("--title", command)
        subtitle_offsets = [
            index for index, value in enumerate(command) if value == "--subtitle-url"
        ]
        self.assertEqual(
            [command[index + 1] for index in subtitle_offsets],
            video["subtitle_urls"],
        )

    def test_extracted_video_keeps_transcript_source(self):
        with patch.object(
            fetch_douyin,
            "get_video_transcript_with_fallback",
            return_value={
                "transcript": "真实语音内容",
                "transcript_source": "cloud-asr",
            },
        ), patch.object(
            fetch_douyin,
            "summarize_with_deepseek",
            return_value="摘要",
        ):
            result = fetch_douyin.extract_video_info(
                {
                    "url": "https://www.douyin.com/video/123456789012",
                    "title": "财经视频",
                    "create_time": 1790006400,
                }
            )

        self.assertEqual(result["transcript"], "真实语音内容")
        self.assertEqual(result["transcript_source"], "cloud-asr")


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

    def test_download_rotates_across_cdn_alternatives(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []

            def curl(command, **kwargs):
                calls.append(command[-1])
                if len(calls) == 1:
                    return types.SimpleNamespace(returncode=35, stdout="", stderr="TLS failure")
                if len(calls) == 2:
                    return types.SimpleNamespace(returncode=22, stdout="", stderr="HTTP 503")
                output = Path(command[command.index("-o") + 1])
                output.write_bytes(b"video")
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")

            urls = [
                "https://v1.example/video.mp4",
                "https://v2.example/video.mp4",
                "https://v3.example/video.mp4",
            ]
            with patch.object(analyze_douyin.subprocess, "run", side_effect=curl):
                with patch.object(analyze_douyin.time, "sleep"):
                    path = asyncio.run(analyze_douyin.download_video(
                        urls, Path(temp), "rotated_video"
                    ))

        self.assertTrue(path.name.endswith(".mp4"))
        self.assertEqual(calls, urls)


class CloudTranscriptionTests(unittest.TestCase):
    def test_local_provider_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "本地 ASR 已移除"):
                analyze_douyin.extract_text_from_audio(
                    Path("unused.mp3"), provider="local"
                )

    def test_auto_without_cloud_credentials_fails_with_config_hint(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GROQ_API_KEY"):
                analyze_douyin.extract_text_from_audio(
                    Path("unused.mp3"), provider="auto"
                )

    def test_auto_records_cloud_asr_as_transcript_source(self):
        with patch.dict(
            os.environ,
            {
                "DOUYIN_ASR_BASE_URL": "https://asr.example/v1",
                "DOUYIN_ASR_API_KEY": "configured",
                "DOUYIN_ASR_MODEL": "whisper-large-v3",
            },
            clear=True,
        ), patch.object(
            analyze_douyin,
            "extract_text_from_audio_cloud",
            return_value="转录文本",
        ):
            text, source = analyze_douyin.extract_text_from_audio(
                Path("unused.mp3"),
                provider="auto",
                return_source=True,
            )

        self.assertEqual(text, "转录文本")
        self.assertEqual(source, "cloud-asr")

    def test_auto_uses_groq_when_only_groq_key_is_configured(self):
        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": "configured"},
            clear=True,
        ), patch.object(
            analyze_douyin,
            "extract_text_from_audio_groq",
            return_value="groq 转录",
        ):
            text, source = analyze_douyin.extract_text_from_audio(
                Path("unused.mp3"),
                provider="auto",
                return_source=True,
            )

        self.assertEqual(text, "groq 转录")
        self.assertEqual(source, "groq-whisper")


class DouyinSubtitleTests(unittest.TestCase):
    def test_vtt_payload_is_normalized_to_transcript(self):
        payload = "\ufeffWEBVTT\n\n00:00:01.000 --> 00:00:03.000\n存储<00:00:01.500>涨价\n\n00:00:03.000 --> 00:00:05.000\n关注<font>供需</font>\n"

        text = analyze_douyin._subtitle_text_from_payload(payload)

        self.assertEqual(text, "存储涨价 关注供需")

    def test_json_subtitle_payload_uses_text_fields_without_timestamps(self):
        payload = json.dumps(
            {"body": [{"from": 0, "to": 1, "content": "第一句"}, {"content": "第二句"}]},
            ensure_ascii=False,
        )

        self.assertEqual(
            analyze_douyin._subtitle_text_from_payload(payload),
            "第一句 第二句",
        )

    def test_known_subtitle_skips_video_download(self):
        with patch.object(
            analyze_douyin,
            "download_video",
            side_effect=AssertionError("native subtitle must bypass media download"),
        ):
            result = asyncio.run(analyze_douyin.analyze_douyin_video(
                "https://www.douyin.com/video/123456789012",
                known_media_urls=["https://cdn.example/video.mp4"],
                known_subtitle_text="抖音原生字幕内容足够长，可以直接使用。",
            ))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["transcript_source"], "douyin_subtitle")
        self.assertEqual(result["transcript"], "抖音原生字幕内容足够长，可以直接使用。")


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

    def test_detail_api_item_preserves_all_cdn_urls_and_rejects_blob(self):
        item = {
            "aweme_id": "123456789012",
            "desc": "目标视频",
            "video": {
                "play_addr": {
                    "url_list": [
                        "blob:https://www.douyin.com/not-downloadable",
                        "https://cdn1.example/video.mp4",
                        "https://cdn2.example/video.mp4",
                    ],
                },
                "bit_rate": [
                    {"play_addr": {"url_list": ["https://cdn3.example/video.mp4"]}}
                ],
            },
        }

        info = analyze_douyin._video_info_from_item(item, "123456789012")

        self.assertEqual(info.video_url, "https://cdn1.example/video.mp4")
        self.assertEqual(info.video_urls, [
            "https://cdn1.example/video.mp4",
            "https://cdn2.example/video.mp4",
            "https://cdn3.example/video.mp4",
        ])

    def test_homepage_item_keeps_media_urls_for_analyzer(self):
        item = {
            "aweme_id": "123456789012",
            "desc": "目标视频",
            "video": {
                "play_addr": {
                    "url_list": [
                        "https://cdn1.example/video.mp4",
                        "https://cdn2.example/video.mp4",
                    ]
                }
            },
        }

        parsed = fetch_douyin.parse_video_item(item)

        self.assertEqual(parsed["media_urls"], [
            "https://cdn1.example/video.mp4",
            "https://cdn2.example/video.mp4",
        ])

    def test_analyzer_uses_homepage_urls_without_detail_page_dependency(self):
        downloaded = []

        async def unexpected_parse(*args, **kwargs):
            raise AssertionError("known homepage media must bypass detail parsing")

        async def fake_download(urls, output_dir, filename):
            downloaded.extend(urls)
            path = Path(output_dir) / f"{filename}.mp4"
            path.write_bytes(b"video")
            return path

        def fake_audio(video_path, output_dir=None):
            path = Path(video_path).with_suffix(".mp3")
            path.write_bytes(b"audio")
            return path

        with tempfile.TemporaryDirectory() as temp:
            with patch.object(analyze_douyin, "parse_douyin_share_url", unexpected_parse):
                with patch.object(analyze_douyin, "download_video", fake_download):
                    with patch.object(analyze_douyin, "extract_audio", fake_audio):
                        with patch.object(analyze_douyin, "extract_text_from_audio", return_value="完整转录"):
                            result = asyncio.run(analyze_douyin.analyze_douyin_video(
                                "https://www.douyin.com/video/123456789012",
                                output_dir=temp,
                                known_media_urls=[
                                    "https://cdn1.example/video.mp4",
                                    "https://cdn2.example/video.mp4",
                                ],
                                known_title="财经视频",
                                known_author_name="测试作者",
                            ))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["transcript"], "完整转录")
        self.assertEqual(downloaded, [
            "https://cdn1.example/video.mp4",
            "https://cdn2.example/video.mp4",
        ])
        self.assertEqual(result["metadata"]["media_source"], "homepage_list")


class GenericCloudAsrTests(unittest.TestCase):
    def test_generic_cloud_asr_posts_to_explicit_openai_compatible_endpoint(self):
        captured = {}

        class FakeResponse:
            text = "云端转录文本"
            headers = {"content-type": "text/plain"}

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, **kwargs):
                captured["client_kwargs"] = kwargs

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def post(self, url, files=None, headers=None):
                captured["url"] = url
                captured["files"] = files
                captured["headers"] = headers
                return FakeResponse()

        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / "sample.mp3"
            audio.write_bytes(b"audio")
            with patch.dict(
                os.environ,
                {
                    "DOUYIN_ASR_BASE_URL": "https://asr.example/v1",
                    "DOUYIN_ASR_API_KEY": "configured",
                    "DOUYIN_ASR_MODEL": "whisper-large-v3",
                },
                clear=True,
            ), patch("httpx.Client", FakeClient):
                text = analyze_douyin.extract_text_from_audio_cloud(audio)

        self.assertEqual(text, "云端转录文本")
        self.assertEqual(
            captured["url"],
            "https://asr.example/v1/audio/transcriptions",
        )
        self.assertEqual(captured["files"]["model"], (None, "whisper-large-v3"))
        self.assertEqual(
            captured["headers"]["Authorization"],
            "Bearer configured",
        )

    def test_auto_uses_generic_cloud_asr_only_when_all_three_values_exist(self):
        with patch.dict(
            os.environ,
            {
                "DOUYIN_ASR_BASE_URL": "https://asr.example/v1",
                "DOUYIN_ASR_API_KEY": "configured",
            },
            clear=True,
        ), patch.object(
            analyze_douyin,
            "extract_text_from_audio_cloud",
            side_effect=AssertionError("incomplete ASR config must not be used"),
        ):
            with self.assertRaisesRegex(RuntimeError, "GROQ_API_KEY"):
                analyze_douyin.extract_text_from_audio(
                    Path("unused.mp3"),
                    provider="auto",
                )

    def test_text_relay_credentials_are_not_reused_as_audio_asr(self):
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_BASE_URL": "https://text-relay.example/v1",
                "DEEPSEEK_API_KEY": "text-only",
                "DOUYIN_TRANSCRIPT_PROVIDER": "auto",
            },
            clear=True,
        ), patch.object(
            analyze_douyin,
            "extract_text_from_audio_cloud",
            side_effect=AssertionError("text relay must not be used for audio"),
        ):
            with self.assertRaisesRegex(RuntimeError, "未配置任何云端 ASR"):
                analyze_douyin.extract_text_from_audio(
                    Path("unused.mp3"),
                    provider="auto",
                )


if __name__ == "__main__":
    unittest.main()
