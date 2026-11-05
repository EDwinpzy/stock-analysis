#!/usr/bin/env python3
"""Fail-fast checks for a reproducible full daily briefing run.

The collector already refuses to compile when final datasets are incomplete.
This preflight runs earlier and reports the conditions that commonly differ
between a developer machine and a clean cloud runtime: the rotation model,
persistent model history, API/cookie credentials, command-line tools, and
writable output directories. It also verifies that the configured Douyin
transcription path is usable before any video is downloaded. It never prints
credential values.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Mapping, Sequence

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
DEFAULT_REPORT_SUBDIR = ("报告", "每日简报")
CN = timezone(timedelta(hours=8))

REQUIRED_SCRIPTS = (
    "build_briefing.py",
    "build_broadsheet.py",
    "verify_broadsheet.py",
    "fetch_rotation.py",
)
CORE_MODULES = (
    "pandas",
    "numpy",
    "requests",
    "httpx",
    "bs4",
    "playwright",
    "akshare",
    "sklearn",
    "scipy",
)
PANEL_COLUMNS = (
    "date", "sh_close", "sh_ma250", "tradable_count", "advance_count", "turnover",
    "limit_up", "limit_down", "first_board", "consecutive", "space", "next_space",
    "bomb_rate", "yday_limitup_ret", "yday_lianban_ret", "p12", "p23", "p3p",
    "board2", "board3", "board4p", "source",
)
WHISPER_MIN_BYTES = 50 * 1024 * 1024
TRANSCRIPTION_KEY_BY_PROVIDER = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
}


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    state: str
    detail: str
    fix: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PreflightReport:
    date: str
    trade_date: str
    mode: str
    data_dir: str
    output_dir: str
    checks: list[Check]
    checked_at: str

    @property
    def blockers(self) -> list[Check]:
        return [item for item in self.checks if item.state == "error"]

    @property
    def warnings(self) -> list[Check]:
        return [item for item in self.checks if item.state == "warning"]

    @property
    def ok(self) -> bool:
        return not self.blockers

    @property
    def status(self) -> str:
        if self.blockers:
            return "blocked"
        if self.warnings:
            return "warning"
        return "ok"

    def as_dict(self) -> dict:
        return {
            "schema_version": 1,
            "date": self.date,
            "trade_date": self.trade_date,
            "mode": self.mode,
            "status": self.status,
            "checked_at": self.checked_at,
            "data_dir": self.data_dir,
            "output_dir": self.output_dir,
            "summary": {
                "ok": sum(item.state == "ok" for item in self.checks),
                "warning": len(self.warnings),
                "error": len(self.blockers),
            },
            "checks": [item.as_dict() for item in self.checks],
        }

    def format_text(self) -> str:
        markers = {"ok": "[OK]", "warning": "[WARN]", "error": "[BLOCK]"}
        lines = [
            f"预检日期: {self.date}  交易日: {self.trade_date}  模式: {self.mode}",
            f"状态: {self.status}  阻断: {len(self.blockers)}  警告: {len(self.warnings)}",
        ]
        for item in self.checks:
            lines.append(f"{markers.get(item.state, '[INFO]')} {item.label}: {item.detail}")
            if item.state != "ok" and item.fix:
                lines.append(f"       修复: {item.fix}")
        return "\n".join(lines)


def _check(key: str, label: str, state: str, detail: str, fix: str = "") -> Check:
    return Check(key=key, label=label, state=state, detail=detail, fix=fix)


def _ok(key: str, label: str, detail: str) -> Check:
    return _check(key, label, "ok", detail)


def _warning(key: str, label: str, detail: str, fix: str = "") -> Check:
    return _check(key, label, "warning", detail, fix)


def _error(key: str, label: str, detail: str, fix: str = "") -> Check:
    return _check(key, label, "error", detail, fix)


def _nearest_existing(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if candidate.is_dir():
            return candidate
    return None


def _writable_check(key: str, label: str, path: Path, *, create: bool = False) -> Check:
    target = path if path.is_dir() else _nearest_existing(path)
    if target is None:
        return _error(key, label, f"路径及其父目录不存在: {path}")
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
            target = path
        except OSError as exc:
            return _error(key, label, f"无法创建目录: {path} ({type(exc).__name__})")
    try:
        with tempfile.NamedTemporaryFile(prefix=".preflight-", dir=target):
            pass
    except OSError as exc:
        return _error(key, label, f"目录不可写: {target} ({type(exc).__name__})")
    return _ok(key, label, f"可写: {path}")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"不可读或JSON无效: {path} ({type(exc).__name__})") from exc


def _choose_cookie_file(
    *,
    env_name: str,
    fallback: Sequence[Path],
    env: Mapping[str, str],
) -> tuple[Path | None, str]:
    configured = str(env.get(env_name) or "").strip()
    if configured:
        return Path(configured).expanduser(), ""
    for path in fallback:
        if path.is_file():
            return path, ""
    display = ", ".join(str(path) for path in fallback)
    return None, f"未设置 {env_name}，且默认位置均不存在: {display}"


def _cookie_count(path: Path | None) -> tuple[int, str]:
    if path is None:
        return 0, "Cookie文件缺失"
    if not path.is_file():
        return 0, f"Cookie文件缺失: {path}"
    if path.stat().st_size == 0:
        return 0, f"Cookie文件为空: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return 0, f"Cookie文件无法解析: {path} ({type(exc).__name__})"
    entries = payload.get("cookies", []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return 0, f"Cookie文件必须是数组或包含cookies数组: {path}"
    count = sum(
        bool(item.get("name") and item.get("value"))
        for item in entries
        if isinstance(item, dict)
    )
    if count < 1:
        return 0, f"Cookie文件没有可用的name/value条目: {path}"
    return count, ""


def _check_cookie(
    *,
    key: str,
    label: str,
    env_name: str,
    fallback: Sequence[Path],
    env: Mapping[str, str],
    required: bool = True,
) -> Check:
    path, reason = _choose_cookie_file(env_name=env_name, fallback=fallback, env=env)
    count, parse_reason = _cookie_count(path)
    if reason or parse_reason:
        detail = reason or parse_reason
        fix = f"从已登录浏览器导出Cookie到 {fallback[-1]}，或用 {env_name} 指定只读挂载路径"
        if not required:
            return _warning(key, label, f"{detail}（可选；公开页仍会尝试）", fix)
        return _error(
            key,
            label,
            detail,
            fix,
        )
    return _ok(key, label, f"已找到 {count} 条可用Cookie；登录时效仍需采集时核验")


def _check_scripts(package_dir: Path) -> Check:
    missing = [name for name in REQUIRED_SCRIPTS if not (package_dir / "scripts" / name).is_file()]
    if missing:
        return _error(
            "compiler_scripts",
            "编译脚本",
            f"缺少: {', '.join(missing)}",
            "确认运行的是完整插件包，不是只复制了部分脚本",
        )
    return _ok("compiler_scripts", "编译脚本", f"{len(REQUIRED_SCRIPTS)} 个入口齐全")


def _check_modules() -> Check:
    missing = [name for name in CORE_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        return _error(
            "python_modules",
            "Python依赖",
            f"缺少: {', '.join(missing)}",
            "按 deploy/cloud/requirements-cloud.txt 安装依赖",
        )
    return _ok("python_modules", "Python依赖", f"{len(CORE_MODULES)} 个核心模块可用")


def _check_browser() -> Check:
    """Launch the packaged Chromium once; a module import alone is not enough."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True, timeout=30000)
            version = browser.version
            browser.close()
    except Exception as exc:  # noqa: BLE001
        return _error(
            "playwright_browser",
            "浏览器运行时",
            f"Chromium 无法启动 ({type(exc).__name__}: {str(exc)[:120]})",
            "运行 python -m playwright install --with-deps chromium；云端镜像需保留浏览器缓存",
        )
    return _ok("playwright_browser", "浏览器运行时", f"Chromium {version} 可启动")


