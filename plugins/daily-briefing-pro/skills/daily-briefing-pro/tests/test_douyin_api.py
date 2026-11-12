import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import douyin_api


VIDEO_PAYLOAD = {
    "success": True,
    "data": {
        "content_id": "7707318535861728374",
        "kind": "video",
        "title": "",
        "description": "",
        "created_at": "2026-11-12T16:12:16Z",
        "duration_ms": 61000,
        "author": {"uid": "author-1", "nickname": "测试博主"},
        "stats": {"digg_count": 12},
        "media": {
            "video": {
                "url": "https://cdn.example/video.mp4",
                "urls": [
                    "https://cdn.example/video.mp4",
                    "https://cdn2.example/video.mp4",
                ],
                "watermark": False,
            }
        },
        "streams": [
            {
                "url": "https://cdn3.example/video.mp4",
                "urls": ["https://cdn3.example/video.mp4"],
            }
        ],
        "web_url": "https://www.douyin.com/video/7707318535861728374",
    },
}


class DouyinPayloadTests(unittest.TestCase):
    def test_normalizes_utc_timestamp_and_media_alternatives(self):
        result = douyin_api.normalize_video_payload(VIDEO_PAYLOAD)

        self.assertEqual(result["aweme_id"], "7707318535861728374")
        self.assertEqual(result["title"], "视频 7707318535861728374")
        self.assertEqual(result["author_name"], "测试博主")
        self.assertEqual(result["digg_count"], 12)
        self.assertEqual(result["create_time"], 1794499936)
        self.assertEqual(result["media_source"], "douyin_api")
        self.assertEqual(
            result["media_urls"],
            [
                "https://cdn.example/video.mp4",
                "https://cdn2.example/video.mp4",
                "https://cdn3.example/video.mp4",
            ],
        )

    def test_rejects_non_http_media_placeholders(self):
        result = douyin_api.normalize_video_payload({
            "content_id": "123456789012",
            "created_at": "2026-11-12T16:12:16Z",
            "media": {"video": {"urls": ["blob:https://douyin.com/id", "data:videos"]}},
        })

        self.assertEqual(result["media_urls"], [])


class DouyinResolverTests(unittest.TestCase):
    def test_login_credentials_select_hosted_api_origin(self):
        env = {
            "DOUYIN_RESOLVER_USERNAME": "user@example.com",
            "DOUYIN_RESOLVER_PASSWORD": "secret",
        }

        self.assertEqual(douyin_api.resolver_base_url(env), douyin_api.DEFAULT_API_BASE_URL)

    def test_unconfigured_environment_uses_public_demo(self):
        self.assertEqual(douyin_api.resolver_base_url({}), douyin_api.DEFAULT_DEMO_BASE_URL)

    def test_api_key_is_sent_as_header_without_demo_login(self):
        seen = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.url.path, request.headers.get("X-API-Key")))
            return httpx.Response(200, json=VIDEO_PAYLOAD)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        async def run():
            resolver = douyin_api.DouyinResolver(
                base_url="https://resolver.example",
                api_key="test-key",
                client=client,
            )
            try:
                return await resolver.resolve("7707318535861728374")
            finally:
                await resolver.aclose()

        result = asyncio.run(run())

        self.assertEqual(result["media_urls"][0], "https://cdn.example/video.mp4")
        self.assertEqual(seen, [("/api/v1/douyin/video", "test-key")])

    def test_demo_auth_is_explicit_fallback(self):
        seen = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.path)
            if request.url.path == "/api/v1/auth/demo":
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {
                            "enabled": True,
                            "username": "demo",
                            "password": "public-demo-password",
                        },
                    },
                )
            if request.url.path == "/api/v1/auth/login":
                return httpx.Response(200, json={"success": True, "data": {}})
            if request.url.path == "/api/v1/douyin/video":
                return httpx.Response(200, json=VIDEO_PAYLOAD)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        async def run():
            resolver = douyin_api.DouyinResolver(
                base_url="https://resolver.example",
                allow_demo=True,
                client=client,
            )
            try:
                return await resolver.resolve("https://www.douyin.com/video/7707318535861728374")
            finally:
                await resolver.aclose()

        result = asyncio.run(run())

        self.assertEqual(result["content_id"], "7707318535861728374")
        self.assertEqual(
            seen,
            [
                "/api/v1/auth/demo",
                "/api/v1/auth/login",
                "/api/v1/douyin/video",
            ],
        )

    def test_demo_can_be_disabled(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("disabled demo mode must not make a request")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async def run():
            resolver = douyin_api.DouyinResolver(
                base_url="https://resolver.example",
                allow_demo=False,
                client=client,
            )
            try:
                await resolver.resolve("7707318535861728374")
            finally:
                await resolver.aclose()

        with self.assertRaisesRegex(douyin_api.DouyinResolverError, "DOUYIN_RESOLVER_API_KEY"):
            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
