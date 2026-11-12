"""Cloud-only data adapters for the portable report collectors.

The reports originally used the guest THS desktop transport for every data
domain. That transport is not a reliable cloud dependency. This module keeps
the same report schemas while sourcing quotes, holders, fund-flow aggregates
and fundamentals from the official iWencai OpenAPI, with Fuyao REST supplying
security lookup, sector membership, snapshots, news and quote fallback.
"""

from __future__ import annotations

import gzip
import io
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import requests


PLUGIN_ROOT = Path(__file__).resolve().parent
MARKET_SCRIPTS = PLUGIN_ROOT / "skills" / "market-query" / "scripts"
if str(MARKET_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(MARKET_SCRIPTS))
DAILY_SCRIPTS = PLUGIN_ROOT / "skills" / "daily-briefing-pro" / "scripts"
if str(DAILY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DAILY_SCRIPTS))

import market_query as mq  # noqa: E402
import _hithink as hithink  # noqa: E402


CN_TZ = ZoneInfo("Asia/Shanghai")
WENCAI_TIMEOUT = int(os.getenv("DAILY_BRIEFING_WENCAI_TIMEOUT", "25"))
QUERY_DELAY = float(os.getenv("DAILY_BRIEFING_WENCAI_DELAY", "0.35"))
EASTMONEY_TIMEOUT = int(os.getenv("DAILY_BRIEFING_EASTMONEY_TIMEOUT", "15"))
EASTMONEY_HOLDER_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/"
    "ShareholderResearch/PageAjax"
)
EASTMONEY_INDUSTRY_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/"
    "IndustryAnalysis/PageAjax"
)
EASTMONEY_COMPANY_SURVEY_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/"
    "CompanySurvey/PageAjax"
)
EASTMONEY_BUSINESS_ANALYSIS_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/"
    "BusinessAnalysis/PageAjax"
)
EASTMONEY_BONUS_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/"
    "BonusFinancing/PageAjax"
)
EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
EASTMONEY_STOCK_URL = "https://push2.eastmoney.com/api/qt/stock/get"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
EASTMONEY_QUOTE_REFERER = "https://quote.eastmoney.com/"
EASTMONEY_SECTOR_SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
EASTMONEY_SECTOR_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_SECTOR_KLINE_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get"
)
EASTMONEY_SECTOR_FLOW_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
)
EASTMONEY_UT = "b2884a393a59ad64002292a3e90d46a5"
EASTMONEY_FINANCE_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/"
    "NewFinanceAnalysis/ZYZBAjaxNew"
)
EASTMONEY_DATACENTER_URL = (
    "https://datacenter.eastmoney.com/securities/api/data/v1/get"
)
EASTMONEY_MARGIN_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EASTMONEY_STOCK_FLOW_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
)
EASTMONEY_NOTICE_LIST_URL = "https://np-anotice-pc.eastmoney.com/api/security/ann"
EASTMONEY_NOTICE_CONTENT_URL = "https://np-cnotice-pc.eastmoney.com/api/content/ann"
GOOGLE_PATENTS_QUERY_URL = "https://patents.google.com/xhr/query"
INDUSTRY_SNAPSHOT_FIELDS = (
    "涨幅",
    "5日涨幅",
    "10日涨幅",
    "20日涨幅",
    "主力净流入",
    "量比",
)
CloudSourceError = mq.QueryError


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if isinstance(value, float) and math.isnan(value) else float(value)
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text in {"暂无", "--", "-", "None", "null", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _first(row: dict[str, Any], *needles: str, default: Any = None) -> Any:
    for needle in needles:
        if needle in row and row[needle] not in (None, ""):
            return row[needle]
    for key, value in row.items():
        if any(needle in str(key) for needle in needles) and value not in (None, ""):
            return value
    return default


def _first_priority(row: dict[str, Any], *needles: str) -> Any:
    """Pick by needle priority, not by the vendor's column insertion order."""

    for needle in needles:
        for key, value in row.items():
            if needle in str(key) and value not in (None, ""):
                return value
    return None


def _has_stock_peer_rows(frame: Any) -> bool:
    """Return whether a peer result contains securities instead of a board index."""

    if frame is None or getattr(frame, "empty", True):
        return False
    for row in frame.to_dict("records"):
        keys = {str(key) for key in row}
        if any("指数" in key for key in keys):
            continue
        code = _first(row, "股票代码", "代码", "ticker", "thscode", default="")
        name = _first(row, "股票简称", "简称", "名称", "Name", default="")
        if re.search(r"\d{6}", str(code)) and str(name).strip():
            return True
    return False


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return not text or text in {"暂无", "暂无数据", "--", "-", "None", "null", "nan"}


def _fill_missing(target: dict[str, Any], source: dict[str, Any]) -> list[str]:
    filled: list[str] = []
    for key, value in source.items():
        if _is_missing(target.get(key)) and not _is_missing(value):
            target[key] = value
            filled.append(key)
    return filled


def _first_key(row: dict[str, Any], *prefixes: str) -> str | None:
    for prefix in prefixes:
        for key in row:
            if str(key).startswith(prefix):
                return str(key)
    return None


def _normalize_name(value: Any) -> str:
    text = str(value or "")
    for suffix in ("Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "I", "II", "III", "IV", "V"):
        if text.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text.strip()


def _join(value: Any, separator: str = "-") -> str:
    if isinstance(value, (list, tuple)):
        return separator.join(_text(item) for item in value if _text(item))
    return _text(value)


def _frame_result(payload: dict[str, Any] | None, error: str = "") -> SimpleNamespace:
    if not payload:
        return SimpleNamespace(df=pd.DataFrame(), error=error or "empty")
    rows = [row for row in payload.get("datas") or [] if isinstance(row, dict)]
    if not rows:
        return SimpleNamespace(df=pd.DataFrame(), error=error or "empty")
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    frame = pd.DataFrame([{key: _json_value(row.get(key)) for key in columns} for row in rows], columns=columns)
    return SimpleNamespace(df=frame, error="", raw=payload)


def _empty(error: str) -> SimpleNamespace:
    return SimpleNamespace(df=pd.DataFrame(), error=error)


def _annual_years() -> list[int]:
    current = datetime.now(CN_TZ).year
    return [current - 3, current - 2, current - 1]


def _eastmoney_market_prefix(code: str) -> str:
    text = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", text):
        raise ValueError(f"无效的六位股票代码：{code!r}")
    if text.startswith(("4", "8", "920")):
        return "BJ"
    if text.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


def _date_key(value: Any) -> str:
    text = _text(value)
    match = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", text)
    return "".join(match.groups()) if match else ""


def _fetch_eastmoney_urllib_json(url: str, headers: dict[str, str]) -> Any:
    """Fetch endpoints whose response differs between HTTP clients."""

    last_error: OSError | None = None
    raw = b""
    for attempt in range(3):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(
                request,
                timeout=EASTMONEY_TIMEOUT,
            ) as response:
                raw = response.read()
            break
        except OSError as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(0.5 * (attempt + 1))
    if not raw and last_error is not None:
        raise last_error
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return _parse_eastmoney_json(raw)


def _parse_eastmoney_json(raw: bytes) -> Any:
    text = raw.decode("utf-8-sig").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _fetch_eastmoney_requests_json(url: str, headers: dict[str, str]) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=EASTMONEY_TIMEOUT,
            )
            response.raise_for_status()
            return _parse_eastmoney_json(response.content)
        except (requests.RequestException, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(0.5 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise ValueError("东方财富请求没有返回内容")


def _fetch_eastmoney_json(
    url: str,
    *,
    referer: str = "https://emweb.securities.eastmoney.com/",
) -> Any:
    """Fetch a public Eastmoney JSON endpoint without browser state."""

    last_error: Exception | None = None
    raw = b""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    if "searchapi.eastmoney.com" in url:
        try:
            return _fetch_eastmoney_urllib_json(url, headers)
        except Exception:
            return _fetch_eastmoney_requests_json(url, headers)
    try:
        for attempt in range(3):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=EASTMONEY_TIMEOUT,
                )
                response.raise_for_status()
                raw = response.content
                break
            except (requests.RequestException, OSError) as exc:
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))
    except (requests.RequestException, OSError):
        return _fetch_eastmoney_urllib_json(url, headers)
    if not raw and last_error is not None:
        raise last_error
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return _parse_eastmoney_json(raw)


def _find_annual_report(code: str) -> dict[str, Any]:
    """Return the newest disclosed annual report for a stock."""

    for page in range(1, 4):
        params = {
            "sr": "-1",
            "page_size": "50",
            "page_index": str(page),
            "ann_type": "A",
            "client_source": "web",
            "stock_list": code,
            "f_node": "0",
            "s_node": "0",
        }
        payload = _fetch_eastmoney_json(
            f"{EASTMONEY_NOTICE_LIST_URL}?{urlencode(params)}",
            referer="https://data.eastmoney.com/",
        )
        items = ((payload or {}).get("data") or {}).get("list") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _text(item.get("title"))
            if not re.search(r"\d{4}年年度报告", title):
                continue
            if any(
                word in title
                for word in ("摘要", "英文", "半年度", "季度", "已取消")
            ):
                continue
            if _text(item.get("art_code")):
                return dict(item)
        if len(items) < 50:
            break
    return {}


def _annual_report_pdf_url(art_code: str) -> str:
    payload = _fetch_eastmoney_json(
        f"{EASTMONEY_NOTICE_CONTENT_URL}?art_code={quote(art_code)}"
        "&client_source=web&page_index=1",
        referer="https://data.eastmoney.com/",
    )
    data = (payload or {}).get("data") or {}
    for item in data.get("attach_list") or []:
        if isinstance(item, dict) and _text(item.get("attach_url")):
            return _text(item.get("attach_url"))
    return ""


def _annual_report_text(art_code: str) -> str:
    url = _annual_report_pdf_url(art_code)
    if not url:
        return ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://data.eastmoney.com/",
    }
    response = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            try:
                from curl_cffi import requests as curl_requests

                response = curl_requests.get(
                    url,
                    impersonate="chrome",
                    headers=headers,
                    timeout=90,
                )
            except ImportError:
                response = requests.get(url, headers=headers, timeout=90)
            response.raise_for_status()
            break
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    if response is None:
        raise ValueError(f"年报 PDF 下载失败：{last_error}")
    if len(response.content) > 40 * 1024 * 1024:
        raise ValueError("年报 PDF 超过 40MB，已跳过正文解析")
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(response.content))
    return "\n".join(
        page.extract_text() or "" for page in reader.pages
    )


def _disclosed_ratio(
    text: str,
    subject_pattern: str,
    total_pattern: str,
) -> float | None:
    """Extract a percentage disclosed immediately after a report phrase."""

    for match in re.finditer(subject_pattern, text):
        window = text[match.start() : match.start() + 500]
        ratio = re.search(
            total_pattern + r".{0,40}?([0-9]+(?:\.[0-9]+)?)\s*%",
            window,
            re.S,
        )
        if ratio:
            return _number(ratio.group(1))
    return None


def _disclosed_rd_ratio(text: str) -> float | None:
    for pattern in (
        r"研发投入(?:总额)?占营业收入(?:的)?比例[（(]?%?[）)]?\s*[:：]?\s*"
        r"([0-9]+(?:\.[0-9]+)?)",
        r"研发投入(?:总额)?占营业收入(?:的)?比重[（(]?%?[）)]?\s*[:：]?\s*"
        r"([0-9]+(?:\.[0-9]+)?)",
    ):
        match = re.search(pattern, text)
        if match:
            return _number(match.group(1))
    return None


def _fetch_google_patents_count(assignee: str) -> int | None:
    """Count public patent publications for an assignee.

    Google Patents is used only when the configured Wencai/THS transports do
    not return a patent count.  It requires no local browser or account.
    """

    name = _text(assignee)
    if not name:
        return None
    query = f"assignee={name}&country=CN"
    url = f"{GOOGLE_PATENTS_QUERY_URL}?url={quote(query, safe='')}&exp="
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://patents.google.com/",
    }
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code in {429, 503}:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            payload = response.json()
            total = ((payload or {}).get("results") or {}).get(
                "total_num_results"
            )
            value = _number(total)
            if value is not None:
                return int(value)
        except Exception:
            if attempt == 2:
                return None
            time.sleep(2 * (attempt + 1))
    return None


def _fetch_eastmoney_holder_payload(code: str) -> dict[str, Any]:
    """Fetch the public F10 shareholder disclosure page.

    The page is used only when the official Wencai query returns no holder
    records.  It is a disclosed-data fallback, not a reconstructed estimate.
    """

    prefix = _eastmoney_market_prefix(code)
    payload = _fetch_eastmoney_json(f"{EASTMONEY_HOLDER_URL}?code={prefix}{code}")
    if not isinstance(payload, dict):
        raise ValueError("东方财富 F10 返回结构无效")
    return payload


def _eastmoney_secid(code: str) -> str:
    """Return the Eastmoney quote secid for a six-digit A-share code."""

    prefix = _eastmoney_market_prefix(code)
    return f"{'1' if prefix == 'SH' else '0'}.{code}"


def _scaled_quote_number(value: Any) -> float | None:
    number = _number(value)
    return number / 100 if number is not None else None


def _cap_yuan(value: Any) -> float | None:
    """Normalize public market-cap values that may be expressed in 亿元."""

    number = _number(value)
    if number is None:
        return None
    return number * 1e8 if abs(number) < 1e8 else number


def _eastmoney_stock_quote(code: str) -> dict[str, Any]:
    """Fetch one quote through the endpoint that remains available when ulist fails."""

    payload = _fetch_eastmoney_json(
        f"{EASTMONEY_STOCK_URL}?secid={_eastmoney_secid(code)}"
        "&fields=f43,f44,f45,f46,f47,f48,f51,f52,f57,f58,f60,f62,"
        "f84,f85,f116,f117,f162,f164,f167,f168,f170,f171,f184",
        referer=EASTMONEY_QUOTE_REFERER,
    )
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {}
    quote_code = _text(data.get("f57"))
    if not re.fullmatch(r"\d{6}", quote_code):
        quote_code = code
    return {
        "f2": _scaled_quote_number(data.get("f43")),
        "f3": _scaled_quote_number(data.get("f170")),
        "f5": _number(data.get("f47")),
        "f6": _number(data.get("f48")),
        "f7": _scaled_quote_number(data.get("f171")),
        "f8": _scaled_quote_number(data.get("f168")),
        "f9": _scaled_quote_number(data.get("f162")),
        "f12": quote_code,
        "f14": re.sub(r"\s+", "", _text(data.get("f58"))),
        "f15": _scaled_quote_number(data.get("f44")),
        "f16": _scaled_quote_number(data.get("f45")),
        "f17": _scaled_quote_number(data.get("f46")),
        "f18": _scaled_quote_number(data.get("f60")),
        "f20": _number(data.get("f116")),
        "f21": _number(data.get("f117")),
        "f23": _scaled_quote_number(data.get("f167")),
        "f25": _scaled_quote_number(data.get("f25")),
        "f51": _scaled_quote_number(data.get("f51")),
        "f52": _scaled_quote_number(data.get("f52")),
        "f62": _number(data.get("f62")),
        "f84": _number(data.get("f84")),
        "f85": _number(data.get("f85")),
        "f164": _scaled_quote_number(data.get("f164")),
        "f184": _scaled_quote_number(data.get("f184")),
    }


def _eastmoney_quote_snapshot(codes: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Fetch current quote and valuation fields keyed by six-digit code."""

    unique: list[str] = []
    for code in codes:
        text = _text(code)[-6:]
        if re.fullmatch(r"\d{6}", text) and text not in unique:
            unique.append(text)
    fields = (
        "f2,f3,f5,f6,f7,f8,f9,f12,f14,f15,f16,f17,f18,"
        "f20,f21,f23,f51,f52,f62,f84,f85,f164,f168,f170,f171"
    )
    output: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for start in range(0, len(unique), 40):
        chunk = unique[start : start + 40]
        secids = ",".join(_eastmoney_secid(code) for code in chunk)
        try:
            payload = _fetch_eastmoney_json(
                f"{EASTMONEY_QUOTE_URL}?fltt=2&invt=2&fields={fields}&secids={secids}",
                referer=EASTMONEY_QUOTE_REFERER,
            )
        except Exception as exc:
            errors.append(f"批量行情请求失败：{exc}")
            continue
        for item in ((payload or {}).get("data") or {}).get("diff") or []:
            if not isinstance(item, dict):
                continue
            code = _text(item.get("f12"))
            if re.fullmatch(r"\d{6}", code):
                output[code] = item
    for code in unique:
        current = output.get(code) or {}
        if _number(current.get("f9")) is not None and _number(current.get("f23")) is not None:
            continue
        try:
            quote = _eastmoney_stock_quote(code)
        except Exception as exc:
            errors.append(f"{code} 单只行情请求失败：{exc}")
            continue
        if quote:
            output[code] = {**current, **quote}
    if not output:
        detail = "；".join(errors[:3])
        raise ValueError("东方财富行情未返回数据" + (f"（{detail}）" if detail else ""))
    return output


def _tencent_quote_snapshot(codes: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Fetch a complete quote snapshot from Tencent's public response."""

    unique: list[str] = []
    for code in codes:
        text = _text(code)[-6:]
        if re.fullmatch(r"\d{6}", text) and text not in unique:
            unique.append(text)
    if not unique:
        return {}
    output: dict[str, dict[str, Any]] = {}
    for start in range(0, len(unique), 50):
        chunk = unique[start : start + 50]
        symbols = ",".join(
            ("sh" if code.startswith(("6", "9")) else "sz") + code
            for code in chunk
        )
        response = requests.get(
            TENCENT_QUOTE_URL + symbols,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://gu.qq.com/",
            },
            timeout=EASTMONEY_TIMEOUT,
        )
        response.raise_for_status()
        text = response.content.decode("gbk", "replace")
        for statement in text.split(";"):
            fields = statement.split("~")
            if len(fields) < 63:
                continue
            code = _text(fields[2])
            if not re.fullmatch(r"\d{6}", code):
                continue

            def field(index: int) -> Any:
                return fields[index] if index < len(fields) else None

            market_cap_yi = _number(field(44))
            circulating_cap_yi = _number(field(45))
            volume_lots = _number(field(36))
            amount_wan = _number(field(37))
            output[code] = {
                "name": re.sub(r"\s+", "", _text(field(1))),
                "price": _number(field(3)),
                "prev_close": _number(field(4)),
                "open": _number(field(5)),
                "volume": volume_lots * 100 if volume_lots is not None else None,
                "amount": amount_wan * 10000 if amount_wan is not None else None,
                "change_pct": _number(field(32)),
                "high": _number(field(33)),
                "low": _number(field(34)),
                "turnover_rate": _number(field(38)),
                "pe": _number(field(39)),
                "amplitude": _number(field(43)),
                "market_cap": (
                    market_cap_yi * 1e8 if market_cap_yi is not None else None
                ),
                "circulating_cap": (
                    circulating_cap_yi * 1e8
                    if circulating_cap_yi is not None
                    else None
                ),
                "pb": _number(field(46)),
                "limit_up": _number(field(47)),
                "limit_down": _number(field(48)),
                "ytd_change": _number(field(62)),
                "5d_change": _number(field(63)),
                "total_shares": _number(field(73)),
                "float_shares": _number(field(72)),
            }
    return output


