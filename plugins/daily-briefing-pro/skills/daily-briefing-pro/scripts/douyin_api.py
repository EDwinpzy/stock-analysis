#!/usr/bin/env python3
"""Cloud-only Douyin media resolver.

The public Douyin web pages increasingly return metadata without a media URL
and can redirect detail pages to unrelated recommendations.  This module uses
the documented dtk API as a replaceable data service so collectors can obtain
the signed CDN URL without relying on a local browser profile or local media
parser.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from network_config import httpx_client_kwargs


DEFAULT_DEMO_BASE_URL = "https://demo.douyin.wtf"
DEFAULT_API_BASE_URL = "https://api.douyin.wtf"
DEFAULT_TIMEOUT_SECONDS = 45.0
DEFAULT_TASK_TIMEOUT_SECONDS = 90.0

_TRUE_VALUES = {"1", "true", "yes", "on"}


class DouyinResolverError(RuntimeError):
    """Raised when the configured cloud resolver cannot return a video."""


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def resolver_enabled(env: Mapping[str, str] | None = None) -> bool:
    values = env if env is not None else os.environ
    return str(values.get("DOUYIN_RESOLVER_ENABLED", "1")).strip().lower() in _TRUE_VALUES


def resolver_base_url(env: Mapping[str, str] | None = None) -> str:
    """Resolve the API origin, preferring an explicit deployment."""
    values = env if env is not None else os.environ
    configured = str(values.get("DOUYIN_RESOLVER_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    has_api_key = bool(str(values.get("DOUYIN_RESOLVER_API_KEY") or "").strip())
    has_login = bool(
        str(values.get("DOUYIN_RESOLVER_USERNAME") or "").strip()
        and str(values.get("DOUYIN_RESOLVER_PASSWORD") or "").strip()
    )
    if has_api_key or has_login:
        return DEFAULT_API_BASE_URL
    return DEFAULT_DEMO_BASE_URL


def _extract_video_id(value: str) -> str:
    match = re.search(r"/(?:video|share/video)/(\d+)", value or "")
    if match:
        return match.group(1)
    match = re.search(r"(?:^|/)(\d{12,})(?:[/?#]|$)", value or "")
    return match.group(1) if match else ""


def _clean_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    return value.replace("playwm", "play")


def _urls_from(value: Any) -> list[str]:
    """Collect media URLs from the normalized dtk response shapes."""
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(_urls_from(child))
    elif isinstance(value, dict):
        for key in ("url", "urls", "url_list", "urlList", "play_url"):
            if key in value:
                found.extend(_urls_from(value[key]))
    result: list[str] = []
    seen: set[str] = set()
    for item in found:
        cleaned = _clean_url(item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _parse_created_at(value: Any) -> int:
    """Convert the API's UTC ISO timestamp to a Beijing-safe Unix timestamp."""
    if isinstance(value, (int, float)):
        number = int(value)
        return number // 1000 if number > 1_000_000_000_000 else number
    text = str(value or "").strip()
    if not text:
        return 0
    if re.fullmatch(r"\d{10,13}", text):
        number = int(text)
        return number // 1000 if number > 1_000_000_000_000 else number
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def normalize_video_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Turn the dtk video response into the collector's stable shape."""
    data: Mapping[str, Any] = payload
    nested = data.get("data")
    if isinstance(nested, Mapping):
        data = nested
    result = data.get("result")
    if isinstance(result, Mapping):
        data = result

    media = data.get("media") if isinstance(data.get("media"), Mapping) else {}
    video = media.get("video") if isinstance(media.get("video"), Mapping) else {}
    author = data.get("author") if isinstance(data.get("author"), Mapping) else {}
    stats = data.get("stats") if isinstance(data.get("stats"), Mapping) else {}

    video_urls = _urls_from(video)
    stream_urls: list[str] = []
    for stream in data.get("streams") or []:
        if isinstance(stream, Mapping):
            stream_urls.extend(_urls_from(stream))
    # Prefer the main (usually non-watermarked) asset, then the remaining
    # stream alternatives.  Keep the order stable for deterministic retries.
    media_urls = list(dict.fromkeys([*video_urls, *stream_urls]))

    content_id = str(data.get("content_id") or "").strip()
    title = str(data.get("title") or data.get("description") or "").strip()
    if not title:
        title = f"视频 {content_id}" if content_id else "抖音视频"
    web_url = str(data.get("web_url") or "").strip() or (
        f"https://www.douyin.com/video/{content_id}" if content_id else ""
    )

    return {
        "aweme_id": content_id,
        "content_id": content_id,
        "title": title,
        "description": str(data.get("description") or "").strip(),
        "url": web_url,
        "author_name": str(author.get("nickname") or "").strip(),
        "author_uid": str(author.get("uid") or author.get("sec_uid") or "").strip(),
        "digg_count": int(stats.get("digg_count") or 0),
        "create_time": _parse_created_at(data.get("created_at")),
        "duration_ms": int(data.get("duration_ms") or 0),
        "media_urls": media_urls[:8],
        "subtitle_urls": _subtitle_urls(data),
        "media_source": "douyin_api",
    }