def _check_tools() -> list[Check]:
    checks = []
    for key, label, command, required in (
        ("ffmpeg", "FFmpeg", "ffmpeg", True),
        ("node", "Node.js", "node", True),
    ):
        location = shutil.which(command)
        if location:
            checks.append(_ok(key, label, f"已安装: {location}"))
        elif required:
            checks.append(_error(key, label, f"未找到 {command}", f"安装 {command} 并确保在 PATH 中"))
        else:
            checks.append(_warning(key, label, f"未找到 {command}"))
    return checks


def _check_hithink(env: Mapping[str, str]) -> tuple[Check, list[str] | None]:
    executable = shutil.which("hithink-finance")
    if not executable:
        return (
            _error(
                "hithink",
                "同花顺数据CLI",
                "未安装 hithink-finance",
                "安装 @hithink-tech/hithink-finance-cli 并配置 API Key",
            ),
            None,
        )
    has_env_key = bool(str(env.get("HITHINK_FINANCE_API_KEY") or "").strip())
    if not has_env_key:
        try:
            result = subprocess.run(
                [executable, "auth", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            payload = json.loads((result.stdout or "").strip().splitlines()[-1])
            configured = result.returncode == 0 and bool((payload.get("data") or {}).get("configured"))
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            return (
                _error(
                    "hithink",
                    "同花顺数据CLI",
                    "无法读取CLI认证状态",
                    "设置 HITHINK_FINANCE_API_KEY，或运行 hithink-finance auth status 检查本机凭据库",
                ),
                None,
            )
        if not configured:
            return (
                _error(
                    "hithink",
                    "同花顺数据CLI",
                    "CLI已安装但未认证",
                    "运行 hithink-finance auth login，或在云端提供 HITHINK_FINANCE_API_KEY",
                ),
                None,
            )

    try:
        from _hithink import trade_dates

        days = trade_dates()
    except Exception as exc:
        return (
            _error(
                "hithink",
                "同花顺数据CLI",
                f"认证已配置，但交易日历请求失败 ({type(exc).__name__})",
                "检查云端网络、API Key 权限和同花顺服务状态",
            ),
            None,
        )
    if not days:
        return (
            _error(
                "hithink",
                "同花顺数据CLI",
                "交易日历返回空列表",
                "检查云端网络、API Key 权限和同花顺服务状态",
            ),
            None,
        )
    source = "环境变量" if has_env_key else "本机凭据库"
    return _ok("hithink", "同花顺数据CLI", f"{source}认证可用；交易日历 {len(days)} 个日期"), days


AI_ENDPOINTS = {
    "DEEPSEEK_API_KEY": "https://api.deepseek.com",
    "OPENAI_API_KEY": "https://api.openai.com/v1",
    "SILICONFLOW_API_KEY": "https://api.siliconflow.cn/v1",
}


def _probe_ai_key(env: Mapping[str, str]) -> tuple[str, str]:
    """Return (state, detail) for the first configured OpenAI-compatible key.

    Only /models is called: it verifies authentication without spending tokens.
    A network failure is a warning because egress policy is environment-specific.
    """
    import requests

    for key_name, base in AI_ENDPOINTS.items():
        value = str(env.get(key_name) or "").strip()
        if not value:
            continue
        try:
            response = requests.get(
                f"{base}/models",
                headers={"Authorization": f"Bearer {value}"},
                timeout=8,
            )
        except requests.RequestException as exc:
            return "warning", f"{key_name} 已配置，但认证探测失败 ({type(exc).__name__})"
        if response.status_code in (401, 403):
            return "error", f"{key_name} 已配置但服务端拒绝认证 (HTTP {response.status_code})"
        if response.status_code >= 500:
            return "warning", f"{key_name} 已配置，服务端返回 HTTP {response.status_code}"
        return "ok", f"{key_name} 认证可用 (HTTP {response.status_code})"
    return "unknown", ""


def _check_semantic_summary(env: Mapping[str, str] | None = None) -> Check:
    values = env if env is not None else os.environ
    try:
        from codex_summary_cli import semantic_summary_status

        available, source = semantic_summary_status()
    except Exception as exc:
        return _error(
            "semantic_summary",
            "AI语义总结",
            f"凭证检测失败 ({type(exc).__name__})",
            "检查 DEEPSEEK_API_KEY / OPENAI_API_KEY，或登录 Codex CLI",
        )
    if available:
        state, detail = _probe_ai_key(values)
        if state == "error":
            return _error(
                "semantic_summary",
                "AI语义总结",
                detail,
                "更换有效的 DEEPSEEK_API_KEY / OPENAI_API_KEY / SILICONFLOW_API_KEY",
            )
        if state == "warning":
            return _warning(
                "semantic_summary",
                "AI语义总结",
                f"{source}；{detail}",
                "确认云端出网策略允许访问模型服务；否则只能复用已有摘要缓存",
            )
        return _ok("semantic_summary", "AI语义总结", f"可用来源: {source}；{detail or '未配置可探测的API Key'}")
    return _error(
        "semantic_summary",
        "AI语义总结",
        f"不可用: {source}",
        "在云端 secrets 配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY；不能只复制本机 Codex 登录态",
    )


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (AttributeError, ImportError, ValueError):
        return False


def _whisper_cache_path(model_name: str, env: Mapping[str, str]) -> Path:
    cache_home = str(env.get("XDG_CACHE_HOME") or "").strip()
    base = Path(cache_home).expanduser() if cache_home else Path.home() / ".cache"
    return base / "whisper" / f"{model_name}.pt"


def _whisper_ready(env: Mapping[str, str]) -> tuple[bool, str]:
    """Verify both the Python packages and the actual model weights."""
    if not (_module_available("whisper") and _module_available("torch")):
        return False, "whisper/torch 未安装"
    try:
        import torch  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return False, f"torch 导入失败 ({type(exc).__name__})"
    model_name = str(env.get("DOUYIN_WHISPER_MODEL") or "small").strip() or "small"
    path = _whisper_cache_path(model_name, env)
    if not path.is_file():
        return False, f"模型权重未下载: {path}"
    if path.stat().st_size < WHISPER_MIN_BYTES:
        return False, f"模型权重不完整: {path} ({path.stat().st_size} bytes)"
    return True, f"{model_name} 权重已就绪 ({path.stat().st_size / 1024 / 1024:.0f} MB)"


def _check_transcription(env: Mapping[str, str]) -> Check:
    """Verify the configured Douyin transcription path before downloading video."""
    provider = str(env.get("DOUYIN_TRANSCRIPT_PROVIDER") or "local").strip().lower()
    cloud_runtime = str(env.get("DAILY_BRIEFING_CLOUD") or "") == "1"
    supported = ("local", "auto", *TRANSCRIPTION_KEY_BY_PROVIDER)
    if provider not in supported:
        return _error(
            "transcription",
            "抖音转录",
            f"未知的 DOUYIN_TRANSCRIPT_PROVIDER={provider}",
            "改为 local、auto、groq、openai 或 siliconflow",
        )

    whisper_ready, whisper_detail = _whisper_ready(env)
    configured = [
        name for name, key in TRANSCRIPTION_KEY_BY_PROVIDER.items()
        if str(env.get(key) or "").strip()
    ]
    if provider == "local":
        if whisper_ready:
            if cloud_runtime:
                return _warning(
                    "transcription",
                    "抖音转录",
                    f"云端显式使用本地 Whisper（{whisper_detail}）；1.5 CPU / 2GB 限制下可能超时",
                    "如已配置转录 API Key，改为 DOUYIN_TRANSCRIPT_PROVIDER=auto",
                )
            return _ok("transcription", "抖音转录", f"本地 Whisper（{whisper_detail}）")
        return _error(
            "transcription",
            "抖音转录",
            f"DOUYIN_TRANSCRIPT_PROVIDER=local，但{whisper_detail}",
            "安装 openai-whisper 与 CPU torch 并预下载模型权重，或显式配置可用的转录 API Key",
        )
    if provider == "auto":
        if configured:
            return _ok("transcription", "抖音转录", f"API Key 可用: {', '.join(configured)}")
        if whisper_ready:
            if cloud_runtime:
                return _warning(
                    "transcription",
                    "抖音转录",
                    f"未配置转录 API Key，将回退到 1.5 CPU 的本地 Whisper（{whisper_detail}），可能超时",
                    "在云端 secrets 配置 GROQ_API_KEY、OPENAI_API_KEY 或 SILICONFLOW_API_KEY",
                )
            return _ok("transcription", "抖音转录", f"未配置 API Key，将使用本地 Whisper（{whisper_detail}）")
        return _error(
            "transcription",
            "抖音转录",
            f"未配置 Groq/OpenAI/SiliconFlow Key，且{whisper_detail}",
            "安装 openai-whisper 与 CPU torch 并预下载模型，或在 secrets 中配置转录 API Key",
        )

    key_name = TRANSCRIPTION_KEY_BY_PROVIDER[provider]
    if str(env.get(key_name) or "").strip():
        return _ok("transcription", "抖音转录", f"{provider} API Key 可用")
    return _error(
        "transcription",
        "抖音转录",
        f"DOUYIN_TRANSCRIPT_PROVIDER={provider}，但 {key_name} 未配置",
        f"在云端 secrets 中配置 {key_name}，或把 provider 改为 local/auto",
    )


def _csv_summary(path: Path, *, date_column: str = "date") -> tuple[int, str]:
    if not path.is_file():
        raise ValueError(f"文件缺失: {path}")
    rows = 0
    latest = ""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or date_column not in reader.fieldnames:
            raise ValueError(f"{path.name} 缺少 {date_column} 列")
        for row in reader:
            rows += 1
            value = str(row.get(date_column) or "")[:10]
            if len(value) == 10 and value > latest:
                latest = value
    return rows, latest


def _check_panel(data_dir: Path, trade_date: str) -> Check:
    path = data_dir / "sentiment_panel_v32.csv"
    if not path.is_file():
        return _error(
            "sentiment_panel",
            "情绪模型历史面板",
            f"文件缺失: {path}",
            "从本机长期数据同步 sentiment_panel_v32.csv，或让云端重新回补至少60个交易日",
        )
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle), [])
    except OSError as exc:
        return _error(
            "sentiment_panel",
            "情绪模型历史面板",
            f"无法读取: {path} ({type(exc).__name__})",
            "恢复可读的面板文件",
        )
    missing_columns = [name for name in PANEL_COLUMNS if name not in header]
    if missing_columns:
        return _error(
            "sentiment_panel",
            "情绪模型历史面板",
            f"缺少模型必需列: {', '.join(missing_columns)}",
            "恢复完整 v3.2 面板；缺列会被下游静默补 0，不能继续生成温度",
        )
    try:
        rows, latest = _csv_summary(path)
    except ValueError as exc:
        return _error(
            "sentiment_panel",
            "情绪模型历史面板",
            str(exc),
            "从本机长期数据同步 sentiment_panel_v32.csv，或让云端重新回补至少60个交易日",
        )
    if rows < 60:
        return _error(
            "sentiment_panel",
            "情绪模型历史面板",
            f"仅 {rows} 行，少于模型最低 {60} 行",
            "补齐面板历史后重试；不能用空面板或旧11因子模型替代",
        )
    if latest and latest < trade_date:
        return _warning(
            "sentiment_panel",
            "情绪模型历史面板",
            f"{rows} 行，截至 {latest}；目标交易日为 {trade_date}，采集阶段需增量回补",
            "若云端无法访问开盘啦历史接口，先运行 seed-data.ps1 同步本机面板",
        )
    if latest and latest > trade_date:
        return _warning(
            "sentiment_panel",
            "情绪模型历史面板",
            f"最新日期 {latest} 晚于目标交易日 {trade_date}",
            "核对目标日期和持久数据目录，避免把未来数据混入历史分位",
        )
    return _ok("sentiment_panel", "情绪模型历史面板", f"{rows} 行，截至 {latest}")


