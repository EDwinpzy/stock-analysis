#!/usr/bin/env python3
"""
抖音视频内容解析工具 — 自包含版本
独立解析抖音分享链接；纯 HTTP 失败时使用 Playwright 页面回退，并用 ffmpeg 处理音频。

功能:
1. 解析分享链接 → 获取无水印视频地址、标题、作者、封面
2. 下载视频 (MP4)
3. 提取音频 (MP3)
4. 语音转文字 (多API自动切换，无API Key时自动降级到本地Whisper)

用法:
    python analyze_douyin.py <抖音分享链接> [--provider auto|local|groq|openai|siliconflow] [--api-key KEY] [--keep-files] [--output-dir DIR] [--json]

说明:
    --provider auto（默认）会按 Groq → OpenAI → SiliconFlow → 本地Whisper 顺序尝试，
    未配置任何API Key时自动使用本地Whisper转录。
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
from typing import Optional, List
from urllib.parse import urljoin

import env_config  # noqa: F401  注入本机凭证（~/.codex/daily-briefing.env）


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
# 优先级: Groq(免费快) > OpenAI(需key) > 本地Whisper(需安装)

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
    'local': {
        'api_base': None,
        'model': 'base',
        'env_key': None,
        'description': '本地Whisper (需pip install openai-whisper)'
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

    video_url = _remove_watermark(_first_url(video.get("play_addr")) or fallback_video_url)
    if images:
        video_url = ""

    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    avatar = _first_url(author.get("avatar_thumb"))
    cover_url = _first_url(video.get("cover"))
    title = str(data.get("desc") or "").strip() or fallback_title or f"douyin_{video_id}"
    return VideoInfo(
        video_url=video_url,
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
        browser = await playwright.chromium.launch(headless=True)
        try:
            errors = []
            # The current mobile page often returns an empty shell. Desktop renders
            # the detail endpoint and its aweme JSON reliably, so try it first.
            browser_attempts = [
                ("desktop", DESKTOP_USER_AGENT, {"width": 1280, "height": 900}),
                ("mobile", MOBILE_HEADERS["User-Agent"], {"width": 390, "height": 844}),
            ]
            for label, user_agent, viewport in browser_attempts:
                context = await new_douyin_context(
                    browser, user_agent=user_agent, viewport=viewport
                )
                page = await context.new_page()
                detail_items = []
                detail_event = asyncio.Event()
                detail_tasks = []

                async def capture_detail(response):
                    if "/aweme/v1/web/aweme/detail/" not in response.url:
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
                    if "/aweme/v1/web/aweme/detail/" in response.url:
                        detail_tasks.append(asyncio.create_task(capture_detail(response)))

                page.on("response", on_response)
                navigation_error = ""
                try:
                    try:
                        await page.goto(share_url, wait_until="domcontentloaded", timeout=30000)
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
                        if parsed.video_url or parsed.images:
                            return parsed

                    video_url = ""
                    video_locator = page.locator("video").first
                    if await video_locator.count():
                        video_url = await video_locator.evaluate(
                            "el => el.currentSrc || el.src || el.getAttribute('src') || ''"
                        )
                        video_url = _remove_watermark(urljoin(page.url, video_url or ""))

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
    http_error = ""

    # 先尝试轻量 HTTP 路径；抖音页面结构变化时再交给浏览器渲染。
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, trust_env=False) as client:
            share_response = await client.get(share_url, headers=MOBILE_HEADERS)
            video_id = _extract_video_id(str(share_response.url)) or video_id
            detail_url = f"https://www.iesdouyin.com/share/video/{video_id}" if video_id else share_url
            response = await client.get(detail_url, headers=MOBILE_HEADERS)
            response.raise_for_status()
        data = _find_video_item(_extract_router_data(response.text))
        if data:
            return _video_info_from_item(data, video_id)
        http_error = "旧版 HTTP 页面未包含 videoInfoRes"
    except Exception as exc:
        http_error = str(exc)

    # 当前抖音常将页面重定向到 m.douyin.com，媒体地址和 SSR 数据只在浏览器页可见。
    try:
        return await _parse_douyin_with_browser(share_url, video_id)
    except Exception as browser_exc:
        detail = f"HTTP解析: {http_error or '未获得有效数据'}；浏览器解析: {browser_exc}"
        raise ValueError(detail) from browser_exc


async def download_video(video_url: str, output_dir: Path, filename: str = "") -> Path:
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
    
    curl_cmd = [
        'curl', '--noproxy', '*', '-f', '-sS', '-L',
        '--connect-timeout', '20', '--max-time', '90',
        '-H', f'Referer: {headers["Referer"]}',
        '-H', f'User-Agent: {headers["User-Agent"]}',
        '-o', str(filepath),
        video_url
    ]
    # Windows Schannel 可能因证书吊销列表不可达而拒绝抖音 CDN；
    # 此时关闭吊销检查，仍保留 HTTPS 证书和主机名校验。
    if os.name == 'nt':
        curl_cmd.insert(1, '--ssl-no-revoke')

    # 抖音 CDN 偶发 TLS 握手失败（curl 退出码 35），保留一次有限重试。
    # 三次 120 秒下载会与 fetch_douyin 的 300 秒子进程截止时间冲突，
    # 让完整分析在 Whisper 开始前就被父进程杀掉。
    last_detail = ""
    for attempt in range(2):
        if attempt:
            time.sleep(2 * attempt)
        try:
            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=100)
        except subprocess.TimeoutExpired:
            last_detail = "curl 单次下载超过 100 秒"
            print(f"  [下载] 第{attempt + 1}次超过时限，重试…", file=sys.stderr)
            continue
        if result.returncode == 0 and filepath.exists() and filepath.stat().st_size > 0:
            return filepath
        last_detail = (result.stderr or result.stdout or '').strip()
        if result.returncode == 0:
            last_detail = "下载文件为空"
        print(f"  [下载] 第{attempt + 1}次失败（退出码 {result.returncode}），重试…", file=sys.stderr)

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
        with httpx.Client(timeout=timeout, trust_env=False) as client:
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
        with httpx.Client(timeout=timeout, trust_env=False) as client:
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
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.post(api_base, files=files, headers=headers)
            response.raise_for_status()
            result = response.json()
            return result.get('text', '')


def extract_text_from_audio_local(audio_path: Path, model_size: str | None = None) -> str:
    """使用本地 Whisper 模型转录 (免费，但需要下载模型)。

    默认 base 对财经口播的中文识别错误率偏高（专有名词、数字经常听错），
    因此默认改用 small，并允许用 DOUYIN_WHISPER_MODEL 覆盖（base/small/medium/large）。
    """
    model_size = model_size or os.environ.get('DOUYIN_WHISPER_MODEL', 'small')
    try:
        import whisper
        import torch
        # Bound CPU preprocessing/decoding threads on both CPU and CUDA runs.
        # Parallel analyzer processes otherwise each inherit PyTorch's large
        # machine-wide default and compete with the Whisper GPU workload.
        try:
            threads = int(os.environ.get('DOUYIN_WHISPER_THREADS', '4'))
        except ValueError:
            threads = 4
        thread_limit = max(1, min(4, threads, os.cpu_count() or 4))
        torch.set_num_threads(thread_limit)
        model = whisper.load_model(model_size)
        # 财经口播里中英混说常见，显式指定语言可减少自动检测带来的漂移。
        result = model.transcribe(str(audio_path), language='zh')
        return result['text']
    except ImportError:
        raise ImportError("请先安装 openai-whisper: pip install openai-whisper")


def extract_text_from_audio(audio_path: Path, provider: str = 'auto', api_key: str = None) -> str:
    """
    多API语音转文字，自动选择可用服务
    
    Args:
        audio_path: 音频文件路径
        provider: 指定服务 ('groq', 'openai', 'siliconflow', 'local', 'auto')
        api_key: API密钥 (可选，某些服务需要)
    
    Returns:
        转录文本
    """
    import os
    
    # 自动模式：按优先级尝试
    if provider == 'auto':
        providers_order = ['groq', 'openai', 'siliconflow', 'local']
    else:
        providers_order = [provider]
    
    errors = []
    
    for prov in providers_order:
        try:
            if prov == 'groq':
                key = api_key or os.environ.get('GROQ_API_KEY', '')
                if key:
                    print(f"  [转录] 使用 Groq Whisper...", file=sys.stderr)
                    return extract_text_from_audio_groq(audio_path, key)
                    
            elif prov == 'openai':
                key = api_key or os.environ.get('OPENAI_API_KEY', '')
                if key:
                    print(f"  [转录] 使用 OpenAI Whisper...", file=sys.stderr)
                    return extract_text_from_audio_openai(audio_path, key)
                    
            elif prov == 'siliconflow':
                key = api_key or os.environ.get('SILICONFLOW_API_KEY', '')
                if key:
                    print(f"  [转录] 使用 SiliconFlow SenseVoice...", file=sys.stderr)
                    return extract_text_from_audio_siliconflow(audio_path, key)
                    
            elif prov == 'local':
                print(f"  [转录] 使用本地 Whisper...", file=sys.stderr)
                return extract_text_from_audio_local(audio_path)
                
        except Exception as e:
            errors.append(f"{prov}: {str(e)[:50]}")
            continue
    
    # 所有服务都失败
    raise Exception(f"所有转录服务均失败: {'; '.join(errors)}")


def format_video_info_dict(video_info: VideoInfo) -> dict:
    """格式化视频信息为字典"""
    return {
        "title": video_info.title,
        "video_url": video_info.video_url,
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

    # Step 2: 下载视频
    print(f"[2/4] 正在下载视频...", file=sys.stderr)
    try:
        if output_dir:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            safe_title = re.sub(r'[\\/:*?"<>|]', '_', video_info.title or "douyin_video")
            safe_title = safe_title[:100]
            video_path = await download_video(video_info.video_url, out_dir, safe_title)
        else:
            tmp_dir = Path(tempfile.mkdtemp())
            video_path = await download_video(video_info.video_url, tmp_dir, f"douyin_{int(time.time())}")
        
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
        transcript = extract_text_from_audio(audio_path, provider=provider, api_key=api_key)
        result["transcript"] = transcript
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
                        choices=['auto', 'groq', 'openai', 'siliconflow', 'local'],
                        help="转录服务 (auto自动选择, groq免费快速)")
    parser.add_argument("--api-key", default="", help="API Key (可选，自动从环境变量读取)")
    parser.add_argument("--keep-files", action="store_true", help="保留下载的视频和音频文件")
    parser.add_argument("--output-dir", default="", help="输出目录 (保留文件到此目录)")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")

    args = parser.parse_args()

    result = await analyze_douyin_video(
        share_url=args.url,
        provider=args.provider,
        api_key=args.api_key,
        keep_files=args.keep_files,
        output_dir=args.output_dir or None,
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
