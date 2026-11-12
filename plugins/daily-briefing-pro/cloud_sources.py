"""Cloud-only data adapters for the portable report collectors.

The reports originally used the guest THS desktop transport for every data
domain. That transport is not a reliable cloud dependency. This module keeps
the same report schemas while sourcing quotes, holders, fund-flow aggregates
and fundamentals from the official iWencai OpenAPI, with Fuyao REST supplying
security lookup, sector membership, snapshots, news and quote fallback.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd


PLUGIN_ROOT = Path(__file__).resolve().parent
MARKET_SCRIPTS = PLUGIN_ROOT / "skills" / "market-query" / "scripts"
if str(MARKET_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(MARKET_SCRIPTS))

import market_query as mq  # noqa: E402


CN_TZ = ZoneInfo("Asia/Shanghai")
WENCAI_TIMEOUT = int(os.getenv("DAILY_BRIEFING_WENCAI_TIMEOUT", "25"))
QUERY_DELAY = float(os.getenv("DAILY_BRIEFING_WENCAI_DELAY", "0.35"))
EASTMONEY_TIMEOUT = int(os.getenv("DAILY_BRIEFING_EASTMONEY_TIMEOUT", "15"))
EASTMONEY_HOLDER_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/"
    "ShareholderResearch/PageAjax"
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


def _fetch_eastmoney_holder_payload(code: str) -> dict[str, Any]:
    """Fetch the public F10 shareholder disclosure page.

    The page is used only when the official Wencai query returns no holder
    records.  It is a disclosed-data fallback, not a reconstructed estimate.
    """

    prefix = _eastmoney_market_prefix(code)
    url = f"{EASTMONEY_HOLDER_URL}?code={prefix}{code}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://emweb.securities.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=EASTMONEY_TIMEOUT) as response:
        raw = response.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("东方财富 F10 返回结构无效")
    return payload


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
            "云端报告需要 IWENCAI_API_KEY；请通过 secrets/iwencai_api_key 注入问财 OpenAPI 凭据",
            "missing_api_key",
        )
    return mq.WencaiClient(key, timeout=WENCAI_TIMEOUT), source or "env"


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
        self.wencai, self.wencai_source = _wencai_client()
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

    def __enter__(self) -> "CloudStockAdapter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def connect(self, max_retries: int = 1) -> SimpleNamespace:
        return SimpleNamespace(error="", connected=True)

    def _query(self, query: str, skill_id: str = "hithink-finance-query", limit: int = 20) -> SimpleNamespace:
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

    def market_data_cn(self, thscode: str, query_key: str) -> SimpleNamespace:
        name = self._name_for(thscode)
        first, second = self._quote_rows(name)
        if not first and not second:
            return _empty("问财行情查询没有返回数据")
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
            "换手率": _number(_first(merged, "换手率")),
            "振幅": _number(_first(merged, "振幅")),
            "主力净流入": main_inflow,
            "主力净量": (main_inflow / amount * 100) if main_inflow is not None and amount else None,
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
        normalized = {key: "暂无" if value is None else value for key, value in row.items()}
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
        if not merged:
            return _empty("问财财务与基本信息查询没有返回数据")

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

    def _eastmoney_holders_frame(self) -> SimpleNamespace:
        if not self._stock_code:
            return _empty("东方财富股东兜底缺少股票代码")
        try:
            payload = _fetch_eastmoney_holder_payload(self._stock_code)
        except Exception as exc:
            return _empty(f"东方财富股东兜底请求失败：{exc}")

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

    def _concentration_frame(self) -> SimpleNamespace:
        query = (
            f"{self.stock_name} 前十大股东持股比例合计 第一大股东持股比例 "
            "第一大股东名称 户均持股数量 户均持股市值"
        )
        result = self._query(query, "hithink-finance-query", limit=5)
        if result.df.empty:
            return result
        row = result.df.iloc[0].to_dict()
        total_key = next(
            (str(key) for key in row if str(key).startswith("持股比例[")),
            None,
        )
        total = _number(row.get(total_key)) if total_key else None
        if total is not None and 0 < total <= 1:
            total *= 100
        row["前十大股东持股比例合计"] = total
        row["第一大股东持股比例"] = _number(_first(row, "持股比例"))
        row["第一大股东名称"] = _text(_first(row, "名称", "第一大股东名称"))
        quantity_key = _first_key(row, "户均持股数量[")
        value_key = _first_key(row, "户均持股市值[")
        if quantity_key:
            row["户均持股数量"] = row.get(quantity_key)
        if value_key:
            row["户均持股市值"] = row.get(value_key)
        return SimpleNamespace(df=pd.DataFrame([row]), error="")

    def _patent_frame(self, query: str) -> SimpleNamespace:
        result = self._query(query, "hithink-finance-query", limit=5)
        if result.df.empty:
            return result
        row = result.df.iloc[0].to_dict()
        for key, value in list(row.items()):
            text = str(key)
            if text.startswith("专利数量["):
                row[f"专利数量合计{text[len('专利数量') :]}"] = value
        return SimpleNamespace(df=pd.DataFrame([row]), error="")

    def _holder_trend_frame(self, query: str) -> SimpleNamespace:
        result = self._query(query, "hithink-finance-query", limit=5)
        if result.df.empty:
            return result
        row = result.df.iloc[0].to_dict()
        today = datetime.now(CN_TZ).strftime("%Y%m%d")
        filtered: dict[str, Any] = {}
        for key, value in row.items():
            match = re.search(r"\[(\d{8})\]", str(key))
            if match and match.group(1) > today:
                continue
            filtered[str(key)] = value
        return SimpleNamespace(df=pd.DataFrame([filtered]), error="")

    def wencai_nlp(self, query: str) -> SimpleNamespace:
        if "公司全称" in query and "主营业务" in query:
            return self._finance_frame()
        if "流通股东" in query:
            return self._holders_frame()
        if "前十大股东持股比例合计" in query:
            return self._concentration_frame()
        if "专利数量" in query:
            return self._patent_frame(query)
        if "股东户数" in query:
            return self._holder_trend_frame(query)
        if "主营业务构成" in query or "产品类型" in query or "境内外收入" in query:
            result = self._query(query, "hithink-business-query", limit=10)
            if not result.df.empty:
                return result
        if "行业" in query and ("市盈率" in query or "成分股" in query):
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
            return result
        row = result.df.iloc[0].to_dict()
        buy_amount_key = _first_key(row, "大单买入额[")
        sell_amount_key = _first_key(row, "大单卖出额[")
        buy_volume_key = _first_key(row, "大单买入量[")
        sell_volume_key = _first_key(row, "大单卖出量[")
        if not buy_amount_key or not sell_amount_key:
            return _empty("问财未返回今日大单买入/卖出金额")
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


def collect_industry_cloud(keyword: str, limit: int = 15) -> dict[str, Any]:
    """Collect the industry report schema using only Fuyao and official Wencai."""

    started = time.time()
    market, market_error = _safe_market_client()
    if not market:
        raise CloudSourceError(market_error or "扶摇行情凭据未配置", "missing_api_key")
    wencai, wencai_source = _wencai_client()
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

    quote_payload: dict[str, Any] = {}
    try:
        quote_payload = market.realtime([member["ticker"] for member in members])
    except mq.QueryError:
        quote_payload = {}
    quote_rows = quote_payload.get("data") or {}
    stocks: list[dict[str, Any]] = []
    warnings: list[str] = []
    for member in members:
        row = financial_by_code.get(member["ticker"]) or financial_by_name.get(member["name"]) or {}
        if not row:
            warnings.append(f"问财未返回成分股财务数据：{member['name']}")
        market_cap = _number(_first(row, "总市值"))
        revenue = _number(_first(row, f"营业收入[{year}1231]", "营业收入"))
        profit = _number(_first(row, f"归母净利润[{year}1231]", "归母净利润", "净利润"))
        quote_row = {}
        for key, value in quote_rows.items():
            if _text(value.get("ticker")) == member["ticker"] or str(key)[-6:] == member["ticker"]:
                quote_row = value
                break
        stock = {
            "name": member["name"],
            "ticker": member["ticker"],
            "thscode": member["thscode"],
            "price": _number(_first(row, "最新价")) or _number(quote_row.get("last_price")),
            "change_pct": _number(_first(row, "最新涨跌幅")) or _number(quote_row.get("price_change_ratio_pct")),
            "pe": _number(
                _first_priority(row, "最新动态市盈率", "市盈率(pe)", "最新市盈率ttm", "市盈率")
            ),
            "pb": _number(_first(row, "最新市净率", "市净率")),
            "dividend_yield": _number(_first_priority(row, "年度股息率", "股息率")),
            "market_cap": market_cap,
            "revenue": revenue,
            "net_profit": profit,
            "gross_margin": _number(_first(row, "销售毛利率")),
            "net_margin": _number(_first(row, "销售净利率")),
            "roe": _number(
                _first_priority(
                    row,
                    f"加权净资产收益率[{year}1231]",
                    "加权净资产收益率",
                    "净资产收益率ROE",
                    "净资产收益率",
                )
            ),
            "revenue_yoy": _number(
                _first_priority(row, f"营业收入同比增长率[{year}1231]", "营业收入同比增长率")
            ),
            "profit_yoy": _number(
                _first_priority(
                    row,
                    f"归母净利润同比增长率[{year}1231]",
                    "归母净利润同比增长率",
                    "净利润同比增长率",
                )
            ),
            "ytd_change": _number(_first(row, "年初至今涨跌幅", "年涨跌幅")),
            "industry": _join(_first(row, "所属同花顺行业")),
            "main_business": _join(_first(row, "主营产品", "主营业务"), "||"),
            "raw": {key: _json_value(value) for key, value in row.items()},
        }
        if market_cap is not None:
            stock["market_cap_yi"] = round(market_cap / 1e8, 2)
        if revenue is not None:
            stock["revenue_yi"] = round(revenue / 1e8, 2)
        if profit is not None:
            stock["net_profit_yi"] = round(profit / 1e8, 2)
        stocks.append(stock)

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
    if not snapshot:
        warnings.append("板块行情快照为空")
    if not news:
        warnings.append("未采集到成分股新闻；报告需用公开信息补充催化")
    if stocks and not any(item.get("revenue") is not None for item in stocks):
        warnings.append("财务数据为空；不得用推算值替代")

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
        "sources": [
            "扶摇 REST：板块目录/成分/板块快照/新闻/个股行情补充",
            f"官方问财 OpenAPI：实时行情主数据、行业财务、估值与增速（{wencai_source}）",
        ],
        "elapsed_seconds": round(time.time() - started, 1),
    }