def _check_static_data(package_dir: Path) -> list[Check]:
    checks = []
    csv_files = {
        "_stock_names.csv": 100,
    }
    for filename, minimum in csv_files.items():
        path = package_dir / "data" / filename
        try:
            rows, _ = _csv_summary(path, date_column="code" if filename == "_stock_names.csv" else "date")
        except ValueError as exc:
            checks.append(_error("stock_names", "股票名称表", str(exc), "恢复插件 data 目录中的完整静态文件"))
            continue
        state = "ok" if rows >= minimum else "error"
        detail = f"{rows} 行"
        checks.append(
            _ok("stock_names", "股票名称表", detail)
            if state == "ok"
            else _error("stock_names", "股票名称表", f"仅 {rows} 行，少于 {minimum}", "恢复完整代码表")
        )

    roster_specs = (
        ("tgb_hot_users.json", "淘股吧名单", 50, "tgb_roster"),
        ("xueqiu_hot_users.json", "雪球名单", 1, "xueqiu_roster"),
    )
    for filename, label, minimum, key in roster_specs:
        path = package_dir / "data" / filename
        try:
            rows = _read_json(path)
            count = len(rows) if isinstance(rows, list) else 0
        except ValueError as exc:
            checks.append(_error(key, label, str(exc), "恢复插件 data 目录中的核验名单"))
            continue
        if count < minimum:
            checks.append(
                _error(key, label, f"仅 {count} 条，至少需要 {minimum}", "恢复核验名单；不得用未核验默认名单")
            )
        elif filename == "tgb_hot_users.json" and count != 50:
            checks.append(_error(key, label, f"应有50条，实际 {count} 条", "恢复原始50人核验名单"))
        else:
            checks.append(_ok(key, label, f"{count} 条"))

    quotes_path = package_dir / "data" / "investment_quotes.json"
    try:
        quotes = _read_json(quotes_path)
        verified = [
            item for item in quotes
            if isinstance(item, dict) and item.get("verified") and item.get("source_url")
        ] if isinstance(quotes, list) else []
    except ValueError as exc:
        checks.append(_error("quotes", "每日金句库", str(exc), "恢复带原始出处的 investment_quotes.json"))
    else:
        if verified:
            checks.append(_ok("quotes", "每日金句库", f"{len(verified)} 条已核验"))
        else:
            checks.append(_error("quotes", "每日金句库", "没有 verified + source_url 条目", "恢复已核验金句库"))
    return checks