def _apply_tencent_quote_fallback(
    stocks: list[dict[str, Any]],
    quotes: dict[str, dict[str, Any]],
) -> list[str]:
    """Fill only missing stock fields, preserving every existing vendor value."""

    filled: list[str] = []
    for item in stocks:
        quote = quotes.get(_text(item.get("ticker"))) or {}
        if not quote:
            continue
        used = False
        for key in ("price", "change_pct", "pe", "pb", "ytd_change"):
            if item.get(key) is None and quote.get(key) is not None:
                item[key] = quote[key]
                used = True
        if item.get("market_cap") is None and quote.get("market_cap") is not None:
            item["market_cap"] = quote["market_cap"]
            used = True
        if item.get("market_cap") is not None:
            item["market_cap_yi"] = round(item["market_cap"] / 1e8, 2)
        if not used:
            continue
        sources = list(item.get("data_sources") or [])
        if "tencent" not in sources:
            sources.append("tencent")
        item["data_sources"] = sources
        filled.append(str(item.get("ticker") or ""))
    return filled


def _fill_missing_dividend_yields(stocks: list[dict[str, Any]]) -> None:
    """Recalculate dividend yields after a quote fallback supplies the price."""

    for stock in stocks:
        if stock.get("dividend_yield") is not None:
            continue
        price = _number(stock.get("price"))
        if price is None:
            continue
        stock["dividend_yield"] = _eastmoney_dividend_yield(
            str(stock.get("ticker") or ""),
            price,
        )


def _eastmoney_annual_reports(code: str) -> dict[int, dict[str, Any]]:
    """Return disclosed annual reports keyed by report year."""

    prefix = _eastmoney_market_prefix(code)
    payload = _fetch_eastmoney_json(
        f"{EASTMONEY_FINANCE_URL}?type=1&code={prefix}{code}"
    )
    if not isinstance(payload, dict):
        raise ValueError("东方财富年度财务返回结构无效")
    annual: dict[int, dict[str, Any]] = {}
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        date = _text(item.get("REPORT_DATE"))
        report_year = _text(item.get("REPORT_YEAR")) or date[:4]
        is_annual = _text(item.get("REPORT_TYPE")) == "年报" or date.startswith(
            report_year + "-12-31"
        )
        if not is_annual or not report_year.isdigit():
            continue
        annual[int(report_year)] = item
    if not annual:
        raise ValueError("东方财富未返回年度财务数据")
    return annual


def _eastmoney_annual_financials(code: str, target_year: int) -> dict[str, Any]:
    """Return the latest disclosed annual report at or before target year."""

    annual = _eastmoney_annual_reports(code)
    eligible = [year for year in annual if year <= target_year]
    selected_year = max(eligible or annual)
    selected = annual[selected_year]
    try:
        income = _eastmoney_income_reports(code).get(selected_year) or {}
    except Exception:
        income = {}
    if income:
        selected = {**selected}
        # Eastmoney's ZYZBAjaxNew field TOTALOPERATEREVE is total operating
        # revenue (营业总收入), while the local/Wencai report uses operating
        # revenue (营业收入). Prefer the income statement field so the same
        # label carries the same accounting definition on both sides.
        if income.get("OPERATE_INCOME") is not None:
            selected["TOTALOPERATEREVE"] = income["OPERATE_INCOME"]
        if income.get("OPERATE_INCOME_YOY") is not None:
            selected["TOTALOPERATEREVETZ"] = income["OPERATE_INCOME_YOY"]
        if income.get("PARENT_NETPROFIT") is not None:
            selected["PARENTNETPROFIT"] = income["PARENT_NETPROFIT"]
        if income.get("PARENT_NETPROFIT_YOY") is not None:
            selected["PARENTNETPROFITTZ"] = income["PARENT_NETPROFIT_YOY"]
        selected["_INCOME_STATEMENT"] = income
    return {**selected, "_SELECTED_REPORT_YEAR": selected_year}


def _eastmoney_income_reports(code: str) -> dict[int, dict[str, Any]]:
    """Return annual income statement rows keyed by report year."""

    prefix = _eastmoney_market_prefix(code)
    params = {
        "source": "HSF10",
        "client": "PC",
        "reportName": "RPT_F10_FINANCE_GINCOME",
        "columns": "ALL",
        "filter": f'(SECUCODE="{code}.{prefix}")(REPORT_TYPE="年报")',
        "pageNumber": 1,
        "pageSize": 12,
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
    }
    payload = _fetch_eastmoney_json(
        f"{EASTMONEY_DATACENTER_URL}?{urlencode(params)}"
    )
    rows = [
        dict(item)
        for item in (((payload or {}).get("result") or {}).get("data") or [])
        if isinstance(item, dict)
    ]
    annual: dict[int, dict[str, Any]] = {}
    for item in rows:
        date = _text(item.get("REPORT_DATE"))
        report_year = date[:4]
        if report_year.isdigit() and date.startswith(report_year + "-12-31"):
            annual[int(report_year)] = item
    return annual


def _eastmoney_main_business(code: str) -> dict[str, str]:
    """Return disclosed product names for one security from the F10 page."""

    if not code:
        return {}
    prefix = _eastmoney_market_prefix(code)
    try:
        payload = _fetch_eastmoney_json(
            f"{EASTMONEY_BUSINESS_ANALYSIS_URL}?code={prefix}{code}"
        )
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    rows = [
        dict(item)
        for item in payload.get("zygcfx") or []
        if isinstance(item, dict) and _text(item.get("ITEM_NAME"))
    ]
    if rows:
        latest = max(
            (_date_key(item.get("REPORT_DATE")) for item in rows),
            default="",
        )
        if latest:
            rows = [
                item
                for item in rows
                if _date_key(item.get("REPORT_DATE")) == latest
            ]
        products = [item for item in rows if _text(item.get("MAINOP_TYPE")) == "2"]
        if not products:
            products = rows
        products.sort(
            key=lambda item: _number(item.get("MBI_RATIO")) or -1,
            reverse=True,
        )
        names: list[str] = []
        for item in products:
            name = _text(item.get("ITEM_NAME"))
            if name and name not in names:
                names.append(name)
        if names:
            return {
                "main_business": "||".join(names[:20]),
                "period": latest,
            }
    scope_rows = payload.get("zyfw") or []
    if isinstance(scope_rows, dict):
        scope_rows = [scope_rows]
    scope = next(
        (
            _text(item.get("BUSINESS_SCOPE"))
            for item in scope_rows
            if isinstance(item, dict) and _text(item.get("BUSINESS_SCOPE"))
        ),
        "",
    )
    if scope:
        return {"main_business": scope[:600], "period": "经营范围"}
    return {}


def _eastmoney_dividend_yield(code: str, price: float | None) -> float | None:
    """Compute a trailing-12-month cash dividend yield from F10 disclosures."""

    if not code or price is None or price <= 0:
        return None
    prefix = _eastmoney_market_prefix(code)
    try:
        payload = _fetch_eastmoney_json(
            f"{EASTMONEY_BONUS_URL}?code={prefix}{code}"
        )
    except Exception:
        return None
    rows = payload.get("fhyx") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    cutoff = datetime.now(CN_TZ) - timedelta(days=370)
    total_per_share = 0.0
    found = False
    for item in rows:
        if not isinstance(item, dict):
            continue
        if "实施方案" not in _text(item.get("ASSIGN_PROGRESS")):
            continue
        date_text = _text(item.get("EX_DIVIDEND_DATE")) or _text(
            item.get("NOTICE_DATE")
        )
        try:
            event_date = datetime.strptime(date_text[:10], "%Y-%m-%d").replace(
                tzinfo=CN_TZ
            )
        except ValueError:
            continue
        if event_date < cutoff:
            continue
        match = re.search(
            r"10\s*派\s*([0-9]+(?:\.[0-9]+)?)\s*元",
            _text(item.get("IMPL_PLAN_PROFILE")),
        )
        if not match:
            continue
        total_per_share += float(match.group(1)) / 10.0
        found = True
    if not found:
        return 0.0
    return round(total_per_share / price * 100.0, 4)


_EASTMONEY_INDUSTRY_BOARD_CACHE: dict[str, str] | None = None


def _eastmoney_industry_boards() -> dict[str, str]:
    """Return the Eastmoney industry-board code map keyed by display name."""

    global _EASTMONEY_INDUSTRY_BOARD_CACHE
    if _EASTMONEY_INDUSTRY_BOARD_CACHE is not None:
        return _EASTMONEY_INDUSTRY_BOARD_CACHE
    boards: dict[str, str] = {}
    page = 1
    while page <= 8:
        payload = _fetch_eastmoney_json(
            f"{EASTMONEY_SECTOR_LIST_URL}?pn={page}&pz=100&po=1&np=1"
            "&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f12,f14"
        )
        data = (payload or {}).get("data") or {}
        rows = [item for item in data.get("diff") or [] if isinstance(item, dict)]
        if not rows:
            break
        for item in rows:
            code = _text(item.get("f12"))
            name = _normalize_name(item.get("f14"))
            if code and name:
                boards.setdefault(name, code)
        total = int(_number(data.get("total")) or 0)
        if total and page * 100 >= total:
            break
        if len(rows) < 100:
            break
        page += 1
    _EASTMONEY_INDUSTRY_BOARD_CACHE = boards
    return boards


def _eastmoney_industry_name(code: str) -> str:
    """Return the Eastmoney industry label for one security."""

    if not code:
        return ""
    payload = _fetch_eastmoney_json(
        f"{EASTMONEY_QUOTE_URL}?fltt=2&invt=2&fields=f12,f14,f100"
        f"&secids={_eastmoney_secid(code)}",
        referer=EASTMONEY_QUOTE_REFERER,
    )
    rows = ((payload or {}).get("data") or {}).get("diff") or []
    for item in rows:
        if isinstance(item, dict) and _text(item.get("f12"))[-6:] == code[-6:]:
            return _normalize_name(item.get("f100"))
    return ""


def _eastmoney_industry_members(industry_name: str) -> list[dict[str, Any]]:
    """Return all A-share members of one Eastmoney industry board."""

    normalized = _normalize_name(industry_name)
    if not normalized:
        return []
    board = _eastmoney_industry_boards().get(normalized)
    if not board:
        return []
    fields = (
        "f2,f3,f9,f12,f14,f20,f21,f23,f25,"
        "f37,f40,f41,f45,f46,f49,f100"
    )
    members: list[dict[str, Any]] = []
    page = 1
    while page <= 5:
        payload = _fetch_eastmoney_json(
            f"{EASTMONEY_SECTOR_LIST_URL}?pn={page}&pz=100&po=1&np=1"
            f"&fltt=2&invt=2&fid=f20&fs=b:{board}&fields={fields}",
            referer=EASTMONEY_QUOTE_REFERER,
        )
        data = (payload or {}).get("data") or {}
        rows = [item for item in data.get("diff") or [] if isinstance(item, dict)]
        if not rows:
            break
        for item in rows:
            code = _text(item.get("f12"))
            if not re.fullmatch(r"(?:60|68|00|30)\d{4}", code):
                continue
            row_industry = _normalize_name(item.get("f100"))
            if row_industry and row_industry != normalized:
                continue
            members.append(item)
        total = int(_number(data.get("total")) or 0)
        if total and page * 100 >= total:
            break
        if len(rows) < 100:
            break
        page += 1
    unique: dict[str, dict[str, Any]] = {}
    for item in members:
        code = _text(item.get("f12"))
        if code and code not in unique:
            unique[code] = item
    return list(unique.values())


def _eastmoney_sector_board(keyword: str) -> dict[str, str]:
    """Resolve an industry name to the public Eastmoney board identifier."""

    normalized = _normalize_name(keyword)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    queries = [keyword.strip(), normalized]
    for query in list(dict.fromkeys(item for item in queries if item)):
        try:
            payload = _fetch_eastmoney_json(
                f"{EASTMONEY_SECTOR_SEARCH_URL}?"
                + urlencode(
                    {
                        "input": query,
                        "type": "14",
                        "token": "D43BF722C8E33BDC906FB84D85E326E8",
                        "markettype": "",
                        "mktnum": "",
                        "jys": "",
                        "classify": "",
                        "securitytype": "",
                        "status": "",
                        "count": "20",
                    }
                ),
                referer=EASTMONEY_QUOTE_REFERER,
            )
        except Exception as exc:
            errors.append(f"搜索：{exc}")
            continue
        candidates = (
            ((payload or {}).get("QuotationCodeTable") or {}).get("Data") or []
            if isinstance(payload, dict)
            else []
        )
        rows = [
            item
            for item in candidates
            if isinstance(item, dict)
            and _text(item.get("Code")).upper().startswith("BK")
            and _text(item.get("MktNum")) == "90"
        ]
        if rows:
            break
    if not rows:
        try:
            for page in range(1, 4):
                payload = _fetch_eastmoney_json(
                    f"{EASTMONEY_SECTOR_LIST_URL}?"
                    + urlencode(
                        {
                            "pn": str(page),
                            "pz": "100",
                            "po": "1",
                            "np": "1",
                            "fltt": "2",
                            "invt": "2",
                            "fid": "f12",
                            "fs": "m:90+t:2",
                            "fields": "f12,f14",
                        }
                    ),
                    referer=EASTMONEY_QUOTE_REFERER,
                )
                page_rows = (payload.get("data") or {}).get("diff") or []
                rows.extend(
                    {
                        "Code": _text(item.get("f12")),
                        "Name": _text(item.get("f14")),
                        "QuoteID": f"90.{_text(item.get('f12'))}",
                    }
                    for item in page_rows
                    if isinstance(item, dict)
                    and _text(item.get("f12")).upper().startswith("BK")
                )
                if len(page_rows) < 100:
                    break
        except Exception as exc:
            errors.append(f"板块列表：{exc}")
    if not rows:
        detail = "；".join(errors)
        raise ValueError(
            f"东方财富未找到板块：{normalized or keyword}"
            + (f"（{detail}）" if detail else "")
        )
    exact = [
        item
        for item in rows
        if _text(item.get("Name")) == keyword.strip()
    ]
    same_level = [
        item
        for item in rows
        if _normalize_name(item.get("Name")) == normalized
    ]
    same_level.sort(
        key=lambda item: (
            0 if _text(item.get("Name")).endswith("Ⅲ") else
            1 if _text(item.get("Name")).endswith("Ⅱ") else 2,
            _text(item.get("Code")),
        )
    )
    hit = (exact or same_level or rows)[0]
    code = _text(hit.get("Code")).upper()
    if not re.fullmatch(r"BK\d{4}", code):
        raise ValueError(f"东方财富板块代码无效：{code or 'empty'}")
    return {
        "code": code,
        "secid": _text(hit.get("QuoteID")) or f"90.{code}",
        "name": _text(hit.get("Name")) or normalized,
    }


def _eastmoney_sector_metrics(keyword: str) -> dict[str, Any]:
    """Return verified board returns, fund flow and volume ratio.

    The board search resolves the public BK code.  Daily closes are used for
    the 5/10/20 trading-session returns; main flow comes from the current fund
    flow row, and volume ratio uses the quote field or the same daily-volume
    ratio when that field is unavailable.
    """

    board = _eastmoney_sector_board(keyword)
    errors: list[str] = []
    metrics: dict[str, float] = {}
    try:
        quote_payload = _fetch_eastmoney_json(
            f"{EASTMONEY_STOCK_URL}?"
            + urlencode(
                {
                    "fltt": "2",
                    "invt": "2",
                    "secid": board["secid"],
                    "fields": "f43,f50,f57,f58,f60,f170",
                }
            ),
            referer=EASTMONEY_QUOTE_REFERER,
        )
    except Exception as exc:
        errors.append(f"行情：{exc}")
        quote_payload = {}
    quote = (
        (quote_payload or {}).get("data")
        if isinstance(quote_payload, dict)
        else None
    )
    if not isinstance(quote, dict):
        quote = {}
    try:
        kline_payload = _fetch_eastmoney_json(
            f"{EASTMONEY_SECTOR_KLINE_URL}?"
            + urlencode(
                {
                    "secid": board["secid"],
                    "ut": EASTMONEY_UT,
                    "klt": "101",
                    "fqt": "1",
                    "lmt": "60",
                    "end": "20500101",
                    "fields1": "f1,f2,f3,f4,f5,f6",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                }
            ),
            referer=EASTMONEY_QUOTE_REFERER,
        )
    except Exception as exc:
        errors.append(f"日线：{exc}")
        kline_payload = {}
    kline_data = (
        (kline_payload or {}).get("data")
        if isinstance(kline_payload, dict)
        else None
    )
    rows: list[tuple[str, float, float | None, float | None]] = []
    for line in (kline_data or {}).get("klines") or []:
        parts = str(line).split(",")
        if len(parts) < 7:
            continue
        close = _number(parts[2])
        if close is None:
            continue
        change_pct = _number(parts[8]) if len(parts) > 8 else None
        rows.append((parts[0], close, _number(parts[5]), change_pct))
    if len(rows) < 21:
        errors.append(
            f"日线不足 21 条：{board['code']}，实际 {len(rows)}"
        )
    else:
        for days in (5, 10, 20):
            base = rows[-1 - days][1]
            if base:
                metrics[f"{days}日涨幅"] = round((rows[-1][1] / base - 1) * 100, 6)
    change = _number(quote.get("f170"))
    if change is None and rows:
        change = rows[-1][3]
    if change is not None:
        metrics["涨幅"] = change
    volume_ratio = _number(quote.get("f50"))
    if volume_ratio is None:
        previous_volumes = [
            volume
            for _, _, volume, _ in rows[-6:-1]
            if volume is not None and volume > 0
        ]
        current_volume = rows[-1][2] if rows else None
        if (
            len(previous_volumes) == 5
            and current_volume is not None
            and current_volume > 0
        ):
            volume_ratio = round(
                current_volume / (sum(previous_volumes) / 5),
                6,
            )
    if volume_ratio is not None:
        metrics["量比"] = volume_ratio

    try:
        flow_payload = _fetch_eastmoney_json(
            f"{EASTMONEY_SECTOR_FLOW_URL}?"
            + urlencode(
                {
                    "lmt": "10",
                    "klt": "101",
                    "ut": EASTMONEY_UT,
                    "secid": board["secid"],
                    "fields1": "f1,f2,f3,f7",
                    "fields2": "f51,f52,f53,f54,f55,f56",
                }
            ),
            referer=EASTMONEY_QUOTE_REFERER,
        )
    except Exception as exc:
        errors.append(f"资金流：{exc}")
        flow_payload = {}
    flow_data = (
        (flow_payload or {}).get("data")
        if isinstance(flow_payload, dict)
        else None
    )
    flow_rows = [
        str(line).split(",")
        for line in (flow_data or {}).get("klines") or []
        if str(line).strip()
    ]
    if flow_rows:
        main_flow = _number(flow_rows[-1][1]) if len(flow_rows[-1]) > 1 else None
        if main_flow is not None:
            metrics["主力净流入"] = main_flow

    if not metrics:
        raise ValueError(
            f"东方财富板块指标为空：{board['code']}；{'；'.join(errors)}"
        )

    return {
        "board": board,
        "as_of": rows[-1][0] if rows else "",
        "metrics": metrics,
        "errors": errors,
        "raw": {
            "quote": quote,
            "kline_tail": rows[-21:],
            "flow_tail": flow_rows[-1:] if flow_rows else [],
        },
    }


