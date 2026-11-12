#!/usr/bin/env python3
"""
抖音视频内容解析工具 — 自包含版本
独立解析抖音分享链接；纯 HTTP 失败时使用 Playwright 页面回退，并用 ffmpeg 处理音频。

功能:
1. 解析分享链接 → 获取无水印视频地址、标题、作者、封面
2. 下载视频 (MP4)
3. 提取音频 (MP3)
4. 语音转文字 (原生字幕优先；无字幕时调用云端 ASR API，不在本机或容器内跑模型)

用法:
    python analyze_douyin.py <抖音分享链接> [--provider auto|groq|openai|siliconflow|cloud] [--api-key KEY] [--keep-files] [--output-dir DIR] [--json]

说明:
    --provider auto（默认）会优先使用抖音原生字幕；没有字幕时优先使用显式配置的
    通用 OpenAI-compatible ASR，然后按 Groq → OpenAI → SiliconFlow 顺序尝试。
    通用 ASR 必须同时配置 DOUYIN_ASR_BASE_URL、DOUYIN_ASR_API_KEY、
    DOUYIN_ASR_MODEL；文本 Relay 不能当作音频接口使用。
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from html import unescape
from pathlib import Path
from typing import Optional, List, Sequence
from urllib.parse import urljoin, urlsplit

import env_config  # noqa: F401  注入本机凭证（~/.codex/daily-briefing.env）
from network_config import (
    curl_proxy_args,
    httpx_client_kwargs,
    playwright_launch_options,
)


def _resolve_cookie_path() -> Path:
    """Use the same persistent cookie file as the daily collector."""
    configured = os.environ.get("DOUYIN_COOKIE_PATH")
    if configured:
        return Path(configured).expanduser()
    data_dir = os.environ.get("DAILY_BRIEFING_DATA_DIR")
    if data_dir:
        return Path(data_dir).expanduser() / "douyin_cookies.json"
    return Path.home() / ".codex" / "daily-briefing-pro" / "data" / "douyin_cookies.json"


COOKIE_PATH = _resolve_cookie_path()


def load_douyin_cookies() -> list[dict]:
    """Load Playwright cookies without exposing their values in diagnostics."""
    try:
        payload = json.loads(COOKIE_PATH.read_text(encoding="utf-8"))
        cookies = payload.get("cookies", []) if isinstance(payload, dict) else payload
        return [
            item for item in cookies
            if isinstance(item, dict) and item.get("name") and item.get("value")
        ]
    except (OSError, ValueError):
        return []


async def new_douyin_context(browser, **kwargs):
    context = await browser.new_context(**kwargs)
    cookies = load_douyin_cookies()
    if cookies:
        try:
            await context.add_cookies(cookies)
        except Exception as exc:
            print(f"  [WARN] 抖音 Cookie 注入失败：{type(exc).__name__}", file=sys.stderr)
    return context

# 模拟移动端请求头
MOBILE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1'
}
DESKTOP_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

# 多种语音转文字 API 配置
# auto 优先级：通用 ASR > Groq > OpenAI > SiliconFlow

TRANSCRIPT_PROVIDERS = {
    'groq': {
        'api_base': 'https://api.groq.com/openai/v1/audio/transcriptions',
        'model': 'whisper-large-v3',
        'env_key': 'GROQ_API_KEY',
        'description': 'Groq Whisper (免费、快速)'
    },
    'openai': {
        'api_base': 'https://api.openai.com/v1/audio/transcriptions',
        'model': 'whisper-1',
        'env_key': 'OPENAI_API_KEY',
        'description': 'OpenAI Whisper'
    },
    'siliconflow': {
        'api_base': 'https://api.siliconflow.cn/v1/audio/transcriptions',
        'model': 'FunAudioLLM/SenseVoiceSmall',
        'env_key': 'SILICONFLOW_API_KEY',
        'description': 'SiliconFlow SenseVoice'
    },
    'cloud': {
        'api_base': None,
        'model': '',
        'env_key': 'DOUYIN_ASR_API_KEY',
        'description': 'OpenAI Compatible 云端 ASR'
    }
}

DEFAULT_PROVIDER = 'auto'


@dataclass
class VideoAuthor:
    uid: str = ""
    name: str = ""
    avatar: str = ""


@dataclass
class ImgInfo:
    url: str = ""
    live_photo_url: str = ""


@dataclass
class VideoInfo:
    video_url: str
    video_urls: List[str] = field(default_factory=list)
    subtitle_urls: List[str] = field(default_factory=list)
    subtitle_text: str = ""
    cover_url: str = ""
    title: str = ""
    music_url: str = ""
    images: List[ImgInfo] = field(default_factory=list)
    author: VideoAuthor = field(default_factory=VideoAuthor)


def _extract_video_id(url: str) -> str:
    """从抖音视频/分享链接中提取数字 aweme_id。"""
    match = re.search(r"/(?:video|share/video)/(\d+)", url or "")
    if match:
        return match.group(1)
    match = re.search(r"(?:^|/)(\d{12,})(?:[/?#]|$)", url or "")
    return match.group(1) if match else ""


def _extract_router_data(html_text: str) -> dict | None:
    """解析页面内嵌的 window._ROUTER_DATA，兼容脚本后的分号/空白。"""
    marker = re.search(r"window\._ROUTER_DATA\s*=\s*", html_text or "")
    if not marker:
        return None
    payload = html_text[marker.end():].lstrip()
    try:
        data, _ = json.JSONDecoder().raw_decode(payload)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _first_url(value) -> str:
    """从抖音常见的 {url_list: [...]} 或 URL 列表字段中取第一个 URL。"""
    if isinstance(value, dict):
        for key in ("url_list", "urlList", "urls"):
            result = _first_url(value.get(key))
            if result:
                return result
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _is_direct_media_url(url: str) -> bool:
    """Reject browser-only and known placeholder URLs that curl cannot use."""
    value = unescape(str(url or "")).strip()
    if not value:
        return False
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return False
    lowered = value.lower()
    return not any(marker in lowered for marker in (
        "douyin_pc_client",
        "/download/douyin_pc_client",
    ))


def _all_urls(value) -> list[str]:
    """Collect all usable HTTP media URLs without inventing an order."""
    found: list[str] = []
    if isinstance(value, dict):
        for key in ("url_list", "urlList", "urls"):
            found.extend(_all_urls(value.get(key)))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_all_urls(item))
    elif isinstance(value, str) and _is_direct_media_url(value):
        found.append(unescape(value.strip()))

    result = []
    seen = set()
    for item in found:
        cleaned = _remove_watermark(item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _subtitle_urls_from_item(data: dict) -> list[str]:
    """Extract caption/subtitle URLs without treating the post caption as text."""
    if not isinstance(data, dict):
        return []

    containers = []
    for key in ("caption_infos", "subtitle_infos", "caption_info", "subtitle_info"):
        containers.append(data.get(key))
    video = data.get("video") if isinstance(data.get("video"), dict) else {}
    for key in ("cla_info", "caption_infos", "subtitle_infos"):
        containers.append(video.get(key))
    for container in list(containers):
        if isinstance(container, dict):
            for key in ("caption_infos", "subtitle_infos", "caption_info", "subtitle_info"):
                containers.append(container.get(key))

    found: list[str] = []

    def collect(value) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()
                if lowered in {
                    "url", "url_list", "urls", "web_url", "subtitle_url", "caption_url",
                }:
                    found.extend(_all_urls(child))
                elif lowered in {
                    "caption_infos", "subtitle_infos", "caption_info", "subtitle_info",
                    "cla_info",
                }:
                    collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect(child)

    for container in containers:
        collect(container)

    result: list[str] = []
    seen: set[str] = set()
    for url in found:
        cleaned = unescape(str(url or "")).strip()
        if not cleaned or not cleaned.lower().startswith(("http://", "https://")):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result[:6]


def _subtitle_text_from_payload(payload: str) -> str:
    """Convert VTT/SRT/JSON subtitle payloads into readable transcript text."""
    text = str(payload or "").lstrip("\ufeff").strip()
    if not text:
        return ""

    if text.startswith(("{", "[")):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if data is not None:
            parts: list[str] = []

            def walk(value) -> None:
                if isinstance(value, dict):
                    for key in ("text", "content", "transcript", "body", "utterances", "sentences"):
                        child = value.get(key)
                        if isinstance(child, str) and child.strip():
                            parts.append(child.strip())
                        elif isinstance(child, (dict, list)):
                            walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)

            walk(data)
            joined = " ".join(dict.fromkeys(part for part in parts if part))
            if joined:
                return re.sub(r"\s+", " ", joined).strip()

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("WEBVTT", "NOTE ")):
            continue
        if line == "NOTE" or "-->" in line or re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = unescape(line).strip()
        if line:
            lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


async def fetch_douyin_subtitle(urls: Sequence[str]) -> tuple[str, str]:
    """Return (transcript, source_url) from the first usable subtitle URL."""
    if not urls:
        return "", ""
    import httpx

    headers = {
        **MOBILE_HEADERS,
        "Referer": "https://www.douyin.com/",
    }
    async with httpx.AsyncClient(
        **httpx_client_kwargs(follow_redirects=True, timeout=20.0)
    ) as client:
        for url in urls:
            try:
                response = await client.get(str(url), headers=headers)
                response.raise_for_status()
                parsed = _subtitle_text_from_payload(response.text)
                if len(parsed) >= 8:
                    return parsed, str(url)
            except Exception:
                continue
    return "", ""


def _video_media_urls(video: dict) -> list[str]:
    """Return every CDN alternative exposed by the current aweme item."""
    if not isinstance(video, dict):
        return []
    sources = [
        video.get("play_addr"),
        video.get("play_addr_h264"),
        video.get("play_addr_265"),
        video.get("download_addr"),
    ]
    for bit_rate in video.get("bit_rate") or []:
        if isinstance(bit_rate, dict):
            sources.append(bit_rate.get("play_addr"))

    result = []
    seen = set()
    for source in sources:
        for url in _all_urls(source):
            if url not in seen:
                seen.add(url)
                result.append(url)
    return result


def _remove_watermark(url: str) -> str:
    """把抖音常见的 playwm 路径切换为 play 无水印路径。"""
    return url.replace("playwm", "play") if url else ""


def _find_video_item(router_data: dict | None) -> dict | None:
    """在不同版本路由数据中寻找 aweme item，不绑定单一 loaderData key。"""
    if not isinstance(router_data, dict):
        return None

    loader_data = router_data.get("loaderData")
    if not isinstance(loader_data, dict):
        return None

    preferred_keys = ("video_(id)/page", "note_(id)/page")
    payloads = [loader_data[key] for key in preferred_keys if key in loader_data]
    payloads.extend(value for key, value in loader_data.items() if key not in preferred_keys)

    def walk(value):
        if isinstance(value, dict):
            info = value.get("videoInfoRes")
            if isinstance(info, dict):
                items = info.get("item_list")
                if isinstance(items, list) and items and isinstance(items[0], dict):
                    return items[0]
            for child in value.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found:
                    return found
        return None

    for payload in payloads:
        found = walk(payload)
        if found:
            return found
    return None


def _find_aweme_detail(payload: dict | None, video_id: str) -> dict | None:
    """Find the exact video item returned by Douyin's web detail API."""
    target = str(video_id)
    if not isinstance(payload, dict) or not target:
        return None

    def walk(value):
        if isinstance(value, dict):
            detail = value.get("aweme_detail")
            if isinstance(detail, dict) and str(detail.get("aweme_id") or "") == target:
                return detail
            if (str(value.get("aweme_id") or "") == target
                    and isinstance(value.get("video"), dict)):
                return value
            for child in value.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found:
                    return found
        return None

    return walk(payload)