def _check_model(model_dir: Path | None, trade_date: str) -> list[Check]:
    if model_dir is None:
        return [
            _error(
                "rotation_model",
                "行业轮动模型",
                "未找到 sw_rotation_model",
                "把模型目录放到插件 models/sw_rotation_model，或把 ROTATION_MODEL_DIR 指向云端可写模型工作目录",
            )
        ]
    checks = []
    missing = [
        name for name in (
            "run.py", "config.json",
            "src/data.py", "src/features.py", "src/engine.py",
        )
        if not (model_dir / name).is_file()
    ]
    if missing:
        checks.append(
            _error(
                "rotation_model",
                "行业轮动模型",
                f"{model_dir} 缺少: {', '.join(missing)}",
                "恢复完整模型源码与配置",
            )
        )
        return checks
    try:
        config = _read_json(model_dir / "config.json")
    except ValueError as exc:
        checks.append(_error("rotation_model", "行业轮动模型", str(exc), "恢复有效 config.json"))
        return checks
    if not isinstance(config, dict):
        checks.append(
            _error(
                "rotation_model",
                "行业轮动模型",
                f"{model_dir / 'config.json'} 必须是JSON对象",
                "恢复原始 config.json；不能用数组或空值代替模型配置",
            )
        )
        return checks

    universe = str(config.get("universe") or "sw").strip().casefold()
    checks.append(_ok("rotation_model", "行业轮动模型", f"{model_dir}；universe={universe}"))
    data_dir = model_dir / "data"
    if not data_dir.is_dir():
        checks.append(
            _error(
                "rotation_inputs",
                "轮动模型输入",
                f"缺少模型数据目录: {data_dir}",
                "恢复模型原始 data/ 输入；不能用旧 rotation_today.json 反推",
            )
        )
    elif universe == "ths":
        required = ("data/ths_industry_info.csv", "data/ths_industry_daily.csv", "data/benchmark_csi300.csv")
        missing_data = [name for name in required if not (model_dir / name).is_file()]
        if missing_data:
            checks.append(
                _error(
                    "rotation_inputs",
                    "轮动模型输入",
                    f"缺少: {', '.join(missing_data)}",
                    "恢复模型原始行情与沪深300基准，不能用旧 rotation_today.json 反推",
                )
            )
        else:
            try:
                info_rows, _ = _csv_summary(model_dir / "data/ths_industry_info.csv", date_column="code")
                daily_rows, latest = _csv_summary(model_dir / "data/ths_industry_daily.csv")
            except ValueError as exc:
                checks.append(_error("rotation_inputs", "轮动模型输入", str(exc), "恢复完整模型数据"))
            else:
                if latest and latest < trade_date:
                    checks.append(
                        _warning(
                            "rotation_inputs",
                            "轮动模型输入",
                            f"{daily_rows} 行，{info_rows} 个行业，截至 {latest}；采集阶段将增量补齐",
                            "云端必须允许访问同花顺行业指数和沪深300行情，否则先同步模型数据目录",
                        )
                    )
                else:
                    checks.append(
                        _ok(
                            "rotation_inputs",
                            "轮动模型输入",
                            f"{daily_rows} 行，{info_rows} 个行业，截至 {latest or '未知'}",
                        )
                    )
    elif universe == "sw":
        required = ("data/sw_l1_info.csv", "data/sw_l1_daily.csv", "data/benchmark_csi300.csv")
        missing_data = [name for name in required if not (model_dir / name).is_file()]
        if missing_data:
            checks.append(
                _error(
                    "rotation_inputs",
                    "轮动模型输入",
                    f"缺少: {', '.join(missing_data)}",
                    "恢复申万一级行业行情与沪深300基准，不能用旧排行结果代替",
                )
            )
        else:
            try:
                info_rows, _ = _csv_summary(model_dir / "data/sw_l1_info.csv", date_column="code")
                daily_rows, latest = _csv_summary(model_dir / "data/sw_l1_daily.csv")
            except ValueError as exc:
                checks.append(_error("rotation_inputs", "轮动模型输入", str(exc), "恢复完整模型数据"))
            else:
                detail = f"{daily_rows} 行，{info_rows} 个行业，截至 {latest or '未知'}"
                if latest and latest < trade_date:
                    checks.append(
                        _warning(
                            "rotation_inputs",
                            "轮动模型输入",
                            detail + "；采集阶段将增量补齐",
                            "云端必须允许访问申万行业指数和沪深300行情，否则先同步模型数据目录",
                        )
                    )
                else:
                    checks.append(_ok("rotation_inputs", "轮动模型输入", detail))
    else:
        checks.append(
            _error(
                "rotation_inputs",
                "轮动模型输入",
                f"未知 universe={universe}",
                "config.json 只支持 ths 或 sw",
            )
        )
    checks.append(_writable_check("rotation_writable", "轮动模型目录可写性", model_dir, create=False))
    if data_dir.is_dir():
        checks.append(
            _writable_check("rotation_data_writable", "轮动模型数据可写性", data_dir, create=False)
        )
    checks.append(
        _writable_check("rotation_output_writable", "轮动模型输出可写性", model_dir / "outputs", create=True)
    )
    return checks


