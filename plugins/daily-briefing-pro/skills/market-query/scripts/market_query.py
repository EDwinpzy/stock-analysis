#!/usr/bin/env python3
"""Portable A-share market query CLI.

Uses the ``thsdk`` service contract or the Fuyao REST API on Windows, Linux
and macOS. It does not read a desktop client, Lumi process or local login
state. All output is UTF-8 JSON, and the CLI never prints or writes an API key.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import math
import os
import secrets
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import requests
except ImportError:  # pragma: no cover - exercised only in broken installs
    requests = None


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


CN = timezone(timedelta(hours=8))
BASE_URL = os.environ.get("THS_MARKET_CLOUD_BASE_URL", "https://fuyao.aicubes.cn").rstrip("/")
API_KEY_ENVS = ("FUYAO_API_KEY", "HITHINK_API_KEY", "HITHINK_FINANCE_API_KEY")
SKILL_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = SKILL_ROOT / "references"

PERIODS = {
    5: "day",
    11: "week",
    12: "month",
    15: "1m",
    16: "5m",
    17: "15m",
    18: "30m",
    19: "60m",
}
PERIOD_LABELS = {
    "day": 5,
    "week": 11,
    "month": 12,
    "1m": 15,
    "5m": 16,
    "15m": 17,
    "30m": 18,
    "60m": 19,
}
ADJUST_TYPES = {"": 0, "none": 0, "forward": 1, "backward": 2}
ADJUST_NAMES = {0: "", 1: "forward", 2: "backward"}
BIG_ORDER_DIRECTIONS = {
    "1": "大单买入",
    "-1": "大单卖出",
    "2": "中单买入",
    "-2": "中单卖出",
    "3": "小单买入",
    "-3": "小单卖出",
    "4": "特大单买入",
    "-4": "特大单卖出",
}
WENCAI_ENDPOINT = os.environ.get(
    "WENCAI_QUERY_ENDPOINT", "https://openapi.iwencai.com/v1/query2data"
)
WENCAI_TIMEOUT_SECONDS = 6
WENCAI_SKILL_IDS = (
    "hithink-basicinfo-query",
    "hithink-finance-query",
    "hithink-industry-query",
    "hithink-business-query",
    "hithink-event-query",
    "hithink-management-query",
    "hithink-market-query",
    "hithink-zhishu-query",
    "hithink-insresearch-query",
    "hithink-macro-query",
    "hithink-fund-query",
    "hithink-futures-query",
    "hithink-sector-selector",
    "hithink-cb-selector",
    "hithink-etf-selector",
    "hithink-fund-selector",
    "hithink-fundcompany-selector",
    "hithink-fundmanager-selector",
    "hithink-hkstock-selector",
    "hithink-usstock-selector",
    "hithink-futures-selector",
)
WENCAI_FALLBACK_SKILLS = {"hithink-market-query"}
WENCAI_API_KEY_ENVS = ("IWENCAI_API_KEY", "WENCAI_API_KEY")
INDICATOR_PERIODS = {
    "1min": 15,
    "5min": 16,
    "15min": 17,
    "30min": 18,
    "60min": 19,
    "day": 5,
    "week": 11,
    "month": 12,
}
INDICATOR_NAMES = (
    "MA5",
    "MA10",
    "MA20",
    "MA30",
    "MA60",
    "MA120",
    "MA200",
    "EMA12",
    "EMA26",
    "MACD",
    "RSI6",
    "RSI14",
    "KDJ",
    "BOLL",
    "ATR14",
    "OBV",
    "VOL_MA5",
    "VOL_MA10",
    "量比",
    "振幅",
)
SORT_FIELDS = {
    "199112": ("price_change_ratio_pct", ("涨幅", "涨跌幅")),
    "264648": ("price_change", ("涨跌",)),
    "10": ("last_price", ("价格", "最新价")),
    "13": ("volume", ("成交量",)),
    "19": ("turnover", ("总金额", "成交额")),
    "6": ("prev_close", ("昨收价", "昨收")),
    "7": ("open_price", ("开盘价", "开盘")),
    "8": ("high_price", ("最高价", "最高")),
    "9": ("low_price", ("最低价", "最低")),
}
CLOUD_BLOCK_NAMES = {
    14: "沪深A股",
    21: "沪市A股",
    27: "深市A股",
    50854: "全部A股",
}
VENDOR_PRICE_SENTINEL = 2_000_000_000.0
VENDOR_NULL_SENTINEL = 2_147_483_648.0
SUBSCRIBE_APIS = (
    "SubscribeRealtime",
    "SubscribeIntradayCandle",
    "SubscribeIntradayTrend",
    "SubscribeTrend",
    "SubscribeIntradayTick",
    "SubscribeTick",
)

# Field IDs used by the desktop market-query skill.  Keeping this mapping
# makes JSON consumers work with the same IDs as the PowerShell client.
REALTIME_FIELD_MAP = {
    "5": "thscode",
    "6": "prev_close",
    "7": "open_price",
    "8": "high_price",
    "9": "low_price",
    "10": "last_price",
    "13": "volume",
    "19": "turnover",
    "55": "name",
    "199112": "price_change_ratio_pct",
    "264648": "price_change",
}
REALTIME_CHINESE_ALIASES = {
    "最新价": "last_price",
    "价格": "last_price",
    "昨收价": "prev_close",
    "昨收": "prev_close",
    "开盘价": "open_price",
    "最高价": "high_price",
    "最低价": "low_price",
    "成交量": "volume",
    "总金额": "turnover",
    "成交额": "turnover",
    "名称": "name",
    "涨幅": "price_change_ratio_pct",
    "涨跌": "price_change",
}
TREND_FIELD_MAP = {
    "1": "time",
    "10": "price",
    "13": "volume",
    "19": "turnover",
}
TICK_FIELD_MAP = {
    "1": "time",
    "10": "price",
    "12": "volume_class",
    "18": "trade_count",
    "49": "last_volume",
}

# Industry names in wencai sometimes carry a Roman-numeral suffix
# (白酒Ⅲ).  The suffix is not accepted by the downstream query endpoint.
ROMAN_SUFFIXES = ("Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "I", "II", "III", "IV", "V")


class QueryError(RuntimeError):
    """A user-facing query failure with a stable machine-readable code."""

    def __init__(self, message: str, code: str = "query_failed", details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


def redact(value: Any) -> Any:
    """Remove API keys and bearer tokens from arbitrary error payloads."""

    text = str(value)
    for name in API_KEY_ENVS + WENCAI_API_KEY_ENVS:
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[redacted]")
    lowered = text.lower()
    marker = "x-api-key"
    if marker in lowered:
        head = lowered.index(marker)
        tail = text.find("\n", head)
        text = text[:head] + "x-api-key=[redacted]" + (text[tail:] if tail >= 0 else "")
    return text


@contextlib.contextmanager
def suppress_native_stdout():
    """Silence native-library writes to fd 1 while Python code runs."""

    try:
        sys.stdout.flush()
    except (AttributeError, OSError, ValueError):
        pass

    with contextlib.redirect_stdout(io.StringIO()):
        saved_fd = None
        devnull = None
        try:
            saved_fd = os.dup(1)
            devnull = open(os.devnull, "w", encoding="utf-8")
            os.dup2(devnull.fileno(), 1)
        except OSError:
            if saved_fd is not None:
                try:
                    os.close(saved_fd)
                except OSError:
                    pass
            if devnull is not None:
                devnull.close()
            saved_fd = None
            devnull = None
        try:
            yield
        finally:
            if saved_fd is not None:
                os.dup2(saved_fd, 1)
                os.close(saved_fd)
            if devnull is not None:
                devnull.close()


def json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if hasattr(value, "item"):
        try:
            return json_value(value.item())
        except (ValueError, TypeError):
            pass
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(v) for v in value]
    text = str(value)
    return None if text.lower() in {"nan", "nat", "none"} else text


def records(frame: Any) -> list[dict[str, Any]]:
    """Convert a pandas DataFrame to clean JSON records without importing pandas."""

    if frame is None:
        return []
    if isinstance(frame, list):
        return [json_value(row) for row in frame if isinstance(row, dict)]
    if not hasattr(frame, "to_dict"):
        return []
    try:
        rows = frame.to_dict(orient="records")
    except TypeError:
        rows = frame.to_dict("records")
    return [{str(k): json_value(v) for k, v in row.items()} for row in rows]


def compact_bar_date(value: Any) -> int | None:
    """Return the ``YYYYMMDD`` field used by the desktop K-line contract."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return int(value.strftime("%Y%m%d"))
    if hasattr(value, "strftime"):
        try:
            return int(value.strftime("%Y%m%d"))
        except (TypeError, ValueError):
            pass
    match = __import__("re").search(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", str(value))
    if not match:
        return None
    return int("".join(match.groups()))


def epoch_seconds(value: Any) -> Any:
    """Normalize a timestamp to the seconds used by the desktop field IDs."""

    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=CN)
            return int(parsed.timestamp())
        except (TypeError, ValueError, OSError):
            pass
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=CN)
        return int(value.timestamp())
    if hasattr(value, "timestamp"):
        try:
            return int(value.timestamp())
        except (TypeError, ValueError, OSError):
            pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return json_value(value)