def _title_from_html(html_text: str) -> str:
    """从 SSR 页面标题提取可展示的标题，避免把 aweme_id 当成内容。"""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text or "", flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", unescape(match.group(1))).strip()
    return re.sub(r"\s*[-|｜]\s*抖音\s*$", "", title).strip()


def _video_info_from_item(
    data: dict,
    video_id: str,
    fallback_video_url: str = "",
    fallback_title: str = "",
) -> VideoInfo:
    """把 aweme item 安全地转换为 VideoInfo，兼容视频和图集字段缺失。"""
    video = data.get("video") if isinstance(data.get("video"), dict) else {}
    images = []
    for image in data.get("images") or []:
        image_url = _first_url(image)
        if image_url:
            images.append(ImgInfo(url=image_url))

    video_urls = _video_media_urls(video)
    fallback_video_url = _remove_watermark(fallback_video_url or "")
    if _is_direct_media_url(fallback_video_url) and fallback_video_url not in video_urls:
        video_urls.append(fallback_video_url)

    video_url = video_urls[0] if video_urls else ""
    if images:
        video_url = ""
        video_urls = []

    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    avatar = _first_url(author.get("avatar_thumb"))
    cover_url = _first_url(video.get("cover"))
    title = str(data.get("desc") or "").strip() or fallback_title or f"douyin_{video_id}"
    return VideoInfo(
        video_url=video_url,
        video_urls=video_urls,
        subtitle_urls=_subtitle_urls_from_item(data),
        cover_url=cover_url,
        title=title,
        images=images,
        author=VideoAuthor(
            uid=str(author.get("sec_uid") or author.get("uid") or ""),
            name=str(author.get("nickname") or ""),
            avatar=avatar,
        ),
    )