def _check_history(data_dir: Path, trade_date: str = "") -> list[Check]:
    checks = []
    rotation = data_dir / "rotation_history.json"
    if rotation.is_file():
        try:
            payload = _read_json(rotation)
            if not isinstance(payload, dict):
                raise ValueError("顶层必须是 {日期: 快照} 对象")
            parsed = []
            for key, value in payload.items():
                if not isinstance(value, dict):
                    raise ValueError(f"{key} 的快照不是对象")
                names = value.get("names")
                if not isinstance(names, list) or not names:
                    raise ValueError(f"{key} 缺少非空 names 数组")
                datetime.strptime(str(key), "%Y-%m-%d")
                parsed.append(str(key))
        except (ValueError, TypeError) as exc:
            checks.append(
                _error(
                    "rotation_history",
                    "轮动历史快照",
                    f"JSON无效: {exc}",
                    "从本机重新同步 rotation_history.json；坏文件会被采集器当作空历史",
                )
            )
        else:
            latest = max(parsed) if parsed else ""
            if trade_date and latest and latest < (
                datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=30)
            ).strftime("%Y-%m-%d"):
                checks.append(
                    _warning(
                        "rotation_history",
                        "轮动历史快照",
                        f"{len(parsed)} 个交易日，最新 {latest}，已超过30天未更新",
                        "同步最新 rotation_history.json；否则新进/跌出会与过期基线比较",
                    )
                )
            else:
                checks.append(
                    _ok("rotation_history", "轮动历史快照", f"{len(parsed)} 个交易日，最新 {latest}")
                )
    else:
        checks.append(
            _warning(
                "rotation_history",
                "轮动历史快照",
                "缺失；首次运行的新进/跌出会标记为 baseline",
                "从本机长期数据同步 rotation_history.json",
            )
        )
    node = data_dir / "node_cycle_history.json"
    if node.is_file():
        try:
            payload = _read_json(node)
            records = payload.get("records", []) if isinstance(payload, dict) else []
            if not isinstance(records, list):
                raise ValueError("records 必须是数组")
            for item in records:
                if not isinstance(item, dict) or not item.get("date"):
                    raise ValueError("存在缺少 date 的记录")
            checks.append(_ok("node_history", "节点票历史", f"{len(records)} 个交易日快照"))
        except ValueError as exc:
            checks.append(
                _error("node_history", "节点票历史", f"JSON无效: {exc}", "从本机同步 node_cycle_history.json")
            )
    else:
        checks.append(
            _warning(
                "node_history",
                "节点票历史",
                "缺失；依赖同花顺历史连板池回补",
                "从本机同步 node_cycle_history.json，避免云端历史接口限流后节点跨度缩水",
            )
        )
    return checks


