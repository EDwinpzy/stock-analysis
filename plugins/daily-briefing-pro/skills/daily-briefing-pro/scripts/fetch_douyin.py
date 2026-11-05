#!/usr/bin/env python3
"""
抖音博主观点抓取（每日简报Pro专用）
使用 Playwright 拦截博主主页 API 获取最新视频，再用本地 Whisper / API 转录，
未配置任何 API Key 时自动降级到本地 Whisper。

v3.5.5 改进（修复 create_time 缺失 + 只取今日 + 并发转录）：
- 抖音列表 API 已不再返回 create_time，改为抓取详情页补全发布时间
- 利用 min_cursor 快速判断博主今日是否更新，减少无效详情页请求
- 只抓取博主主页中**今日发布**的视频，按北京时间（UTC+8）过滤
- 转录改为**并发执行**，默认最多 3 条同时转录，避免本地 Whisper 资源耗尽
- 转录失败/为空时，自动用视频标题+话题标签兜底提取观点和标的
- 扩大标的/板块关键词库，覆盖 A 股、港股、美股常见科技与消费标的
- 输出新增 warning 字段标注哪些视频使用了兜底摘要
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from runtime_paths import get_data_dir

import httpx
import env_config  # noqa: F401  注入本机凭证（~/.codex/daily-briefing.env）
from playwright.async_api import async_playwright

# 本地 Whisper 会为每个 analyzer 进程单独加载模型。8GB 显存机器上并发
# 会让小模型同时争用 GPU，因此默认串行；用户可显式调到2，最大不超过2。
def resolve_max_concurrent_transcripts(value: str | None = None) -> int:
    raw = value if value is not None else os.environ.get("DOUYIN_MAX_CONCURRENT", "1")
    try:
        return min(2, max(1, int(raw)))
    except (TypeError, ValueError):
        return 1


MAX_CONCURRENT_TRANSCRIPTS = resolve_max_concurrent_transcripts()
TRANSCRIBE_TIMEOUT_SECONDS = 600
# 当天无更新时允许回退的最近发布日窗口（抖音博主常在下午/晚间发布，周末照常更新）
MAX_STALE_DAYS = int(os.environ.get("DOUYIN_MAX_STALE_DAYS", "7"))
DESKTOP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# 默认追踪博主（与 抖音博主观点 skill 保持一致）
# 口罩哥两个入口合并；第三个博主可在环境变量 DOUYIN_BLOGGERS_EXTRA 中配置
# 格式：(博主名, URL或sec_uid)
DEFAULT_BLOGGERS = [
    ("口罩哥", "MS4wLjABAAAAO5TIp1flPZXvqelTSBPiwPbb8F7Lpf_PfCT8_xJRk0QuwS92L7dBVfR7W0M9rudR"),
    ("机构一手调研（福总）", "MS4wLjABAAAAtMbrLdV2Zk-ATVxn98zg3bnur76IEWbK43UzDgHmwC8"),
]

# 允许用户通过环境变量追加博主：name|url,name|url
EXTRA_BLOGGERS = os.environ.get("DOUYIN_BLOGGERS_EXTRA", "")

SCRIPT_DIR = Path(__file__).parent
TRANSCRIPT_CACHE_DIR = get_data_dir(SCRIPT_DIR.parent) / 'douyin_transcripts'


def _resolve_cookie_path() -> Path:
    """Use the persistent runtime directory for cookies, not the install cache."""
    configured = os.environ.get("DOUYIN_COOKIE_PATH")
    if configured:
        return Path(configured).expanduser()
    data_dir = os.environ.get("DAILY_BRIEFING_DATA_DIR")
    if data_dir:
        return Path(data_dir).expanduser() / "douyin_cookies.json"
    return Path.home() / ".codex" / "daily-briefing-pro" / "data" / "douyin_cookies.json"


COOKIE_PATH = _resolve_cookie_path()


def load_douyin_cookies() -> list[dict]:
    """加载浏览器导出的 Playwright cookie JSON；失败时保持公开页模式。"""
    try:
        payload = json.loads(COOKIE_PATH.read_text(encoding="utf-8"))
        cookies = payload.get("cookies", []) if isinstance(payload, dict) else payload
        return [item for item in cookies if isinstance(item, dict) and item.get("name") and item.get("value")]
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

# 标的/板块关键词库（持续扩展）
CANDIDATE_SYMBOLS = [
    # 板块
    "半导体", "芯片", "存储", "HBM", "DRAM", "NAND", "AI", "算力", "CPO", "光模块",
    "机器人", "人形机器人", "具身智能", "新能源", "锂电", "光伏", "储能", "风电",
    "券商", "银行", "地产", "消费", "医药", "创新药", "白酒", "汽车", "整车",
    "云计算", "数据中心", "液冷", "铜缆", "PCB", "MLCC", "被动元件", "苹果链",
    "华为", "小米", "阿里", "腾讯", "百度", "字节", "美团", "拼多多", "京东",
    "军工", "商业航天", "卫星", "黄金", "有色", "煤炭", "石油", "电力",
    # A 股/港股常见标的
    "中芯国际", "华虹公司", "中微公司", "北方华创", "长电科技", "通富微电",
    "江波龙", "佰维存储", "兆易创新", "北京君正", "寒武纪", "海光信息",
    "中际旭创", "新易盛", "天孚通信", "光迅科技", "华工科技", "源杰科技",
    "浪潮信息", "工业富联", "中科曙光", "紫光股份", "中兴通讯", "科大讯飞",
    "宁德时代", "比亚迪", "隆基绿能", "阳光电源", "通威股份", "TCL中环",
    "贵州茅台", "五粮液", "泸州老窖", "山西汾酒", "东方财富", "中信证券",
    "药明康德", "恒瑞医药", "迈瑞医疗", "百济神州", "康方生物",
    "美团", "腾讯控股", "阿里巴巴", "小米集团", "百度集团", "京东集团",
    # 美股常见标的
    "英伟达", "NVIDIA", "苹果", "Apple", "微软", "Microsoft", "谷歌", "Google",
    "特斯拉", "Tesla", "Meta", "台积电", "AMD", "高通", "英特尔", "美光",
    "亚马逊", "Amazon", "奈飞", "Netflix", "博通", "Broadcom", "德州仪器",
]

# 方向关键词库
BULLISH_WORDS = [
    "利好", "看多", "上涨", "机会", "买点", "加仓", "主升浪", "放量", "抄底",
    "反弹", "修复", "冲刺", "起飞", "爆发", "龙头", "重点关注", "看好", "必涨",
    "牛市", "主升浪", "突破", "新高", "上车", "拿住",
]
BEARISH_WORDS = [
    "利空", "看空", "下跌", "风险", "卖点", "减仓", "崩盘", "回调", "主跌",
    "破位", "暴跌", "跌停", "炸板", "退潮", "撤退", "快跑", "结束", "见顶",
    "疯狂", "最后的疯狂", "谨慎", "注意风险", "管住手", "亏钱",
]


def parse_extra_bloggers():
    """解析环境变量中追加的博主配置：name|url,name|url"""
    result = []
    if not EXTRA_BLOGGERS.strip():
        return result
    for entry in EXTRA_BLOGGERS.split(","):
        if "|" not in entry:
            continue
        name, url = entry.split("|", 1)
        name = name.strip()
        url = url.strip()
        if name and url:
            result.append((name, url))
    return result


# 模块级目标日期（可通过 set_target_date() 覆盖，用于周末回退）
_TARGET_DATE: str | None = None


def bj_now_str() -> str:
    """当前北京时间日期字符串（支持 --date 覆盖和模块级变量覆盖）"""
    global _TARGET_DATE
    if _TARGET_DATE:
        return _TARGET_DATE
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def set_target_date(date_str: str | None):
    """设置模块级目标日期（用于周末回退搜索前一天）"""
    global _TARGET_DATE
    _TARGET_DATE = date_str


def ts_to_bj_str(timestamp: int) -> str:
    """将 Unix 时间戳（秒）转为北京时间字符串"""
    if not timestamp:
        return "unknown"
    tz_bj = timezone(timedelta(hours=8))
    try:
        return datetime.fromtimestamp(int(timestamp), tz=tz_bj).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(timestamp)


def is_today_beijing(timestamp: int | float | None) -> bool:
    """判断 Unix 时间戳（秒或毫秒）是否为北京时间今日"""
    if not timestamp:
        return False
    ts = int(timestamp)
    # 毫秒时间戳（13位）转秒
    if ts > 1_000_000_000_000:
        ts = ts // 1000
    tz_bj = timezone(timedelta(hours=8))
    dt = datetime.fromtimestamp(ts, tz=tz_bj)
    return dt.strftime("%Y-%m-%d") == bj_now_str()


def parse_video_item(item: dict) -> dict | None:
    """解析单个 aweme_item（列表 API 已不返回 create_time，此处仅解析基础字段）"""
    vid = item.get('aweme_id')
    if not vid:
        return None
    statistics = item.get('statistics', {}) or {}
    return {
        'aweme_id': vid,
        'title': item.get('desc', '').strip() or f"视频 {vid}",
        'url': f'https://www.douyin.com/video/{vid}',
        'digg_count': statistics.get('digg_count', 0),
        'create_time': item.get('create_time') or item.get('createTime') or 0,  # 详情页继续核验
    }


def _is_placeholder_title(title: str) -> bool:
    """列表接口常返回空 desc；这些标题不能作为视频内容标题。"""
    value = (title or "").strip()
    return not value or bool(re.fullmatch(r"(?:视频\s+\d+|douyin_\d+)", value))


def _is_generic_detail_title(title: str) -> bool:
    """抖音 SSR 常见的作者级页面标题，不是单条视频文案。"""
    value = (title or "").strip()
    return bool(re.search(r"在抖音记录美好生活\d{8}$", value))


def _resolve_video_title(title: str, data: dict) -> str:
    """列表 desc 为空时，使用详情页 SSR 标题；不覆盖真实列表标题。"""
    if not _is_placeholder_title(title) or not isinstance(data, dict):
        return title
    metadata = data.get("metadata", {})
    metadata_title = metadata.get("title", "") if isinstance(metadata, dict) else ""
    metadata_title = metadata_title.strip()
    if metadata_title and not _is_placeholder_title(metadata_title) and not _is_generic_detail_title(metadata_title):
        return metadata_title
    # 详情页没有公开单条文案时保留明确的 ID 占位标题，避免把作者级标题
    # 误当成每一条视频的真实标题；实际内容由 transcript 字段承载。
    return title


def extract_detail_timestamp(content: str, body_text: str = "") -> int:
    """从详情页 HTML 或可见文本里解析发布时间戳（秒）。"""
    # 常见格式: "create_time":1783452514
    m = re.search(r'"create_time"\s*:\s*(\d{10,13})', content or '')
    if m:
        ts = int(m.group(1))
        return ts // 1000 if ts > 1_000_000_000_000 else ts
    # 桌面端页面不一定暴露 SSR JSON，但会展示真实发布时间。
    m = re.search(r'发布时间\s*[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', body_text or '')
    if m:
        try:
            return int(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(
                tzinfo=timezone(timedelta(hours=8))
            ).timestamp())
        except ValueError:
            pass
    return 0


async def _read_detail_timestamp(page, url: str, timeout: int, settle_ms: int) -> tuple[int, str]:
    """在给定 page 上打开详情页并解析发布时间，返回 (时间戳, 错误描述)。"""
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
    except Exception as exc:
        return 0, f"goto:{type(exc).__name__}"
    # 详情页是客户端渲染，需要等接口数据落到 DOM；content() 在导航中会抛错，重试即可。
    await page.wait_for_timeout(settle_ms)
    for _ in range(4):
        try:
            content = await page.content()
        except Exception:
            content = ""
        try:
            body_text = await page.locator("body").inner_text(timeout=5000)
        except Exception:
            body_text = ""
        ts = extract_detail_timestamp(content, body_text)
        if ts:
            return ts, ""
        await page.wait_for_timeout(2500)
    return 0, "no-timestamp"


async def fetch_video_create_time_playwright(page, aweme_id: str, timeout: int = 30000) -> int:
    """通过 Playwright 访问视频详情页提取 create_time（秒级时间戳）。

    抖音对 httpx 等纯 HTTP 请求有反爬拦截；2026-09 起移动端 UA 的详情页还会
    被静默拦截（HTTP 200 但 DOM 为空），因此这里先走桌面端渲染，再回退移动端。
    """
    url = f"https://www.douyin.com/video/{aweme_id}"
    errors = []

    browser = page.context.browser
    if browser:
        desktop_context = await new_douyin_context(browser,
            user_agent=DESKTOP_USER_AGENT,
            viewport={'width': 1440, 'height': 900},
        )
        try:
            desktop_page = await desktop_context.new_page()
            for attempt in range(2):
                ts, err = await _read_detail_timestamp(
                    desktop_page, url, timeout, 6000 if attempt == 0 else 3000)
                if ts:
                    return ts
                errors.append(f"桌面页{attempt + 1}:{err}")
        except Exception as exc:
            errors.append(f"桌面页异常:{type(exc).__name__}")
        finally:
            await desktop_context.close()

    ts, err = await _read_detail_timestamp(page, url, timeout, 2500)
    if ts:
        return ts
    errors.append(f"移动页:{err}")

    print(f"  Playwright获取详情页失败 {aweme_id}: {'；'.join(errors)}", file=sys.stderr)
    return 0


async def fill_create_times(videos: list, browser, max_concurrent: int = 3,
                            stop_before_date: str | None = None) -> list:
    """按主页顺序（新→旧）补全视频 create_time，返回带时间戳的视频列表。

    详情页没有批量接口，只能逐条渲染核验；而主页列表本身按发布时间倒序，
    所以一旦确认某批视频整体早于 stop_before_date，更早的条目无需再核验。
    """
    if not videos:
        return videos
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(v: dict) -> dict:
        # 列表接口有时会直接返回真实发布时间；已有值无需再开浏览器核验。
        if v.get('create_time'):
            return v
        async with semaphore:
            ctx = await new_douyin_context(browser,
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15',
                viewport={'width': 390, 'height': 844}
            )
            page = await ctx.new_page()
            try:
                ts = await fetch_video_create_time_playwright(page, v['aweme_id'])
                v['create_time'] = ts
                return v
            finally:
                await ctx.close()

    stop_ts = 0
    if stop_before_date:
        stop_ts = int(datetime.strptime(stop_before_date, "%Y-%m-%d").replace(
            tzinfo=timezone(timedelta(hours=8))).timestamp())

    filled: list = []
    for start in range(0, len(videos), max_concurrent):
        chunk = videos[start:start + max_concurrent]
        results = await asyncio.gather(*[fetch_one(v) for v in chunk], return_exceptions=True)
        resolved = []
        for r in results:
            if isinstance(r, Exception):
                print(f"  补全时间异常: {r}", file=sys.stderr)
                continue
            resolved.append(r)
        filled.extend(resolved)
        # 主页按新→旧排列，一旦出现早于目标窗口的条目，后面的必然更早。
        if stop_ts:
            dated = [v['create_time'] for v in resolved if v.get('create_time')]
            if dated and min(dated) < stop_ts:
                print(f"  已核验 {len(filled)} 条并越过目标窗口，停止核验更早视频", file=sys.stderr)
                break

    return filled


def extract_symbols(text: str) -> list:
    """从文本中提取可能的股票/板块关键词"""
    if not text:
        return []
    text = text.replace("#", "")
    found = []
    for c in CANDIDATE_SYMBOLS:
        if c in text and c not in found:
            found.append(c)
    return found[:6]


def infer_direction(text: str) -> str:
    """从文本推断多空方向"""
    if not text:
        return "关注"
    t = text.lower()
    b = sum(1 for w in BULLISH_WORDS if w in t)
    s = sum(1 for w in BEARISH_WORDS if w in t)
    if b > s:
        return "利好"
    if s > b:
        return "利空"
    return "关注"


def summarize_with_deepseek(text: str) -> str:
    """调用 LLM 总结观点；失败时返回空串，由上层使用标题/话题兜底。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key or len(text) < 20:
        return ""
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2")
    model = os.environ.get("DEEPSEEK_MODEL", "xopqwen35397b")
    import httpx
    import time as _time
    last_error = ""
    for attempt, backoff in enumerate((0, 4, 12), start=1):
        if backoff:
            _time.sleep(backoff)
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": (
                            "你是财经短视频观点提炼助手。输入是抖音财经博主口播的语音转写，"
                            "常见同音错字（例如“偷看”=token、“米子”=小米、“存主”=存储、"
                            "“布恩斯坦”=伯恩斯坦）。请在内部按上下文纠正转写错误，"
                            "只输出提炼后的结论：1-2句话，包含明确判断（看多/看空/中性）、"
                            "核心逻辑，涉及的标的/板块用【】标注，80字以内。"
                            "禁止输出纠错清单、错字对照，或用“内容杂乱/无法提炼”之类套话敷衍。"
                            "只能使用转录里确实出现过的标的与板块，不要补充原文没提到的个股。"
                            "若通篇确实没有可辨识的投资观点，只回复“无明确观点”。")},
                        {"role": "user", "content": text}
                    ],
                    "temperature": 0.3
                },
                timeout=60
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content:
                return content
            last_error = "返回内容为空"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            last_error = last_error.splitlines()[0][:120]
            # 4xx 多为参数/鉴权问题，重试没有意义
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status and 400 <= status < 500:
                break
            print(f"  DeepSeek总结第{attempt}次失败: {last_error}", file=sys.stderr)
    if last_error:
        print(f"  DeepSeek总结失败: {last_error}", file=sys.stderr)
    return ""