def _hithink_sector_metrics(
    sector_code: str,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fill sector returns and volume ratio from the official THS index feed."""

    code = _text(sector_code).upper()
    if code.startswith("URFI") and len(code) > 4:
        code = f"{code[4:]}.TI"
    elif re.fullmatch(r"\d{6}", code):
        code = f"{code}.TI"
    if not re.fullmatch(r"\d{6}\.TI", code):
        raise ValueError(f"同花顺行业指数代码无效：{sector_code or 'empty'}")
    end = datetime.now(CN_TZ)
    start = end - timedelta(days=70)
    payload = hithink.call(
        "index",
        "history",
        "--thscode",
        code,
        "--start-ms",
        str(int(start.timestamp() * 1000)),
        "--end-ms",
        str(int(end.timestamp() * 1000)),
        timeout=60,
    )
    rows = sorted(
        (
            row
            for row in payload.get("item") or []
            if isinstance(row, dict) and _number(row.get("close_price")) is not None
        ),
        key=lambda row: int(row.get("date_ms") or 0),
    )
    if len(rows) < 21:
        raise ValueError(f"同花顺行业日线不足 21 条：{code}，实际 {len(rows)}")
    closes = [_number(row.get("close_price")) for row in rows]
    metrics: dict[str, float] = {}
    for days in (5, 10, 20):
        base = closes[-1 - days]
        if base:
            metrics[f"{days}日涨幅"] = round((closes[-1] / base - 1) * 100, 6)
    snapshot = snapshot or {}
    change = _number(snapshot.get("涨幅"))
    if change is None and len(closes) >= 2 and closes[-2]:
        change = round((closes[-1] / closes[-2] - 1) * 100, 6)
    if change is not None:
        metrics["涨幅"] = change
    volume = _number(snapshot.get("成交量"))
    if volume is None:
        volume = _number(rows[-1].get("volume"))
    previous_volumes = [
        _number(row.get("volume"))
        for row in rows[-6:-1]
    ]
    if (
        volume is not None
        and volume > 0
        and len(previous_volumes) == 5
        and all(value is not None and value > 0 for value in previous_volumes)
    ):
        metrics["量比"] = round(volume / (sum(previous_volumes) / 5), 6)
    as_of = datetime.fromtimestamp(
        int(rows[-1].get("date_ms") or 0) / 1000,
        CN_TZ,
    ).strftime("%Y-%m-%d")
    return {
        "board": {"code": code, "secid": code, "name": _text(snapshot.get("名称")) or code},
        "as_of": as_of,
        "metrics": metrics,
        "raw": {"history_tail": [_json_value(row) for row in rows[-21:]]},
    }


def _thsdk_sector_metrics(
    sector_code: str,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read the same extended block snapshot used by the local collector."""

    code = _text(sector_code).upper()
    if code.startswith("URFI"):
        block_code = code
    elif re.fullmatch(r"\d{6}\.TI", code):
        block_code = f"URFI{code.split('.')[0]}"
    elif re.fullmatch(r"\d{6}", code):
        block_code = f"URFI{code}"
    else:
        raise ValueError(f"同花顺板块代码无效：{sector_code or 'empty'}")

    response = None
    errors: list[str] = []
    with mq.ThsClient() as client:
        for query_key in ("扩展", "基础数据"):
            try:
                response = client.ths.market_data_block(block_code, query_key)
            except Exception as exc:
                errors.append(f"{query_key}：{exc}")
                continue
            if (
                not response.error
                and response.df is not None
                and len(response.df)
            ):
                break
            if response.error:
                errors.append(f"{query_key}：{response.error}")
    if response is None or response.error or response.df is None or not len(response.df):
        raise ValueError(
            f"同花顺板块快照为空：{block_code}"
            + (f"；{'；'.join(errors)}" if errors else "")
        )
    rows = mq.records(response.df)
    if not rows:
        raise ValueError(f"同花顺板块快照没有记录：{block_code}")
    row = rows[0]
    metrics = {
        key: value
        for key in INDUSTRY_SNAPSHOT_FIELDS
        if (value := _number(row.get(key))) is not None
    }
    if not metrics:
        raise ValueError(f"同花顺板块快照缺少指标：{block_code}")
    snapshot = snapshot or {}
    return {
        "board": {
            "code": block_code,
            "secid": block_code,
            "name": _text(snapshot.get("名称")) or block_code,
        },
        "as_of": _text(_first(row, "日期", "数据日期", "更新时间", "时间")),
        "metrics": metrics,
        "raw": {"row": _json_value(row)},
    }


def _previous_close(row: dict[str, Any]) -> float | None:
    """Return the prior close when the vendor exposes dated close columns.

    iWencai answers a "昨收价" request with ``收盘价[YYYYMMDD]`` columns
    instead of a field literally named 昨收价.  Prefer a dated column that is
    not today's session, then fall back to the latest dated close.
    """

    direct = _number(_first(row, "昨收价", "昨收", "昨日收盘价"))
    if direct is not None:
        return direct
    dated = sorted(str(key) for key in row if str(key).startswith("收盘价["))
    if not dated:
        return None
    today = datetime.now(CN_TZ).strftime("%Y%m%d")
    prior = [key for key in dated if today not in key]
    return _number(row.get((prior or dated)[-1]))


def _wencai_client() -> tuple[mq.WencaiClient, str]:
    key, source = mq.wencai_api_key()
    if not key:
        raise CloudSourceError(
            "官方问财 OpenAPI 未配置 IWENCAI_API_KEY；将使用公开数据源降级",
            "missing_api_key",
        )
    return mq.WencaiClient(key, timeout=WENCAI_TIMEOUT), source or "env"


def _optional_wencai_client() -> tuple[mq.WencaiClient | None, str, str]:
    try:
        client, source = _wencai_client()
        return client, source, ""
    except CloudSourceError as exc:
        return None, "", str(exc)


def _safe_market_client() -> tuple[mq.CloudClient | None, str]:
    try:
        return mq.CloudClient(timeout=30), ""
    except mq.QueryError as exc:
        return None, str(exc)


class CloudStockAdapter:
    """Adapter exposing the subset of the THS client used by the stock collector."""

    source = "cloud"
    is_cloud = True
    _initialized = True

    def __init__(self) -> None:
        self.wencai, self.wencai_source, self.wencai_error = (
            _optional_wencai_client()
        )
        self.market, self.market_error = _safe_market_client()
        if not self.market:
            raise CloudSourceError(
                f"云端个股报告需要 FUYAO_API_KEY；{self.market_error or '扶摇行情凭据未配置'}",
                "missing_api_key",
            )
        self._names: dict[str, str] = {}
        self._cache: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._news_cache: list[dict[str, Any]] | None = None
        self.stock_name = ""
        self._stock_code = ""
        self.holders_source = ""
        self.holders_error = ""
        self.peers_source = ""
        self.peers_error = ""
        self.peers_expected_count = 0
        self.peers_scope = ""
        self.finance_source = ""
        self.finance_error = ""
        self.quote_source = ""
        self.quote_fallback_error = ""
        self.quote_fill_sources: list[str] = []
        self.chip_sources: list[str] = []
        self.barrier_sources: list[str] = []
        self.product_source = ""
        self.product_error = ""
        self._ths_client: mq.ThsClient | None = None
        self._ths_connect_error = ""
        self._ths_connect_retry_at = 0.0
        self._last_ths_query_at = 0.0
        self._f10_payload_cache: dict[str, Any] | None = None
        self._f10_payload_error = ""
        self._company_survey_cache: dict[str, Any] | None = None
        self._annual_report_cache: dict[str, Any] | None = None

    def __enter__(self) -> "CloudStockAdapter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._reset_ths_client()
        return None

    def _reset_ths_client(self) -> None:
        client = getattr(self, "_ths_client", None)
        self._ths_client = None
        if client is not None:
            try:
                client.__exit__(None, None, None)
            except Exception:
                pass

    def connect(self, max_retries: int = 1) -> SimpleNamespace:
        return SimpleNamespace(error="", connected=True)

    def _record_source(self, domain: str, source: str) -> None:
        attribute = f"{domain}_sources"
        values = list(getattr(self, attribute, []) or [])
        if source and source not in values:
            values.append(source)
        setattr(self, attribute, values)

    def _ths_connection(self) -> mq.ThsClient | None:
        client = getattr(self, "_ths_client", None)
        if client is not None:
            return client
        now = time.monotonic()
        retry_at = getattr(self, "_ths_connect_retry_at", 0.0)
        if retry_at and now < retry_at:
            return None
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                client = mq.ThsClient()
                client.__enter__()
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                break
            self._ths_client = client
            self._ths_connect_error = ""
            self._ths_connect_retry_at = 0.0
            return client
        self._ths_connect_error = f"同花顺 thsdk 连接失败：{last_error}"
        self._ths_connect_retry_at = now + 60.0
        return None

    def _ths_wencai_frame(self, query: str, limit: int = 20) -> SimpleNamespace:
        client = self._ths_connection()
        if client is None:
            return _empty(
                getattr(self, "_ths_connect_error", "")
                or "同花顺 thsdk 不可用"
            )
        last_query_at = getattr(self, "_last_ths_query_at", 0.0)
        wait = 0.6 - (time.monotonic() - last_query_at)
        if wait > 0:
            time.sleep(wait)
        try:
            payload = client.wencai(query, page=1, limit=limit)
        except Exception as exc:
            message = str(exc)
            if "请先连接" not in message and "not connect" not in message.lower():
                return _empty(f"同花顺 thsdk 问财查询失败：{message}")
            self._reset_ths_client()
            client = self._ths_connection()
            if client is None:
                return _empty(
                    getattr(self, "_ths_connect_error", "")
                    or "同花顺 thsdk 重连失败"
                )
            try:
                payload = client.wencai(query, page=1, limit=limit)
            except Exception as retry_exc:
                return _empty(f"同花顺 thsdk 问财重连后失败：{retry_exc}")
        finally:
            self._last_ths_query_at = time.monotonic()
        return _frame_result(payload)

    def _query(self, query: str, skill_id: str = "hithink-finance-query", limit: int = 20) -> SimpleNamespace:
        if self.wencai is None:
            return _empty(self.wencai_error or "官方问财 OpenAPI 未配置")
        cache_key = (skill_id, query, int(limit))
        if cache_key in self._cache:
            return _frame_result(self._cache[cache_key])
        try:
            payload = self.wencai.query(skill_id, query, page=1, limit=limit)
        except mq.QueryError as exc:
            return _empty(str(exc))
        self._cache[cache_key] = payload
        if QUERY_DELAY > 0:
            time.sleep(QUERY_DELAY)
        return _frame_result(payload)

    def _name_for(self, thscode: str) -> str:
        code = str(thscode)[-6:]
        if re.fullmatch(r"\d{6}", code):
            self._stock_code = code
        name = self._names.get(code)
        if name:
            return name
        if self.market:
            try:
                result = self.market.search(code, limit=5)
            except mq.QueryError:
                result = {}
            for item in result.get("items") or []:
                if str(item.get("ticker") or "") == code:
                    self._names[code] = str(item.get("name") or code)
                    return self._names[code]
        return self.stock_name or code

    def search_symbols(self, keyword: str) -> SimpleNamespace:
        if not self.market:
            return _empty(self.market_error or "扶摇行情凭据未配置")
        try:
            result = self.market.search(keyword, limit=20)
        except mq.QueryError as exc:
            return _empty(str(exc))
        display = {"SH": "沪A", "SZ": "深A", "BJ": "北A"}
        rows = []
        for item in result.get("items") or []:
            if str(item.get("asset_type") or "") != "a-share":
                continue
            code = str(item.get("ticker") or "")
            name = _text(item.get("name")) or code
            thscode = str(item.get("thscode") or "")
            if not code or not thscode:
                continue
            self._names[code] = name
            rows.append(
                {
                    "Code": code,
                    "Name": name,
                    "THSCODE": thscode,
                    "MarketDisplay": display.get(str(item.get("exchange") or ""), "A股"),
                }
            )
        frame = pd.DataFrame(rows, columns=["Code", "Name", "THSCODE", "MarketDisplay"])
        return SimpleNamespace(df=frame, error="" if rows else "empty")

    def _quote_rows(self, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
        first = self._query(
            f"{name} 最新价 最新涨跌幅 成交量 成交额 总市值 流通市值 市盈率TTM 换手率 振幅",
            "hithink-market-query",
            limit=5,
        )
        second = self._query(
            f"{name} 开盘价 最高价 最低价 昨收价 涨停价 跌停价 主力净流入 5日涨幅",
            "hithink-market-query",
            limit=5,
        )
        row_one = first.df.iloc[0].to_dict() if not first.df.empty else {}
        row_two = second.df.iloc[0].to_dict() if not second.df.empty else {}
        return row_one, row_two

    def _thsdk_quote_fallback(self, thscode: str) -> dict[str, Any]:
        client = self._ths_connection()
        if client is None:
            return {}
        try:
            payload = client.realtime([thscode])
        except Exception as exc:
            self.quote_fallback_error = f"同花顺 thsdk 行情兜底失败：{exc}"
            return {}
        data = payload.get("data") if isinstance(payload, dict) else {}
        item = (data or {}).get(thscode)
        if not isinstance(item, dict):
            item = next(
                (
                    value
                    for value in (data or {}).values()
                    if isinstance(value, dict)
                ),
                {},
            )
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        price = _number(raw.get("价格")) or _number(item.get("last_price"))
        prev_close = _number(raw.get("昨收价")) or _number(item.get("prev_close"))
        open_change = _number(raw.get("开盘涨幅"))
        open_price = None
        if open_change is not None and prev_close not in (None, 0):
            open_price = prev_close * (1 + open_change / 100)
        return {
            "价格": price,
            "涨幅": _number(raw.get("涨幅")) or _number(
                item.get("price_change_ratio_pct")
            ),
            "涨跌": (
                price - prev_close
                if price is not None and prev_close is not None
                else None
            ),
            "成交量": _number(raw.get("成交量")) or _number(item.get("volume")),
            "总金额": _number(raw.get("总金额")) or _number(item.get("turnover")),
            "总市值": _number(raw.get("总市值")),
            "流通市值": _number(raw.get("流通市值")),
            "市盈率TTM": _number(raw.get("市盈率TTM")),
            "市净率": _number(raw.get("市净率")),
            "换手率": _number(raw.get("换手率")),
            "振幅": _number(raw.get("振幅")),
            "主力净流入": _number(raw.get("主力净流入")),
            "主力净量": _number(raw.get("主力净量")),
            "最高价": _number(raw.get("最高价")) or _number(item.get("high_price")),
            "最低价": _number(raw.get("最低价")) or _number(item.get("low_price")),
            "开盘价": open_price,
            "开盘涨幅": open_change,
            "昨收价": prev_close,
            "涨停价": _number(raw.get("涨停价")),
            "跌停价": _number(raw.get("跌停价")),
            "名称": _text(raw.get("名称")) or _text(item.get("name")),
            "5日涨幅": _number(raw.get("5日涨幅")),
        }

    def _eastmoney_quote_fallback(self, thscode: str) -> dict[str, Any]:
        """Fill quote fields from independent public sources."""

        code = str(thscode)[-6:]
        if not re.fullmatch(r"\d{6}", code):
            return {}
        output: dict[str, Any] = {}
        errors: list[str] = []

        thsdk = self._thsdk_quote_fallback(thscode)
        if _fill_missing(output, thsdk):
            self._record_source("quote_fill", "thsdk")

        eastmoney: dict[str, Any] = {}
        try:
            quote = _eastmoney_stock_quote(code) or {}
            price = _number(quote.get("f2"))
            prev_close = _number(quote.get("f18"))
            change_pct = _number(quote.get("f3"))
            if prev_close is None and price is not None and change_pct is not None:
                ratio = 1 + change_pct / 100
                if abs(ratio) > 1e-9:
                    prev_close = price / ratio
            open_price = _number(quote.get("f17"))
            eastmoney = {
                "价格": price,
                "涨幅": change_pct,
                "涨跌": (
                    price - prev_close
                    if price is not None and prev_close is not None
                    else None
                ),
                "成交量": _number(quote.get("f5")),
                "总金额": _number(quote.get("f6")),
                "总市值": _number(quote.get("f20")),
                "流通市值": _number(quote.get("f21")),
                "市盈率TTM": _number(quote.get("f164")),
                "市净率": _number(quote.get("f23")),
                "换手率": _number(quote.get("f8")),
                "振幅": _number(quote.get("f7")),
                "主力净流入": _number(quote.get("f62")),
                "主力净量": _number(quote.get("f184")),
                "最高价": _number(quote.get("f15")),
                "最低价": _number(quote.get("f16")),
                "开盘价": open_price,
                "开盘涨幅": (
                    (open_price / prev_close - 1) * 100
                    if open_price is not None and prev_close not in (None, 0)
                    else None
                ),
                "昨收价": prev_close,
                "涨停价": _number(quote.get("f51")),
                "跌停价": _number(quote.get("f52")),
                "名称": _text(quote.get("f14")),
                "总股本": _number(quote.get("f84")),
                "流通a股": _number(quote.get("f85")),
                "限售a股": (
                    _number(quote.get("f84")) - _number(quote.get("f85"))
                    if _number(quote.get("f84")) is not None
                    and _number(quote.get("f85")) is not None
                    else None
                ),
            }
        except Exception as exc:
            errors.append(f"东方财富行情兜底失败：{exc}")
        if _fill_missing(output, eastmoney):
            self._record_source("quote_fill", "eastmoney")

        try:
            tencent = _tencent_quote_snapshot([code]).get(code) or {}
        except Exception as exc:
            errors.append(f"腾讯行情兜底失败：{exc}")
            tencent = {}
        tencent_quote = {
            "价格": _number(tencent.get("price")),
            "涨幅": _number(tencent.get("change_pct")),
            "成交量": _number(tencent.get("volume")),
            "总金额": _number(tencent.get("amount")),
            "总市值": _number(tencent.get("market_cap")),
            "流通市值": _number(tencent.get("circulating_cap")),
            "市盈率TTM": _number(tencent.get("pe")),
            "市净率": _number(tencent.get("pb")),
            "换手率": _number(tencent.get("turnover_rate")),
            "振幅": _number(tencent.get("amplitude")),
            "最高价": _number(tencent.get("high")),
            "最低价": _number(tencent.get("low")),
            "开盘价": _number(tencent.get("open")),
            "昨收价": _number(tencent.get("prev_close")),
            "涨停价": _number(tencent.get("limit_up")),
            "跌停价": _number(tencent.get("limit_down")),
            "名称": _text(tencent.get("name")),
            "5日涨幅": _number(tencent.get("5d_change")),
            "总股本": _number(tencent.get("total_shares")),
            "流通a股": _number(tencent.get("float_shares")),
            "限售a股": (
                _number(tencent.get("total_shares"))
                - _number(tencent.get("float_shares"))
                if _number(tencent.get("total_shares")) is not None
                and _number(tencent.get("float_shares")) is not None
                else None
            ),
        }
        if _fill_missing(output, tencent_quote):
            self._record_source("quote_fill", "tencent")

        price = _number(output.get("价格"))
        prev_close = _number(output.get("昨收价"))
        open_price = _number(output.get("开盘价"))
        if _is_missing(output.get("涨跌")) and price is not None and prev_close is not None:
            output["涨跌"] = price - prev_close
        if _is_missing(output.get("开盘涨幅")) and open_price is not None and prev_close not in (None, 0):
            output["开盘涨幅"] = (open_price / prev_close - 1) * 100
        self.quote_fallback_error = "；".join(errors) if errors and not output else ""
        return output

    def market_data_cn(self, thscode: str, query_key: str) -> SimpleNamespace:
        name = self._name_for(thscode)
        self.quote_source = ""
        self.quote_fill_sources = []
        self.quote_fallback_error = ""
        first, second = self._quote_rows(name)
        merged = {**second, **first}
        price = _number(_first(merged, "最新价"))
        prev_close = _previous_close(merged)
        open_price = _number(_first(merged, "开盘价"))
        amount = _number(_first(merged, "成交额"))
        main_inflow = _number(_first(merged, "主力资金流向", "主力净流入"))
        five_day_key = next(
            (
                key
                for key in merged
                if str(key).startswith("涨跌幅[") and "-" in str(key)
            ),
            None,
        )
        row = {
            "价格": price,
            "涨幅": _number(_first(merged, "最新涨跌幅", "涨跌幅")),
            "涨跌": price - prev_close if price is not None and prev_close is not None else None,
            "成交量": _number(_first(merged, "成交量")),
            "总金额": amount,
            "总市值": _number(_first(merged, "总市值")),
            "流通市值": _number(_first(merged, "流通市值")),
            "市盈率TTM": _number(_first(merged, "最新市盈率ttm", "市盈率TTM")),
            "市净率": _number(_first(merged, "最新市净率", "市净率")),
            "换手率": _number(_first(merged, "换手率")),
            "振幅": _number(_first(merged, "振幅")),
            "主力净流入": main_inflow,
            "主力净量": _number(_first(merged, "主力净量")),
            "最高价": _number(_first(merged, "最高价")),
            "最低价": _number(_first(merged, "最低价")),
            "开盘价": open_price,
            "开盘涨幅": (
                (open_price / prev_close - 1) * 100
                if open_price is not None and prev_close not in (None, 0)
                else None
            ),
            "昨收价": prev_close,
            "涨停价": _number(_first(merged, "涨停价")),
            "跌停价": _number(_first(merged, "跌停价")),
            "名称": _text(_first(merged, "股票简称", "name")) or name,
            "5日涨幅": _number(merged.get(five_day_key)) if five_day_key else None,
        }
        required_quote_fields = (
            "价格",
            "涨幅",
            "成交量",
            "总金额",
            "总市值",
            "流通市值",
            "市盈率TTM",
            "市净率",
            "换手率",
            "振幅",
            "主力净流入",
            "主力净量",
            "最高价",
            "最低价",
            "昨收价",
            "涨停价",
            "跌停价",
            "5日涨幅",
        )
        fallback: dict[str, Any] = {}
        if any(_is_missing(row.get(key)) for key in required_quote_fields):
            fallback = self._eastmoney_quote_fallback(thscode)
        _fill_missing(row, fallback)
        price = _number(row.get("价格"))
        if price is None:
            return _empty(
                self.quote_fallback_error or "问财与公开行情源均没有返回数据"
            )
        prev_close = _number(row.get("昨收价"))
        open_price = _number(row.get("开盘价"))
        if price is not None and prev_close is not None:
            row["涨跌"] = price - prev_close
        if open_price is not None and prev_close not in (None, 0):
            row["开盘涨幅"] = (open_price / prev_close - 1) * 100
        if _is_missing(row.get("主力净量")):
            flow = _number(row.get("主力净流入"))
            cap = _number(row.get("流通市值")) or _number(row.get("总市值"))
            row["主力净量"] = (
                round(flow / cap * 100, 6)
                if flow is not None and cap not in (None, 0)
                else None
            )
        if _is_missing(_number(_first(merged, "最新价"))):
            self.quote_source = self.quote_fill_sources[0]
        else:
            self.quote_source = "wencai"
        normalized = {
            key: "暂无" if _is_missing(value) else value
            for key, value in row.items()
        }
        return SimpleNamespace(df=pd.DataFrame([normalized]), error="")

    def _finance_frame(self) -> SimpleNamespace:
        name = self.stock_name or "该股票"
        years = _annual_years()
        revenue = " ".join(f"{year}年营业收入" for year in years)
        profit = " ".join(f"{year}年归属于母公司所有者的净利润" for year in years)
        roe = " ".join(f"{year}年加权净资产收益率" for year in years)
        debt = " ".join(f"{year}年资产负债率" for year in years)
        margin = " ".join(f"{year}年销售毛利率" for year in years)
        queries = [
            (f"{name} {revenue} {profit}", "hithink-finance-query", 5),
            (f"{name} {roe} {debt}", "hithink-finance-query", 5),
            (f"{name} {margin}", "hithink-finance-query", 5),
            (
                f"{name} 注册地址 实际控制人 控股股东 所属同花顺行业 上市日期 "
                "公司全称 主营业务 主营产品名称",
                "hithink-basicinfo-query",
                5,
            ),
        ]
        merged: dict[str, Any] = {}
        for query, skill, limit in queries:
            result = self._query(query, skill, limit=limit)
            if not result.df.empty:
                merged.update(result.df.iloc[0].to_dict())
        wencai_fields = dict(merged)
        basic = self._eastmoney_basic_fallback()
        for key, value in basic.items():
            if merged.get(key) in (None, ""):
                merged[key] = value
        fallback = self._eastmoney_finance_fallback(years)
        if fallback:
            for key, value in fallback.items():
                if merged.get(key) in (None, ""):
                    merged[key] = value
        if basic or fallback:
            self.finance_source = "mixed" if wencai_fields else "eastmoney"
        if not merged:
            return _empty(
                "; ".join(
                    item
                    for item in (
                        self.wencai_error,
                        getattr(self, "finance_error", ""),
                    )
                    if item
                )
                or "问财与东方财富均未返回财务和基本信息"
            )
        if self.finance_source not in {"mixed", "eastmoney"}:
            self.finance_source = "wencai"
        self.finance_error = ""

        aliases: dict[str, Any] = {}
        for key, value in merged.items():
            text = str(key)
            if text.startswith("归母净利润"):
                aliases[text.replace("归母净利润", "归属于母公司所有者的净利润", 1)] = value
            if text.startswith("年涨跌幅"):
                aliases[text.replace("年涨跌幅", "年初至今涨跌幅", 1)] = value
            if text.startswith("加权净资产收益率"):
                suffix = text[len("加权净资产收益率") :]
                aliases[f"净资产收益率ROE{suffix}"] = value
        if not any(str(key).startswith("净资产收益率ROE") for key in merged):
            for key, value in merged.items():
                text = str(key)
                if text.startswith("净资产收益率") and not text.startswith("加权"):
                    aliases[f"净资产收益率ROE{text[len('净资产收益率') :]}"] = value
        merged.update(aliases)

        industry = _join(merged.get("所属同花顺行业"))
        products = _join(merged.get("主营产品"), "||")
        business = _text(merged.get("经营范围")) or products
        controlling = _text(merged.get("股东名称"))
        merged.update(
            {
                "公司中文名称": _text(merged.get("中文名称")) or _text(merged.get("公司中文名称")),
                "新股上市日期": _text(merged.get("上市日期")) or _text(merged.get("新股上市日期")),
                "所属同花顺行业": industry or _text(merged.get("所属同花顺行业")),
                "主营产品名称": products or _text(merged.get("主营产品名称")),
                "主营业务": business or _text(merged.get("主营业务")),
            }
        )
        if controlling:
            merged.setdefault("控股股东名称", controlling)
        return SimpleNamespace(df=pd.DataFrame([{key: _json_value(value) for key, value in merged.items()}]), error="")

    def _eastmoney_basic_fallback(self) -> dict[str, Any]:
        """Fill company identity fields when Wencai basic-info queries are unavailable."""

        if not self._stock_code:
            return {}
        prefix = _eastmoney_market_prefix(self._stock_code)
        try:
            payload = _fetch_eastmoney_json(
                f"{EASTMONEY_COMPANY_SURVEY_URL}?code={prefix}{self._stock_code}"
            )
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}

        def first_row(key: str) -> dict[str, Any]:
            value = payload.get(key)
            if isinstance(value, dict):
                return dict(value)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        return dict(item)
            return {}

        survey = {**first_row("fxxg"), **first_row("jbzl")}
        output: dict[str, Any] = {}
        company = _text(survey.get("ORG_NAME"))
        industry = _text(survey.get("EM2016"))
        address = _text(survey.get("REG_ADDRESS"))
        business_scope = _text(survey.get("BUSINESS_SCOPE"))
        listing = _date_key(survey.get("LISTING_DATE"))
        if company:
            output["公司中文名称"] = company
            output["中文名称"] = company
        if industry:
            output["所属同花顺行业"] = industry
            output["所属行业"] = industry
        if address:
            output["注册地址"] = address
        if business_scope:
            output["经营范围"] = business_scope
            output["主营业务"] = business_scope
        if listing:
            output["新股上市日期"] = (
                f"{listing[:4]}-{listing[4:6]}-{listing[6:]}"
            )

        holder_payload, holder_error = self._f10_payload()
        if not holder_error:
            controller_rows = holder_payload.get("sjkzr") or []
            if isinstance(controller_rows, dict):
                controller_rows = [controller_rows]
            controller = next(
                (
                    _text(item.get("HOLDER_NAME"))
                    for item in controller_rows
                    if isinstance(item, dict) and _text(item.get("HOLDER_NAME"))
                ),
                "",
            )
            if controller:
                output["实际控制人"] = controller
            top_rows = [
                dict(item)
                for item in holder_payload.get("sdgd") or []
                if isinstance(item, dict)
            ]
            if top_rows:
                top_rows.sort(
                    key=lambda item: _number(item.get("HOLDER_RANK")) or 10**9
                )
                holding = _text(top_rows[0].get("HOLDER_NAME"))
                if holding:
                    output["控股股东名称"] = holding
        if output:
            output["基本信息数据来源"] = "东方财富F10"
        return output

    def _eastmoney_finance_fallback(self, years: list[int]) -> dict[str, Any]:
        """Fill annual finance fields when the Wencai finance query is unavailable."""

        if not self._stock_code:
            return {}
        try:
            annual = _eastmoney_annual_reports(self._stock_code)
        except Exception as exc:
            self.finance_error = f"东方财富年度财务兜底请求失败：{exc}"
            return {}
        try:
            income = _eastmoney_income_reports(self._stock_code)
        except Exception:
            income = {}

        output: dict[str, Any] = {}
        fields = (
            ("营业收入", "TOTALOPERATEREVE"),
            ("归属于母公司所有者的净利润", "PARENTNETPROFIT"),
            ("销售毛利率", "XSMLL"),
            ("销售净利率", "XSJLL"),
            ("加权净资产收益率", "ROEJQ"),
            ("资产负债率", "ZCFZL"),
            ("营业收入同比增长率", "TOTALOPERATEREVETZ"),
            ("归母净利润同比增长率", "PARENTNETPROFITTZ"),
        )
        for year in years:
            report = dict(annual.get(year) or {})
            if not report:
                continue
            income_report = income.get(year) or {}
            if income_report.get("OPERATE_INCOME") is not None:
                report["TOTALOPERATEREVE"] = income_report["OPERATE_INCOME"]
            if income_report.get("OPERATE_INCOME_YOY") is not None:
                report["TOTALOPERATEREVETZ"] = income_report["OPERATE_INCOME_YOY"]
            for label, field in fields:
                value = _number(report.get(field))
                if value is not None:
                    output[f"{label}[{year}1231]"] = value
        return output

    def _holders_frame(self) -> SimpleNamespace:
        query = (
            f"{self.stock_name} 前十大流通股东名称 机构持股占流通股比例 "
            "股东户数 陆股通持股占流通a股比"
        )
        result = self._query(query, "hithink-finance-query", limit=10)
        if not result.df.empty:
            rows = [row.to_dict() for _, row in result.df.iterrows()]
            rows.sort(key=lambda row: _number(row.get("排名")) or 10**9)
            names: list[str] = []
            for row in rows:
                name = _text(row.get("名称"))
                if name and name not in names:
                    names.append(name)
            merged = dict(rows[0])
            if not names:
                existing = _text(merged.get("前十大流通股东名称"))
                if existing:
                    names = [
                        item.strip()
                        for item in re.split(r"[|,，;；]", existing)
                        if item.strip()
                    ]
            if names:
                merged["前十大流通股东名称"] = "||".join(names)
                self.holders_source = "wencai"
                self.holders_error = ""
                return SimpleNamespace(df=pd.DataFrame([merged]), error="")

        self.holders_error = result.error or "问财未返回前十大流通股东名录"
        fallback = self._eastmoney_holders_frame()
        if not fallback.df.empty:
            self.holders_source = "eastmoney"
            self.holders_error = ""
            return fallback
        self.holders_source = ""
        self.holders_error = "; ".join(
            item for item in (self.holders_error, fallback.error) if item
        )
        return _empty(self.holders_error)

    def _f10_payload(self) -> tuple[dict[str, Any], str]:
        if getattr(self, "_f10_payload_cache", None) is not None:
            return self._f10_payload_cache, ""
        cached_error = getattr(self, "_f10_payload_error", "")
        if cached_error:
            return {}, cached_error
        if not self._stock_code:
            return {}, "东方财富 F10 兜底缺少股票代码"
        try:
            payload = _fetch_eastmoney_holder_payload(self._stock_code)
        except Exception as exc:
            self._f10_payload_error = f"东方财富 F10 请求失败：{exc}"
            return {}, self._f10_payload_error
        self._f10_payload_cache = payload
        self._f10_payload_error = ""
        return payload, ""

    def _eastmoney_holders_frame(self) -> SimpleNamespace:
        payload, error = self._f10_payload()
        if error:
            return _empty(error)

        free_holders = [
            dict(item)
            for item in payload.get("sdltgd") or []
            if isinstance(item, dict)
        ]
        if not free_holders:
            return _empty("东方财富未返回前十大流通股东")
        free_holders.sort(
            key=lambda item: _number(item.get("HOLDER_RANK")) or 10**9
        )
        names = []
        for item in free_holders:
            name = _text(item.get("HOLDER_NAME"))
            if name and name not in names:
                names.append(name)
        if not names:
            return _empty("东方财富前十大流通股东名称为空")

        holder_date = _date_key(free_holders[0].get("END_DATE"))

        institutions = [
            dict(item)
            for item in payload.get("jgcc") or []
            if isinstance(item, dict)
        ]
        institution_ratio = None
        institution_date = ""
        if institutions:
            institution_date = max(
                (_date_key(item.get("REPORT_DATE")) for item in institutions),
                default="",
            )
            latest = [
                item
                for item in institutions
                if not institution_date
                or _date_key(item.get("REPORT_DATE")) == institution_date
            ]
            total_rows = [
                item for item in latest if _text(item.get("ORG_TYPE")) == "00"
            ]
            ratio_rows = total_rows or latest
            institution_ratio = max(
                (
                    value
                    for value in (
                        _number(item.get("TOTAL_SHARES_RATIO"))
                        for item in ratio_rows
                    )
                    if value is not None
                ),
                default=None,
            )
        if institution_ratio is None:
            return _empty("东方财富未返回机构持股占流通股比例")

        holder_counts = [
            dict(item)
            for item in payload.get("gdrs") or []
            if isinstance(item, dict)
        ]
        holder_count_row: dict[str, Any] = {}
        holder_count_date = ""
        if holder_counts:
            holder_count_date = max(
                (_date_key(item.get("END_DATE")) for item in holder_counts),
                default="",
            )
            holder_count_row = next(
                (
                    item
                    for item in holder_counts
                    if not holder_count_date
                    or _date_key(item.get("END_DATE")) == holder_count_date
                ),
                {},
            )

        row: dict[str, Any] = {
            "前十大流通股东名称": "||".join(names[:10]),
            f"机构持股占流通股比例[{institution_date or holder_date}]": institution_ratio,
            "股票代码": self._stock_code,
            "股票简称": self.stock_name,
            "股东数据来源": "东方财富F10",
        }
        holder_total = _number(holder_count_row.get("HOLDER_TOTAL_NUM"))
        holder_change = _number(holder_count_row.get("TOTAL_NUM_RATIO"))
        if holder_total is not None:
            row[f"总户数[{holder_count_date}]"] = holder_total
        if holder_change is not None:
            row[f"总户数较上期增长率[{holder_count_date}]"] = holder_change
        return SimpleNamespace(
            df=pd.DataFrame([row]),
            error="",
            source="eastmoney",
            period=holder_date,
        )

    def _eastmoney_holder_trend_frame(self) -> SimpleNamespace:
        payload, error = self._f10_payload()
        if error:
            return _empty(error)
        rows = [
            dict(item)
            for item in payload.get("gdrs") or []
            if isinstance(item, dict)
        ]
        records = []
        for item in rows:
            period = _date_key(item.get("END_DATE"))
            count = _number(item.get("HOLDER_TOTAL_NUM"))
            if period and count is not None:
                records.append((period, count))
        if not records:
            return _empty("东方财富 F10 未返回股东户数")
        records.sort()
        output: dict[str, Any] = {
            "股票代码": (
                f"{self._stock_code}.{_eastmoney_market_prefix(self._stock_code)}"
                if self._stock_code
                else ""
            ),
            "股票简称": self.stock_name,
        }
        for period, count in records:
            output[f"股东户数(报告期)[{period}]"] = count
        return SimpleNamespace(df=pd.DataFrame([output]), error="")

    def _eastmoney_share_structure_frame(self) -> SimpleNamespace:
        if not self._stock_code:
            return _empty("股本结构兜底缺少股票代码")
        try:
            tencent = _tencent_quote_snapshot([self._stock_code]).get(
                self._stock_code
            ) or {}
        except Exception:
            tencent = {}
        total = _number(tencent.get("total_shares"))
        floating = _number(tencent.get("float_shares"))
        period = datetime.now(CN_TZ).strftime("%Y%m%d")
        source = "tencent"
        if total is None or floating is None:
            source = "eastmoney"
            payload, error = self._f10_payload()
            if error:
                return _empty(error)
            rows = [
                dict(item)
                for item in payload.get("ltgf") or []
                if isinstance(item, dict)
            ]
            if not rows:
                return _empty("东方财富 F10 未返回股本结构")
            latest = max(rows, key=lambda item: _date_key(item.get("END_DATE")))
            period = _date_key(latest.get("END_DATE")) or period
            limited = _number(latest.get("LIMITED_SHARES")) or 0.0
            held = _number(latest.get("HOLD_NUM_COUNT"))
            other_unlimited = _number(latest.get("OTHER_UNLIMITED_SHARES"))
            floating = _number(latest.get("FREE_SHARES"))
            total = _number(latest.get("TOTAL_SHARES"))
            if held is not None and other_unlimited is not None:
                total = held + limited + other_unlimited
                floating = total - limited
            if total is None and limited is not None and floating is not None:
                total = floating + limited
            if floating is None and total is not None and limited is not None:
                floating = total - limited
        else:
            limited = total - floating
        if total is None or floating is None:
            return _empty("公开数据源未返回完整股本结构")
        if limited is None:
            limited = total - floating
        output = {
            f"总股本[{period}]": total,
            f"流通a股[{period}]": floating,
            f"限售a股[{period}]": max(0, limited),
            "股票代码": (
                f"{self._stock_code}.{_eastmoney_market_prefix(self._stock_code)}"
                if self._stock_code
                else ""
            ),
            "股票简称": self.stock_name,
        }
        return SimpleNamespace(df=pd.DataFrame([output]), error="", source=source)

    def _eastmoney_concentration_frame(self) -> SimpleNamespace:
        payload, error = self._f10_payload()
        if error:
            return _empty(error)
        holder_rows = [
            dict(item)
            for item in payload.get("gdrs") or []
            if isinstance(item, dict)
        ]
        top_rows = [
            dict(item)
            for item in payload.get("sdgd") or []
            if isinstance(item, dict)
        ]
        if not top_rows:
            return _empty("东方财富 F10 未返回前十大股东")
        top_rows.sort(
            key=lambda item: _number(item.get("HOLDER_RANK")) or 10**9
        )
        first = top_rows[0]
        latest_holder = (
            max(holder_rows, key=lambda item: _date_key(item.get("END_DATE")))
            if holder_rows
            else {}
        )
        period = _date_key(first.get("END_DATE"))
        price = _number(latest_holder.get("PRICE"))
        hold_num = _number(first.get("HOLD_NUM"))
        row = {
            "前十大股东持股比例合计": _number(
                latest_holder.get("HOLD_RATIO_TOTAL")
            ),
            "大股东公告日期": period,
            "大股东名称": _text(first.get("HOLDER_NAME")),
            "大股东持股市值": (
                hold_num * price
                if hold_num is not None and price is not None
                else None
            ),
            "大股东持股数量": hold_num,
            "大股东持股比例": _number(first.get("HOLD_NUM_RATIO")),
            "大股东排名": _number(first.get("HOLDER_RANK")),
            "大股东股份类别": _text(first.get("SHARES_TYPE")),
            "最新户均持股市值": _number(latest_holder.get("AVG_HOLD_AMT")),
            "最新户均持股数量": _number(latest_holder.get("AVG_FREE_SHARES")),
            "股票代码": (
                f"{self._stock_code}.{_eastmoney_market_prefix(self._stock_code)}"
                if self._stock_code
                else ""
            ),
            "股票简称": self.stock_name,
        }
        if row["前十大股东持股比例合计"] is None:
            return _empty("东方财富 F10 未返回前十大股东持股比例合计")
        return SimpleNamespace(df=pd.DataFrame([row]), error="")

    def _eastmoney_unlock_frame(self) -> SimpleNamespace:
        payload, error = self._f10_payload()
        if error:
            return _empty(error)
        rows = [
            dict(item)
            for item in payload.get("xsjj") or []
            if isinstance(item, dict)
        ]
        if rows:
            latest = max(rows, key=lambda item: _date_key(item.get("END_DATE")))
            output = {
                "下次解禁日期": _date_key(latest.get("END_DATE")),
                "下次解禁数量": _number(latest.get("LIMITED_SHARES")),
                "下次解禁股数占流通股比例": _number(
                    latest.get("LIMITED_SHARES_RATIO")
                ),
                "解禁股类型": _text(latest.get("SHARES_TYPE")),
                "数据来源": "东方财富F10",
            }
        else:
            output = {
                "未来解禁安排": "截至采集时点，东方财富 F10 公告口径未返回待解禁记录",
                "数据来源": "东方财富F10",
            }
        return SimpleNamespace(df=pd.DataFrame([output]), error="")

    def _peers_frame(self, query: str) -> SimpleNamespace:
        """Use Wencai first, then disclosed Eastmoney peer data when quota is exhausted."""

        result = self._query(query, "hithink-industry-query", limit=50)
        if _has_stock_peer_rows(result.df):
            self.peers_source = "wencai"
            self.peers_error = ""
            self.peers_expected_count = 0
            self.peers_scope = ""
            return result

        self.peers_error = (
            "问财同业查询返回行业指数而非个股"
            if not result.df.empty
            else (result.error or "问财未返回同业数据")
        )
        fallback = self._eastmoney_peers_frame()
        if (
            fallback.df.empty
            or str(getattr(fallback, "scope", "")) == "eastmoney_f10_sample"
        ):
            fuyao_fallback = self._fuyao_peers_frame(query)
            if not fuyao_fallback.df.empty:
                fallback = fuyao_fallback
        if not fallback.df.empty:
            self.peers_source = str(
                getattr(fallback, "source", "") or "eastmoney"
            )
            self.peers_error = ""
            self.peers_expected_count = int(
                getattr(fallback, "expected_count", 0) or 0
            )
            self.peers_scope = str(getattr(fallback, "scope", "") or "")
            return fallback

        self.peers_source = ""
        self.peers_expected_count = 0
        self.peers_scope = ""
        self.peers_error = "; ".join(
            item for item in (self.peers_error, fallback.error) if item
        )
        return _empty(self.peers_error)

    def _fuyao_peers_frame(self, query: str) -> SimpleNamespace:
        """Build a full board from Fuyao membership when Eastmoney push2 is down."""

        match = re.match(r"\s*([^，,]+?)(?:行业)?[，,]", query)
        industry_name = match.group(1).strip() if match else ""
        industry_name = re.sub(r"(?:行业|概念)$", "", industry_name).strip()
        if not industry_name or self.market is None:
            return _empty("无法从同业查询中确定扶摇板块名称")
        try:
            payload = self.market.sector(industry_name)
        except Exception as exc:
            return _empty(f"扶摇板块成员请求失败：{exc}")
        members: list[dict[str, Any]] = []
        for item in payload.get("members") or []:
            if not isinstance(item, dict):
                continue
            code = _text(item.get("ticker"))
            if not re.fullmatch(r"\d{6}", code):
                code = re.search(
                    r"(\d{6})",
                    _text(item.get("thscode")),
                ).group(1) if re.search(r"(\d{6})", _text(item.get("thscode"))) else ""
            if not re.fullmatch(r"\d{6}", code):
                continue
            name = re.sub(r"\s+", "", _text(item.get("name")))
            if not name:
                continue
            members.append({"f12": code, "f14": name})
        if not members:
            return _empty(f"扶摇板块 {industry_name} 未返回成分股")
        frame = self._eastmoney_peers_frame_from_board(members, industry_name)
        if not frame.df.empty:
            frame.source = "fuyao"
            frame.scope = industry_name
            frame.expected_count = len(members)
        return frame

    def _eastmoney_peers_frame(self) -> SimpleNamespace:
        """Build the peer table from public F10 discovery and quote snapshots."""

        if not self._stock_code:
            return _empty("东方财富同业兜底缺少股票代码")
        board_error = ""
        try:
            industry_name = _eastmoney_industry_name(self._stock_code)
            board_members = (
                _eastmoney_industry_members(industry_name)
                if industry_name
                else []
            )
        except Exception as exc:
            industry_name = ""
            board_members = []
            board_error = f"东方财富行业板块请求失败：{exc}"
        if board_members:
            board_frame = self._eastmoney_peers_frame_from_board(
                board_members,
                industry_name,
            )
            if not board_frame.df.empty:
                return board_frame
        prefix = _eastmoney_market_prefix(self._stock_code)
        try:
            payload = _fetch_eastmoney_json(
                f"{EASTMONEY_INDUSTRY_URL}?code={prefix}{self._stock_code}"
            )
        except Exception as exc:
            detail = f"东方财富同业名单请求失败：{exc}"
            if board_error:
                detail = f"{board_error}；{detail}"
            return _empty(detail)
        if not isinstance(payload, dict):
            detail = "东方财富同业名单返回结构无效"
            if board_error:
                detail = f"{board_error}；{detail}"
            return _empty(detail)

        def index_rows(key: str) -> dict[str, dict[str, Any]]:
            indexed: dict[str, dict[str, Any]] = {}
            for item in payload.get(key) or []:
                if not isinstance(item, dict):
                    continue
                code = _text(item.get("CORRE_SECURITY_CODE"))
                if re.fullmatch(r"\d{6}", code):
                    indexed.setdefault(code, item)
            return indexed

        valuation_rows = index_rows("gzbj")
        ratio_rows = index_rows("dbfxbj")
        size_rows: dict[str, dict[str, Any]] = {}
        for key in ("gsgm", "gsgm_zsz", "gsgm_ltsz", "gsgm_yysr", "gsgm_jlr"):
            for code, item in index_rows(key).items():
                size_rows.setdefault(code, item)

        codes: list[str] = []
        for code in (self._stock_code, *valuation_rows, *size_rows):
            if code not in codes:
                codes.append(code)
        if self._stock_code not in codes:
            codes.insert(0, self._stock_code)
        if not codes:
            return _empty("东方财富未返回同业股票代码")

        try:
            quotes = _eastmoney_quote_snapshot(codes)
        except Exception as exc:
            quotes = {}
            quote_error = str(exc)
        else:
            quote_error = ""

        try:
            tencent_quotes = _tencent_quote_snapshot(codes)
        except Exception:
            tencent_quotes = {}

        rows_by_code: dict[str, dict[str, Any]] = {}
        for code in codes:
            quote = quotes.get(code) or {}
            tencent = tencent_quotes.get(code) or {}
            valuation = valuation_rows.get(code) or {}
            size = size_rows.get(code) or {}
            ratio = ratio_rows.get(code) or {}
            name = re.sub(
                r"\s+",
                "",
                _coalesce(
                    _text(quote.get("f14")),
                    _text(valuation.get("CORRE_SECURITY_NAME")),
                    _text(size.get("CORRE_SECURITY_NAME")),
                    _text(size.get("SECURITY_NAME_ABBR")),
                    "",
                ),
            )
            if not name:
                continue
            revenue = _number(size.get("TOTAL_OPERATEINCOME"))
            profit = _number(size.get("NETPROFIT"))
            tencent_used = False
            pe = _coalesce(
                _number(quote.get("f9")),
                _number(valuation.get("PE_TTM")),
                _number(valuation.get("PE")),
            )
            if pe is None and _number(tencent.get("pe")) is not None:
                pe = _number(tencent.get("pe"))
                tencent_used = True
            pb = _coalesce(
                _number(quote.get("f23")),
                _number(valuation.get("PB_MRQ")),
                _number(valuation.get("PB")),
            )
            if pb is None and _number(tencent.get("pb")) is not None:
                pb = _number(tencent.get("pb"))
                tencent_used = True
            market_cap = _coalesce(
                _number(quote.get("f20")),
                _cap_yuan(size.get("TOTAL_CAP")),
            )
            if market_cap is None and _number(tencent.get("market_cap")) is not None:
                market_cap = _number(tencent.get("market_cap"))
                tencent_used = True
            circulating_cap = _coalesce(
                _number(quote.get("f21")),
                _cap_yuan(size.get("FREECAP")),
            )
            if (
                circulating_cap is None
                and _number(tencent.get("circulating_cap")) is not None
            ):
                circulating_cap = _number(tencent.get("circulating_cap"))
                tencent_used = True
            row = {
                "股票代码": f"{code}.{_eastmoney_market_prefix(code)}",
                "股票简称": name,
                "市盈率(pe)": pe,
                "市净率(pb)": pb,
                "总市值": market_cap,
                "流通市值": circulating_cap,
                "净资产收益率": _number(ratio.get("ROE_AVG")),
                "营业收入": revenue,
                "净利润": profit,
                "销售净利率": (
                    profit / revenue * 100
                    if profit is not None and revenue not in (None, 0)
                    else None
                ),
                "最新价": _number(quote.get("f2")),
                "最新涨跌幅": _number(quote.get("f3")),
                "数据来源": (
                    "东方财富F10/行情+腾讯行情"
                    if tencent_used
                    else "东方财富F10/行情"
                ),
            }
            rows_by_code[code] = (
                {
                    key: value
                    for key, value in row.items()
                    if value not in (None, "")
                }
            )

        if not rows_by_code:
            detail = f"（{quote_error}）" if quote_error else ""
            return _empty(f"东方财富未返回同业行情数据{detail}")

        ordered_codes = sorted(
            rows_by_code,
            key=lambda code: (
                _number(rows_by_code[code].get("总市值")) or 0,
                _text(rows_by_code[code].get("股票代码")),
            ),
            reverse=True,
        )
        annual_errors: list[str] = []
        target_year = max(1, datetime.now(CN_TZ).year - 1)
        for code in ordered_codes[:6]:
            try:
                annual = _eastmoney_annual_financials(code, target_year)
            except Exception as exc:
                annual_errors.append(f"{code} 年度财务请求失败：{exc}")
                continue
            row = rows_by_code[code]
            revenue = _number(annual.get("TOTALOPERATEREVE"))
            profit = _number(annual.get("PARENTNETPROFIT"))
            annual_values = {
                "营业收入": revenue,
                "净利润": profit,
                "销售毛利率": _number(annual.get("XSMLL")),
                "销售净利率": _coalesce(
                    _number(annual.get("XSJLL")),
                    (
                        profit / revenue * 100
                        if profit is not None and revenue not in (None, 0)
                        else None
                    ),
                ),
                "净资产收益率": _number(annual.get("ROEJQ")),
                "营业收入同比": _number(annual.get("TOTALOPERATEREVETZ")),
                "净利润同比": _number(annual.get("PARENTNETPROFITTZ")),
            }
            row.update(
                {
                    key: value
                    for key, value in annual_values.items()
                    if value not in (None, "")
                }
            )

        rows = [rows_by_code[code] for code in ordered_codes]
        if not rows:
            detail = "；".join(annual_errors[:2])
            return _empty("东方财富未返回同业行情数据" + (f"（{detail}）" if detail else ""))
        rows.sort(
            key=lambda row: (
                _number(row.get("总市值")) or 0,
                _text(row.get("股票代码")),
            ),
            reverse=True,
        )
        return SimpleNamespace(
            df=pd.DataFrame(rows),
            error="",
            source="eastmoney",
            expected_count=0,
            scope="eastmoney_f10_sample",
        )

    def _eastmoney_peers_frame_from_board(
        self,
        members: list[dict[str, Any]],
        industry_name: str,
    ) -> SimpleNamespace:
        """Build a full-industry peer table from board membership and F10."""

        codes: list[str] = []
        names: dict[str, str] = {}
        for item in members:
            code = _text(item.get("f12"))
            if not re.fullmatch(r"\d{6}", code):
                continue
            if code not in codes:
                codes.append(code)
            name = re.sub(r"\s+", "", _text(item.get("f14")))
            if name:
                names[code] = name
        if self._stock_code and self._stock_code not in codes:
            codes.insert(0, self._stock_code)
        if not codes:
            return _empty("东方财富行业板块未返回同业股票代码")
        try:
            quotes = _eastmoney_quote_snapshot(codes)
        except Exception as exc:
            quotes = {}
            quote_error = str(exc)
        else:
            quote_error = ""
        try:
            tencent_quotes = _tencent_quote_snapshot(codes)
        except Exception:
            tencent_quotes = {}

        target_year = max(1, datetime.now(CN_TZ).year - 1)
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for code in codes:
            quote = quotes.get(code) or {}
            tencent = tencent_quotes.get(code) or {}
            name = re.sub(
                r"\s+",
                "",
                _coalesce(
                    _text(quote.get("f14")),
                    names.get(code),
                    "",
                ),
            )
            if not name:
                continue
            try:
                annual = _eastmoney_annual_financials(code, target_year)
            except Exception as exc:
                annual = {}
                errors.append(f"{code} 年度财务请求失败：{exc}")
            price = _coalesce(
                _number(quote.get("f2")),
                _number(tencent.get("price")),
            )
            revenue = _number(annual.get("TOTALOPERATEREVE"))
            profit = _number(annual.get("PARENTNETPROFIT"))
            net_margin = _number(annual.get("XSJLL"))
            if net_margin is None and profit is not None and revenue not in (None, 0):
                net_margin = profit / revenue * 100
            row = {
                "股票代码": f"{code}.{_eastmoney_market_prefix(code)}",
                "股票简称": name,
                "市盈率(pe)": _coalesce(
                    _number(quote.get("f9")),
                    _number(tencent.get("pe")),
                ),
                "市净率(pb)": _coalesce(
                    _number(quote.get("f23")),
                    _number(tencent.get("pb")),
                ),
                "总市值": _coalesce(
                    _number(quote.get("f20")),
                    _number(tencent.get("market_cap")),
                ),
                "流通市值": _coalesce(
                    _number(quote.get("f21")),
                    _number(tencent.get("circulating_cap")),
                ),
                "净资产收益率": _number(annual.get("ROEJQ")),
                "营业收入": revenue,
                "净利润": profit,
                "销售毛利率": _number(annual.get("XSMLL")),
                "销售净利率": net_margin,
                "营业收入同比": _number(annual.get("TOTALOPERATEREVETZ")),
                "净利润同比": _number(annual.get("PARENTNETPROFITTZ")),
                "股息率": _eastmoney_dividend_yield(code, price),
                "最新价": price,
                "最新涨跌幅": _coalesce(
                    _number(quote.get("f3")),
                    _number(tencent.get("change_pct")),
                ),
                "所属行业": industry_name,
                "数据来源": "东方财富行业板块/行情/年报",
            }
            rows.append(
                {
                    key: value
                    for key, value in row.items()
                    if value not in (None, "")
                }
            )
        if not rows:
            detail = "；".join(errors[:2]) or quote_error
            return _empty(
                "东方财富行业板块未返回同业行情数据"
                + (f"（{detail}）" if detail else "")
            )
        rows.sort(
            key=lambda row: (
                _number(row.get("总市值")) or 0,
                _text(row.get("股票代码")),
            ),
            reverse=True,
        )
        return SimpleNamespace(
            df=pd.DataFrame(rows),
            error="",
            source="eastmoney",
            expected_count=len(rows),
            scope=industry_name,
        )

    def _concentration_frame(self) -> SimpleNamespace:
        query = (
            f"{self.stock_name} 前十大股东持股比例合计 第一大股东持股比例 "
            "第一大股东名称 户均持股数量 户均持股市值"
        )
        result = self._query(query, "hithink-finance-query", limit=5)
        row: dict[str, Any] = {}
        if not result.df.empty:
            row.update(result.df.iloc[0].to_dict())
            self._record_source("chip", "wencai")

        if _number(row.get("前十大股东持股比例合计")) is None:
            thsdk = self._ths_wencai_frame(query, limit=5)
            if not thsdk.df.empty and _fill_missing(row, thsdk.df.iloc[0].to_dict()):
                self._record_source("chip", "thsdk")

        if _number(row.get("前十大股东持股比例合计")) is None:
            fallback = self._eastmoney_concentration_frame()
            if not fallback.df.empty and _fill_missing(
                row, fallback.df.iloc[0].to_dict()
            ):
                self._record_source("chip", "eastmoney")

        total = _number(row.get("前十大股东持股比例合计"))
        if total is None:
            total_key = next(
                (
                    str(key)
                    for key in row
                    if str(key).startswith("前十大股东持股比例合计[")
                ),
                None,
            )
            candidate = _number(row.get(total_key)) if total_key else None
            if candidate is not None and 0 < candidate <= 1:
                total = candidate
        if total is None:
            total_key = next(
                (
                    str(key)
                    for key in row
                    if str(key).startswith("持股比例[")
                ),
                None,
            )
            candidate = _number(row.get(total_key)) if total_key else None
            if candidate is not None and 0 < candidate <= 1:
                total = candidate
        if total is not None and 0 < total <= 1:
            total *= 100
        row["前十大股东持股比例合计"] = total
        first_ratio = _number(
            _first(
                row,
                "大股东持股比例",
                "第一大股东持股比例",
                "持股比例",
            )
        )
        first_name = _text(
            _first(row, "大股东名称", "第一大股东名称", "名称")
        )
        row["第一大股东持股比例"] = first_ratio
        row["第一大股东名称"] = first_name
        quantity_key = _first_key(row, "最新户均持股数量[", "户均持股数量[")
        value_key = _first_key(row, "最新户均持股市值[", "户均持股市值[")
        if quantity_key:
            row["户均持股数量"] = row.get(quantity_key)
        if value_key:
            row["户均持股市值"] = row.get(value_key)
        if total is None:
            return _empty("问财、thsdk 与东方财富 F10 均未返回股东集中度")
        return SimpleNamespace(df=pd.DataFrame([row]), error="")

    def _company_survey(self) -> dict[str, Any]:
        cached = getattr(self, "_company_survey_cache", None)
        if cached is not None:
            return cached
        if not self._stock_code:
            return {}
        prefix = _eastmoney_market_prefix(self._stock_code)
        try:
            payload = _fetch_eastmoney_json(
                f"{EASTMONEY_COMPANY_SURVEY_URL}?"
                f"code={prefix}{self._stock_code}"
            )
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        self._company_survey_cache = payload
        return payload

    def _company_full_name(self) -> str:
        payload = self._company_survey()
        rows = payload.get("jbzl") or []
        if isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            if isinstance(row, dict) and _text(row.get("ORG_NAME")):
                return _text(row.get("ORG_NAME"))
        return self.stock_name

    def _annual_report_values(self) -> dict[str, Any]:
        """Read disclosed customer/supplier and R&D values from the annual report."""

        cached = getattr(self, "_annual_report_cache", None)
        if cached is not None:
            return cached
        if not self._stock_code:
            return {}
        result: dict[str, Any] = {}
        try:
            notice = _find_annual_report(self._stock_code)
            art_code = _text(notice.get("art_code"))
            title = _text(notice.get("title"))
            period_match = re.search(r"(\d{4})年年度报告", title)
            period = (
                f"{period_match.group(1)}1231" if period_match else ""
            )
            if art_code:
                text = _annual_report_text(art_code)
                if text:
                    result["text_length"] = len(text)
                    result["period"] = period
                    result["customer"] = _disclosed_ratio(
                        text,
                        r"前五名(?:销售)?客户"
                        r"(?:销售额|销售金额|合计销售金额|销售额合计)",
                        r"占(?:年度)?销售总额(?:的)?(?:比例)?",
                    )
                    result["supplier"] = _disclosed_ratio(
                        text,
                        r"前五名(?:销售)?供应商"
                        r"(?:采购额|采购金额|合计采购金额|采购额合计)",
                        r"占(?:年度)?采购总额(?:的)?(?:比例)?",
                    )
                    result["rd_ratio"] = _disclosed_rd_ratio(text)
        except Exception as exc:
            result["error"] = str(exc)
        self._annual_report_cache = result
        return result

    def _patent_frame(self, query: str) -> SimpleNamespace:
        result = self._query(query, "hithink-finance-query", limit=5)
        row: dict[str, Any] = {}
        if not result.df.empty:
            row.update(result.df.iloc[0].to_dict())
            self._record_source("barrier", "wencai")

        def has_patents() -> bool:
            return any("专利数量" in str(key) for key in row)

        def has_rd_ratio() -> bool:
            return any(
                "研发投入占营业收入的比重" in str(key)
                or "研发投入占比" in str(key)
                for key in row
            )

        if not (has_patents() and has_rd_ratio()):
            thsdk = self._ths_wencai_frame(query, limit=5)
            if not thsdk.df.empty:
                if _fill_missing(row, thsdk.df.iloc[0].to_dict()):
                    self._record_source("barrier", "thsdk")
        if not (has_patents() and has_rd_ratio()):
            rd = self._eastmoney_rd_fallback()
            if rd and _fill_missing(row, rd):
                self._record_source("barrier", "eastmoney")
        if not (has_patents() and has_rd_ratio()):
            report = self._annual_report_values()
            period = _text(report.get("period")) or datetime.now(
                CN_TZ
            ).strftime("%Y%m%d")
            rd_ratio = _number(report.get("rd_ratio"))
            if rd_ratio is not None and not has_rd_ratio():
                row[f"研发投入占营业收入的比重[{period}]"] = rd_ratio
                self._record_source("barrier", "eastmoney_annual")
            if not has_patents():
                count = _fetch_google_patents_count(
                    self._company_full_name()
                )
                if count is not None:
                    row[f"专利数量合计[{period}]"] = count
                    row["专利统计口径"] = (
                        "Google Patents 公开专利文献（按申请人）"
                    )
                    self._record_source("barrier", "google_patents")
        for key, value in list(row.items()):
            text = str(key)
            if text.startswith("专利数量["):
                row[f"专利数量合计{text[len('专利数量') :]}"] = value
        if not row:
            return _empty("问财、thsdk 与东方财富均未返回研发专利数据")
        return SimpleNamespace(df=pd.DataFrame([row]), error="")

    def _holder_trend_frame(self, query: str) -> SimpleNamespace:
        result = self._query(query, "hithink-finance-query", limit=5)
        row: dict[str, Any] = {}
        if not result.df.empty:
            row.update(result.df.iloc[0].to_dict())
            self._record_source("chip", "wencai")
        if not any(
            re.search(r"(股东户数|总户数)(?:\([^)]*\))?\[\d{8}\]", str(key))
            for key in row
        ):
            fallback = self._eastmoney_holder_trend_frame()
            if not fallback.df.empty and _fill_missing(
                row, fallback.df.iloc[0].to_dict()
            ):
                self._record_source("chip", "eastmoney")
        if not any(
            re.search(r"(股东户数|总户数)(?:\([^)]*\))?\[\d{8}\]", str(key))
            for key in row
        ):
            thsdk = self._ths_wencai_frame(query, limit=5)
            if not thsdk.df.empty and _fill_missing(
                row, thsdk.df.iloc[0].to_dict()
            ):
                self._record_source("chip", "thsdk")
        if not row:
            return _empty("问财、东方财富 F10 与 thsdk 均未返回股东户数")
        today = datetime.now(CN_TZ).strftime("%Y%m%d")
        filtered: dict[str, Any] = {}
        for key, value in row.items():
            match = re.search(r"\[(\d{8})\]", str(key))
            if match and match.group(1) > today:
                continue
            filtered[str(key)] = value
        return SimpleNamespace(df=pd.DataFrame([filtered]), error="")

    def _share_structure_frame(self, query: str) -> SimpleNamespace:
        result = self._query(query, "hithink-finance-query", limit=5)
        if not result.df.empty:
            row = result.df.iloc[0].to_dict()
            if any("总股本" in str(key) for key in row):
                self._record_source("chip", "wencai")
                return result

        fallback = self._eastmoney_share_structure_frame()
        if not fallback.df.empty:
            self._record_source(
                "chip", getattr(fallback, "source", "eastmoney") or "eastmoney"
            )
            return fallback

        thsdk = self._ths_wencai_frame(query, limit=5)
        if not thsdk.df.empty:
            self._record_source("chip", "thsdk")
            return thsdk
        return _empty(
            "; ".join(
                item
                for item in (
                    getattr(result, "error", ""),
                    getattr(fallback, "error", ""),
                    getattr(thsdk, "error", ""),
                )
                if item
            )
            or "问财、腾讯行情、东方财富 F10 与 thsdk 均未返回股本结构"
        )

    def _unlock_frame(self, query: str) -> SimpleNamespace:
        result = self._query(query, "hithink-finance-query", limit=5)
        if not result.df.empty:
            self._record_source("chip", "wencai")
            return result
        thsdk = self._ths_wencai_frame(query, limit=5)
        if not thsdk.df.empty:
            self._record_source("chip", "thsdk")
            return thsdk
        fallback = self._eastmoney_unlock_frame()
        if not fallback.df.empty:
            self._record_source("chip", "eastmoney")
            return fallback
        return _empty(
            "; ".join(
                item
                for item in (
                    getattr(result, "error", ""),
                    getattr(thsdk, "error", ""),
                    getattr(fallback, "error", ""),
                )
                if item
            )
            or "未返回解禁信息"
        )

    def _margin_frame(self, query: str) -> SimpleNamespace:
        result = self._query(query, "hithink-finance-query", limit=5)
        if not result.df.empty and any(
            "融资余额" in str(key) for key in result.df.columns
        ):
            self._record_source("chip", "wencai")
            return result
        thsdk = self._ths_wencai_frame(query, limit=5)
        if not thsdk.df.empty:
            self._record_source("chip", "thsdk")
            return thsdk
        fallback = self._eastmoney_margin_frame()
        if not fallback.df.empty:
            self._record_source("chip", "eastmoney")
            return fallback
        return _empty(
            "; ".join(
                item
                for item in (
                    getattr(result, "error", ""),
                    getattr(thsdk, "error", ""),
                    getattr(fallback, "error", ""),
                )
                if item
            )
            or "问财、thsdk 与东方财富均未返回融资余额"
        )

    def _eastmoney_margin_frame(self) -> SimpleNamespace:
        if not self._stock_code:
            return _empty("东方财富融资余额兜底缺少股票代码")
        params = {
            "reportName": "RPTA_WEB_RZRQ_GGMX",
            "columns": "ALL",
            "filter": f'(SCODE="{self._stock_code}")',
            "pageNumber": "1",
            "pageSize": "20",
            "sortColumns": "DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        try:
            payload = _fetch_eastmoney_json(
                f"{EASTMONEY_MARGIN_URL}?{urlencode(params)}",
                referer="https://data.eastmoney.com/rzrq/",
            )
        except Exception as exc:
            return _empty(f"东方财富融资融券请求失败：{exc}")
        rows = [
            dict(item)
            for item in (((payload or {}).get("result") or {}).get("data") or [])
            if isinstance(item, dict)
        ]
        if not rows:
            return _empty("东方财富未返回融资融券明细")
        rows.sort(key=lambda item: _date_key(item.get("DATE")), reverse=True)
        latest = rows[0]
        period = _date_key(latest.get("DATE"))
        if not period:
            return _empty("东方财富融资融券明细缺少交易日期")
        output: dict[str, Any] = {
            "融资融券数据日期": period,
            "数据来源": "东方财富数据中心",
        }
        for label, field in (
            ("融资余额", "RZYE"),
            ("融资买入额", "RZMRE"),
            ("融资偿还额", "RZCHE"),
            ("融资净买入", "RZJME"),
            ("融券余额", "RQYE"),
            ("融资融券余额", "RZRQYE"),
            ("融资余额占流通市值比", "RZYEZB"),
        ):
            value = _number(latest.get(field))
            if value is not None:
                output[f"{label}[{period}]"] = value
        if not any(key.startswith("融资余额[") for key in output):
            return _empty("东方财富融资融券明细缺少融资余额")
        return SimpleNamespace(
            df=pd.DataFrame([output]),
            error="",
            source="eastmoney",
            period=period,
        )

    def _eastmoney_rd_fallback(self) -> dict[str, Any]:
        if not self._stock_code:
            return {}
        prefix = _eastmoney_market_prefix(self._stock_code)
        params = {
            "source": "HSF10",
            "client": "PC",
            "reportName": "RPT_F10_BUSINESS_RDEXPENSE",
            "columns": "ALL",
            "filter": f'(SECUCODE="{self._stock_code}.{prefix}")',
            "sortTypes": "-1",
            "sortColumns": "REPORT_DATE",
        }
        try:
            payload = _fetch_eastmoney_json(
                f"{EASTMONEY_DATACENTER_URL}?{urlencode(params)}"
            )
        except Exception:
            return {}
        rows = [
            dict(item)
            for item in (((payload or {}).get("result") or {}).get("data") or [])
            if isinstance(item, dict)
        ]
        if not rows:
            return {}
        annual = sorted(
            (row for row in rows if _text(row.get("REPORT_TYPE")) == "年报"),
            key=lambda row: _date_key(row.get("REPORT_DATE")),
            reverse=True,
        )
        others = sorted(
            (row for row in rows if _text(row.get("REPORT_TYPE")) != "年报"),
            key=lambda row: _date_key(row.get("REPORT_DATE")),
            reverse=True,
        )
        output: dict[str, Any] = {}
        for row in (*annual[:2], *others[:2]):
            period = _date_key(row.get("REPORT_DATE"))
            if not period:
                continue
            expense = _number(row.get("RESEARCH_EXPENSE"))
            ratio = _number(row.get("RESEARCH_EXPENSE_RATIO"))
            if expense is not None:
                output[f"研发费用[{period}]"] = expense
            if ratio is not None:
                output[f"研发投入占营业收入的比重[{period}]"] = ratio
        return output

    def _customer_supplier_frame(
        self, query: str, metric: str
    ) -> SimpleNamespace:
        result = self._query(query, "hithink-finance-query", limit=5)
        if not result.df.empty and any(
            metric in str(column) for column in result.df.columns
        ):
            self._record_source("barrier", "wencai")
            return result
        thsdk = self._ths_wencai_frame(query, limit=5)
        if not thsdk.df.empty and any(
            metric in str(column) for column in thsdk.df.columns
        ):
            self._record_source("barrier", "thsdk")
            return thsdk
        fallback = self._eastmoney_customer_supplier_frame(metric)
        if not fallback.df.empty:
            self._record_source("barrier", "eastmoney")
            return fallback
        report = self._annual_report_values()
        key = "customer" if "客户" in metric else "supplier"
        value = _number(report.get(key))
        period = _text(report.get("period"))
        if value is not None and period:
            self._record_source("barrier", "eastmoney_annual")
            return SimpleNamespace(
                df=pd.DataFrame(
                    [
                        {
                            f"{metric}[{period}]": value,
                            "数据来源": "东方财富年报正文",
                        }
                    ]
                ),
                error="",
            )
        return _empty("问财、thsdk 与东方财富数据中心均未返回集中度")

    def _eastmoney_customer_supplier_frame(
        self, metric: str
    ) -> SimpleNamespace:
        if not self._stock_code:
            return _empty("客户/供应商集中度缺少股票代码")
        prefix = _eastmoney_market_prefix(self._stock_code)
        metric_type = "客户" if "客户" in metric else "供应商"
        params = {
            "source": "HSF10",
            "client": "PC",
            "reportName": "RPT_F10_BUSINESS_CUSTSUPP",
            "columns": "ALL",
            "filter": f'(SECUCODE="{self._stock_code}.{prefix}")',
            "sortTypes": "-1",
            "sortColumns": "REPORT_DATE",
        }
        try:
            payload = _fetch_eastmoney_json(
                f"{EASTMONEY_DATACENTER_URL}?{urlencode(params)}"
            )
        except Exception as exc:
            return _empty(f"东方财富集中度请求失败：{exc}")
        rows = [
            dict(item)
            for item in (((payload or {}).get("result") or {}).get("data") or [])
            if isinstance(item, dict) and _text(item.get("TYPE")) == metric_type
        ]
        if not rows:
            return _empty("东方财富数据中心未返回客户/供应商明细")
        latest_period = max(_date_key(row.get("REPORT_DATE")) for row in rows)
        latest = [
            row
            for row in rows
            if _date_key(row.get("REPORT_DATE")) == latest_period
            and (_number(row.get("RANK")) or 99) <= 5
        ]
        values = [
            value
            for value in (_number(row.get("TOI_RATIO")) for row in latest)
            if value is not None
        ]
        if not values:
            return _empty("东方财富客户/供应商集中度没有有效比例")
        output = {
            f"{metric}[{latest_period}]": round(sum(values), 6),
            "数据来源": "东方财富数据中心",
        }
        return SimpleNamespace(df=pd.DataFrame([output]), error="")

    def _eastmoney_product_frame(self) -> SimpleNamespace:
        """Return disclosed product and regional mix from the public F10 page."""

        if not self._stock_code:
            return _empty("东方财富主营构成兜底缺少股票代码")
        payload = getattr(self, "_eastmoney_business_cache", None)
        if payload is None:
            prefix = _eastmoney_market_prefix(self._stock_code)
            try:
                payload = _fetch_eastmoney_json(
                    f"{EASTMONEY_BUSINESS_ANALYSIS_URL}?code={prefix}{self._stock_code}"
                )
            except Exception as exc:
                return _empty(f"东方财富主营构成请求失败：{exc}")
            self._eastmoney_business_cache = payload
        if not isinstance(payload, dict):
            return _empty("东方财富主营构成返回结构无效")

        rows = [
            dict(item)
            for item in payload.get("zygcfx") or []
            if isinstance(item, dict) and _text(item.get("ITEM_NAME"))
        ]
        if not rows:
            scope_rows = payload.get("zyfw") or []
            if isinstance(scope_rows, dict):
                scope_rows = [scope_rows]
            scope = next(
                (
                    _text(item.get("BUSINESS_SCOPE"))
                    for item in scope_rows
                    if isinstance(item, dict) and _text(item.get("BUSINESS_SCOPE"))
                ),
                "",
            )
            if not scope:
                return _empty("东方财富未返回主营构成或经营范围")
            return SimpleNamespace(
                df=pd.DataFrame(
                    [
                        {
                            "所属行业": _text(
                                next(
                                    (
                                        item.get("EM2016")
                                        for item in payload.get("jbzl") or []
                                        if isinstance(item, dict)
                                    ),
                                    "",
                                )
                            ),
                            "经营范围": scope,
                            "主营业务": scope,
                            "数据来源": "东方财富F10",
                        }
                    ]
                ),
                error="",
                source="eastmoney",
            )

        latest_period = max(
            (_date_key(item.get("REPORT_DATE")) for item in rows),
            default="",
        )
        if latest_period:
            rows = [
                item
                for item in rows
                if _date_key(item.get("REPORT_DATE")) == latest_period
            ]

        def composition(kind: str) -> tuple[list[str], list[str]]:
            selected = [
                item
                for item in rows
                if _text(item.get("MAINOP_TYPE")) == kind
            ]
            selected.sort(
                key=lambda item: _number(item.get("MBI_RATIO")) or -1,
                reverse=True,
            )
            names: list[str] = []
            lines: list[str] = []
            for item in selected:
                name = _text(item.get("ITEM_NAME"))
                if not name or name in names:
                    continue
                names.append(name)
                income = _number(item.get("MAIN_BUSINESS_INCOME"))
                ratio = _number(item.get("MBI_RATIO"))
                details = []
                if income is not None:
                    details.append(f"收入{income / 1e8:.2f}亿元")
                if ratio is not None:
                    details.append(f"占比{ratio * 100:.2f}%")
                lines.append(
                    f"{name}（{'，'.join(details)}）"
                    if details
                    else name
                )
            return names, lines

        products, product_lines = composition("2")
        industries, industry_lines = composition("1")
        regions, region_lines = composition("3")
        if not any((products, industries, regions)):
            products = [
                _text(item.get("ITEM_NAME"))
                for item in rows
                if _text(item.get("ITEM_NAME"))
            ]
            product_lines = products
        output: dict[str, Any] = {
            "主营构成报告期": latest_period or "最新披露",
            "主营产品名称": "||".join(products[:20]),
            "主营业务构成": "；".join(product_lines[:20]),
            "数据来源": "东方财富F10",
        }
        if industries:
            output["行业构成"] = "；".join(industry_lines[:20])
        if regions:
            output["经营区域构成"] = "；".join(region_lines[:20])
        if not output["主营产品名称"] and not output["主营业务构成"]:
            return _empty("东方财富主营构成没有可展示项目")
        return SimpleNamespace(
            df=pd.DataFrame([output]),
            error="",
            source="eastmoney",
            period=latest_period,
        )

    def wencai_nlp(self, query: str) -> SimpleNamespace:
        if "公司全称" in query and "主营业务" in query:
            return self._finance_frame()
        if "流通股东" in query:
            return self._holders_frame()
        if "前十大股东持股比例合计" in query:
            return self._concentration_frame()
        if "总股本" in query and ("流通a股" in query or "限售a股" in query):
            return self._share_structure_frame(query)
        if "下次解禁" in query:
            return self._unlock_frame(query)
        if "融资余额" in query:
            return self._margin_frame(query)
        if "客户销售额合计占比" in query:
            return self._customer_supplier_frame(query, "客户销售额合计占比(前五大)")
        if "供应商采购金额合计占比" in query:
            return self._customer_supplier_frame(
                query, "供应商采购金额合计占比(前五大)"
            )
        if "专利数量" in query:
            return self._patent_frame(query)
        if "股东户数" in query:
            return self._holder_trend_frame(query)
        if (
            "主营业务构成" in query
            or "产品类型" in query
            or "境内外收入" in query
            or "境外收入" in query
            or "境内收入" in query
        ):
            result = self._query(query, "hithink-business-query", limit=10)
            if not result.df.empty:
                self.product_source = "wencai"
                self.product_error = ""
                return result
            fallback = self._eastmoney_product_frame()
            if not fallback.df.empty:
                self.product_source = "eastmoney"
                self.product_error = ""
                return fallback
            self.product_source = ""
            self.product_error = "; ".join(
                item
                for item in (
                    getattr(result, "error", ""),
                    getattr(fallback, "error", ""),
                )
                if item
            )
            return _empty(
                self.product_error or "问财与东方财富均未返回主营构成"
            )
        if "市盈率" in query and "市净率" in query:
            return self._peers_frame(query)
        if "行业" in query and "成分股" in query:
            return self._query(query, "hithink-industry-query", limit=50)
        return self._query(query, "hithink-finance-query", limit=20)

    def big_order_flow(self, thscode: str) -> SimpleNamespace:
        name = self._name_for(thscode)
        result = self._query(
            f"{name} 今日大单买入量 大单卖出量 大单买入额 大单卖出额",
            "hithink-market-query",
            limit=5,
        )
        if result.df.empty:
            fallback = self._ths_big_order_flow(thscode)
            if not fallback.df.empty:
                return fallback
            eastmoney = self._eastmoney_big_order_flow(thscode)
            if not eastmoney.df.empty:
                return eastmoney
            return _empty(
                "; ".join(
                    item
                    for item in (
                        getattr(result, "error", ""),
                        getattr(fallback, "error", ""),
                        getattr(eastmoney, "error", ""),
                    )
                    if item
                )
                or "问财、thsdk 与东方财富均未返回资金流"
            )
        row = result.df.iloc[0].to_dict()
        buy_amount_key = _first_key(row, "大单买入额[")
        sell_amount_key = _first_key(row, "大单卖出额[")
        buy_volume_key = _first_key(row, "大单买入量[")
        sell_volume_key = _first_key(row, "大单卖出量[")
        if not buy_amount_key or not sell_amount_key:
            fallback = self._ths_big_order_flow(thscode)
            if not fallback.df.empty:
                return fallback
            eastmoney = self._eastmoney_big_order_flow(thscode)
            if not eastmoney.df.empty:
                return eastmoney
            return _empty(
                "; ".join(
                    item
                    for item in (
                        "问财未返回今日大单买入/卖出金额",
                        getattr(fallback, "error", ""),
                        getattr(eastmoney, "error", ""),
                    )
                    if item
                )
            )
        period = re.search(r"\[(\d{8})\]", buy_amount_key)
        trade_date = period.group(1) if period else datetime.now(CN_TZ).strftime("%Y%m%d")
        formatted_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
        buy_amount = _number(row.get(buy_amount_key))
        sell_amount = _number(row.get(sell_amount_key))
        main_net_inflow = (
            buy_amount - sell_amount
            if buy_amount is not None and sell_amount is not None
            else None
        )
        rows = [
            {
                "时间": formatted_date,
                "成交方向": "1",
                "成交量": row.get(buy_volume_key) if buy_volume_key else "",
                "总金额": row.get(buy_amount_key),
                "委托买入价": "",
                "委托卖出价": "",
            },
            {
                "时间": formatted_date,
                "成交方向": "-1",
                "成交量": row.get(sell_volume_key) if sell_volume_key else "",
                "总金额": row.get(sell_amount_key),
                "委托买入价": "",
                "委托卖出价": "",
            },
        ]
        return SimpleNamespace(
            df=pd.DataFrame(rows, columns=["时间", "成交方向", "成交量", "总金额", "委托买入价", "委托卖出价"]),
            error="",
            scope="daily_aggregate",
            source="wencai",
            main_net_inflow=main_net_inflow,
        )

    def _eastmoney_big_order_flow(self, thscode: str) -> SimpleNamespace:
        """Return daily net-flow aggregates when tick-like big orders are unavailable."""

        code = str(thscode)[-6:]
        if not re.fullmatch(r"\d{6}", code):
            code = self._stock_code
        if not re.fullmatch(r"\d{6}", str(code or "")):
            return _empty("东方财富资金流兜底缺少股票代码")
        params = {
            "lmt": "10",
            "klt": "101",
            "ut": EASTMONEY_UT,
            "secid": _eastmoney_secid(str(code)),
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56",
        }
        try:
            payload = _fetch_eastmoney_json(
                f"{EASTMONEY_STOCK_FLOW_URL}?{urlencode(params)}",
                referer=EASTMONEY_QUOTE_REFERER,
            )
        except Exception as exc:
            return _empty(f"东方财富资金流请求失败：{exc}")
        klines = ((payload or {}).get("data") or {}).get("klines") or []
        rows = []
        for line in klines:
            values = str(line).split(",")
            if len(values) < 6:
                continue
            row = {
                "时间": values[0],
                "主力净流入": _number(values[1]),
                "小单净流入": _number(values[2]),
                "中单净流入": _number(values[3]),
                "大单净流入": _number(values[4]),
                "超大单净流入": _number(values[5]),
                "数据来源": "东方财富",
            }
            rows.append(
                {
                    key: value
                    for key, value in row.items()
                    if value is not None and value != ""
                }
            )
        if not rows:
            return _empty("东方财富未返回个股日度资金流")
        latest_main = _number(rows[-1].get("主力净流入"))
        return SimpleNamespace(
            df=pd.DataFrame(rows),
            error="",
            scope="daily_net_flow",
            source="eastmoney",
            main_net_inflow=latest_main,
        )

    def _ths_big_order_flow(self, thscode: str) -> SimpleNamespace:
        client = self._ths_connection()
        if client is None:
            return _empty(
                getattr(self, "_ths_connect_error", "")
                or "同花顺 thsdk 不可用"
            )
        try:
            payload = client.capital_flow(thscode, count=200)
        except Exception as exc:
            message = str(exc)
            if "请先连接" not in message and "not connect" not in message.lower():
                return _empty(f"thsdk 大单流向查询失败：{message}")
            self._reset_ths_client()
            client = self._ths_connection()
            if client is None:
                return _empty(
                    getattr(self, "_ths_connect_error", "")
                    or "thsdk 大单流向重连失败"
                )
            try:
                payload = client.capital_flow(thscode, count=200)
            except Exception as retry_exc:
                return _empty(f"thsdk 大单流向重连后失败：{retry_exc}")
        rows = [dict(row) for row in payload.get("items") or [] if isinstance(row, dict)]
        if not rows:
            return _empty("thsdk 未返回大单成交")
        rows.sort(key=lambda row: float(row.get("时间") or 0))
        big_rows = [
            row
            for row in rows
            if str(row.get("成交方向码")) in {"1", "-1", "4", "-4"}
        ]
        if big_rows:
            rows = big_rows[-20:]
        else:
            rows = rows[-20:]
        unique_rows = []
        seen = set()
        for row in rows:
            key = (
                row.get("时间"),
                row.get("成交方向码"),
                row.get("成交量"),
                row.get("总金额"),
            )
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(row)
        rows = unique_rows[-20:]
        for row in rows:
            code = row.get("成交方向码")
            if code not in (None, ""):
                row["成交方向"] = str(code)
        columns = list(payload.get("columns") or rows[0].keys())
        return SimpleNamespace(
            df=pd.DataFrame(rows, columns=columns),
            error="",
            scope="tick",
            source="thsdk",
        )

    def _news_items(self, code: str) -> list[dict[str, Any]]:
        if self._news_cache is not None:
            return self._news_cache
        if not self.market:
            self._news_cache = []
            return []
        try:
            result = self.market.news(code, count=20)
        except mq.QueryError:
            self._news_cache = []
            return []
        items = []
        for item in result.get("items") or []:
            title = _text(item.get("title"))
            if not title:
                continue
            publish_ms = _number(item.get("publish_time_ms"))
            items.append(
                {
                    "Time": publish_ms / 1000 if publish_ms else "",
                    "Title": title,
                    "Source": _text(item.get("source")),
                    "Summary": _text(item.get("summary")),
                    "_category": "新闻",
                }
            )
        self._news_cache = items
        return items

    def news(self, text_id: int, pure_code: str, market_prefix: str) -> SimpleNamespace:
        items = self._news_items(pure_code)
        if not items:
            return _empty(self.market_error or "扶摇新闻查询没有返回数据")
        ranges = {0x3805: items[:10], 0x3806: items[10:20], 0x3808: items[20:30]}
        current = ranges.get(int(text_id), [])
        frame = pd.DataFrame(current, columns=["Time", "Title", "Source", "Summary", "_category"])
        return SimpleNamespace(df=frame, error="" if current else "empty")


def preflight_industry_cloud(keyword: str) -> dict[str, Any]:
    """Check report-grade industry channels without full collection."""

    started = time.time()
    market, market_error = _safe_market_client()
    if not market:
        raise CloudSourceError(market_error or "扶摇行情凭据未配置", "missing_api_key")

    sector_data = market.sector(keyword)
    sector_raw = sector_data.get("sector") or {}
    sector_name = _text(sector_raw.get("name")) or keyword
    sector_code = _text(sector_raw.get("thscode")) or _text(sector_raw.get("vendor_thscode"))
    members = [
        item
        for item in sector_data.get("members") or []
        if isinstance(item, dict) and _text(item.get("thscode"))
    ]
    if not members:
        raise CloudSourceError(f"板块 {sector_name} 没有成分股", "empty_sector")

    ticker = _text(members[0].get("ticker"))[-6:]
    quote = market.realtime([ticker])
    if not quote.get("data"):
        raise CloudSourceError("扶摇实时行情预检未返回数据", "empty_quote")

    wencai, wencai_source, wencai_error = _optional_wencai_client()
    wencai_ok = False
    if wencai:
        try:
            wencai_payload = wencai.query(
                "hithink-industry-query",
                f"{sector_name}行业成分股 最新价",
                page=1,
                limit=5,
            )
            frame = _frame_result(wencai_payload)
            if frame.df.empty:
                wencai_error = (
                    f"没有返回 {sector_name} 数据：{frame.error or 'empty'}"
                )
            else:
                wencai_ok = True
        except mq.QueryError as exc:
            wencai_error = str(exc)

    thsdk_probe: dict[str, Any] | None = None
    thsdk_error = ""
    eastmoney_probe: dict[str, Any] | None = None
    eastmoney_error = ""
    hithink_probe: dict[str, Any] | None = None
    hithink_error = ""
    fallback_metrics: dict[str, Any] = {}
    if not wencai_ok:
        try:
            thsdk_probe = _thsdk_sector_metrics(
                sector_code,
                sector_data.get("snapshot") or {},
            )
        except Exception as exc:
            thsdk_error = str(exc)
        else:
            for key, value in (thsdk_probe.get("metrics") or {}).items():
                if _number(value) is not None:
                    fallback_metrics[key] = value

        missing = [
            key
            for key in INDUSTRY_SNAPSHOT_FIELDS
            if _number(fallback_metrics.get(key)) is None
        ]
        if missing:
            try:
                eastmoney_probe = _eastmoney_sector_metrics(sector_name or keyword)
            except Exception as exc:
                eastmoney_error = str(exc)
            else:
                for key, value in (eastmoney_probe.get("metrics") or {}).items():
                    if (
                        _number(fallback_metrics.get(key)) is None
                        and _number(value) is not None
                    ):
                        fallback_metrics[key] = value

        missing = [
            key
            for key in INDUSTRY_SNAPSHOT_FIELDS
            if _number(fallback_metrics.get(key)) is None
        ]
        if missing:
            try:
                hithink_probe = _hithink_sector_metrics(
                    sector_code,
                    sector_data.get("snapshot") or {},
                )
            except Exception as exc:
                hithink_error = str(exc)
            else:
                for key, value in (hithink_probe.get("metrics") or {}).items():
                    if (
                        _number(fallback_metrics.get(key)) is None
                        and _number(value) is not None
                    ):
                        fallback_metrics[key] = value

        missing = [
            key
            for key in INDUSTRY_SNAPSHOT_FIELDS
            if _number(fallback_metrics.get(key)) is None
        ]
        if missing:
            details = [
                f"问财={wencai_error or '未返回数据'}",
                f"同花顺thsdk={thsdk_error or '未返回指标'}",
                f"东方财富={eastmoney_error or '未返回指标'}",
                f"同花顺={hithink_error or '未返回指标'}",
            ]
            raise CloudSourceError(
                "行业预检失败：" + "；".join(details)
                + "；缺少板块指标：" + "、".join(missing),
                "industry_probe_failed",
            )

    result = {
        "ok": True,
        "mode": "preflight",
        "sector": sector_raw,
        "members_count": len(members),
        "channels": {
            "fuyao": "ok",
            "wencai": "ok" if wencai_ok else "unavailable",
            "thsdk": (
                "ok" if thsdk_probe
                else "unavailable" if thsdk_error
                else "not_needed"
            ),
            "eastmoney": (
                "ok" if eastmoney_probe
                else "unavailable" if eastmoney_error
                else "not_needed"
            ),
            "hithink": (
                "ok" if hithink_probe
                else "unavailable" if hithink_error
                else "not_needed"
            ),
            "wencai_source": wencai_source,
        },
        "elapsed_seconds": round(time.time() - started, 1),
    }
    if wencai_error and not wencai_ok:
        warnings = [f"官方问财不可用：{wencai_error}"]
        if thsdk_probe:
            warnings.append("已用同花顺 thsdk 板块扩展快照兜底")
        if eastmoney_probe:
            warnings.append("已用东方财富板块指标兜底")
        if hithink_probe:
            warnings.append("已用同花顺行业指数日线兜底")
        result["warnings"] = warnings
    if thsdk_probe:
        result["thsdk_board"] = thsdk_probe["board"]
        result["thsdk_as_of"] = thsdk_probe["as_of"]
    if eastmoney_probe:
        result["eastmoney_board"] = eastmoney_probe["board"]
        result["eastmoney_as_of"] = eastmoney_probe["as_of"]
    if hithink_probe:
        result["hithink_board"] = hithink_probe["board"]
        result["hithink_as_of"] = hithink_probe["as_of"]
    if fallback_metrics:
        result["sector_metrics"] = fallback_metrics
    return result


def collect_industry_cloud(keyword: str, limit: int = 15) -> dict[str, Any]:
    """Collect the industry report schema using only Fuyao and official Wencai."""

    started = time.time()
    warnings: list[str] = []
    market, market_error = _safe_market_client()
    if not market:
        raise CloudSourceError(market_error or "扶摇行情凭据未配置", "missing_api_key")
    wencai, wencai_source, wencai_error = _optional_wencai_client()
    if wencai_error:
        warnings.append(f"官方问财不可用，将使用东方财富补齐行业数据：{wencai_error}")
    sector_data = market.sector(keyword)
    sector_raw = sector_data.get("sector") or {}
    sector_name = _text(sector_raw.get("name")) or keyword
    sector_code = _text(sector_raw.get("thscode")) or _text(sector_raw.get("vendor_thscode"))
    members_all = [
        {
            "thscode": _text(item.get("thscode")).upper(),
            "ticker": _text(item.get("ticker"))[-6:],
            "name": _normalize_name(item.get("name")),
            "main_board": _text(item.get("thscode"))[-6:].startswith(("60", "00")),
        }
        for item in sector_data.get("members") or []
        if isinstance(item, dict) and _text(item.get("thscode"))
    ]
    members_all.sort(key=lambda item: (not item["main_board"], item["ticker"]))
    members = members_all[: max(1, int(limit))]
    if not members:
        raise CloudSourceError(f"板块 {sector_name} 没有成分股", "empty_sector")

    def query(query_text: str, skill_id: str) -> SimpleNamespace:
        if not wencai:
            return _empty(wencai_error or "wencai unavailable")
        try:
            payload = wencai.query(skill_id, query_text, page=1, limit=50)
        except mq.QueryError as exc:
            return _empty(str(exc))
        if QUERY_DELAY > 0:
            time.sleep(QUERY_DELAY)
        return _frame_result(payload)

    year = datetime.now(CN_TZ).year - 1
    financial = query(
        f"{sector_name}行业成分股 市盈率(pe) 总市值 市净率 {year}年加权净资产收益率 "
        f"{year}年营业收入 {year}年销售毛利率 {year}年销售净利率 {year}年股息率",
        "hithink-industry-query",
    )
    growth = query(
        f"{sector_name}行业成分股 {year}年归母净利润同比增长率 年初至今涨跌幅 "
        "所属同花顺行业 主营业务 非ST",
        "hithink-industry-query",
    )
    if financial.df.empty and growth.df.empty:
        financial = query(
            f"{sector_name}概念成分股 市盈率(pe) 总市值 市净率 {year}年加权净资产收益率 "
            f"{year}年营业收入 {year}年销售毛利率 {year}年销售净利率 {year}年股息率",
            "hithink-industry-query",
        )
        growth = query(
            f"{sector_name}概念成分股 {year}年归母净利润同比增长率 年初至今涨跌幅 "
            "所属同花顺行业 主营业务 非ST",
            "hithink-industry-query",
        )

    financial_by_code: dict[str, dict[str, Any]] = {}
    financial_by_name: dict[str, dict[str, Any]] = {}
    for frame in (financial.df, growth.df):
        for _, series in frame.iterrows():
            row = series.to_dict()
            code = _text(_first(row, "股票代码", "代码"))
            pure = code[-6:] if len(code) >= 6 else code
            name = _normalize_name(_first(row, "股票简称", "名称"))
            if not pure and not name:
                continue
            item = financial_by_code.get(pure, {})
            item.update(row)
            if pure:
                financial_by_code[pure] = item
            if name:
                financial_by_name[name] = item

    def pick_metric(row: dict[str, Any], *needles: str) -> float | None:
        return _number(_first_priority(row, *needles))

    def missing_metrics(row: dict[str, Any]) -> list[str]:
        values = {
            "price": pick_metric(row, "最新价"),
            "change_pct": pick_metric(row, "最新涨跌幅"),
            "pe": pick_metric(
                row,
                "最新动态市盈率",
                "市盈率(pe)",
                "最新市盈率ttm",
                "市盈率",
            ),
            "pb": pick_metric(row, "最新市净率", "市净率"),
            "market_cap": pick_metric(row, "总市值"),
            "revenue": pick_metric(row, f"营业收入[{year}1231]", "营业收入"),
            "net_profit": pick_metric(
                row,
                f"归母净利润[{year}1231]",
                "归母净利润",
                "净利润",
            ),
            "gross_margin": pick_metric(row, "销售毛利率"),
            "net_margin": pick_metric(row, "销售净利率"),
            "roe": pick_metric(
                row,
                f"加权净资产收益率[{year}1231]",
                "加权净资产收益率",
                "净资产收益率ROE",
                "净资产收益率",
            ),
            "revenue_yoy": pick_metric(
                row,
                f"营业收入同比增长率[{year}1231]",
                "营业收入同比增长率",
            ),
            "profit_yoy": pick_metric(
                row,
                f"归母净利润同比增长率[{year}1231]",
                "归母净利润同比增长率",
                "净利润同比增长率",
            ),
            "ytd_change": pick_metric(row, "年初至今涨跌幅", "年涨跌幅"),
            "dividend_yield": pick_metric(row, "年度股息率", "股息率"),
        }
        missing = [name for name, value in values.items() if value is None]
        if _is_missing(_join(_first(row, "主营产品", "主营业务"), "||")):
            missing.append("main_business")
        return missing

    fallback_codes: list[str] = []
    for member in members:
        row = (
            financial_by_code.get(member["ticker"])
            or financial_by_name.get(member["name"])
            or {}
        )
        if missing_metrics(row):
            fallback_codes.append(member["ticker"])

    fallback: dict[str, dict[str, Any]] = {}
    fallback_errors: list[str] = []
    if fallback_codes:
        try:
            fallback_quotes = _eastmoney_quote_snapshot(fallback_codes)
        except Exception as exc:
            fallback_quotes = {}
            fallback_errors.append(f"行情请求失败：{exc}")
        for member in members:
            code = member["ticker"]
            if code not in fallback_codes:
                continue
            quote = fallback_quotes.get(code, {})
            annual: dict[str, Any] = {}
            try:
                annual = _eastmoney_annual_financials(code, year)
            except Exception as exc:
                fallback_errors.append(f"{code} 年度财务请求失败：{exc}")
            business = _eastmoney_main_business(code)
            price = _number(quote.get("f2"))
            values = {
                "price": price,
                "change_pct": _number(quote.get("f3")),
                "pe": _number(quote.get("f9")),
                "pb": _number(quote.get("f23")),
                "market_cap": _number(quote.get("f20")),
                "ytd_change": _number(quote.get("f25")),
                "revenue": _number(annual.get("TOTALOPERATEREVE")),
                "net_profit": _number(annual.get("PARENTNETPROFIT")),
                "gross_margin": _number(annual.get("XSMLL")),
                "net_margin": _number(annual.get("XSJLL")),
                "roe": _number(annual.get("ROEJQ")),
                "revenue_yoy": _number(annual.get("TOTALOPERATEREVETZ")),
                "profit_yoy": _number(annual.get("PARENTNETPROFITTZ")),
                "dividend_yield": _eastmoney_dividend_yield(code, price),
                "main_business": business.get("main_business", ""),
            }
            values = {
                key: value
                for key, value in values.items()
                if value not in (None, "")
            }
            if values:
                values["raw"] = {
                    "annual": annual,
                    "quote": quote,
                    "business": business,
                }
                fallback[code] = values
        if fallback:
            warnings.append(
                "问财行业财务数据不完整，已使用东方财富 F10 年报与实时行情补齐"
                if wencai
                else "行业财务数据不完整，已使用东方财富 F10 年报与实时行情补齐"
            )
        if fallback_errors:
            warnings.append("东方财富行业兜底未完整成功：" + "；".join(fallback_errors[:5]))

    quote_payload: dict[str, Any] = {}
    try:
        quote_payload = market.realtime([member["ticker"] for member in members])
    except mq.QueryError:
        quote_payload = {}
    quote_rows = quote_payload.get("data") or {}
    stocks: list[dict[str, Any]] = []
    for member in members:
        row = financial_by_code.get(member["ticker"]) or financial_by_name.get(member["name"]) or {}
        fallback_row = fallback.get(member["ticker"], {})
        if not row and not fallback_row:
            warnings.append(f"成分股财务数据不可用：{member['name']}")
        elif not row and wencai:
            warnings.append(f"问财未返回成分股财务数据：{member['name']}")
        market_cap = _coalesce(
            _number(_first(row, "总市值")),
            fallback_row.get("market_cap"),
        )
        revenue = _coalesce(
            _number(_first(row, f"营业收入[{year}1231]", "营业收入")),
            fallback_row.get("revenue"),
        )
        profit = _coalesce(
            _number(_first(row, f"归母净利润[{year}1231]", "归母净利润", "净利润")),
            fallback_row.get("net_profit"),
        )
        quote_row = {}
        for key, value in quote_rows.items():
            if _text(value.get("ticker")) == member["ticker"] or str(key)[-6:] == member["ticker"]:
                quote_row = value
                break
        stock = {
            "name": member["name"],
            "ticker": member["ticker"],
            "thscode": member["thscode"],
            "price": _coalesce(
                _number(_first(row, "最新价")),
                _number(quote_row.get("last_price")),
                fallback_row.get("price"),
            ),
            "change_pct": _coalesce(
                _number(_first(row, "最新涨跌幅")),
                _number(quote_row.get("price_change_ratio_pct")),
                fallback_row.get("change_pct"),
            ),
            "pe": _coalesce(
                _number(
                    _first_priority(
                        row,
                        "最新动态市盈率",
                        "市盈率(pe)",
                        "最新市盈率ttm",
                        "市盈率",
                    )
                ),
                fallback_row.get("pe"),
            ),
            "pb": _coalesce(
                _number(_first(row, "最新市净率", "市净率")),
                fallback_row.get("pb"),
            ),
            "dividend_yield": _coalesce(
                _number(_first_priority(row, "年度股息率", "股息率")),
                fallback_row.get("dividend_yield"),
            ),
            "market_cap": market_cap,
            "revenue": revenue,
            "net_profit": profit,
            "gross_margin": _coalesce(
                _number(_first(row, "销售毛利率")),
                fallback_row.get("gross_margin"),
            ),
            "net_margin": _coalesce(
                _number(_first(row, "销售净利率")),
                fallback_row.get("net_margin"),
            ),
            "roe": _coalesce(
                _number(
                    _first_priority(
                        row,
                        f"加权净资产收益率[{year}1231]",
                        "加权净资产收益率",
                        "净资产收益率ROE",
                        "净资产收益率",
                    )
                ),
                fallback_row.get("roe"),
            ),
            "revenue_yoy": _coalesce(
                _number(
                    _first_priority(
                        row,
                        f"营业收入同比增长率[{year}1231]",
                        "营业收入同比增长率",
                    )
                ),
                fallback_row.get("revenue_yoy"),
            ),
            "profit_yoy": _coalesce(
                _number(
                    _first_priority(
                        row,
                        f"归母净利润同比增长率[{year}1231]",
                        "归母净利润同比增长率",
                        "净利润同比增长率",
                    )
                ),
                fallback_row.get("profit_yoy"),
            ),
            "ytd_change": _coalesce(
                _number(_first(row, "年初至今涨跌幅", "年涨跌幅")),
                fallback_row.get("ytd_change"),
            ),
            "industry": _join(_first(row, "所属同花顺行业")) or sector_name,
            "main_business": (
                _join(_first(row, "主营产品", "主营业务"), "||")
                or fallback_row.get("main_business", "")
            ),
            "raw": {key: _json_value(value) for key, value in row.items()},
        }
        if fallback_row:
            stock["data_sources"] = (["wencai"] if row else []) + ["eastmoney"]
            stock["raw"]["_eastmoney"] = _json_value(fallback_row.get("raw") or {})
        if market_cap is not None:
            stock["market_cap_yi"] = round(market_cap / 1e8, 2)
        if revenue is not None:
            stock["revenue_yi"] = round(revenue / 1e8, 2)
        if profit is not None:
            stock["net_profit_yi"] = round(profit / 1e8, 2)
        stocks.append(stock)

    missing_quote_fields = {
        "price",
        "change_pct",
        "pe",
        "pb",
        "market_cap_yi",
        "ytd_change",
    }
    tencent_codes = [
        str(item.get("ticker") or "")
        for item in stocks
        if any(item.get(key) is None for key in missing_quote_fields)
    ]
    tencent_used_codes: list[str] = []
    if tencent_codes:
        try:
            tencent_quotes = _tencent_quote_snapshot(tencent_codes)
        except Exception as exc:
            warnings.append(f"腾讯行情兜底失败：{exc}")
        else:
            tencent_used_codes = _apply_tencent_quote_fallback(
                stocks,
                tencent_quotes,
            )
            if tencent_used_codes:
                warnings.append(
                    "东方财富行情不完整，已使用腾讯行情补齐估值、总市值与年内涨幅"
                )

    # Dividend yield depends on price. Recalculate after quote fallbacks so a
    # successful Tencent fill is not discarded merely because Eastmoney's
    # batch quote was unavailable.
    _fill_missing_dividend_yields(stocks)

    snapshot = {
        str(key): value
        for key, value in (sector_data.get("snapshot") or {}).items()
        if str(key) != "raw" and isinstance(value, (str, int, float, bool))
    }
    index_metrics = query(
        f"{sector_name}行业 5日涨幅 10日涨幅 20日涨幅 主力净流入 量比",
        "hithink-industry-query",
    )
    if not index_metrics.df.empty:
        index_row = index_metrics.df.iloc[0].to_dict()
        change_keys = [
            (str(key), value)
            for key, value in index_row.items()
            if str(key).startswith("涨跌幅[")
        ]

        def window_days(item: tuple[str, Any]) -> int:
            match = re.search(r"\[(\d{8})-(\d{8})\]", item[0])
            if not match:
                return 10**9
            start = datetime.strptime(match.group(1), "%Y%m%d")
            end = datetime.strptime(match.group(2), "%Y%m%d")
            return max(0, (end - start).days)

        change_keys.sort(key=window_days)
        if len(change_keys) >= 3:
            snapshot["5日涨幅"] = _number(change_keys[0][1])
            snapshot["10日涨幅"] = _number(change_keys[1][1])
            snapshot["20日涨幅"] = _number(change_keys[2][1])
        snapshot["主力净流入"] = _number(_first(index_row, "主力净买入额", "主力净流入"))
        snapshot["量比"] = _number(_first(index_row, "量比"))

    thsdk_sector_used = False
    thsdk_sector_board: dict[str, str] = {}
    thsdk_sector_as_of = ""
    thsdk_sector_metrics: dict[str, Any] = {}
    eastmoney_sector_used = False
    eastmoney_sector_board: dict[str, str] = {}
    eastmoney_sector_as_of = ""
    eastmoney_sector_metrics: dict[str, Any] = {}
    hithink_sector_used = False
    hithink_sector_board: dict[str, str] = {}
    hithink_sector_as_of = ""
    missing_snapshot = [
        key
        for key in INDUSTRY_SNAPSHOT_FIELDS
        if _number(snapshot.get(key)) is None
    ]
    if missing_snapshot:
        try:
            thsdk_sector = _thsdk_sector_metrics(
                sector_code,
                sector_data.get("snapshot") or {},
            )
        except Exception as exc:
            warnings.append(f"同花顺 thsdk 板块快照兜底失败：{exc}")
        else:
            thsdk_sector_metrics = thsdk_sector.get("metrics") or {}
            for key, value in thsdk_sector_metrics.items():
                if _number(snapshot.get(key)) is None:
                    snapshot[key] = value
            thsdk_sector_used = True
            thsdk_sector_board = thsdk_sector.get("board") or {}
            thsdk_sector_as_of = _text(thsdk_sector.get("as_of"))
            warnings.append(
                "问财板块指标不完整，已使用同花顺 thsdk 板块扩展快照补齐"
                if wencai
                else "板块指标不完整，已使用同花顺 thsdk 板块扩展快照补齐"
            )

    missing_snapshot = [
        key
        for key in INDUSTRY_SNAPSHOT_FIELDS
        if _number(snapshot.get(key)) is None
    ]
    if missing_snapshot:
        try:
            eastmoney_sector = _eastmoney_sector_metrics(sector_name or keyword)
        except Exception as exc:
            warnings.append(f"东方财富板块指标兜底失败：{exc}")
        else:
            eastmoney_sector_metrics = eastmoney_sector.get("metrics") or {}
            for key, value in eastmoney_sector_metrics.items():
                if _number(snapshot.get(key)) is None:
                    snapshot[key] = value
            eastmoney_sector_used = True
            eastmoney_sector_board = eastmoney_sector.get("board") or {}
            eastmoney_sector_as_of = _text(eastmoney_sector.get("as_of"))
            warnings.append(
                "问财板块指标不完整，已使用东方财富板块行情补齐"
                if wencai
                else "板块指标不完整，已使用东方财富板块行情补齐"
            )

    missing_snapshot = [
        key
        for key in INDUSTRY_SNAPSHOT_FIELDS
        if _number(snapshot.get(key)) is None
    ]
    if missing_snapshot:
        try:
            hithink_sector = _hithink_sector_metrics(
                sector_code,
                sector_data.get("snapshot") or {},
            )
        except Exception as exc:
            warnings.append(f"同花顺行业指数兜底失败：{exc}")
        else:
            for key, value in (hithink_sector.get("metrics") or {}).items():
                if snapshot.get(key) is None:
                    snapshot[key] = value
            hithink_sector_used = True
            hithink_sector_board = hithink_sector.get("board") or {}
            hithink_sector_as_of = _text(hithink_sector.get("as_of"))
            warnings.append(
                "问财板块指标不完整，已使用同花顺行业指数日线补齐"
                if wencai
                else "板块指标不完整，已使用同花顺行业指数日线补齐"
            )

    missing_snapshot = [
        key
        for key in INDUSTRY_SNAPSHOT_FIELDS
        if _number(snapshot.get(key)) is None
    ]
    if missing_snapshot:
        raise CloudSourceError(
            "行业板块指标缺失：" + "、".join(missing_snapshot),
            "incomplete_sector_metrics",
        )

    news: list[dict[str, Any]] = []
    seen: set[str] = set()
    for member in members[:5]:
        try:
            payload = market.news(member["ticker"], count=3)
        except mq.QueryError:
            continue
        for item in payload.get("items") or []:
            title = _text(item.get("title"))
            if not title or title in seen:
                continue
            seen.add(title)
            publish_ms = _number(item.get("publish_time_ms"))
            news.append(
                {
                    "title": title,
                    "time": publish_ms / 1000 if publish_ms else "",
                    "stock": member["name"],
                    "ticker": member["ticker"],
                    "category": "新闻",
                    "raw": {key: _json_value(value) for key, value in item.items()},
                }
            )

    sector = {
        **sector_raw,
        "name": sector_name,
        "keyword": keyword,
        "normalized_keyword": _normalize_name(keyword),
        "block_code": sector_code,
        "kind": "industry",
        "candidates": [],
    }
    if thsdk_sector_used:
        sector["thsdk_block_code"] = thsdk_sector_board.get("code", "")
        sector["metrics_as_of"] = thsdk_sector_as_of
    if eastmoney_sector_used:
        sector["eastmoney_block_code"] = eastmoney_sector_board.get("code", "")
        sector["metrics_as_of"] = (
            sector.get("metrics_as_of")
            or eastmoney_sector_as_of
            or hithink_sector_as_of
        )
    if hithink_sector_used:
        sector["hithink_index_code"] = hithink_sector_board.get("code", "")
        sector["metrics_as_of"] = hithink_sector_as_of or sector.get("metrics_as_of", "")
    if not snapshot:
        warnings.append("板块行情快照为空")
    if not news:
        warnings.append("未采集到成分股新闻；报告需用公开信息补充催化")
    if stocks and not any(item.get("revenue") is not None for item in stocks):
        warnings.append("财务数据为空；不得用推算值替代")

    sources = ["扶摇 REST：板块目录/成分/板块快照/新闻/个股行情补充"]
    if wencai:
        sources.append(
            "官方问财 OpenAPI：实时行情主数据、行业财务、估值与增速"
            f"（{wencai_source}）"
        )
    if fallback:
        sources.append("东方财富 F10/行情：问财缺失项的年度财务、估值与行情")
    if tencent_used_codes:
        sources.append("腾讯行情：缺失的估值、总市值与年内涨幅")
    if thsdk_sector_used:
        labels = [
            key
            for key in INDUSTRY_SNAPSHOT_FIELDS
            if key in thsdk_sector_metrics
        ]
        sources.append("同花顺 thsdk 板块扩展快照（与本地同源）：" + "、".join(labels))
    if eastmoney_sector_used:
        labels = [
            key
            for key in INDUSTRY_SNAPSHOT_FIELDS
            if key in eastmoney_sector_metrics
        ]
        sources.append("东方财富板块行情：" + "、".join(labels))
    if hithink_sector_used:
        sources.append("同花顺金融数据CLI：行业指数日线与量比")

    return {
        "fetch_time": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "keyword": keyword,
        "sector": sector,
        "members_count": len(members),
        "members": members,
        "stocks": stocks,
        "sector_snapshot": snapshot,
        "news": news,
        "warnings": warnings,
        "missing_sections": [] if stocks else ["stocks"],
        "sources": sources,
        "elapsed_seconds": round(time.time() - started, 1),
    }