def _check_resume_datasets(data_dir: Path, report_date: str, trade_date: str) -> Check:
    """Fail before compilation when a --resume run lacks complete dated data."""
    try:
        from briefing_integrity import MODULES, validate_data
    except Exception as exc:
        return _error(
            "resume_inputs",
            "续跑数据",
            f"完整性校验模块不可用 ({type(exc).__name__})",
            "确认插件包中的 briefing_integrity.py 完整存在",
        )

    data = {}
    for filename in (*MODULES, "node_cycle_today.json", "indices_today.json"):
        try:
            payload = _read_json(data_dir / filename)
            data[filename] = payload if isinstance(payload, dict) else {}
        except ValueError:
            data[filename] = {}
    try:
        quote = (data_dir / "quote_today.html").read_text(encoding="utf-8-sig")
    except OSError:
        quote = ""

    try:
        failures = validate_data(data, report_date, trade_date, quote)
    except Exception as exc:
        return _error(
            "resume_inputs",
            "续跑数据",
            f"完整性校验执行失败 ({type(exc).__name__})",
            "重新运行完整采集；不要用 --resume 跳过数据核验",
        )
    if failures:
        preview = "；".join(failures[:5])
        if len(failures) > 5:
            preview += f"；另有 {len(failures) - 5} 项"
        return _error(
            "resume_inputs",
            "续跑数据",
            preview,
            "重新运行完整采集，或修复对应数据文件后再使用 --resume",
        )
    return _ok(
        "resume_inputs",
        "续跑数据",
        f"{len(MODULES) + 2} 个模块和每日一句均通过完整性校验",
    )