def _subtitle_urls(data: Mapping[str, Any]) -> list[str]:
    """Extract native caption URLs if a provider returns them."""
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                lowered = str(key).lower()
                if lowered in {
                    "subtitle_url",
                    "caption_url",
                    "caption_infos",
                    "subtitle_infos",
                    "caption_info",
                    "subtitle_info",
                }:
                    found.extend(_urls_from(child))
                elif isinstance(child, (Mapping, list, tuple)):
                    walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child)

    walk(data)
    return list(dict.fromkeys(found))[:6]


class DouyinResolver:
    """Reusable authenticated client for the cloud resolver."""

    def __init__(
        self,
        *,
        base_url: str = "",
        api_key: str = "",
        username: str = "",
        password: str = "",
        allow_demo: bool | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or resolver_base_url()).rstrip("/")
        self.api_key = (
            api_key or os.environ.get("DOUYIN_RESOLVER_API_KEY", "")
        ).strip()
        self.username = (
            username or os.environ.get("DOUYIN_RESOLVER_USERNAME", "")
        ).strip()
        self.password = (
            password or os.environ.get("DOUYIN_RESOLVER_PASSWORD", "")
        ).strip()
        self.allow_demo = (
            _env_bool("DOUYIN_RESOLVER_ALLOW_DEMO", True)
            if allow_demo is None
            else allow_demo
        )
        self._client = client or httpx.AsyncClient(
            **httpx_client_kwargs(
                follow_redirects=True,
                timeout=httpx.Timeout(timeout),
            )
        )
        self._owns_client = client is None
        self._auth_lock = asyncio.Lock()
        self._authenticated = bool(self.api_key)
        self._demo_session = False

    async def __aenter__(self) -> "DouyinResolver":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key} if self.api_key else {}

    async def _login(self, username: str, password: str) -> None:
        response = await self._client.post(
            f"{self.base_url}/api/v1/auth/login",
            params={"lang": "zh"},
            json={"username": username, "password": password},
            headers=self._headers(),
        )
        payload = _response_json(response)
        if response.status_code >= 400 or not payload.get("success"):
            raise DouyinResolverError(
                f"抖音解析服务登录失败: HTTP {response.status_code}"
            )
        self._authenticated = True

    async def _authenticate(self) -> None:
        if self._authenticated:
            return
        async with self._auth_lock:
            if self._authenticated:
                return
            if self.username and self.password:
                await self._login(self.username, self.password)
                return
            if not self.allow_demo:
                raise DouyinResolverError(
                    "抖音解析服务未配置：请设置 DOUYIN_RESOLVER_API_KEY，"
                    "或 DOUYIN_RESOLVER_USERNAME / DOUYIN_RESOLVER_PASSWORD"
                )
            response = await self._client.get(
                f"{self.base_url}/api/v1/auth/demo",
                params={"lang": "zh"},
            )
            payload = _response_json(response)
            demo = payload.get("data") if isinstance(payload.get("data"), Mapping) else {}
            if response.status_code >= 400 or not payload.get("success") or not demo.get("enabled"):
                raise DouyinResolverError(
                    f"抖音解析服务未启用匿名演示账号: HTTP {response.status_code}"
                )
            username = str(demo.get("username") or "").strip()
            password = str(demo.get("password") or "").strip()
            if not username or not password:
                raise DouyinResolverError("抖音解析服务返回了不完整的演示凭据")
            await self._login(username, password)
            self._demo_session = True

    async def _request(self, path: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        await self._authenticate()
        response = await self._client.get(
            f"{self.base_url}{path}",
            params={**params, "wait": 30, "lang": "zh"},
            headers=self._headers(),
        )
        payload = _response_json(response)
        if response.status_code == 202:
            task_id = str(
                (payload.get("data") or {}).get("task_id")
                if isinstance(payload.get("data"), Mapping)
                else ""
            ).strip()
            if not task_id:
                raise DouyinResolverError("抖音解析服务返回 202，但缺少 task_id")
            payload = await self._poll(task_id)
        if response.status_code >= 400:
            detail = payload.get("error")
            if isinstance(detail, Mapping):
                detail = detail.get("message") or detail.get("code")
            raise DouyinResolverError(
                f"抖音解析服务 HTTP {response.status_code}: {str(detail or '')[:160]}"
            )
        if not payload.get("success"):
            detail = payload.get("error")
            if isinstance(detail, Mapping):
                detail = detail.get("message") or detail.get("code")
            raise DouyinResolverError(f"抖音解析服务返回失败: {str(detail or '')[:160]}")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise DouyinResolverError("抖音解析服务没有返回视频数据")
        return data

    async def _poll(self, task_id: str) -> Mapping[str, Any]:
        deadline = time.monotonic() + DEFAULT_TASK_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            response = await self._client.get(
                f"{self.base_url}/api/v1/tasks/{task_id}",
                params={"lang": "zh"},
                headers=self._headers(),
            )
            payload = _response_json(response)
            if response.status_code >= 400 or not payload.get("success"):
                raise DouyinResolverError(
                    f"抖音解析任务失败: HTTP {response.status_code}"
                )
            data = payload.get("data") if isinstance(payload.get("data"), Mapping) else {}
            state = str(data.get("state") or "").lower()
            if state in {"done", "succeeded", "success"}:
                result = data.get("result") or data.get("data") or data
                if not isinstance(result, Mapping):
                    raise DouyinResolverError("抖音解析任务没有返回视频数据")
                return {"success": True, "data": result}
            if state in {"failed", "error", "cancelled"}:
                detail = data.get("error") or data.get("message") or state
                raise DouyinResolverError(f"抖音解析任务失败: {str(detail)[:160]}")
            await asyncio.sleep(2)
        raise DouyinResolverError("抖音解析任务超过等待时限")

    async def resolve(self, value: str) -> dict[str, Any]:
        """Resolve a Douyin video id, canonical URL, or share link."""
        target = str(value or "").strip()
        if not target:
            raise DouyinResolverError("抖音视频地址为空")
        aweme_id = _extract_video_id(target)
        params: dict[str, Any] = {"aweme_id": aweme_id} if aweme_id else {"url": target}
        data = await self._request("/api/v1/douyin/video", params)
        normalized = normalize_video_payload(data)
        if not normalized.get("media_urls"):
            raise DouyinResolverError("抖音解析服务未返回可下载媒体")
        return normalized


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


async def resolve_video(value: str, **kwargs: Any) -> dict[str, Any]:
    """Convenience one-shot resolver for callers that only need one video."""
    async with DouyinResolver(**kwargs) as resolver:
        return await resolver.resolve(value)