def transcribe_video(video_url: str, provider: str = "local") -> dict:
    """调用 analyze_douyin.py 转录单个视频"""
    try:
        child_env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            # The analyzer runs in another process; give it the same resolved
            # persistent cookie path even if the caller configured a relative path.
            "DOUYIN_COOKIE_PATH": str(COOKIE_PATH.resolve()),
        }
        # Parent-owned temp directory ensures timeout/error paths also remove partial
        # MP4/MP3 files left behind when analyze_douyin is terminated.
        with tempfile.TemporaryDirectory(prefix="douyin_transcribe_") as output_dir:
            command = [
                sys.executable, str(SCRIPT_DIR / "analyze_douyin.py"),
                "--provider", provider, "--json", "--output-dir", output_dir, video_url,
            ]
            result = subprocess.run(
                command,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(SCRIPT_DIR.parent), timeout=TRANSCRIBE_TIMEOUT_SECONDS,
                env=child_env,
            )
        data = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if not data and result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip())
            except Exception:
                pass
        if data:
            return data
        detail = (result.stderr or result.stdout or "").strip()
        if result.returncode:
            detail = detail or f"分析器退出码 {result.returncode}"
        else:
            detail = detail or "分析器未返回 JSON 结果"
        return {"status": "error", "error": detail[:500]}
    except subprocess.TimeoutExpired as exc:
        detail = exc.stderr or exc.output or ""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        detail = str(detail).strip().splitlines()[-1:] or [""]
        suffix = f"；末条日志：{detail[0][:180]}" if detail[0] else ""
        return {
            "status": "error",
            "error": f"分析器超过{TRANSCRIBE_TIMEOUT_SECONDS}秒时限{suffix}",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_video_transcript_with_fallback(video: dict) -> dict:
    """获取视频转录，失败/为空时返回 warning 和兜底摘要"""
    url = video.get("url", "")
    title = video.get("title", "")

    cached = load_video_transcript(video)
    data = cached or transcribe_video(url, os.environ.get("DOUYIN_TRANSCRIPT_PROVIDER", "local"))
    title = _resolve_video_title(title, data)
    transcript = data.get("transcript", "") if isinstance(data, dict) else ""

    if not transcript:
        # 转录失败时只保留标题+话题标签作为明确标注的元数据兜底。
        # 不把它伪装成转录原文，也不在简报中展示原文截断。
        hashtags = re.findall(r'#([^#\s]+)', title)
        clean_title = re.sub(r'#([^#\s]+)', '', title).strip()
        if hashtags:
            fallback_text = f"标题：{clean_title}；话题：{'、'.join(hashtags)}"
        else:
            fallback_text = f"标题：{clean_title}"
        data = data if isinstance(data, dict) else {}
        detail = str(data.get("warning") or data.get("error") or "").strip()
        data["transcript"] = ""
        data["fallback_text"] = fallback_text
        data["warning"] = ("转录失败，已使用标题+话题标签兜底"
                           + (f"（原因：{detail[:240]}）" if detail else ""))
    else:
        data = data if isinstance(data, dict) else {}

    data["_resolved_title"] = title
    if transcript and not data.get('warning') and not data.get('error'):
        save_video_transcript(video, data)

    return data


def _video_cache_identity(video: dict) -> dict | None:
    url = str(video.get('url') or '')
    match = re.fullmatch(r'https://www\.douyin\.com/video/(\d{10,25})', url)
    if not match:
        return None
    return {'id': match.group(1), 'url': url, 'create_time': video.get('create_time'),
            'model': os.environ.get('DOUYIN_WHISPER_MODEL', 'small'), 'version': 1}


def load_video_transcript(video: dict) -> dict | None:
    identity = _video_cache_identity(video)
    if not identity:
        return None
    try:
        payload = json.loads((TRANSCRIPT_CACHE_DIR / f"{identity['id']}.json").read_text(encoding='utf-8'))
        if payload.get('identity') != identity:
            return None
        data = payload.get('data') or {}
        if not isinstance(data, dict) or not str(data.get('transcript') or '').strip() or data.get('warning') or data.get('error'):
            return None
        return {**data, 'transcript_source': 'verified_video_cache'}
    except (OSError, ValueError, AttributeError):
        return None


def save_video_transcript(video: dict, data: dict) -> None:
    identity = _video_cache_identity(video)
    if not identity or not str(data.get('transcript') or '').strip() or data.get('warning') or data.get('error'):
        return
    TRANSCRIPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Never persist media paths (temporary files), cookies, or analyzer logs.
    payload = {'identity': identity, 'data': {key: data[key] for key in ('transcript', '_resolved_title') if key in data},
               'verified_at': datetime.now(timezone(timedelta(hours=8))).isoformat()}
    fd, name = tempfile.mkstemp(prefix='transcript-', suffix='.tmp', dir=TRANSCRIPT_CACHE_DIR)
    path = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(path, TRANSCRIPT_CACHE_DIR / f"{identity['id']}.json")
    finally:
        path.unlink(missing_ok=True)


def extract_video_info(video: dict) -> dict:
    """同步执行转录+总结+标的方向提取（供并发调用）"""
    data = get_video_transcript_with_fallback(video)
    transcript = data.get('transcript', '')
    fallback_text = data.get('fallback_text', '')
    warning = data.get('warning', '')
    summary = summarize_with_deepseek(transcript)
    summary_source = "ai" if summary else ""
    display_title = data.get("_resolved_title") or video.get("title", "")

    # 列表接口不给标题时，用转录开头生成可读标题，避免简报里出现「视频 768…」占位。
    if transcript and _is_placeholder_title(display_title):
        cleaned = re.sub(r"[\s，。、！？,.!?]+", "", transcript)
        if cleaned:
            display_title = cleaned[:20] + ("…" if len(cleaned) > 20 else "")
            video['title_source'] = '转录开头'

    # AI 总结失败时给出明确标注的转录摘录，不能把它误标成 AI 总结。
    if transcript and not summary:
        summary = "（AI总结未生成，转录摘录）" + transcript[:80]
        summary_source = "transcript"

    combined_text = f"{display_title} {transcript} {fallback_text}"
    symbols = extract_symbols(combined_text)
    direction = infer_direction(combined_text)
    return {
        "title": display_title,
        "url": video['url'],
        "transcript": transcript,
        "fallback_text": fallback_text,
        "summary": summary,
        "symbols": symbols,
        "direction": direction,
        "warning": warning,
        "title_source": video.get('title_source', '原始标题'),
        "summary_source": summary_source or ("title_hashtags" if fallback_text else ("transcript" if transcript else "unavailable")),
        "created_at": ts_to_bj_str(video.get("create_time", 0)),
    }


LATEST_SEEN: dict = {}  # 博主 -> 主页里最新的视频日期，用于标注“已停更”


async def probe_latest_video_date(sec_uid: str, browser) -> str:
    """目标日无视频时，用桌面UA读一次主页，返回该账号最近一次发布的日期。

    移动UA偶发抓不到 /web/api/v2/aweme/post 响应，这里用与验证脚本一致的
    桌面UA + response 监听，保证「已停更」能给出确切日期而不是笼统留白。
    """
    latest = ""
    ctx = await new_douyin_context(browser,
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        viewport={"width": 1440, "height": 900},
    )
    page = await ctx.new_page()
    seen_payloads = []

    async def capture(response):
        if "/aweme/v1/web/aweme/post/" in response.url or "/web/api/v2/aweme/post" in response.url:
            try:
                seen_payloads.append(await response.json())
            except Exception:
                pass

    page.on("response", lambda r: asyncio.create_task(capture(r)))
    try:
        await page.goto(f"https://www.douyin.com/user/{sec_uid}",
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(6000)
    except Exception as exc:
        print(f"    [WARN] 停更探测失败: {type(exc).__name__}", file=sys.stderr)
    finally:
        for payload in seen_payloads:
            for item in payload.get("aweme_list") or []:
                ts = item.get("create_time")
                if not ts:
                    continue
                day = datetime.fromtimestamp(int(ts), timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
                if day > latest:
                    latest = day
        await ctx.close()
    return latest


async def fetch_blogger_videos(name: str, share_url_or_secuid: str, browser,
                               max_videos: int | None = None,
                               resolve_until_date: str | None = None):
    """获取博主主页视频列表，补全发布时间后按新→旧返回（复用传入的browser实例）
    share_url_or_secuid: 可以是短链URL，也可以是sec_uid（不以http开头）
    resolve_until_date: 核验到此日期即可停止（更早的视频不再逐条渲染详情页）
    """
    print(f"[抖音] 开始抓取: {name}", file=sys.stderr)
    videos = []
    min_cursor_ms = 0
    ctx = await new_douyin_context(browser,
        user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15',
        viewport={'width': 390, 'height': 844}
    )
    page = await ctx.new_page()

    # 判断传入的是 sec_uid 还是 URL
    is_secuid = not share_url_or_secuid.startswith('http')
    sec_uid = None

    if is_secuid:
        # 直接使用 sec_uid，跳过短链解析
        sec_uid = share_url_or_secuid
        print(f"  直接使用 sec_uid: {sec_uid[:20]}...", file=sys.stderr)
    else:
        # 解析短链获取 sec_uid（兼容 ieddouyin.com / iesdouyin.com）
        try:
            await page.goto(share_url_or_secuid, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  打开短链失败: {e}", file=sys.stderr)
            await ctx.close()
            return []

        full_url = page.url

        # 先尝试 iesdouyin.com / iedsdouyin.com 跳转到 douyin.com
        if 'iesdouyin.com' in full_url or 'iedsdouyin.com' in full_url:
            print(f"  检测到 iesdouyin.com，提取 sec_uid 并跳转到 douyin.com...", file=sys.stderr)
            # 从 URL 中提取 sec_uid 参数（更可靠）
            m_sec = re.search(r'sec_uid=([^&]+)', full_url)
            if m_sec:
                sec_uid = m_sec.group(1)
                print(f"  从 sec_uid 参数提取: {sec_uid[:20]}...", file=sys.stderr)
            else:
                # 回退到 /user/ 路径提取
                m_user = re.search(r'/user/([^/?]+)', full_url)
                if m_user:
                    sec_uid = m_user.group(1)
            if sec_uid:
                user_url = f'https://www.douyin.com/user/{sec_uid}'
                try:
                    await page.goto(user_url, wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(5000)
                    full_url = page.url
                except Exception as e:
                    print(f"  跳转失败: {e}", file=sys.stderr)
            else:
                try:
                    await page.goto(full_url.replace('iesdouyin.com', 'douyin.com').replace('iedsdouyin.com', 'douyin.com'), wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(5000)
                    full_url = page.url
                except Exception as e:
                    print(f"  跳转失败: {e}", file=sys.stderr)

        m = re.search(r'/user/([^/?]+)', full_url)
        if not sec_uid:
            sec_uid = m.group(1) if m else None
        if not sec_uid:
            print(f"  未能解析 sec_uid: {full_url}", file=sys.stderr)
            await ctx.close()
            return []

    captured = []
    early_exit = False  # 早退标志

    async def capture(response):
        nonlocal early_exit
        url = response.url
        if '/web/api/v2/aweme/post' in url:
            try:
                data = await response.json()
                min_cursor = data.get('min_cursor', 0)
                has_more = data.get('has_more', False)
                count = len(data.get('aweme_list', []))
                print(f"    - aweme_list: {count}条, min_cursor={min_cursor}, has_more={has_more}", file=sys.stderr)
                if min_cursor:
                    min_cursor_sec = min_cursor // 1000
                    print(f"    - min_cursor北京时间: {ts_to_bj_str(min_cursor_sec)}", file=sys.stderr)
                captured.append(data)
                # 早退：如果 min_cursor 对应的日期早于目标日期，说明已翻过目标日期的视频
                if min_cursor and has_more is False:
                    # min_cursor 是毫秒时间戳，转为日期比较
                    cursor_dt = datetime.fromtimestamp(min_cursor // 1000, timezone(timedelta(hours=8)))
                    target_dt = datetime.strptime(bj_now_str(), "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=8)))
                    if cursor_dt.date() < target_dt.date():
                        early_exit = True
                        print(f"  [早退] min_cursor日期 {cursor_dt.strftime('%Y-%m-%d')} 早于目标日期 {bj_now_str()}，停止滚动", file=sys.stderr)
            except Exception as e:
                print(f"    - JSON解析失败: {e}", file=sys.stderr)

    page.on('response', lambda r: asyncio.create_task(capture(r)))

    user_page = f'https://www.douyin.com/user/{sec_uid}'
    print(f"  访问主页: {user_page}", file=sys.stderr)
    opened = False
    for attempt in range(2):
        try:
            await page.goto(user_page, wait_until='domcontentloaded', timeout=45000)
            opened = True
            break
        except Exception as exc:
            print(f"  主页加载失败（第{attempt + 1}次）: {type(exc).__name__}", file=sys.stderr)
            await page.wait_for_timeout(3000)
    if not opened:
        await ctx.close()
        print(f"  {name} 主页不可访问，跳过", file=sys.stderr)
        return []
    await page.wait_for_timeout(5000)

    # 滚动加载更多（支持早退，增加到20次滚动以获取更多视频）
    for i in range(20):
        if early_exit:
            break
        await page.evaluate('window.scrollBy(0, 3000)')
        await page.wait_for_timeout(2000)
        print(f"    滚动 {i+1}/20", file=sys.stderr)

    # 收集已捕获的数据
    seen = set()
    for data in captured:
        if min_cursor_ms == 0 and data.get('min_cursor'):
            min_cursor_ms = int(data['min_cursor'])
        for item in data.get('aweme_list', []):
            # 记录主页里最新的视频日期：用于区分“目标日无视频”和“账号已停更”
            ts = item.get('create_time')
            if ts:
                day = datetime.fromtimestamp(int(ts), timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
                if day > LATEST_SEEN.get(name, ""):
                    LATEST_SEEN[name] = day
            v = parse_video_item(item)
            if v is None or v['aweme_id'] in seen:
                continue
            seen.add(v['aweme_id'])
            videos.append(v)

    await ctx.close()  # 只关闭context，不关闭browser（复用）

    if not videos:
        print(f"  主页无任何视频", file=sys.stderr)
        return []

    # 通过详情页并发核验每条视频的真实 create_time
    print(f"  主页共 {len(videos)} 条视频，开始核验真实发布时间...", file=sys.stderr)
    videos = await fill_create_times(videos, browser, max_concurrent=3,
                                     stop_before_date=resolve_until_date)

    for v in videos:
        ts = v.get('create_time')
        if not ts:
            continue
        day = datetime.fromtimestamp(int(ts), timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        if day > LATEST_SEEN.get(name, ""):
            LATEST_SEEN[name] = day

    dated = [v for v in videos if v.get('create_time')]
    print(f"  已核验 {len(dated)}/{len(videos)} 条发布时间，最新 {LATEST_SEEN.get(name, '-')}", file=sys.stderr)
    for v in videos[:5]:
        print(f"    - {v['aweme_id']} | {ts_to_bj_str(v.get('create_time', 0))} | {v['title'][:40]}", file=sys.stderr)
    return videos


def finalize_douyin_output(
    output: dict,
    expected_video_count: int,
    collection_errors: list[str] | None = None,
) -> dict:
    """Mark a run complete only when every selected video has a transcript."""
    collection_errors = collection_errors or []
    videos = [
        video
        for blogger in output.get("bloggers", [])
        for video in blogger.get("videos", [])
        if isinstance(video, dict)
    ]
    transcript_count = sum(bool(str(video.get("transcript") or "").strip()) for video in videos)
    video_count = len(videos)
    missing_transcripts = max(expected_video_count - transcript_count, 0)

    output["expected_video_count"] = expected_video_count
    output["video_count"] = video_count
    output["transcript_count"] = transcript_count

    notes = [str(output.get("note") or "").strip()] if output.get("note") else []
    if expected_video_count == 0:
        output["status"] = "error"
        notes.append(f"最近{MAX_STALE_DAYS}天无可核验视频；未使用旧缓存冒充当日内容。")
    else:
        incomplete = missing_transcripts > 0 or video_count < expected_video_count or bool(collection_errors)
        if transcript_count == 0:
            output["status"] = "error"
        elif incomplete:
            output["status"] = "partial"
        else:
            output["status"] = "ok"

        if missing_transcripts:
            notes.append(
                f"转录未完整：{transcript_count}/{expected_video_count}条获得语音文本，"
                f"{missing_transcripts}条仅有标题/话题等元数据兜底。"
            )

        failed = [
            f"{video.get('title') or video.get('url') or '未知视频'}：{video['warning']}"
            for video in videos if video.get("warning")
        ]
        if failed:
            notes.append("转录或下载失败明细：" + "；".join(failed[:3]))

    if collection_errors:
        detail = "；".join(str(error)[:120] for error in collection_errors[:3])
        notes.append(f"主页或条目采集异常{len(collection_errors)}项：{detail}")

    output["note"] = "；".join(note for note in notes if note)
    return output


async def main():
    today = bj_now_str()
    output = {
        "date": today,
        "requested_date": today,
        "data_date": "",
        "bloggers": [],
        "note": "",
        "source": "抖音公开主页/视频详情页（Playwright）",
    }

    # 合并默认博主 + 环境变量追加
    all_bloggers = DEFAULT_BLOGGERS + parse_extra_bloggers()

    # 合并同一博主的多个入口
    blogger_map = {}
    for name, url in all_bloggers:
        # 口罩哥两个入口合并
        key = "口罩哥" if "口罩哥" in name else name
        blogger_map.setdefault(key, []).append(url)

    collection_errors = []
    notes = []
    expected_video_count = 0
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRANSCRIPTS)

    async def process_one_video(video: dict, blogger_name: str) -> dict:
        """带并发限制的单个视频处理"""
        async with semaphore:
            print(f"  转录: {video['title'][:40]}...", file=sys.stderr)
            loop = asyncio.get_running_loop()
            # 转录+总结是同步阻塞调用（subprocess/httpx），扔到线程池执行
            return await loop.run_in_executor(None, extract_video_info, video)

    # 启动一个共享的 Playwright browser，所有博主复用
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for blogger_name, urls in blogger_map.items():
            # 只核验到「允许的最早回退日」，避免为整页历史视频逐条渲染详情页
            earliest = (datetime.strptime(today, "%Y-%m-%d")
                        - timedelta(days=MAX_STALE_DAYS)).strftime("%Y-%m-%d")
            all_videos = []
            for url in urls:
                try:
                    vids = await fetch_blogger_videos(blogger_name, url, browser, max_videos=None,
                                                      resolve_until_date=earliest)
                    all_videos.extend(vids)
                except Exception as exc:
                    # 单个入口失败不能打断整轮采集，其它博主仍需照常产出
                    collection_errors.append(f"{blogger_name}:主页抓取失败 {type(exc).__name__}")
                    print(f"  [WARN] {blogger_name} 入口失败: {type(exc).__name__}: {exc}",
                          file=sys.stderr)

            # 去重并按发布时间倒序（抖音博主一天可能发多条）
            seen = set()
            unique = []
            for v in sorted(all_videos, key=lambda x: x.get('create_time', 0) or 0, reverse=True):
                if v['aweme_id'] not in seen:
                    seen.add(v['aweme_id'])
                    unique.append(v)

            by_date: dict[str, list] = {}
            for v in unique:
                if not v.get('create_time'):
                    continue
                day = datetime.fromtimestamp(int(v['create_time']), timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
                by_date.setdefault(day, []).append(v)

            used_date = today
            selected = sorted(by_date.get(today, []), key=lambda x: x.get('digg_count', 0), reverse=True)

            # 当天未更新时，回退到最近一个有视频的发布日（博主常在下午/晚间发布，
            # 且周末照常更新，所以这里按自然日回退，不做工作日跳过）。
            if not selected:
                for day in sorted(by_date, reverse=True):
                    if day > today or day < earliest:
                        continue
                    selected = sorted(by_date[day], key=lambda x: x.get('digg_count', 0), reverse=True)
                    used_date = day
                    break
                if selected:
                    print(f"  [抖音] {blogger_name} {today}无更新，回退到最近发布日 {used_date}"
                          f"（{len(selected)} 条）", file=sys.stderr)
                    notes.append(f"{blogger_name}采用{used_date}视频（{today}暂未更新）")

            if not selected:
                print(f"  [抖音] {blogger_name} 最近{MAX_STALE_DAYS}天无可核验视频，"
                      f"主页最近发布 {LATEST_SEEN.get(blogger_name, '') or '未知'}", file=sys.stderr)
                if not LATEST_SEEN.get(blogger_name):
                    sec = urls[0] if urls else ""
                    if sec and not sec.startswith("http"):
                        probed = await probe_latest_video_date(sec, browser)
                        if probed:
                            LATEST_SEEN[blogger_name] = probed
                            print(f"  [抖音] {blogger_name} 主页最近发布 {probed}", file=sys.stderr)

            blogger_item = {"name": blogger_name, "data_date": used_date if selected else "", "videos": []}
            blogger_item["last_seen_date"] = LATEST_SEEN.get(blogger_name, "")
            expected_video_count += len(selected)
            # 并发处理该博主选中的视频
            tasks = [process_one_video(v, blogger_name) for v in selected]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    collection_errors.append(f"{blogger_name}:处理异常 {str(result)[:160]}")
                    continue
                blogger_item["videos"].append(result)

            output["bloggers"].append(blogger_item)

        await browser.close()

    actual_dates = sorted({b.get("data_date") for b in output["bloggers"] if b.get("data_date")})
    output["data_date"] = actual_dates[-1] if len(actual_dates) == 1 else (f"{actual_dates[0]}~{actual_dates[-1]}" if actual_dates else "")
    if notes:
        output["note"] = "；".join(notes)
    finalize_douyin_output(output, expected_video_count, collection_errors)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