def build_preflight(
    report_date: str,
    trade_date: str,
    *,
    data_dir: Path | None = None,
    package_dir: Path | None = None,
    output_dir: Path | None = None,
    collecting: bool = True,
    env: Mapping[str, str] | None = None,
) -> PreflightReport:
    """Evaluate all startup conditions without exposing secret values."""
    package = Path(package_dir or BASE_DIR)
    values = env if env is not None else os.environ
    if data_dir:
        data = Path(data_dir)
    else:
        from runtime_paths import get_data_dir

        data = get_data_dir(package, env=values)
    configured_output = str(values.get("BRIEFING_OUTPUT_DIR") or "").strip()
    output = (
        Path(output_dir)
        if output_dir
        else Path(configured_output).expanduser()
        if configured_output
        else Path.cwd().joinpath(*DEFAULT_REPORT_SUBDIR)
    )
    checks: list[Check] = []

    checks.append(_check_scripts(package))
    checks.append(_check_modules())
    checks.append(_check_browser())
    checks.append(_writable_check("data_writable", "持久数据目录", data, create=True))
    checks.append(_writable_check("output_writable", "报告输出目录", output, create=True))

    if collecting:
        try:
            from cloud_bootstrap import bootstrap

            boot = bootstrap(package, data, values)
        except Exception as exc:  # noqa: BLE001
            checks.append(
                _warning(
                    "cloud_bootstrap",
                    "云端基线恢复",
                    f"执行失败 ({type(exc).__name__}: {str(exc)[:120]})",
                    "检查插件 data/cloud-baseline 是否完整",
                )
            )
        else:
            if boot["errors"]:
                checks.append(
                    _error(
                        "cloud_bootstrap",
                        "云端基线恢复",
                        "；".join(boot["errors"])[:300],
                        "恢复 data/cloud-baseline 中的历史数据与模型压缩包",
                    )
                )
            else:
                detail = f"新增 {boot['data_seeded']} 个基线文件"
                if boot["model_dir"]:
                    detail += f"；轮动模型 {boot['model_dir']}"
                checks.append(_ok("cloud_bootstrap", "云端基线恢复", detail))

        checks.extend(_check_tools())
        hithink_check, trading_days = _check_hithink(values)
        checks.append(hithink_check)
        checks.append(_check_semantic_summary(values))
        checks.append(_check_transcription(values))
        home = Path.home()
        checks.append(
            _check_cookie(
                key="tgb_cookie",
                label="淘股吧Cookie",
                env_name="TGB_COOKIE_PATH",
                fallback=(data / "tgb_cookies.json", home / ".codex" / "tgb_cookies.json"),
                env=values,
            )
        )
        checks.append(
            _check_cookie(
                key="douyin_cookie",
                label="抖音Cookie",
                env_name="DOUYIN_COOKIE_PATH",
                fallback=(data / "douyin_cookies.json",),
                env=values,
            )
        )
        checks.append(
            _check_cookie(
                key="xueqiu_cookie",
                label="雪球Cookie",
                env_name="XUEQIU_COOKIE_PATH",
                fallback=(data / "xueqiu_cookies.json", home / ".codex" / "xueqiu_cookies.json"),
                env=values,
                required=False,
            )
        )
        checks.append(_check_panel(data, trade_date))
        checks.extend(_check_static_data(package))
        checks.extend(_check_history(data, trade_date))

        model_path = None
        try:
            from fetch_rotation import find_model_dir

            model_path = find_model_dir()
        except Exception as exc:
            checks.append(
                _error(
                    "rotation_model",
                    "行业轮动模型",
                    f"模型路径检测失败 ({type(exc).__name__})",
                    "检查 ROTATION_MODEL_DIR 和插件 models 目录",
                )
            )
        else:
            checks.extend(_check_model(model_path, trade_date))
            if model_path and trading_days:
                latest_day = max(day for day in trading_days if day <= report_date) if any(
                    day <= report_date for day in trading_days
                ) else ""
                if latest_day and latest_day != trade_date:
                    checks.append(
                        _warning(
                            "trade_calendar",
                            "交易日历",
                            f"日历最近交易日为 {latest_day}，当前编排日为 {trade_date}",
                            "核对目标日期；节假日不能按普通工作日推断",
                        )
                    )
                else:
                    checks.append(_ok("trade_calendar", "交易日历", f"最近交易日 {latest_day or trade_date}"))
    else:
        checks.append(_check_resume_datasets(data, report_date, trade_date))

    return PreflightReport(
        date=report_date,
        trade_date=trade_date,
        mode="collection" if collecting else "resume",
        data_dir=str(data),
        output_dir=str(output),
        checks=checks,
        checked_at=datetime.now(CN).isoformat(timespec="seconds"),
    )


def write_report(report: PreflightReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="每日简报运行前检查")
    parser.add_argument("--date", default=datetime.now(CN).strftime("%Y-%m-%d"))
    parser.add_argument("--trade-date", default="")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--package-dir", type=Path, default=BASE_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-report", type=Path)
    args = parser.parse_args(argv)

    try:
        import env_config  # noqa: F401  Load the same non-secret credential file as collectors.
        from trading_date import get_recent_trade_date

        trade_date = args.trade_date or get_recent_trade_date(args.date)
        report = build_preflight(
            args.date,
            trade_date,
            data_dir=args.data_dir,
            package_dir=args.package_dir,
            output_dir=args.output_dir,
            collecting=not args.resume,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2

    if args.write_report:
        write_report(report, args.write_report)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.json else report.format_text())
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