def first_value(row: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    for key, value in row.items():
        for name in names:
            if name in str(key) and value not in (None, ""):
                return value
    return default


def market_prefix(code: str) -> str:
    code = str(code).strip().upper()
    if len(code) == 10 and code[:4] in {"USHA", "USZA", "USBJ", "USTM", "USTA"}:
        return code[:4]
    if not code.isdigit() or len(code) != 6:
        return "USHA"
    if code.startswith("6") or code.startswith("9"):
        return "USHA" if code.startswith("6") else "USTM"
    if code.startswith(("43", "87")):
        return "USTA"
    if code.startswith("8"):
        return "USTM"
    if code.startswith(("4", "9")):
        return "USBJ"
    return "USZA"


def normalize_thscode(value: str) -> str:
    text = str(value).strip().upper()
    if len(text) == 10 and text[:4] in {"USHA", "USZA", "USBJ", "USTM", "USTA"}:
        return text
    if "." in text and not text.startswith("URFI"):
        ticker, suffix = text.rsplit(".", 1)
        if ticker.isdigit() and len(ticker) == 6:
            if suffix == "SH":
                return ("USTM" if ticker.startswith("9") else "USHA") + ticker
            if suffix == "SZ":
                return "USZA" + ticker
            if suffix == "BJ":
                return "USBJ" + ticker
    if text.isdigit() and len(text) == 6:
        return market_prefix(text) + text
    return text


def cloud_thscode(value: str) -> str:
    """Convert a THS ``USxx`` code to the Fuyao ``{ticker}.{suffix}`` form."""

    text = str(value).strip().upper()
    if "." in text or text.startswith("URFI"):
        return text
    normalized = normalize_thscode(text)
    suffixes = {"USHA": "SH", "USZA": "SZ", "USBJ": "BJ", "USTM": "SH", "USTA": "SZ"}
    prefix = normalized[:4]
    suffix = suffixes.get(prefix)
    if suffix and len(normalized) == 10:
        return f"{normalized[-6:]}.{suffix}"
    return normalized


def market_name(thscode: str) -> str:
    prefix = thscode[:4].upper()
    return {"USHA": "SH", "USZA": "SZ", "USBJ": "BJ", "USTM": "SH", "USTA": "SZ"}.get(prefix, prefix)


def parse_codes(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        raw = value.replace("，", ",").split(",")
    else:
        raw = list(value)
    result: list[str] = []
    for item in raw:
        code = normalize_thscode(item)
        if code and code not in result:
            result.append(code)
    if not result:
        raise QueryError("至少需要一个证券代码", "invalid_argument")
    return result


def split_code(value: str) -> dict[str, str]:
    thscode = normalize_thscode(value)
    ticker = thscode[-6:] if len(thscode) >= 6 else thscode
    return {
        "thscode": thscode,
        "ticker": ticker,
        "market": thscode[:4],
        "exchange": market_name(thscode),
    }


def numeric(value: Any, max_abs: float | None = None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text.lower() in {"", "-", "--", "nan", "none", "null"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if abs(abs(number) - VENDOR_NULL_SENTINEL) <= 1.0:
        return None
    if max_abs is not None and abs(number) >= max_abs:
        return None
    return number


def split_vendor_code(value: Any) -> tuple[str, str]:
    text = str(value or "").strip().upper()
    if "." in text:
        ticker, suffix = text.rsplit(".", 1)
        if ticker.isdigit() and suffix in {"SH", "SZ", "BJ"}:
            return ticker, suffix
    normalized = normalize_thscode(text)
    return normalized[-6:], market_name(normalized)


def block_numbers(value: str | Iterable[str] | None) -> list[int]:
    if value is None:
        return []
    raw = value.replace("，", ",").split(",") if isinstance(value, str) else list(value)
    result: list[int] = []
    for item in raw:
        text = str(item).strip()
        if not text:
            continue
        try:
            number = int(text)
        except ValueError as exc:
            raise QueryError(f"板块 ID 必须是整数：{text}", "invalid_argument") from exc
        if number not in result:
            result.append(number)
    return result


def sort_result(
    block: str,
    sort_field: int,
    sort_order: int,
    offset: int,
    count: int,
    total: int,
    items: list[dict[str, Any]],
    missing_count: int,
    source_fields: dict[str, str],
) -> dict[str, Any]:
    return {
        "block": block,
        "block_name": CLOUD_BLOCK_NAMES.get(int(block)) if str(block).isdigit() else block,
        "sortField": int(sort_field),
        "sortOrder": int(sort_order),
        "offset": max(0, int(offset)),
        "count": len(items),
        "total": int(total),
        "missing_count": int(missing_count),
        "fields": source_fields,
        "items": items,
    }


def selfstock_path(explicit: str = "") -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.getenv("THS_SELFSTOCK_PATH"):
        candidates.append(Path(os.environ["THS_SELFSTOCK_PATH"]).expanduser())
    candidates.extend(
        [
            Path("/run/secrets/ths_selfstock.json"),
            Path.home() / ".codex" / "daily-briefing-pro" / "data" / "ths_selfstock.json",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _selfstock_items(data: Any) -> list[dict[str, str]]:
    if isinstance(data, list):
        rows = data
    else:
        container = data.get("Data") if isinstance(data.get("Data"), dict) else data.get("data", data)
        if not isinstance(container, dict):
            return []
        count = int(container.get("Count") or container.get("num") or 0)
        raw = container.get("Selfstock") or container.get("selfstock") or ""
        if not raw or count <= 0:
            return []
        parts = [part for part in str(raw).split("|") if part]
        codes = parts[:count]
        markets = [part.lstrip(",") for part in parts[count : count * 2]]
        rows = [
            {"C": code, "M": markets[index] if index < len(markets) else ""}
            for index, code in enumerate(codes)
        ]

    market_map = {"17": "SH", "33": "SZ", "48": "BJ", "20": "BJ"}
    items: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("C") or row.get("code") or "").strip()
        if not code:
            continue
        market = str(row.get("M") or row.get("market") or "")
        exchange = market_map.get(market, market)
        vendor = f"{code}.{exchange}" if exchange in {"SH", "SZ", "BJ"} else code
        security = normalize_thscode(vendor)
        duplicate = any(item["security"] == security for item in items)
        if duplicate:
            continue
        items.append(
            {
                "security": security,
                "thscode": security,
                "ticker": code[-6:],
                "vendor_thscode": vendor,
                "name": str(row.get("N") or row.get("name") or ""),
            }
        )
    return items


def watchlist_payload(explicit_path: str = "") -> dict[str, Any]:
    path = selfstock_path(explicit_path)
    if path is None:
        return {
            "sectorId": "-1",
            "name": "自选股",
            "source": "unavailable",
            "count": 0,
            "securities": [],
            "note": "未找到 THS_SELFSTOCK_PATH 或 /run/secrets/ths_selfstock.json",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QueryError(f"读取自选股文件失败：{redact(exc)}", "invalid_selfstock") from exc
    items = _selfstock_items(data)
    return {
        "sectorId": "-1",
        "name": "自选股",
        "source": str(path),
        "count": len(items),
        "securities": items,
    }


def sectors_payload(explicit_path: str = "") -> dict[str, Any]:
    watchlist = watchlist_payload(explicit_path)
    return {
        "count": 1,
        "items": [
            {
                "sectorId": "-1",
                "name": "自选股",
                "count": watchlist["count"],
                "source": watchlist["source"],
            }
        ],
    }


def field_ids(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    raw = value.replace("，", ",").split(",") if isinstance(value, str) else list(value)
    return [str(item).strip() for item in raw if str(item).strip()]


def select_push_fields(payload: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    if not fields:
        return payload
    wanted = set(fields)
    result = dict(payload)
    if isinstance(result.get("data"), dict):
        result["data"] = {
            code: ({key: value for key, value in record.items() if str(key) in wanted} if isinstance(record, dict) else record)
            for code, record in result["data"].items()
        }
    if isinstance(result.get("items"), list):
        result["items"] = [
            {key: value for key, value in item.items() if str(key) in wanted}
            if isinstance(item, dict)
            else item
            for item in result["items"]
        ]
    return result


def subscribe_payload(client: ThsClient | CloudClient, args: argparse.Namespace, source: str) -> dict[str, Any]:
    api = str(args.subscribe_api)
    target = str(args.target)
    if api == "SubscribeRealtime":
        result = client.realtime(target)
    elif api == "SubscribeIntradayCandle":
        result = client.candle(
            target,
            period=int(args.period),
            count=int(args.count),
            adjust=int(args.adjust),
        )
    elif api in {"SubscribeIntradayTrend", "SubscribeTrend"}:
        result = client.trend(target)
    elif api in {"SubscribeIntradayTick", "SubscribeTick"}:
        result = client.tick(target, count=int(args.count))
    else:
        raise QueryError(f"未知订阅接口：{api}", "invalid_argument")
    return {
        "api": api,
        "source": source,
        "mode": "one_shot",
        "timeout_ms": int(args.timeout_ms),
        "push": select_push_fields(result, field_ids(args.fields)),
    }


def security_code(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        market = str(value.get("market") or "")
        code = str(value.get("code") or value.get("ticker") or value.get("thscode") or "")
        if market and code and not code.startswith(market):
            return market + code[-6:]
        return code
    raise QueryError(f"无法解析证券参数：{value!r}", "invalid_argument")


class WencaiClient:
    """Client for the official iWencai structured-query endpoint.

    The native Lumi ``wencai_query`` tool calls
    ``https://openapi.iwencai.com/v1/query2data`` directly and passes the
    selected skill through ``X-Claw-Skill-Id``.  Keeping that contract here
    means the cloud path does not silently replace one of the 21 skills with
    the older natural-language transport.
    """

    def __init__(self, key: str, timeout: int = WENCAI_TIMEOUT_SECONDS):
        if requests is None:  # pragma: no cover - broken installs only
            raise QueryError("缺少 requests 依赖，无法调用问财 OpenAPI", "missing_dependency")
        self.key = key
        self.timeout = timeout

    def query(
        self,
        skill_id: str,
        query: str,
        page: int = 1,
        limit: int = 10,
    ) -> dict[str, Any]:
        if skill_id not in WENCAI_SKILL_IDS:
            raise QueryError(f"未知问财 skillId：{skill_id}", "invalid_skill")
        query = str(query).strip()
        if not query:
            raise QueryError("wencai_query 需要非空 query", "invalid_argument")
        page_number = max(1, int(page))
        page_size = max(1, min(int(limit), 100))
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "X-Claw-Call-Type": "normal",
            "X-Claw-Skill-Id": skill_id,
            "X-Claw-Skill-Version": "1.0.0",
            "X-Claw-Plugin-Id": "none",
            "X-Claw-Plugin-Version": "none",
            "X-Claw-Trace-Id": secrets.token_hex(32),
        }
        body = {
            "query": query,
            "page": str(page_number),
            "limit": str(page_size),
            "is_cache": "1",
            "expand_index": "true",
        }
        try:
            response = requests.post(
                WENCAI_ENDPOINT,
                headers=headers,
                json=body,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise QueryError(f"问财 OpenAPI 请求失败：{redact(exc)}", "wencai_network_error") from exc
        if response.status_code < 200 or response.status_code >= 300:
            excerpt = redact(response.text[:300])
            raise QueryError(
                f"问财 OpenAPI HTTP {response.status_code}：{excerpt}",
                "wencai_http_error",
                {"status_code": response.status_code},
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise QueryError("问财 OpenAPI 返回的不是 JSON", "wencai_invalid_response") from exc
        if not isinstance(payload, dict):
            raise QueryError("问财 OpenAPI 返回结构无效", "wencai_invalid_response")
        outer_status = payload.get("status_code", payload.get("code"))
        outer_message = payload.get("status_msg") or payload.get("message")
        inner = payload.get("data")
        if isinstance(inner, dict) and ("datas" in inner or "columns" in inner):
            payload = inner
        status_code = payload.get("status_code", payload.get("code", outer_status))
        if status_code not in (None, 0, "0"):
            message = (
                payload.get("status_msg")
                or payload.get("message")
                or outer_message
                or "问财查询失败"
            )
            raise QueryError(
                f"问财 OpenAPI 返回错误：{redact(message)}",
                "wencai_query_failed",
                {"status_code": status_code},
            )
        return json_value(payload)


def wencai_api_key() -> tuple[str | None, str | None]:
    for name in WENCAI_API_KEY_ENVS:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip(), f"env:{name}"
    return None, None


def _ma_series(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        result.append(running / period if index >= period - 1 else None)
    return result


def _ema_series(values: list[float], period: int) -> list[float | None]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    result: list[float | None] = [values[0]]
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current
        result.append(current)
    return result


def _rsi_series(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result
    gains = [max(values[index] - values[index - 1], 0.0) for index in range(1, len(values))]
    losses = [max(values[index - 1] - values[index], 0.0) for index in range(1, len(values))]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    def calculate(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        strength = gain / loss
        return 100.0 - 100.0 / (1.0 + strength)

    result[period] = calculate(average_gain, average_loss)
    for index in range(period + 1, len(values)):
        average_gain = (average_gain * (period - 1) + gains[index - 1]) / period
        average_loss = (average_loss * (period - 1) + losses[index - 1]) / period
        result[index] = calculate(average_gain, average_loss)
    return result


def _kdj_series(
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> list[dict[str, float | None] | None]:
    result: list[dict[str, float | None] | None] = [None] * len(closes)
    k_value = 50.0
    d_value = 50.0
    for index in range(8, len(closes)):
        highest = max(highs[index - 8 : index + 1])
        lowest = min(lows[index - 8 : index + 1])
        rsv = 50.0 if highest == lowest else (closes[index] - lowest) / (highest - lowest) * 100.0
        k_value = (2.0 * k_value + rsv) / 3.0
        d_value = (2.0 * d_value + k_value) / 3.0
        result[index] = {
            "k": k_value,
            "d": d_value,
            "j": 3.0 * k_value - 2.0 * d_value,
        }
    return result


def _boll_series(
    values: list[float],
    period: int = 20,
    width: float = 2.0,
) -> list[dict[str, float | None] | None]:
    result: list[dict[str, float | None] | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        middle = sum(window) / period
        variance = sum((value - middle) ** 2 for value in window) / period
        deviation = math.sqrt(max(variance, 0.0))
        result[index] = {
            "middle": middle,
            "upper": middle + width * deviation,
            "lower": middle - width * deviation,
        }
    return result


def _atr_series(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:
    result: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return result
    true_ranges = [highs[0] - lows[0]]
    for index in range(1, len(closes)):
        true_ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )
    atr = sum(true_ranges[1 : period + 1]) / period
    result[period] = atr
    for index in range(period + 1, len(closes)):
        atr = (atr * (period - 1) + true_ranges[index]) / period
        result[index] = atr
    return result


def build_indicator_values(
    bars: list[dict[str, Any]],
    indicators: list[str],
) -> dict[str, list[Any]]:
    """Calculate the standard indicators requested by the portable contract."""

    closes = [float(bar["close"]) for bar in bars]
    highs = [float(bar["high"]) for bar in bars]
    lows = [float(bar["low"]) for bar in bars]
    volumes = [float(bar.get("volume") or 0.0) for bar in bars]
    calculated: dict[str, list[Any]] = {}
    for name in indicators:
        if name.startswith("MA") and name[2:].isdigit():
            calculated[name] = _ma_series(closes, int(name[2:]))
        elif name.startswith("EMA") and name[3:].isdigit():
            calculated[name] = _ema_series(closes, int(name[3:]))
        elif name == "MACD":
            ema12 = _ema_series(closes, 12)
            ema26 = _ema_series(closes, 26)
            dif = [
                (ema12[index] - ema26[index])
                if ema12[index] is not None and ema26[index] is not None
                else None
                for index in range(len(closes))
            ]
            dea = _ema_series([value or 0.0 for value in dif], 9)
            calculated[name] = [
                {
                    "dif": dif[index],
                    "dea": dea[index],
                    "hist": (
                        2.0 * (dif[index] - dea[index])
                        if dif[index] is not None and dea[index] is not None
                        else None
                    ),
                }
                for index in range(len(closes))
            ]
        elif name.startswith("RSI") and name[3:].isdigit():
            calculated[name] = _rsi_series(closes, int(name[3:]))
        elif name == "KDJ":
            calculated[name] = _kdj_series(highs, lows, closes)
        elif name == "BOLL":
            calculated[name] = _boll_series(closes)
        elif name == "ATR14":
            calculated[name] = _atr_series(highs, lows, closes)
        elif name == "OBV":
            obv = 0.0
            series: list[float] = []
            for index, close in enumerate(closes):
                if index:
                    if close > closes[index - 1]:
                        obv += volumes[index]
                    elif close < closes[index - 1]:
                        obv -= volumes[index]
                series.append(obv)
            calculated[name] = series
        elif name.startswith("VOL_MA") and name[6:].isdigit():
            calculated[name] = _ma_series(volumes, int(name[6:]))
        elif name == "量比":
            series: list[float | None] = [None] * len(volumes)
            for index in range(5, len(volumes)):
                baseline = sum(volumes[index - 5 : index]) / 5.0
                series[index] = volumes[index] / baseline if baseline else None
            calculated[name] = series
        elif name == "振幅":
            series: list[float | None] = [None] * len(closes)
            for index in range(1, len(closes)):
                if closes[index - 1]:
                    series[index] = (highs[index] - lows[index]) / closes[index - 1] * 100.0
            calculated[name] = series
        else:
            raise QueryError(f"不支持的技术指标：{name}", "unsupported_indicator")
    return calculated


def indicator_payload(client: ThsClient | CloudClient, request: dict[str, Any]) -> dict[str, Any]:
    securities = request.get("securities")
    if not isinstance(securities, list) or not securities:
        raise QueryError("indicator_query 需要非空 securities", "invalid_argument")
    if len(securities) > 50:
        raise QueryError("indicator_query 最多支持 50 个证券", "invalid_argument")
    indicators = request.get("indicators")
    if not isinstance(indicators, list) or not indicators:
        raise QueryError("indicator_query 需要非空 indicators", "invalid_argument")
    if len(indicators) > 20:
        raise QueryError("indicator_query 最多支持 20 个指标", "invalid_argument")
    indicators = [str(name) for name in indicators]
    unknown = [name for name in indicators if name not in INDICATOR_NAMES]
    if unknown:
        raise QueryError(f"不支持的技术指标：{', '.join(unknown)}", "unsupported_indicator")
    period_name = str(request.get("period") or "day")
    if period_name not in INDICATOR_PERIODS:
        raise QueryError(f"不支持的周期：{period_name}", "unsupported_period")
    period = INDICATOR_PERIODS[period_name]
    adjust_name = str(request.get("adjust") or "forward")
    if adjust_name not in ADJUST_TYPES:
        raise QueryError(f"不支持的复权方式：{adjust_name}", "invalid_argument")
    adjust = ADJUST_TYPES[adjust_name]
    mode = str(request.get("mode") or "latest")
    if mode not in {"latest", "series"}:
        raise QueryError(f"不支持的输出模式：{mode}", "invalid_argument")
    output_bars = 1 if mode == "latest" else max(1, min(int(request.get("bars") or 1), 250))
    if isinstance(client, CloudClient) and period != 5:
        raise QueryError("扶摇公开 REST 只提供日 K；该周期请使用 --mode ths", "unsupported_period")

    data: dict[str, Any] = {}
    history: dict[str, Any] = {}
    for security in securities:
        thscode = normalize_thscode(security_code(security))
        candle_payload = client.candle(thscode, period=period, count=750, adjust=adjust)
        candle_rows = (candle_payload.get("data") or {}).get(thscode) or []
        parsed: list[dict[str, Any]] = []
        for row in candle_rows:
            close = numeric(row.get("11"))
            high = numeric(row.get("8"))
            low = numeric(row.get("9"))
            timestamp = epoch_seconds(row.get("time"))
            if not isinstance(timestamp, int):
                compact = row.get("1")
                if isinstance(compact, int) and 19000101 <= compact <= 29991231:
                    timestamp = int(
                        datetime.strptime(str(compact), "%Y%m%d")
                        .replace(tzinfo=CN)
                        .timestamp()
                    )
                else:
                    timestamp = epoch_seconds(compact)
            if close is None or high is None or low is None or not isinstance(timestamp, int):
                continue
            parsed.append(
                {
                    "date": timestamp,
                    "close": close,
                    "high": high,
                    "low": low,
                    "volume": numeric(row.get("13")),
                }
            )
        if not parsed:
            raise QueryError(f"{thscode} 没有可用的 K 线数据", "insufficient_history")
        values_by_indicator = build_indicator_values(parsed, indicators)
        start = max(0, len(parsed) - output_bars)
        records = [
            {
                "time": parsed[index]["date"],
                "values": {
                    name: values_by_indicator[name][index]
                    for name in indicators
                },
            }
            for index in range(start, len(parsed))
        ]
        data[thscode] = records if mode == "series" else records[-1]
        history[thscode] = {
            "requestedBars": 750,
            "actualBars": len(parsed),
            "startTime": parsed[0]["date"],
            "endTime": parsed[-1]["date"],
            "warmupBars": max(0, len(parsed) - len(records)),
            "requiredWarmupBars": 500,
            "status": "warmed_up" if len(parsed) >= 500 else "insufficient_history",
            **({"obvBasis": "window_relative"} if "OBV" in indicators else {}),
        }
    return {
        "success": True,
        "mode": mode,
        "period": period_name,
        "indicators": indicators,
        "bars": output_bars,
        "data": data,
        "history": history,
        "calculationBasis": "finite_history_replay",
    }


def wencai_query_payload(
    request: dict[str, Any],
    mode: str,
    client: ThsClient | None = None,
) -> dict[str, Any]:
    skill_id = str(request.get("skillId") or "hithink-market-query").strip()
    if skill_id not in WENCAI_SKILL_IDS:
        raise QueryError(f"未知问财 skillId：{skill_id}", "invalid_skill")
    query = str(request.get("query") or "").strip()
    if not query:
        raise QueryError("wencai_query 需要非空 query", "invalid_argument")
    page = max(1, int(request.get("page") or 1))
    limit = max(1, min(int(request.get("limit") or 10), 100))
    key, _ = wencai_api_key()
    if mode != "ths" and key:
        result = WencaiClient(key).query(skill_id, query, page=page, limit=limit)
        return {"tool": "wencai_query", "source": "wencai", "result": result}
    if mode == "cloud":
        raise QueryError(
            "cloud 模式需要 IWENCAI_API_KEY；它是问财 OpenAPI 凭据，不能用扶摇行情 Key 冒充",
            "missing_api_key",
        )
    if skill_id not in WENCAI_FALLBACK_SKILLS:
        raise QueryError(
            f"skillId={skill_id} 需要 IWENCAI_API_KEY；thsdk 的 wencai_nlp 只能作为市场问句降级通道",
            "missing_api_key",
        )
    if client is None:
        with ThsClient() as ths_client:
            result = ths_client.wencai(query, page=page, limit=limit)
    else:
        result = client.wencai(query, page=page, limit=limit)
    return {"tool": "wencai_query", "source": "ths", "result": result}


def call_payload(
    client: ThsClient | CloudClient,
    args: argparse.Namespace,
    source: str,
    mode: str | None = None,
) -> dict[str, Any]:
    tool = str(args.tool)
    request = getattr(args, "call_args", {})
    if not isinstance(request, dict):
        raise QueryError("call 参数必须是 JSON 对象", "invalid_argument")
    result: dict[str, Any]
    if tool == "search_securities":
        keyword = request.get("keyword") or request.get("keywords") or ""
        if isinstance(keyword, list):
            keyword = keyword[0] if keyword else ""
        result = client.search(str(keyword), limit=int(request.get("limit") or 20))
    elif tool == "search_blocks":
        result = client.blocks(str(request.get("keyword") or ""), limit=int(request.get("limit") or 50))
    elif tool == "realtime_query":
        values = request.get("securities") or request.get("codes") or request.get("securities_codes") or []
        if isinstance(values, str):
            codes = values
        else:
            codes = [security_code(value) for value in values]
        result = client.realtime(codes)
    elif tool == "candle_query":
        value = request.get("security") or request.get("code") or ""
        result = client.candle(
            security_code(value),
            period=int(request.get("period") or 5),
            count=int(request.get("count") or 60),
            adjust=int(request.get("adjustType") or request.get("adjust") or 1),
        )
    elif tool == "sort_query":
        result = client.sort(
            str(request.get("block") or 14),
            int(request.get("sortField") or 199112),
            int(request.get("sortOrder") if request.get("sortOrder") is not None else 1),
            int(request.get("offset") or 0),
            int(request.get("count") or 60),
            request.get("excludeBlocks") or "",
        )
    elif tool == "trend_query":
        result = client.trend(security_code(request.get("security") or request.get("code") or ""))
    elif tool == "tick_query":
        result = client.tick(
            security_code(request.get("security") or request.get("code") or ""),
            count=int(request.get("count") or 20),
        )
    elif tool == "indicator_query":
        result = indicator_payload(client, request)
    elif tool == "wencai_query":
        effective_mode = mode or ("ths" if source == "ths" else "cloud")
        return wencai_query_payload(
            request,
            effective_mode,
            client if isinstance(client, ThsClient) else None,
        )
    else:
        raise QueryError(f"call 不支持只读工具：{tool}", "unsupported_tool")
    return {"tool": tool, "source": source, "result": result}


def cloud_api_key() -> tuple[str | None, str | None]:
    for name in API_KEY_ENVS:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip(), f"env:{name}"
    return None, None


def writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".market-query-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


class CloudClient:
    """Small, auditable Fuyao REST client.

    The response contract is ``{code, message, data, request_id}``.  HTTP 200
    can still be a business failure, so callers must inspect ``code``.
    """

    def __init__(self, base_url: str = BASE_URL, key: str | None = None, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.key = key or cloud_api_key()[0]
        self.timeout = timeout
        self._ticker_names: dict[str, str] | None = None
        if not self.key:
            raise QueryError(
                "未配置扶摇 API Key；请设置 FUYAO_API_KEY、HITHINK_API_KEY 或 HITHINK_FINANCE_API_KEY",
                "missing_api_key",
            )
        if requests is None:
            raise QueryError("缺少 requests 依赖，请先安装 requirements-cloud.txt", "missing_dependency")

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not path.startswith("/api/"):
            raise QueryError("只允许 /api/ 路径", "invalid_path")
        if any(token in path for token in ("\n", "\r", "#")):
            raise QueryError("路径不能包含换行或片段", "invalid_path")
        if "/dump/" in path and path.rstrip("/").endswith("/download-url"):
            raise QueryError("短时签名下载链接已被主动阻止", "blocked_endpoint")
        url = self.base_url + path
        clean_params = {
            key: (",".join(str(v) for v in val) if isinstance(val, (list, tuple)) else val)
            for key, val in (params or {}).items()
            if val is not None
        }
        headers = {
            "X-api-key": self.key,
            "Accept": "application/json",
            "User-Agent": "codex-market-query/cloud-python",
        }
        last_error = ""
        for attempt in range(1, 4):
            try:
                response = requests.get(
                    url,
                    params=clean_params,
                    headers=headers,
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except Exception as exc:  # requests exceptions vary by version
                last_error = redact(exc)
                if attempt < 3:
                    time.sleep(0.3 * attempt)
                    continue
                raise QueryError(f"云端请求失败：{last_error}", "network_error") from exc

            status = int(response.status_code)
            if status in (301, 302, 303, 307, 308):
                raise QueryError("云端接口返回重定向，已阻止凭证转发", "redirect_blocked")
            if status == 429 and attempt < 3:
                time.sleep(attempt)
                continue
            if status >= 500 and attempt < 3:
                time.sleep(0.4 * attempt)
                continue
            if status in (401, 403):
                raise QueryError(f"云端鉴权失败（HTTP {status}）", "auth_failed")
            if status >= 400:
                raise QueryError(f"云端接口返回 HTTP {status}", "http_error")
            try:
                body = response.json()
            except ValueError as exc:
                raise QueryError(f"云端接口返回非 JSON（HTTP {status}）", "invalid_response") from exc
            if not isinstance(body, dict):
                raise QueryError("云端接口返回结构不是对象", "invalid_response")
            code = body.get("code", 0)
            if code not in (0, "0", None):
                message = redact(body.get("message") or "unknown")
                raise QueryError(f"云端业务错误 code={code}: {message}", "business_error")
            return body
        raise QueryError(f"云端请求重试耗尽：{last_error}", "network_error")

    # ---- typed helpers -------------------------------------------------

    def search(self, keyword: str, asset_type: str | None = None, limit: int = 20) -> dict[str, Any]:
        params: dict[str, Any] = {"q": keyword, "limit": max(1, min(int(limit), 50))}
        if asset_type:
            params["asset_type"] = asset_type
        body = self.get("/api/meta/tickers/search", params)
        data = body.get("data") or {}
        items = []
        for row in data.get("item") or []:
            vendor_code = str(row.get("thscode") or "")
            canonical = normalize_thscode(vendor_code)
            items.append(
                {
                    "name": row.get("name"),
                    "thscode": canonical,
                    "vendor_thscode": vendor_code,
                    "ticker": row.get("ticker"),
                    "exchange": row.get("exchange"),
                    "asset_type": row.get("asset_type"),
                    "market": "THS" if asset_type == "a-share-index" else market_name(canonical),
                    "raw": row,
                }
            )
        return {"timestamp": data.get("timestamp"), "items": items, "request_id": body.get("request_id")}

    def ticker_names(self) -> dict[str, str]:
        if self._ticker_names is not None:
            return self._ticker_names
        body = self.get(
            "/api/meta/tickers/list",
            {"asset_type": "a-share", "limit": 10000, "offset": 0},
        )
        data = body.get("data") or {}
        names: dict[str, str] = {}
        for row in data.get("item") or []:
            vendor_code = str(row.get("thscode") or "").upper()
            name = str(row.get("name") or "")
            if vendor_code:
                names[vendor_code] = name
        self._ticker_names = names
        return names

    def _snapshot_rows(self) -> tuple[list[dict[str, Any]], Any]:
        rows: list[dict[str, Any]] = []
        timestamp = None
        offset = 0
        while True:
            body = self.get(
                "/api/a-share/prices/snapshot",
                {"limit": 10000, "offset": offset},
            )
            data = body.get("data") or {}
            timestamp = data.get("timestamp", timestamp)
            chunk = [row for row in data.get("item") or [] if isinstance(row, dict)]
            rows.extend(chunk)
            total = int(data.get("total") or len(rows))
            if not chunk or len(rows) >= total:
                break
            offset = len(rows)
        return rows, timestamp

    def sort(
        self,
        block: str,
        sort_field: int = 199112,
        sort_order: int = 1,
        offset: int = 0,
        count: int = 60,
        exclude_blocks: str = "",
    ) -> dict[str, Any]:
        field_key = str(int(sort_field))
        if field_key not in SORT_FIELDS:
            raise QueryError(
                f"云端排行不支持按 FieldID {sort_field} 排序",
                "unsupported_sort_field",
            )
        if int(sort_order) not in (0, 1):
            raise QueryError("sortOrder 只能是 0（升序）或 1（降序）", "invalid_argument")

        block_text = str(block).strip()
        sector_members: set[str] | None = None
        block_id: int | None = None
        if block_text.isdigit():
            block_id = int(block_text)
            if block_id not in CLOUD_BLOCK_NAMES:
                raise QueryError(
                    f"扶摇纯 REST 模式只支持市场板块 {sorted(CLOUD_BLOCK_NAMES)}；"
                    "其余板块请使用 auto/ths 模式，或传 --block 881273.TI 形式的指数代码",
                    "unsupported_cloud_block",
                )
        elif block_text.upper().endswith(".TI") or block_text.upper().startswith("URFI"):
            sector_data = self.sector(block_text)
            sector_members = {
                normalize_thscode(str(item.get("thscode") or ""))
                for item in sector_data.get("members") or []
                if item.get("thscode")
            }
        else:
            sector_data = self.sector(block_text)
            sector_members = {
                normalize_thscode(str(item.get("thscode") or ""))
                for item in sector_data.get("members") or []
                if item.get("thscode")
            }

        excluded: set[str] = set()
        for excluded_block in block_numbers(exclude_blocks):
            if excluded_block not in CLOUD_BLOCK_NAMES:
                raise QueryError(
                    f"扶摇纯 REST 模式不支持排除板块 {excluded_block}",
                    "unsupported_cloud_block",
                )
            excluded.add(str(excluded_block))

        rows, timestamp = self._snapshot_rows()
        names = self.ticker_names()
        metric_name, _ = SORT_FIELDS[field_key]
        ranked: list[dict[str, Any]] = []
        missing_count = 0
        for row in rows:
            ticker, suffix = split_vendor_code(row.get("thscode"))
            if sector_members is not None:
                security = normalize_thscode(str(row.get("thscode") or ""))
                if security not in sector_members:
                    continue
            elif block_id == 14 and suffix not in {"SH", "SZ"}:
                continue
            elif block_id == 21 and suffix != "SH":
                continue
            elif block_id == 27 and suffix != "SZ":
                continue
            elif block_id == 50854 and suffix not in {"SH", "SZ", "BJ"}:
                continue
            if "14" in excluded and suffix in {"SH", "SZ"}:
                continue
            if "21" in excluded and suffix == "SH":
                continue
            if "27" in excluded and suffix == "SZ":
                continue
            if "50854" in excluded:
                continue

            fields: dict[str, Any] = {}
            for current_field, (current_name, _) in SORT_FIELDS.items():
                value = row.get(current_name)
                if current_field == "6" and value is None:
                    value = row.get("prev_price", row.get("prev_close"))
                if current_field == "264648" and value is None:
                    last = numeric(row.get("last_price"), max_abs=VENDOR_PRICE_SENTINEL)
                    previous = numeric(
                        row.get("prev_price", row.get("prev_close")),
                        max_abs=VENDOR_PRICE_SENTINEL,
                    )
                    value = None if last is None or previous is None else last - previous
                if current_field in {"199112", "264648", "10", "6", "7", "8", "9"}:
                    value = numeric(value, max_abs=VENDOR_PRICE_SENTINEL)
                else:
                    value = numeric(value)
                fields[current_field] = value
            value = numeric(
                fields.get(field_key),
                max_abs=VENDOR_PRICE_SENTINEL
                if field_key in {"199112", "264648", "10", "6", "7", "8", "9"}
                else None,
            )
            if value is None:
                missing_count += 1
                continue
            vendor_code = str(row.get("thscode") or "")
            security = normalize_thscode(vendor_code)
            ranked.append(
                {
                    "security": security,
                    "thscode": security,
                    "vendor_thscode": vendor_code,
                    "ticker": ticker,
                    "name": names.get(vendor_code, row.get("name") or ""),
                    "value": value,
                    "fields": fields,
                }
            )

        reverse = int(sort_order) == 1
        ranked.sort(key=lambda item: item["security"])
        ranked.sort(key=lambda item: item["value"], reverse=reverse)
        total = len(ranked)
        start = max(0, int(offset))
        end = start + max(1, int(count))
        items = []
        for index, item in enumerate(ranked[start:end], start=start + 1):
            item = dict(item)
            item["rank"] = index
            items.append(item)
        return sort_result(
            block_text,
            sort_field,
            sort_order,
            start,
            count,
            total,
            items,
            missing_count,
            {key: value[0] for key, value in SORT_FIELDS.items()},
        ) | {"timestamp": timestamp}

    def realtime(self, codes: Iterable[str]) -> dict[str, Any]:
        values = parse_codes(codes)
        vendor_codes = [cloud_thscode(code) for code in values]
        body = self.get("/api/a-share/prices/snapshot", {"thscodes": ",".join(vendor_codes)})
        data = body.get("data") or {}
        rows = {str(row.get("thscode")): row for row in data.get("item") or []}
        out: dict[str, Any] = {}
        for code in values:
            vendor_code = cloud_thscode(code)
            row = rows.get(vendor_code)
            if not row:
                continue
            record = {field: row.get(name) for field, name in REALTIME_FIELD_MAP.items() if name in row}
            record.update(
                {
                    "name": row.get("name", ""),
                    "thscode": normalize_thscode(code),
                    "vendor_thscode": vendor_code,
                    "ticker": row.get("ticker", code[-6:]),
                    "last_price": row.get("last_price"),
                    "prev_close": row.get("prev_price"),
                    "open_price": row.get("open_price"),
                    "high_price": row.get("high_price"),
                    "low_price": row.get("low_price"),
                    "price_change": row.get("price_change"),
                    "price_change_ratio_pct": row.get("price_change_ratio_pct"),
                    "volume": row.get("volume"),
                    "turnover": row.get("turnover"),
                    "raw": row,
                }
            )
            record.update(
                {
                    "5": row.get("thscode") or vendor_code,
                    "6": row.get("prev_price", row.get("prev_close")),
                    "7": row.get("open_price"),
                    "8": row.get("high_price"),
                    "9": row.get("low_price"),
                    "10": row.get("last_price"),
                    "13": row.get("volume"),
                    "19": row.get("turnover"),
                    "55": row.get("name", ""),
                    "199112": row.get("price_change_ratio_pct"),
                    "264648": row.get("price_change"),
                }
            )
            out[code[:4] + code[-6:]] = record
        if not out:
            raise QueryError("云端快照没有返回匹配的证券", "not_found")
        for record in out.values():
            if record.get("name"):
                continue
            try:
                matches = self.search(str(record["ticker"]), limit=10).get("items") or []
            except QueryError:
                continue
            for match in matches:
                if (
                    match.get("vendor_thscode") == record["vendor_thscode"]
                    or match.get("ticker") == record["ticker"]
                ):
                    record["name"] = str(match.get("name") or "")
                    record["55"] = record["name"]
                    break
        return {
            "timestamp": data.get("timestamp"),
            "securities": [split_code(code) for code in values],
            "data": out,
            "request_id": body.get("request_id"),
        }

    def candle(
        self,
        code: str,
        period: int = 5,
        count: int = 60,
        adjust: int = 1,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> dict[str, Any]:
        if period != 5:
            raise QueryError("扶摇云端目前只支持日 K（Period=5）", "unsupported_period")
        values = parse_codes([code])
        if len(values) != 1:
            raise QueryError("K 线一次只接受一个证券", "invalid_argument")
        thscode = values[0]
        vendor_code = cloud_thscode(thscode)
        if start_ms is None or end_ms is None:
            end_ms = int(time.time() * 1000)
            days = min(3650, max(14, int(math.ceil(max(count, 1) * 2.2))))
            start_ms = end_ms - days * 86400000
        if start_ms > end_ms:
            raise QueryError("开始时间不能晚于结束时间", "invalid_argument")
        adjust_name = ADJUST_NAMES.get(int(adjust), "forward")
        body = self.get(
            "/api/a-share/prices/historical",
            {
                "thscode": vendor_code,
                "interval": "1d",
                "start": int(start_ms),
                "end": int(end_ms),
                "adjust": adjust_name or "none",
            },
        )
        data = body.get("data") or {}
        items = sorted(data.get("item") or [], key=lambda row: int(row.get("date_ms") or 0))
        bars = []
        for row in items[-max(count, 1) :]:
            date_ms = int(row.get("date_ms") or 0)
            if not date_ms:
                continue
            date = datetime.fromtimestamp(date_ms / 1000, CN)
            bars.append(
                {
                    "1": int(date.strftime("%Y%m%d")),
                    "7": row.get("open_price"),
                    "8": row.get("high_price"),
                    "9": row.get("low_price"),
                    "11": row.get("close_price"),
                    "13": row.get("volume"),
                    "19": row.get("turnover"),
                    "time": int(date.timestamp()),
                    "date_ms": date_ms,
                }
            )
        return {
            "timestamp": data.get("timestamp"),
            "securities": [split_code(thscode)],
            "vendor_thscode": vendor_code,
            "period": 5,
            "adjustType": int(adjust),
            "data": {thscode[:4] + thscode[-6:]: bars},
            "request_id": body.get("request_id"),
        }

    def sector(self, target: str) -> dict[str, Any]:
        text = str(target).strip()
        if text.upper().startswith("URFI") and len(text) >= 10:
            sector = {
                "name": text.upper(),
                "thscode": text.upper(),
                "ticker": text.upper()[4:],
                "exchange": "THS",
                "asset_type": "a-share-index",
            }
        elif text.upper().endswith(".TI"):
            code = text.upper()
            name = code
            try:
                matches = self.search(code, asset_type="a-share-index", limit=10).get("items") or []
                match = next(
                    (
                        item
                        for item in matches
                        if str(item.get("vendor_thscode") or item.get("thscode") or "").upper() == code
                    ),
                    None,
                )
                if match and match.get("name"):
                    name = str(match["name"])
            except QueryError:
                pass
            sector = {
                "name": name,
                "thscode": code,
                "ticker": code.split(".")[0],
                "exchange": "TI",
                "asset_type": "a-share-index",
            }
        else:
            search = self.search(text, asset_type="a-share-index", limit=5)
            if not search["items"]:
                raise QueryError(f"云端没有找到行业/板块：{text}", "not_found")
            hit = search["items"][0]
            sector = {
                "name": hit.get("name"),
                "thscode": hit.get("vendor_thscode") or hit.get("thscode"),
                "ticker": hit.get("ticker"),
                "exchange": hit.get("exchange"),
                "asset_type": hit.get("asset_type"),
            }
        thscode = str(sector["thscode"])
        lookup = thscode
        if thscode.upper().startswith("URFI"):
            lookup = thscode[4:] + ".TI"
        body = self.get("/api/a-share-index/constituents/ths-stock-list", {"thscode": lookup})
        data = body.get("data") or {}
        snapshot: dict[str, Any] = {}
        snapshot_error = ""
        try:
            snapshot_body = self.get(
                "/api/a-share-index/prices/snapshot",
                {"thscodes": lookup},
            )
            snapshot_data = snapshot_body.get("data") or {}
            snapshot_row = next(
                (
                    row
                    for row in (snapshot_data.get("item") or [])
                    if isinstance(row, dict)
                    and str(row.get("thscode") or "").upper() == lookup.upper()
                ),
                None,
            )
            if snapshot_row:
                ticker = str(sector.get("ticker") or lookup.split(".")[0])
                vendor = str(snapshot_row.get("thscode") or lookup)
                snapshot = {
                    "代码": f"URFI{ticker}" if vendor.upper().endswith(".TI") else vendor,
                    "名称": sector.get("name") or vendor,
                    "成交量": snapshot_row.get("volume"),
                    "总金额": snapshot_row.get("turnover"),
                    "最新价": snapshot_row.get("last_price"),
                    "涨跌": snapshot_row.get("price_change"),
                    "涨幅": snapshot_row.get("price_change_ratio_pct"),
                    "开盘价": snapshot_row.get("open_price"),
                    "最高价": snapshot_row.get("high_price"),
                    "最低价": snapshot_row.get("low_price"),
                    "昨收": snapshot_row.get("prev_price"),
                    "raw": snapshot_row,
                }
            else:
                snapshot_error = "云端指数快照没有返回该板块"
        except QueryError as exc:
            snapshot_error = str(exc)
        return {
            "timestamp": data.get("timestamp"),
            "sector": sector,
            "members": data.get("item") or [],
            "snapshot": snapshot,
            "snapshot_error": snapshot_error,
            "request_id": body.get("request_id"),
        }

    def news(self, code: str, count: int = 20) -> dict[str, Any]:
        values = parse_codes([code])
        if len(values) != 1:
            raise QueryError("新闻查询一次只接受一个证券", "invalid_argument")
        thscode = values[0]
        vendor_code = cloud_thscode(thscode)
        body = self.get(
            "/api/news/stock/timeline-list",
            {"thscode": vendor_code, "offset": "first", "size": max(1, min(int(count), 100))},
        )
        data = body.get("data") or {}
        items = [json_value(row) for row in data.get("items") or [] if isinstance(row, dict)][
            : max(1, int(count))
        ]
        for item in items:
            item["_category"] = "新闻"
        columns: list[str] = []
        for item in items:
            for key in item:
                if key not in columns:
                    columns.append(key)
        return {
            "thscode": thscode,
            "vendor_thscode": vendor_code,
            "items": items,
            "columns": columns,
            "has_more": data.get("has_more"),
            "offset": data.get("offset"),
            "request_id": body.get("request_id"),
        }

    def generic(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.get(path, params)


class ThsClient:
    """Thin wrapper around the cross-platform ``thsdk`` transport."""

    def __init__(self):
        self._ths = None
        self._module = None
        self.mode = "guest"
        self._stdout_guard = None

    def __enter__(self) -> "ThsClient":
        try:
            import thsdk  # type: ignore
        except ImportError as exc:
            raise QueryError("未安装 thsdk；请安装 requirements.txt", "missing_dependency") from exc
        self._module = thsdk
        self.mode = "account" if (os.getenv("THS_USERNAME") and os.getenv("THS_PASSWORD")) else "guest"
        # Some thsdk releases print batch-query diagnostics directly to stdout.
        # Keep stdout reserved for the CLI's JSON contract.
        self._stdout_guard = suppress_native_stdout()
        self._stdout_guard.__enter__()
        try:
            self._ths = thsdk.THS()
            self._ths.connect()
        except Exception as exc:
            self._stdout_guard.__exit__(None, None, None)
            self._stdout_guard = None
            raise QueryError(f"连接同花顺行情服务失败：{redact(exc)}", "ths_connect_failed") from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._ths is not None:
            try:
                self._ths.disconnect()
            except Exception:
                pass
        if self._stdout_guard is not None:
            self._stdout_guard.__exit__(exc_type, exc, tb)
            self._stdout_guard = None

    @property
    def ths(self):
        if self._ths is None:
            raise QueryError("同花顺客户端尚未连接", "ths_not_connected")
        return self._ths

    def search(self, keyword: str, limit: int = 20) -> dict[str, Any]:
        response = self.ths.search_symbols(keyword)
        if response.error:
            raise QueryError(f"同花顺证券检索失败：{response.error}", "ths_query_failed")
        rows = records(response.df)
        items = []
        for row in rows[: max(1, int(limit))]:
            thscode = str(first_value(row, "THSCODE", "thscode", "代码", default="")).upper()
            name = first_value(row, "Name", "name", "名称", default="")
            ticker = first_value(row, "Code", "code", "代码", default=thscode[-6:])
            items.append(
                {
                    "thscode": thscode,
                    "ticker": str(ticker),
                    "name": name,
                    "market": thscode[:4],
                    "market_display": first_value(row, "MarketDisplay", "市场", default=""),
                    "raw": row,
                }
            )
        return {"count": len(rows), "items": items}

    def realtime(self, codes: Iterable[str]) -> dict[str, Any]:
        values = parse_codes(codes)
        groups: dict[str, list[str]] = {}
        for code in values:
            groups.setdefault(code[:4], []).append(code)
        output: dict[str, Any] = {}
        raw_rows: list[dict[str, Any]] = []
        for group in groups.values():
            response = self.ths.market_data_cn(group if len(group) > 1 else group[0], "汇总")
            if response.error:
                raise QueryError(f"同花顺实时行情失败：{response.error}", "ths_query_failed")
            for row in records(response.df):
                raw_rows.append(row)
        for code in values:
            row = next(
                (
                    item
                    for item in raw_rows
                    if str(first_value(item, "THSCODE", "thscode", "代码", default="")).upper() == code
                ),
                None,
            )
            if row is None and len(values) == 1:
                row = raw_rows[0] if raw_rows else None
            if row is None:
                continue
            record: dict[str, Any] = {}
            for field, canonical in REALTIME_FIELD_MAP.items():
                value = first_value(row, *[k for k, v in REALTIME_CHINESE_ALIASES.items() if v == canonical], default=None)
                if value is not None:
                    record[field] = value
            record.update(
                {
                    "thscode": code,
                    "ticker": code[-6:],
                    "name": first_value(row, "名称", "Name", default=""),
                    "last_price": numeric(first_value(row, "最新价", "价格", default=None)),
                    "prev_close": numeric(first_value(row, "昨收价", "昨收", default=None)),
                    "open_price": numeric(first_value(row, "开盘价", default=None)),
                    "high_price": numeric(first_value(row, "最高价", default=None)),
                    "low_price": numeric(first_value(row, "最低价", default=None)),
                    "price_change": numeric(first_value(row, "涨跌", default=None)),
                    "price_change_ratio_pct": numeric(first_value(row, "涨幅", default=None)),
                    "volume": numeric(first_value(row, "成交量", default=None)),
                    "turnover": numeric(first_value(row, "总金额", "成交额", default=None)),
                    "raw": row,
                }
            )
            record.update(
                {
                    "5": code,
                    "6": record.get("prev_close"),
                    "7": record.get("open_price"),
                    "8": record.get("high_price"),
                    "9": record.get("low_price"),
                    "10": record.get("last_price"),
                    "13": record.get("volume"),
                    "19": record.get("turnover"),
                    "55": record.get("name", ""),
                    "199112": record.get("price_change_ratio_pct"),
                    "264648": record.get("price_change"),
                }
            )
            output[code[:4] + code[-6:]] = record
        if not output:
            raise QueryError("同花顺实时行情没有返回记录", "not_found")
        return {"securities": [split_code(code) for code in values], "data": output}

    def candle(
        self,
        code: str,
        period: int = 5,
        count: int = 60,
        adjust: int = 1,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> dict[str, Any]:
        interval = PERIODS.get(int(period))
        if not interval:
            raise QueryError(f"不支持的 K 线周期：{period}", "unsupported_period")
        values = parse_codes([code])
        thscode = values[0]
        adjust_name = ADJUST_NAMES.get(int(adjust), "forward")
        kwargs: dict[str, Any] = {"interval": interval, "adjust": adjust_name}
        if start_ms is not None and end_ms is not None:
            kwargs["start_time"] = datetime.fromtimestamp(start_ms / 1000, CN)
            kwargs["end_time"] = datetime.fromtimestamp(end_ms / 1000, CN)
        else:
            kwargs["count"] = max(1, int(count))
        response = self.ths.klines(thscode, **kwargs)
        if response.error:
            raise QueryError(f"同花顺 K 线查询失败：{response.error}", "ths_query_failed")
        rows = records(response.df)[-max(1, int(count)) :]
        bars = []
        for row in rows:
            date_value = first_value(row, "时间", "日期", "date", default=None)
            bars.append(
                {
                    "1": compact_bar_date(date_value),
                    "7": first_value(row, "开盘价", "开盘", "open", default=None),
                    "8": first_value(row, "最高价", "最高", "high", default=None),
                    "9": first_value(row, "最低价", "最低", "low", default=None),
                    "11": first_value(row, "收盘价", "收盘", "close", default=None),
                    "13": first_value(row, "成交量", "volume", default=None),
                    "19": first_value(row, "成交额", "总金额", "amount", default=None),
                    "time": date_value,
                    "raw": row,
                }
            )
        return {
            "securities": [split_code(thscode)],
            "period": int(period),
            "adjustType": int(adjust),
            "data": {thscode[:4] + thscode[-6:]: bars},
        }

    def trend(self, code: str) -> dict[str, Any]:
        """Return the current-day minute trend using the THS transport."""

        thscode = normalize_thscode(code)
        response = self.ths.intraday_data(thscode)
        if response.error:
            raise QueryError(f"同花顺分时查询失败：{response.error}", "ths_query_failed")
        rows = records(response.df)
        items = []
        for row in rows:
            time_value = first_value(row, "时间", "time", default=None)
            item = {
                "1": epoch_seconds(time_value),
                "10": numeric(first_value(row, "价格", "最新价", "price", default=None)),
                "13": numeric(first_value(row, "成交量", "volume", default=None)),
                "19": numeric(first_value(row, "总金额", "成交额", "turnover", default=None)),
                "time": json_value(time_value),
                "raw": row,
            }
            items.append(item)
        return {
            "securities": [split_code(thscode)],
            "count": len(items),
            "items": items,
            "columns": list(rows[0].keys()) if rows else [],
        }

    def tick(self, code: str, count: int = 20) -> dict[str, Any]:
        """Return recent level-1 ticks, trimmed to the requested count."""

        thscode = normalize_thscode(code)
        response = self.ths.tick_level1(thscode)
        if response.error:
            raise QueryError(f"同花顺逐笔查询失败：{response.error}", "ths_query_failed")
        rows = records(response.df)
        rows = rows[-max(1, int(count)) :]
        items = []
        for row in rows:
            time_value = first_value(row, "时间", "time", default=None)
            item = {
                "1": epoch_seconds(time_value),
                "10": first_value(row, "价格", "最新价", "price", default=None),
                "12": first_value(row, "成交方向", "成交量分类", "volume_class", default=None),
                "18": first_value(row, "交易笔数", "成交次数", "trade_count", default=None),
                "49": first_value(row, "当前量", "现量", "last_volume", default=None),
                "time": json_value(time_value),
                "raw": row,
            }
            items.append(item)
        return {
            "securities": [split_code(thscode)],
            "count": len(items),
            "items": items,
            "columns": list(rows[0].keys()) if rows else [],
        }

    def wencai(self, query: str, page: int = 1, limit: int = 10) -> dict[str, Any]:
        """Return the portable THS natural-language query result."""

        condition = str(query).strip()
        if not condition:
            raise QueryError("wencai_query 需要非空 query", "invalid_argument")
        page_number = max(1, int(page))
        page_size = max(1, min(int(limit), 100))
        response = self.ths.wencai_nlp(condition)
        if response.error:
            raise QueryError(f"同花顺问财查询失败：{response.error}", "ths_query_failed")
        rows = records(response.df)
        frame = getattr(response, "df", None)
        columns = []
        if frame is not None and getattr(frame, "columns", None) is not None:
            columns = [str(column) for column in frame.columns]
        elif rows:
            columns = list(rows[0].keys())
        start = (page_number - 1) * page_size
        return {
            "datas": rows[start : start + page_size],
            "columns": columns,
            "row_count": len(rows),
            "status_code": 0,
        }

    def _directory_rows(
        self,
        getter: Any,
        kind: str,
        attempts: int = 3,
        retry_delay: float = 0.6,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        errors: list[str] = []
        attempt_count = max(1, int(attempts))
        for attempt in range(attempt_count):
            try:
                response = getter()
            except Exception as exc:
                errors.append(f"{kind}: {exc}")
            else:
                if response is not None and not response.error:
                    rows = records(response.df) if response.df is not None else []
                    if rows:
                        return rows, errors
                error = getattr(response, "error", None) if response is not None else None
                errors.append(f"{kind}: {error or '目录为空'}")
            if attempt + 1 < attempt_count:
                time.sleep(retry_delay * (attempt + 1))
        return [], errors

    def blocks(self, keyword: str, limit: int = 50) -> dict[str, Any]:
        items = []
        directory_errors: list[str] = []
        directory_rows = 0
        for kind, getter in (("industry", self.ths.ths_industry), ("concept", self.ths.ths_concept)):
            rows, errors = self._directory_rows(getter, kind)
            directory_errors.extend(errors)
            directory_rows += len(rows)
            for row in rows:
                code = str(first_value(row, "代码", "板块代码", "code", "板块", default=""))
                name = str(first_value(row, "名称", "板块名称", "name", default=""))
                if not keyword or keyword.lower() in name.lower() or keyword.lower() in code.lower():
                    items.append({"block_code": code, "name": name, "kind": kind})
        if not directory_rows and directory_errors:
            raise QueryError(
                "板块目录读取失败：" + "；".join(directory_errors),
                "ths_query_failed",
            )
        return {"count": len(items), "items": items[: max(1, int(limit))]}

    def _block_codes(self, block: int) -> list[str]:
        response = self.ths.block(int(block))
        if response.error:
            raise QueryError(f"板块 {block} 成员查询失败：{response.error}", "ths_query_failed")
        rows = records(response.df)
        codes: list[str] = []
        for row in rows:
            code = str(
                first_value(row, "代码", "证券代码", "THSCODE", "thscode", default="")
            ).upper()
            if code and code not in codes:
                codes.append(normalize_thscode(code))
        if not codes:
            raise QueryError(f"板块 {block} 没有返回成员", "not_found")
        return codes

    def sort(
        self,
        block: int = 14,
        sort_field: int = 199112,
        sort_order: int = 1,
        offset: int = 0,
        count: int = 60,
        exclude_blocks: str = "",
    ) -> dict[str, Any]:
        field_key = str(int(sort_field))
        if field_key not in SORT_FIELDS:
            raise QueryError(
                f"thsdk 排行不支持按 FieldID {sort_field} 排序",
                "unsupported_sort_field",
            )
        if int(sort_order) not in (0, 1):
            raise QueryError("sortOrder 只能是 0（升序）或 1（降序）", "invalid_argument")

        members = self._block_codes(int(block))
        excluded: set[str] = set()
        for excluded_block in block_numbers(exclude_blocks):
            excluded.update(self._block_codes(excluded_block))
        members = [code for code in members if code not in excluded]

        groups: dict[str, list[str]] = {}
        for code in members:
            groups.setdefault(code[:4], []).append(code)
        rows: list[dict[str, Any]] = []
        for group in groups.values():
            response = self.ths.market_data_cn(group if len(group) > 1 else group[0], "基础数据")
            if response.error:
                raise QueryError(f"排行行情查询失败：{response.error}", "ths_query_failed")
            rows.extend(records(response.df))

        ranked: list[dict[str, Any]] = []
        missing_count = 0
        seen: set[str] = set()
        for row in rows:
            code = normalize_thscode(
                str(first_value(row, "代码", "证券代码", "THSCODE", "thscode", default=""))
            )
            if not code or code in seen or code not in members:
                continue
            seen.add(code)
            fields: dict[str, Any] = {}
            for current_field, (current_name, current_aliases) in SORT_FIELDS.items():
                value = first_value(row, *current_aliases, default=None)
                if current_field in {"199112", "264648"} and value is None:
                    last = numeric(
                        first_value(row, "价格", "最新价", default=None),
                        max_abs=VENDOR_PRICE_SENTINEL,
                    )
                    previous = numeric(
                        first_value(row, "昨收价", "昨收", default=None),
                        max_abs=VENDOR_PRICE_SENTINEL,
                    )
                    if last is not None and previous not in (None, 0):
                        value = (
                            (last - previous) / previous * 100
                            if current_field == "199112"
                            else last - previous
                        )
                if current_field in {"199112", "264648", "10", "6", "7", "8", "9"}:
                    value = numeric(value, max_abs=VENDOR_PRICE_SENTINEL)
                else:
                    value = numeric(value)
                fields[current_field] = value
            value = numeric(
                fields.get(field_key),
                max_abs=VENDOR_PRICE_SENTINEL
                if field_key in {"199112", "264648", "10", "6", "7", "8", "9"}
                else None,
            )
            if value is None:
                missing_count += 1
                continue
            ranked.append(
                {
                    "security": code,
                    "thscode": code,
                    "ticker": code[-6:],
                    "name": first_value(row, "名称", "Name", default=""),
                    "value": value,
                    "fields": fields,
                }
            )

        reverse = int(sort_order) == 1
        ranked.sort(key=lambda item: item["security"])
        ranked.sort(key=lambda item: item["value"], reverse=reverse)
        total = len(ranked)
        start = max(0, int(offset))
        end = start + max(1, int(count))
        items = []
        for index, item in enumerate(ranked[start:end], start=start + 1):
            item = dict(item)
            item["rank"] = index
            items.append(item)
        return sort_result(
            str(block),
            sort_field,
            sort_order,
            start,
            count,
            total,
            items,
            missing_count,
            {key: value[0] for key, value in SORT_FIELDS.items()},
        )

    def sector(self, target: str) -> dict[str, Any]:
        text = str(target).strip()
        block_code = ""
        name = text
        kind = "sector"
        if text.upper().startswith("URFI") and len(text) >= 10:
            block_code = text.upper()
        elif text.upper().endswith(".TI"):
            block_code = "URFI" + text.split(".")[0]
        else:
            matches = self.blocks(text, limit=50)["items"]
            if not matches:
                raise QueryError(f"同花顺没有找到行业/板块：{text}", "not_found")
            match = matches[0]
            block_code = str(match["block_code"])
            name = str(match["name"])
            kind = str(match["kind"])
        members_resp = self.ths.block_constituents(block_code)
        if members_resp.error:
            raise QueryError(f"板块成分查询失败：{members_resp.error}", "ths_query_failed")
        members = []
        for row in records(members_resp.df):
            thscode = str(first_value(row, "代码", "证券代码", "THSCODE", default="")).upper()
            members.append(
                {
                    "thscode": thscode,
                    "ticker": thscode[-6:],
                    "name": first_value(row, "名称", "证券名称", default=""),
                    "raw": row,
                }
            )
        snapshot = {}
        for query_key in ("基础数据", "扩展"):
            response = self.ths.market_data_block(block_code, query_key)
            if not response.error and response.df is not None and len(response.df):
                snapshot = records(response.df)[0]
                break
        return {
            "sector": {"name": name, "block_code": block_code, "kind": kind},
            "members": members,
            "snapshot": snapshot,
        }

    def news(self, code: str, count: int = 20) -> dict[str, Any]:
        thscode = normalize_thscode(code)
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        per_category = max(1, min(20, math.ceil(max(1, int(count)) / 3)))
        for text_id, category in ((0x3805, "公告"), (0x3806, "研报"), (0x3808, "社区")):
            if len(items) >= max(1, int(count)):
                break
            response = self.ths.news(text_id, thscode[-6:], thscode[:4])
            if response.error:
                errors.append(f"{category}: {response.error}")
                continue
            added = 0
            for row in records(response.df):
                item = dict(row)
                item["_category"] = category
                item["_text_id"] = text_id
                items.append(item)
                added += 1
                if added >= per_category or len(items) >= max(1, int(count)):
                    break
            time.sleep(0.2)
        columns: list[str] = []
        for item in items:
            for key in item:
                if key not in columns:
                    columns.append(key)
        if not items and errors:
            raise QueryError("新闻查询失败：" + "; ".join(errors), "ths_query_failed")
        return {
            "thscode": thscode,
            "items": items,
            "columns": columns,
            "errors": errors,
        }

    def capital_flow(self, code: str, count: int = 20) -> dict[str, Any]:
        thscode = normalize_thscode(code)
        response = self.ths.big_order_flow(thscode)
        if response.error:
            raise QueryError(f"资金流向查询失败：{response.error}", "ths_query_failed")
        rows = records(response.df)
        for row in rows:
            direction = row.get("成交方向")
            if direction is not None:
                row["成交方向码"] = direction
                row["成交方向"] = BIG_ORDER_DIRECTIONS.get(str(direction), str(direction))
        return {"items": rows[-max(1, int(count)) :], "columns": list(rows[0].keys()) if rows else []}


def status_payload(probe: bool = False) -> dict[str, Any]:
    thsdk_info: dict[str, Any] = {"available": False}
    ths_probe_ok = False
    try:
        import thsdk  # type: ignore

        thsdk_info["available"] = True
        thsdk_info["version"] = getattr(thsdk, "__version__", "unknown")
        thsdk_info["credentials"] = "account" if (os.getenv("THS_USERNAME") and os.getenv("THS_PASSWORD")) else "guest"
    except ImportError:
        thsdk_info["error"] = "未安装 thsdk"
    if probe:
        started = time.time()
        try:
            with ThsClient() as client:
                result = client.search("贵州茅台", limit=1)
            thsdk_info["probe"] = {
                "ok": bool(result.get("items")),
                "elapsed_seconds": round(time.time() - started, 2),
            }
            ths_probe_ok = bool(thsdk_info["probe"]["ok"])
        except Exception as exc:
            thsdk_info["probe"] = {"ok": False, "error": redact(exc)}

    key, source = cloud_api_key()
    cloud_info: dict[str, Any] = {
        "configured": bool(key),
        "source": source,
        "base_url": BASE_URL,
    }
    cloud_probe_ok = False
    if probe:
        if key:
            started = time.time()
            try:
                client = CloudClient(key=key)
                result = client.search("贵州茅台", limit=1)
                cloud_info["probe"] = {
                    "ok": bool(result.get("items")),
                    "elapsed_seconds": round(time.time() - started, 2),
                }
                cloud_probe_ok = bool(cloud_info["probe"]["ok"])
            except Exception as exc:
                cloud_info["probe"] = {"ok": False, "error": redact(exc)}
        else:
            cloud_info["probe"] = {"ok": False, "error": "missing_api_key"}
    wencai_key, wencai_source = wencai_api_key()
    wencai_info: dict[str, Any] = {
        "configured": bool(wencai_key),
        "source": wencai_source,
        "endpoint": WENCAI_ENDPOINT,
    }
    wencai_probe_ok = False
    if probe:
        if wencai_key:
            started = time.time()
            try:
                result = WencaiClient(wencai_key).query(
                    "hithink-market-query",
                    "贵州茅台",
                    limit=1,
                )
                wencai_info["probe"] = {
                    "ok": bool(result.get("datas")),
                    "elapsed_seconds": round(time.time() - started, 2),
                }
                wencai_probe_ok = bool(wencai_info["probe"]["ok"])
            except Exception as exc:
                wencai_info["probe"] = {"ok": False, "error": redact(exc)}
        else:
            wencai_info["probe"] = {"ok": False, "error": "missing_api_key"}
    cli = shutil.which("hithink-finance")
    data_dir = Path(os.getenv("DAILY_BRIEFING_DATA_DIR", Path.home() / ".codex" / "daily-briefing-pro" / "data"))
    output_dir = Path(os.getenv("BRIEFING_OUTPUT_DIR", Path.cwd() / "报告"))
    configured = bool(thsdk_info.get("available")) or bool(key) or bool(wencai_key)
    return {
        "ok": (
            ths_probe_ok or cloud_probe_ok or wencai_probe_ok
        ) if probe else configured,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "thsdk": thsdk_info,
        "cloud_api": cloud_info,
        "wencai": wencai_info,
        "hithink_cli": {"available": bool(cli), "path": cli},
        "data_dir": {"path": str(data_dir), "writable": writable_dir(data_dir)},
        "output_dir": {"path": str(output_dir), "writable": writable_dir(output_dir)},
        "time": datetime.now(CN).isoformat(timespec="seconds"),
    }


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("auto", "ths", "cloud"), default="auto", help="数据通道，默认 auto")
    parser.add_argument("--include-meta", action="store_true", help="附加来源和耗时")
    parser.add_argument("--compact", action="store_true", help="输出单行 JSON")


def run_action(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    attempts: list[dict[str, Any]] = []

    if args.action == "call" and getattr(args, "tool", "") == "wencai_query":
        request = getattr(args, "call_args", {})
        if not isinstance(request, dict):
            raise QueryError("call 参数必须是 JSON 对象", "invalid_argument")
        wencai = wencai_query_payload(request, args.mode)
        if args.include_meta:
            return {
                "_meta": {
                    "source": wencai.get("source", "wencai"),
                    "attempts": [],
                    "elapsed_seconds": round(time.time() - started, 2),
                    "time": datetime.now(CN).isoformat(timespec="seconds"),
                },
                "data": wencai,
            }
        return wencai

    if args.action == "watchlist":
        return watchlist_payload(getattr(args, "selfstock_path", ""))
    if args.action == "sectors":
        return sectors_payload(getattr(args, "selfstock_path", ""))
    if args.action == "call" and getattr(args, "tool", "") == "search_fields":
        request = getattr(args, "call_args", {})
        return load_catalog(
            "fields",
            str(request.get("query") or ""),
            int(request.get("limit") or 20),
            bool(request.get("all")),
            data_type=str(request.get("dataType") or ""),
        )
    if args.action == "call" and getattr(args, "tool", "") == "manageSector":
        request = getattr(args, "call_args", {})
        if request.get("operation") != "query":
            raise QueryError("call 只允许 manageSector 的查询操作", "unsupported_tool")
        return (
            sectors_payload()
            if str(request.get("sectorId") or "") != "-1"
            else watchlist_payload()
        )

    def attempt(source: str, fn):
        try:
            value = fn()
            attempts.append({"source": source, "success": True, "message": ""})
            return value
        except Exception as exc:
            attempts.append({"source": source, "success": False, "message": redact(exc)})
            raise

    if args.action in {"trend", "tick"} and args.mode == "cloud":
        raise QueryError(
            "分时和逐笔数据在扶摇公开 REST 通道没有对应端点；请使用 --mode ths 或 auto",
            "unsupported_cloud",
        )

    sources: list[str] = []
    if args.mode in ("auto", "ths"):
        sources.append("ths")
    if args.action not in {"trend", "tick"} and args.mode in ("auto", "cloud") and cloud_api_key()[0]:
        sources.append("cloud")
    if args.mode == "cloud" and not cloud_api_key()[0]:
        raise QueryError(
            "cloud 模式需要 FUYAO_API_KEY、HITHINK_API_KEY 或 HITHINK_FINANCE_API_KEY",
            "missing_api_key",
        )

    result: dict[str, Any] | None = None
    errors: list[str] = []
    for source in sources:
        try:
            if source == "ths":
                if args.action in ("cloud-get", "datahub-get"):
                    continue
                with ThsClient() as client:
                    result = attempt(source, lambda client=client: dispatch_ths(client, args))
            else:
                client = CloudClient()
                result = attempt(source, lambda client=client: dispatch_cloud(client, args))
            if result is not None:
                break
        except Exception as exc:
            errors.append(f"{source}: {redact(exc)}")
            if args.mode != "auto":
                raise
    if result is None:
        message = "; ".join(errors) or "没有可用的数据通道"
        raise QueryError(message, "all_sources_failed")

    if args.include_meta:
        result = {
            "_meta": {
                "source": attempts[-1]["source"] if attempts else "unknown",
                "attempts": attempts,
                "elapsed_seconds": round(time.time() - started, 2),
                "time": datetime.now(CN).isoformat(timespec="seconds"),
            },
            "data": result,
        }
    return result


def dispatch_ths(client: ThsClient, args: argparse.Namespace) -> dict[str, Any]:
    action = args.action
    if action == "search":
        return client.search(args.keyword, args.limit)
    if action == "realtime":
        return client.realtime(args.codes)
    if action == "candle":
        return client.candle(args.code, args.period, args.count, args.adjust)
    if action == "trend":
        return client.trend(args.code)
    if action == "tick":
        return client.tick(args.code, args.count)
    if action == "blocks":
        return client.blocks(args.keyword, args.limit)
    if action == "sort":
        return client.sort(
            args.block,
            args.sort_field,
            args.sort_order,
            args.offset,
            args.count,
            args.exclude_blocks,
        )
    if action == "subscribe":
        return subscribe_payload(client, args, "ths")
    if action == "call":
        return call_payload(client, args, "ths", mode=args.mode)
    if action == "sector":
        return client.sector(args.target)
    if action == "news":
        return client.news(args.code, args.count)
    if action == "capital-flow":
        return client.capital_flow(args.code, args.count)
    raise QueryError(f"{action} 不支持 ths 通道", "unsupported_action")


def dispatch_cloud(client: CloudClient, args: argparse.Namespace) -> dict[str, Any]:
    action = args.action
    if action == "search":
        return client.search(args.keyword, limit=args.limit)
    if action == "realtime":
        return client.realtime(args.codes)
    if action == "candle":
        return client.candle(args.code, args.period, args.count, args.adjust)
    if action in ("trend", "tick"):
        raise QueryError(
            "分时和逐笔数据在扶摇公开 REST 通道没有对应端点",
            "unsupported_cloud",
        )
    if action == "blocks":
        return client.search(args.keyword, asset_type="a-share-index", limit=args.limit)
    if action == "sort":
        return client.sort(
            args.block,
            args.sort_field,
            args.sort_order,
            args.offset,
            args.count,
            args.exclude_blocks,
        )
    if action == "subscribe":
        api = str(args.subscribe_api)
        if api in {"SubscribeIntradayTrend", "SubscribeTrend", "SubscribeIntradayTick", "SubscribeTick"}:
            raise QueryError(
                "扶摇公开 REST 没有分时/逐笔订阅端点；请使用 --mode ths 或 auto",
                "unsupported_cloud",
            )
        if api == "SubscribeIntradayCandle" and int(args.period) != 5:
            raise QueryError(
                "扶摇公开 REST 只提供日 K，分钟 K 订阅请使用 --mode ths 或 auto",
                "unsupported_period",
            )
        return subscribe_payload(client, args, "cloud")
    if action == "call":
        return call_payload(client, args, "cloud", mode=args.mode)
    if action == "sector":
        return client.sector(args.target)
    if action == "news":
        return client.news(args.code, args.count)
    if action == "capital-flow":
        raise QueryError(
            "扶摇公开 API 的资金流接口标记为 client-only，云端模式无法查询逐笔大单",
            "unsupported_cloud",
        )
    if action in ("cloud-get", "datahub-get"):
        return client.generic(args.path, args.params)
    raise QueryError(f"{action} 不支持 cloud 通道", "unsupported_action")


def load_catalog(
    source: str,
    query: str = "",
    limit: int = 20,
    show_all: bool = False,
    data_type: str = "",
) -> dict[str, Any]:
    files = {
        "cloud": "cloud-apis.csv",
        "datahub": "datahub-apis.csv",
        "dataaccessor": "dataaccessor-apis.csv",
        "subscribe": "dataaccessor-subscribe-apis.csv",
        "fields": "dataaccessor-fields.csv",
    }
    path = REFERENCE_ROOT / files[source]
    if not path.is_file():
        raise QueryError(f"目录文件不存在：{path}", "missing_reference")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if data_type:
        rows = [row for row in rows if str(row.get("dataType") or "").lower() == data_type.lower()]
    if query:
        needle = query.lower()
        rows = [
            row
            for row in rows
            if needle in " ".join(str(v) for v in row.values()).lower()
        ]
    total = len(rows)
    if not show_all:
        rows = rows[: max(1, int(limit))]
    return {"source": source, "count": total, "items": rows, "truncated": len(rows) < total}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A 股行情查询（可移植 Python 版）")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("status", help="检查服务端行情通道")
    p.add_argument("--probe", action="store_true", help="实际连接一次行情服务")
    add_common(p)

    p = sub.add_parser("search", help="按名称或代码检索证券")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=20)
    add_common(p)

    p = sub.add_parser("realtime", help="实时行情快照")
    p.add_argument("codes", help="逗号分隔的代码，例如 600519,000001")
    add_common(p)

    p = sub.add_parser("candle", help="K 线")
    p.add_argument("code")
    p.add_argument("--period", type=int, default=5, choices=sorted(PERIODS))
    p.add_argument("--count", type=int, default=60)
    p.add_argument("--adjust", type=int, default=1, choices=(0, 1, 2))
    add_common(p)

    p = sub.add_parser("trend", help="分时（仅 ths 通道）")
    p.add_argument("code")
    add_common(p)

    p = sub.add_parser("tick", help="逐笔（仅 ths 通道）")
    p.add_argument("code")
    p.add_argument("--count", type=int, default=20)
    add_common(p)

    p = sub.add_parser("blocks", help="检索行业/概念板块")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=50)
    add_common(p)

    p = sub.add_parser("sort", help="按板块和字段排序")
    p.add_argument("--block", default="14", help="板块 ID，默认 14=沪深A股")
    p.add_argument("--sort-field", type=int, default=199112, help="排序 FieldID")
    p.add_argument("--sort-order", type=int, choices=(0, 1), default=1, help="0=升序，1=降序")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=60)
    p.add_argument("--exclude-blocks", default="")
    add_common(p)

    p = sub.add_parser("sector", help="行业/板块成分与快照")
    p.add_argument("--target", required=True, help="板块名称、URFI 代码或指数代码")
    add_common(p)

    p = sub.add_parser("watchlist", help="读取自选股（跨平台文件）")
    p.add_argument("--selfstock-path", default="")
    add_common(p)

    p = sub.add_parser("sectors", help="列出自选分组（跨平台文件）")
    p.add_argument("--selfstock-path", default="")
    add_common(p)

    p = sub.add_parser("subscribe", help="一次性订阅快照（收到首帧等价结果后结束）")
    p.add_argument("--api", dest="subscribe_api", choices=SUBSCRIBE_APIS, required=True)
    p.add_argument("--target", required=True, help="证券代码，多个用逗号分隔")
    p.add_argument("--fields", default="")
    p.add_argument("--period", type=int, default=5)
    p.add_argument("--adjust", type=int, choices=(0, 1, 2), default=1)
    p.add_argument("--count", type=int, default=60)
    p.add_argument("--timeout-ms", type=int, default=10000)
    add_common(p)

    p = sub.add_parser("call", help="调用白名单只读工具")
    p.add_argument(
        "--tool",
        required=True,
        choices=(
            "search_securities",
            "search_blocks",
            "search_fields",
            "realtime_query",
            "candle_query",
            "sort_query",
            "trend_query",
            "tick_query",
            "indicator_query",
            "wencai_query",
            "manageSector",
        ),
    )
    p.add_argument("--arguments-json", default="{}")
    add_common(p)

    p = sub.add_parser("news", help="个股新闻")
    p.add_argument("code")
    p.add_argument("--count", type=int, default=20)
    add_common(p)

    p = sub.add_parser("capital-flow", help="个股大单/资金流向")
    p.add_argument("code")
    p.add_argument("--count", type=int, default=20)
    add_common(p)

    p = sub.add_parser("catalog", help="本地接口目录检索")
    p.add_argument("--source", choices=("cloud", "datahub", "dataaccessor", "subscribe", "fields"), default="cloud")
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--all", action="store_true")
    p.add_argument("--compact", action="store_true", help="输出单行 JSON")

    p = sub.add_parser("fields", help="字段目录检索")
    p.add_argument("--data-type", default="")
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--all", action="store_true")
    p.add_argument("--compact", action="store_true", help="输出单行 JSON")

    p = sub.add_parser("cloud-get", help="调用已登记的扶摇 GET 接口")
    p.add_argument("path")
    p.add_argument("--params-json", default="{}")
    add_common(p)

    p = sub.add_parser("datahub-get", help="cloud-get 的兼容别名")
    p.add_argument("path")
    p.add_argument("--params-json", default="{}")
    add_common(p)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            payload = status_payload(probe=args.probe)
        elif args.action == "catalog":
            payload = load_catalog(args.source, args.query, args.limit, args.all)
        elif args.action == "fields":
            payload = load_catalog(
                "fields",
                args.query,
                args.limit,
                args.all,
                data_type=args.data_type,
            )
        else:
            if hasattr(args, "params_json"):
                try:
                    args.params = json.loads(args.params_json or "{}")
                except json.JSONDecodeError as exc:
                    raise QueryError(f"--params-json 不是有效 JSON：{exc}", "invalid_argument") from exc
            if hasattr(args, "arguments_json"):
                try:
                    args.call_args = json.loads(args.arguments_json or "{}")
                except json.JSONDecodeError as exc:
                    raise QueryError(f"--arguments-json 不是有效 JSON：{exc}", "invalid_argument") from exc
            payload = run_action(args)
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=None if getattr(args, "compact", False) else 2,
                default=str,
            )
        )
        if args.action == "status":
            return 0 if payload.get("ok", False) else 1
        return 0
    except QueryError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": redact(exc), "details": exc.details}},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # pragma: no cover - defensive boundary
        print(
            json.dumps(
                {"ok": False, "error": {"code": "unexpected_error", "message": redact(exc)}},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