async def _parse_douyin_with_browser(share_url: str, video_id: str) -> VideoInfo:
    """用真实浏览器渲染当前抖音页面，作为纯 HTTP 旧接口的兜底。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("当前页面需要 Playwright 浏览器渲染，但环境未安装 playwright") from exc

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            **playwright_launch_options(headless=True)
        )
        try:
            errors = []
            # The current mobile page often returns an empty shell. Desktop renders
            # the detail endpoint and its aweme JSON reliably, so try it first.
            desktop_url = f"https://www.douyin.com/video/{video_id}" if video_id else share_url
            mobile_url = f"https://m.douyin.com/share/video/{video_id}" if video_id else share_url
            browser_attempts = [
                ("desktop", desktop_url, DESKTOP_USER_AGENT, {"width": 1280, "height": 900}),
                ("mobile", mobile_url, MOBILE_HEADERS["User-Agent"], {"width": 390, "height": 844}),
            ]
            for label, target_url, user_agent, viewport in browser_attempts:
                context = await new_douyin_context(
                    browser, user_agent=user_agent, viewport=viewport
                )
                page = await context.new_page()
                detail_items = []
                detail_event = asyncio.Event()
                detail_tasks = []

                async def capture_detail(response):
                    if not any(marker in response.url for marker in (
                        "/aweme/v1/web/aweme/detail/",
                        "/aweme/v1/web/aweme/post/",
                        "/web/api/v2/aweme/post",
                    )):
                        return
                    try:
                        payload = await response.json()
                        item = _find_aweme_detail(payload, video_id)
                        if item:
                            detail_items.append(item)
                            detail_event.set()
                    except Exception:
                        pass

                def on_response(response):
                    if any(marker in response.url for marker in (
                        "/aweme/v1/web/aweme/detail/",
                        "/aweme/v1/web/aweme/post/",
                        "/web/api/v2/aweme/post",
                    )):
                        detail_tasks.append(asyncio.create_task(capture_detail(response)))

                page.on("response", on_response)
                navigation_error = ""
                try:
                    try:
                        await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    except Exception as exc:
                        navigation_error = str(exc)
                    # The media API may arrive after DOMContentLoaded; wait for its
                    # response instead of relying only on a short fixed delay.
                    try:
                        await asyncio.wait_for(detail_event.wait(), timeout=12)
                    except asyncio.TimeoutError:
                        pass
                    if detail_tasks:
                        await asyncio.gather(*detail_tasks, return_exceptions=True)
                    page_html = await page.content()
                    page_title = await page.title()
                    title = _title_from_html(page_html) or re.sub(r"\s*[-|｜]\s*抖音\s*$", "", page_title).strip()

                    for item in detail_items:
                        parsed = _video_info_from_item(item, video_id, fallback_title=title)
                        if parsed.video_urls or parsed.images:
                            return parsed

                    video_url = ""
                    video_locator = page.locator("video").first
                    if await video_locator.count():
                        video_url = await video_locator.evaluate(
                            "el => el.currentSrc || el.src || el.getAttribute('src') || ''"
                        )
                        video_url = _remove_watermark(urljoin(page.url, video_url or ""))
                        if not _is_direct_media_url(video_url):
                            video_url = ""

                    data = _find_video_item(_extract_router_data(page_html))
                    if data:
                        return _video_info_from_item(data, video_id, video_url, title)
                    if video_url:
                        return VideoInfo(video_url=video_url, title=title or f"douyin_{video_id}")

                    detail = f"未找到视频媒体或 aweme 数据（最终地址: {page.url}）"
                    if navigation_error:
                        detail += f"；页面导航提示: {navigation_error[:160]}"
                    errors.append(f"{label}: {detail}")
                finally:
                    await context.close()
            raise ValueError("；".join(errors) or "浏览器未返回视频数据")
        finally:
            await browser.close()


async def parse_douyin_share_url(share_text: str) -> VideoInfo:
    """
    从抖音分享链接解析无水印视频信息
    """
    # 提取分享链接
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', share_text)
    if not urls:
        raise ValueError("未找到有效的分享链接")

    import httpx

    share_url = urls[0]
    video_id = _extract_video_id(share_url)
    http_errors = []

    # The same video is exposed through several entry points. During upstream
    # incidents one host can return 503 while another still serves the SSR item.
    endpoint_candidates = [share_url]
    if video_id:
        endpoint_candidates.extend([
            f"https://www.douyin.com/video/{video_id}",
            f"https://www.iesdouyin.com/share/video/{video_id}",
            f"https://m.douyin.com/share/video/{video_id}",
        ])
    endpoints = []
    seen_endpoints = set()
    for endpoint in endpoint_candidates:
        if endpoint and endpoint not in seen_endpoints:
            seen_endpoints.add(endpoint)
            endpoints.append(endpoint)

    # Two bounded rounds give transient 503s a chance to recover without
    # multiplying every request into an unbounded retry loop.
    async with httpx.AsyncClient(
        **httpx_client_kwargs(follow_redirects=True, timeout=20.0)
    ) as client:
        for round_index in range(2):
            for endpoint in endpoints:
                try:
                    response = await client.get(endpoint, headers=MOBILE_HEADERS)
                    if response.status_code >= 500 or response.status_code == 429:
                        http_errors.append(f"{endpoint}: HTTP {response.status_code}")
                        continue
                    response.raise_for_status()
                    resolved_id = _extract_video_id(str(response.url)) or video_id
                    data = _find_video_item(_extract_router_data(response.text))
                    if data:
                        parsed = _video_info_from_item(data, resolved_id)
                        if parsed.video_urls or parsed.images:
                            return parsed
                    http_errors.append(f"{endpoint}: 页面未包含可下载媒体")
                except Exception as exc:
                    http_errors.append(f"{endpoint}: {type(exc).__name__}: {exc}")
            if round_index == 0:
                await asyncio.sleep(1)

    http_error = "；".join(http_errors[-4:])

    # 当前抖音常将页面重定向到 m.douyin.com，媒体地址和 SSR 数据只在浏览器页可见。
    try:
        return await _parse_douyin_with_browser(share_url, video_id)
    except Exception as browser_exc:
        detail = f"HTTP解析: {http_error or '未获得有效数据'}；浏览器解析: {browser_exc}"
        raise ValueError(detail) from browser_exc


async def download_video(
    video_url: str | Sequence[str],
    output_dir: Path,
    filename: str = "",
) -> Path:
    """下载视频到本地（使用 curl，解决 httpx DNS 解析问题）"""
    import subprocess
    
    if not filename:
        filename = f"douyin_{int(time.time())}.mp4"
    if not filename.endswith(".mp4"):
        filename += ".mp4"
    
    filepath = output_dir / filename
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 使用 curl 下载（支持重定向，添加 Referer 头）
    headers = {
        'Referer': 'https://www.douyin.com/',
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
    }
    
    if isinstance(video_url, str):
        candidates = [video_url]
    else:
        candidates = list(video_url)
    candidates = list(dict.fromkeys(
        url for url in (_remove_watermark(str(item or "").strip()) for item in candidates)
        if _is_direct_media_url(url)
    ))
    if not candidates:
        raise ValueError("没有可下载的抖音媒体地址（已拒绝 blob/data/占位地址）")

    curl_cmd = [
        'curl', *curl_proxy_args(), '-f', '-sS', '-L',
        '--connect-timeout', '20', '--max-time', '90',
        '-H', f'Referer: {headers["Referer"]}',
        '-H', f'User-Agent: {headers["User-Agent"]}',
        '-o', str(filepath),
    ]
    # Windows Schannel 可能因证书吊销列表不可达而拒绝抖音 CDN；
    # 此时关闭吊销检查，仍保留 HTTPS 证书和主机名校验。
    if os.name == 'nt':
        curl_cmd.insert(1, '--ssl-no-revoke')

    # 抖音 CDN 偶发 TLS 握手失败（curl 退出码 35），保留一次有限重试。
    # 三次 120 秒下载会与 fetch_douyin 的 300 秒子进程截止时间冲突，
    # 让完整分析在 Whisper 开始前就被父进程杀掉。
    # Keep the total media-download window below the 600 second analyzer
    # deadline so Whisper still has time to run after a CDN incident.
    deadline = time.monotonic() + 300
    max_attempts = max(2, min(6, len(candidates) * 2))
    last_detail = ""
    for attempt in range(max_attempts):
        if attempt:
            time.sleep(1.5 * min(attempt, 3))
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            last_detail = "多 CDN 下载总时限已到"
            break
        candidate = candidates[attempt % len(candidates)]
        filepath.unlink(missing_ok=True)
        try:
            result = subprocess.run(
                [*curl_cmd, candidate],
                capture_output=True,
                text=True,
                timeout=min(100, max(2, int(remaining))),
            )
        except subprocess.TimeoutExpired:
            last_detail = "curl 单次下载超过 100 秒"
            print(f"  [下载] 第{attempt + 1}次超过时限，重试…", file=sys.stderr)
            continue
        if result.returncode == 0 and filepath.exists() and filepath.stat().st_size > 0:
            return filepath
        last_detail = (result.stderr or result.stdout or '').strip()
        if result.returncode == 0:
            last_detail = "下载文件为空"
        print(
            f"  [下载] 第{attempt + 1}次失败（退出码 {result.returncode}，"
            f"CDN {attempt % len(candidates) + 1}/{len(candidates)}），重试…",
            file=sys.stderr,
        )

    raise Exception(f"curl下载失败: {last_detail or '无错误输出'}")


def extract_audio(video_path: Path, output_dir: Optional[Path] = None) -> Path:
    """从视频中提取音频为 MP3"""
    if output_dir:
        audio_path = output_dir / video_path.with_suffix('.mp3').name
    else:
        audio_path = video_path.with_suffix('.mp3')
    
    try:
        import ffmpeg
        stream = (
            ffmpeg
            .input(str(video_path))
            .output(str(audio_path), acodec='libmp3lame', q=0)
        )
        command = ffmpeg.compile(stream, overwrite_output=True)
        subprocess.run(command, capture_output=True, text=True, timeout=90, check=True)
        return audio_path
    except ImportError:
        # 降级：使用命令行 ffmpeg
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "libmp3lame", "-ab", "320k", str(audio_path)],
            capture_output=True, text=True, timeout=90
        )
        if result.returncode != 0:
            raise Exception(f"ffmpeg 提取音频失败: {result.stderr}")
        return audio_path


def extract_text_from_audio_groq(audio_path: Path, api_key: str) -> str:
    """调用 Groq API 将语音转为文字 (免费、快速)"""
    import httpx
    
    api_base = 'https://api.groq.com/openai/v1/audio/transcriptions'
    model = 'whisper-large-v3'
    
    with open(audio_path, 'rb') as f:
        files = {
            'file': (audio_path.name, f, 'audio/mpeg'),
            'model': (None, model),
            'response_format': (None, 'text')
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        
        timeout = httpx.Timeout(300.0)
        with httpx.Client(**httpx_client_kwargs(timeout=timeout)) as client:
            response = client.post(api_base, files=files, headers=headers)
            response.raise_for_status()
            return response.text.strip()


def extract_text_from_audio_openai(audio_path: Path, api_key: str) -> str:
    """调用 OpenAI Whisper API"""
    import httpx
    
    api_base = 'https://api.openai.com/v1/audio/transcriptions'
    model = 'whisper-1'
    
    with open(audio_path, 'rb') as f:
        files = {
            'file': (audio_path.name, f, 'audio/mpeg'),
            'model': (None, model)
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        
        timeout = httpx.Timeout(300.0)
        with httpx.Client(**httpx_client_kwargs(timeout=timeout)) as client:
            response = client.post(api_base, files=files, headers=headers)
            response.raise_for_status()
            result = response.json()
            return result.get('text', '')


def extract_text_from_audio_siliconflow(audio_path: Path, api_key: str) -> str:
    """调用 SiliconFlow API 将语音转为文字"""
    import httpx
    
    api_base = 'https://api.siliconflow.cn/v1/audio/transcriptions'
    model = 'FunAudioLLM/SenseVoiceSmall'
    
    with open(audio_path, 'rb') as f:
        files = {
            'file': (audio_path.name, f, 'audio/mpeg'),
            'model': (None, model)
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        
        timeout = httpx.Timeout(300.0)
        with httpx.Client(**httpx_client_kwargs(timeout=timeout)) as client:
            response = client.post(api_base, files=files, headers=headers)
            response.raise_for_status()
            result = response.json()
            return result.get('text', '')


def cloud_asr_config(api_key: str = "") -> tuple[str, str, str] | None:
    """Return a fully explicit generic ASR config without using text-relay defaults."""

    base_url = os.environ.get('DOUYIN_ASR_BASE_URL', '').strip()
    key = (api_key or os.environ.get('DOUYIN_ASR_API_KEY', '')).strip()
    model = os.environ.get('DOUYIN_ASR_MODEL', '').strip()
    if not (base_url and key and model):
        return None
    return base_url, key, model


def extract_text_from_audio_cloud(
    audio_path: Path,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> str:
    """Transcribe through any explicitly configured OpenAI-compatible ASR endpoint."""
    import httpx

    base_url = (
        base_url or os.environ.get('DOUYIN_ASR_BASE_URL', '')
    ).strip().rstrip("/")
    key = (api_key or os.environ.get('DOUYIN_ASR_API_KEY', '')).strip()
    model = (model or os.environ.get('DOUYIN_ASR_MODEL', '')).strip()
    if not (base_url and key and model):
        raise ValueError(
            "通用云端 ASR 需要同时配置 DOUYIN_ASR_BASE_URL、"
            "DOUYIN_ASR_API_KEY 和 DOUYIN_ASR_MODEL"
        )
    api_base = (
        base_url
        if base_url.endswith("/audio/transcriptions")
        else f"{base_url}/audio/transcriptions"
    )

    with open(audio_path, 'rb') as handle:
        files = {
            'file': (audio_path.name, handle, 'audio/mpeg'),
            'model': (None, model),
        }
        headers = {"Authorization": f"Bearer {key}"}
        timeout = httpx.Timeout(300.0)
        with httpx.Client(**httpx_client_kwargs(timeout=timeout)) as client:
            response = client.post(api_base, files=files, headers=headers)
            response.raise_for_status()
            content_type = str(response.headers.get('content-type', '')).lower()
            text = response.text.strip()
            if 'json' in content_type or text.startswith('{'):
                result = response.json()
                if isinstance(result, dict):
                    return str(
                        result.get('text')
                        or result.get('transcript')
                        or result.get('result')
                        or ''
                    ).strip()
            return text


ASR_CONFIG_HINT = (
    "请配置 GROQ_API_KEY、SILICONFLOW_API_KEY、OPENAI_API_KEY 之一，"
    "或同时配置 DOUYIN_ASR_BASE_URL、DOUYIN_ASR_API_KEY、DOUYIN_ASR_MODEL"
)


def _provider_has_credentials(provider: str, api_key: str = "") -> bool:
    if provider == "cloud":
        return cloud_asr_config(api_key=api_key or "") is not None
    if api_key:
        return True
    env_key = TRANSCRIPT_PROVIDERS[provider].get("env_key")
    return bool(env_key and os.environ.get(str(env_key), "").strip())


def extract_text_from_audio(
    audio_path: Path,
    provider: str = 'auto',
    api_key: str = None,
    return_source: bool = False,
) -> str | tuple[str, str]:
    """
    多API语音转文字，自动选择可用服务
    
    Args:
        audio_path: 音频文件路径
        provider: 指定服务 ('cloud', 'groq', 'openai', 'siliconflow', 'auto')
        api_key: API密钥 (可选，某些服务需要)
    
    Returns:
        转录文本
    """
    import os
    
    provider = (provider or 'auto').strip().lower()
    if provider in {'local', 'whisper', 'faster-whisper', 'openai-whisper'}:
        raise ValueError(f"本地 ASR 已移除，抖音转录只走云端 API；{ASR_CONFIG_HINT}")

    # 自动模式：只按已配置的云端 API 顺序尝试，不做任何本地推理。
    if provider == 'auto':
        providers_order = [
            name for name in ('cloud', 'groq', 'openai', 'siliconflow')
            if _provider_has_credentials(name, api_key)
        ]
        if not providers_order:
            raise RuntimeError(f"未配置任何云端 ASR；{ASR_CONFIG_HINT}")
    elif provider in TRANSCRIPT_PROVIDERS:
        providers_order = [provider]
    else:
        raise ValueError(
            f"未知的转录服务 {provider}；可选 auto、cloud、groq、openai、siliconflow"
        )
    
    errors = []
    
    for prov in providers_order:
        try:
            if prov == 'cloud':
                print(f"  [转录] 使用 OpenAI Compatible 云端 ASR...", file=sys.stderr)
                text = extract_text_from_audio_cloud(audio_path, api_key=api_key or '')
                return (text, "cloud-asr") if return_source else text

            elif prov == 'groq':
                key = api_key or os.environ.get('GROQ_API_KEY', '')
                if key:
                    print(f"  [转录] 使用 Groq Whisper...", file=sys.stderr)
                    text = extract_text_from_audio_groq(audio_path, key)
                    return (text, "groq-whisper") if return_source else text
                    
            elif prov == 'openai':
                key = api_key or os.environ.get('OPENAI_API_KEY', '')
                if key:
                    print(f"  [转录] 使用 OpenAI Whisper...", file=sys.stderr)
                    text = extract_text_from_audio_openai(audio_path, key)
                    return (text, "openai-asr") if return_source else text
                    
            elif prov == 'siliconflow':
                key = api_key or os.environ.get('SILICONFLOW_API_KEY', '')
                if key:
                    print(f"  [转录] 使用 SiliconFlow SenseVoice...", file=sys.stderr)
                    text = extract_text_from_audio_siliconflow(audio_path, key)
                    return (text, "siliconflow-sensevoice") if return_source else text

        except Exception as e:
            errors.append(f"{prov}: {str(e)[:50]}")
            continue

    if not errors:
        raise RuntimeError(f"未配置所选云端 ASR 的凭证；{ASR_CONFIG_HINT}")
    # 所有服务都失败
    raise RuntimeError(f"所有云端转录服务均失败: {'; '.join(errors)}")


def format_video_info_dict(video_info: VideoInfo) -> dict:
    """格式化视频信息为字典"""
    return {
        "title": video_info.title,
        "video_url": video_info.video_url,
        "video_urls": video_info.video_urls,
        "subtitle_urls": video_info.subtitle_urls,
        "cover_url": video_info.cover_url,
        "music_url": video_info.music_url,
        "author": {
            "uid": video_info.author.uid,
            "name": video_info.author.name,
            "avatar": video_info.author.avatar,
        },
        "images": [
            {"url": img.url, "live_photo_url": img.live_photo_url}
            for img in video_info.images
        ],
    }


async def analyze_douyin_video(
    share_url: str,
    provider: str = 'auto',
    api_key: Optional[str] = None,
    keep_files: bool = False,
    output_dir: Optional[str] = None,
    known_media_urls: Optional[Sequence[str]] = None,
    known_subtitle_urls: Optional[Sequence[str]] = None,
    known_subtitle_text: str = "",
    known_title: str = "",
    known_author_name: str = "",
) -> dict:
    """
    全链路分析抖音视频：
    1. 解析链接 → 元数据
    2. 下载视频
    3. 提取音频
    4. 语音转文字 (多API支持)
    """
    result = {
        "status": "processing",
        "metadata": {},
        "video_path": "",
        "audio_path": "",
        "transcript": "",
    }

    # Step 1: 解析视频链接
    print(f"[1/4] 正在解析视频链接...", file=sys.stderr)
    known_media_urls = [
        url for url in (
            _remove_watermark(str(item or "").strip())
            for item in (known_media_urls or [])
        )
        if _is_direct_media_url(url)
    ]
    if known_media_urls:
        # The homepage response already contains the canonical title and signed
        # CDN URLs. Do not make transcription depend on a detail-page request
        # that can be rate-limited or return a JavaScript-only shell.
        video_info = VideoInfo(
            video_url=known_media_urls[0],
            video_urls=known_media_urls,
            subtitle_urls=list(dict.fromkeys(
                str(item or "").strip()
                for item in (known_subtitle_urls or [])
                if str(item or "").strip().lower().startswith(("http://", "https://"))
            )),
            subtitle_text=str(known_subtitle_text or "").strip(),
            title=known_title or f"douyin_{_extract_video_id(share_url) or 'video'}",
            author=VideoAuthor(name=known_author_name),
        )
        result["metadata"] = format_video_info_dict(video_info)
        result["metadata"]["media_source"] = "homepage_list"
        print(f"  → 标题: {video_info.title}", file=sys.stderr)
        print(f"  → 作者: {video_info.author.name}", file=sys.stderr)
        print(f"  → 使用主页列表中的 {len(known_media_urls)} 个媒体地址", file=sys.stderr)
    else:
        try:
            video_info = await parse_douyin_share_url(share_url)
            result["metadata"] = format_video_info_dict(video_info)
            print(f"  → 标题: {video_info.title}", file=sys.stderr)
            print(f"  → 作者: {video_info.author.name}", file=sys.stderr)
        except Exception as e:
            result["status"] = "error"
            result["error"] = f"解析链接失败: {str(e)}"
            return result

    # 判断是否为图集（无视频）
    if not video_info.video_url:
        result["status"] = "no_video"
        result["note"] = "该链接为图片合集，没有可下载的视频"
        return result

    # Douyin increasingly marks videos with native captions.  Prefer the
    # platform subtitle over ASR: it is deterministic, faster, and avoids both
    # the text-only relay limitation and CPU-heavy audio decoding.
    subtitle_text = str(video_info.subtitle_text or "").strip()
    subtitle_source = "provided"
    if not subtitle_text and video_info.subtitle_urls:
        print("[1.5/4] 检测到抖音原生字幕，优先读取...", file=sys.stderr)
        subtitle_text, subtitle_url = await fetch_douyin_subtitle(video_info.subtitle_urls)
        subtitle_source = subtitle_url
    if subtitle_text:
        result["transcript"] = subtitle_text
        result["transcript_source"] = "douyin_subtitle"
        result["metadata"]["subtitle_source"] = subtitle_source
        result["status"] = "success"
        print(f"  → 使用原生字幕 ({len(subtitle_text)} 字符)", file=sys.stderr)
        return result

    # Step 2: 下载视频
    print(f"[2/4] 正在下载视频...", file=sys.stderr)
    try:
        if output_dir:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            safe_title = re.sub(r'[\\/:*?"<>|]', '_', video_info.title or "douyin_video")
            safe_title = safe_title[:100]
            video_path = await download_video(video_info.video_urls or video_info.video_url, out_dir, safe_title)
        else:
            tmp_dir = Path(tempfile.mkdtemp())
            video_path = await download_video(
                video_info.video_urls or video_info.video_url,
                tmp_dir,
                f"douyin_{int(time.time())}",
            )
        
        result["video_path"] = str(video_path)
        file_size = os.path.getsize(video_path)
        print(f"  → 完成: {file_size / 1024 / 1024:.1f} MB", file=sys.stderr)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"下载视频失败: {str(e)}"
        return result

    # Step 3: 提取音频
    print(f"[3/4] 正在提取音频...", file=sys.stderr)
    try:
        out_dir = Path(output_dir) if output_dir else None
        audio_path = extract_audio(video_path, out_dir)
        result["audio_path"] = str(audio_path)
        audio_size = os.path.getsize(audio_path)
        print(f"  → 完成: {audio_size / 1024:.1f} KB", file=sys.stderr)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"提取音频失败: {str(e)}"
        return result

    # Step 4: 语音转文字 (多API自动切换)
    print(f"[4/4] 正在进行语音转文字...", file=sys.stderr)
    try:
        transcribed = extract_text_from_audio(
            audio_path,
            provider=provider,
            api_key=api_key,
            return_source=True,
        )
        if isinstance(transcribed, tuple):
            transcript, transcript_source = transcribed
        else:
            # Keep custom analyzers/tests that still return a plain string
            # compatible; the built-in implementations return source metadata.
            transcript, transcript_source = str(transcribed), ""
        result["transcript"] = transcript
        if transcript_source:
            result["transcript_source"] = transcript_source
        print(f"  → 完成 ({len(transcript)} 字符)", file=sys.stderr)
    except Exception as e:
        result["status"] = "partial"
        result["warning"] = f"语音转文字失败: {str(e)}"
        result["transcript"] = ""

    # 清理临时文件（未指定 --keep-files 且未指定 --output-dir 时清理）
    if not keep_files and not output_dir and video_path:
        try:
            os.remove(video_path)
            result["video_path"] = ""
        except Exception:
            pass
        try:
            os.remove(audio_path)
            result["audio_path"] = ""
        except Exception:
            pass
        print("  → 临时文件已清理", file=sys.stderr)

    if not result.get("warning"):
        result["status"] = "success"
    return result


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="抖音视频内容解析工具 - 多API转录支持")
    parser.add_argument("url", help="抖音分享链接或视频链接")
    parser.add_argument("--provider", default="auto", 
                        choices=['auto', 'cloud', 'groq', 'openai', 'siliconflow'],
                        help="云端转录服务 (auto 优先通用 ASR，再尝试 Groq/OpenAI/SiliconFlow)")
    parser.add_argument("--api-key", default="", help="API Key (可选，自动从环境变量读取)")
    parser.add_argument("--keep-files", action="store_true", help="保留下载的视频和音频文件")
    parser.add_argument("--output-dir", default="", help="输出目录 (保留文件到此目录)")
    parser.add_argument(
        "--media-url",
        action="append",
        default=[],
        help="主页列表已取得的媒体 CDN 地址（可重复）",
    )
    parser.add_argument(
        "--subtitle-url",
        action="append",
        default=[],
        help="主页列表已取得的抖音字幕地址（可重复）",
    )
    parser.add_argument("--subtitle-text", default="", help="已取得的抖音字幕文本")
    parser.add_argument("--title", default="", help="主页列表中的视频标题")
    parser.add_argument("--author-name", default="", help="主页列表中的作者名")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")

    args = parser.parse_args()

    result = await analyze_douyin_video(
        share_url=args.url,
        provider=args.provider,
        api_key=args.api_key,
        keep_files=args.keep_files,
        output_dir=args.output_dir or None,
        known_media_urls=args.media_url,
        known_subtitle_urls=args.subtitle_url,
        known_subtitle_text=args.subtitle_text,
        known_title=args.title,
        known_author_name=args.author_name,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print()
        print("=" * 60)
        meta = result.get("metadata", {})
        print(f"🎬 标题: {meta.get('title', '无标题')}")
        author = meta.get("author", {})
        print(f"👤 作者: {author.get('name', '未知')}")
        
        if result["status"] == "error":
            print(f"❌ 错误: {result.get('error', '未知错误')}")
            return
        
        if result["status"] == "no_video":
            print(f"📷 类型: 图片合集 (无视频内容)")
            print(f"ℹ️  {result.get('note', '')}")
            return
        
        video_path = result.get("video_path", "")
        audio_path = result.get("audio_path", "")
        print(f"📹 视频: {video_path if video_path else '已清理'}")
        print(f"🎵 音频: {audio_path if audio_path else '已清理'}")
        
        transcript = result.get("transcript", "")
        if transcript:
            print(f"\n📝 语音转文字内容:")
            print("─" * 40)
            print(transcript)
            print("─" * 40)
            print(f"  (共 {len(transcript)} 字符)")
        
        if result.get("warning"):
            print(f"\n⚠️  警告: {result['warning']}")


if __name__ == "__main__":
    asyncio.run(main())
