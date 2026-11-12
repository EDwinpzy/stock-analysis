#!/usr/bin/env python3
"""Collect reproducible industry-chain data for the industry-analysis skill.

The skill previously embedded thsdk snippets in SKILL.md.  This script turns
that workflow into a deterministic collector so the same report can be built
on Windows, Linux or macOS without a desktop client.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


CN_TZ = ZoneInfo("Asia/Shanghai")
CN_NOW = datetime.now(CN_TZ)
PREV_YEAR = CN_NOW.year - 1
ROMAN_SUFFIXES = ("Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "I", "II", "III", "IV", "V")


class IndustryError(RuntimeError):
    pass


@contextlib.contextmanager
def suppress_native_stdout():
    """Keep thsdk native diagnostics out of the collector's stdout contract."""

    original_stdout = sys.stdout
    saved_fd = None
    python_stdout = None
    devnull = None
    try:
        original_stdout.flush()
        saved_fd = os.dup(1)
        python_stdout = io.TextIOWrapper(
            os.fdopen(os.dup(saved_fd), "wb", closefd=True),
            encoding=getattr(original_stdout, "encoding", None) or "utf-8",
            errors="replace",
            write_through=True,
        )
        devnull = open(os.devnull, "w", encoding="utf-8")
        os.dup2(devnull.fileno(), 1)
        sys.stdout = python_stdout
        yield
    finally:
        if python_stdout is not None:
            try:
                python_stdout.flush()
            except (OSError, ValueError):
                pass
        sys.stdout = original_stdout
        if saved_fd is not None:
            os.dup2(saved_fd, 1)
            os.close(saved_fd)
        if python_stdout is not None:
            python_stdout.close()
        if devnull is not None:
            devnull.close()


def json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        try:
            return json_value(value.item())
        except (ValueError, TypeError):
            pass
    text = str(value)
    return None if text.lower() in {"nan", "nat", "none"} else text


def records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or not hasattr(frame, "to_dict"):
        return []
    try:
        rows = frame.to_dict(orient="records")
    except TypeError:
        rows = frame.to_dict("records")
    return [{str(k): json_value(v) for k, v in row.items()} for row in rows]


def resolve_source(value: str) -> str:
    """Resolve ``auto`` without surprising local users or cloud callers."""

    if value == "auto":
        return "cloud" if os.getenv("DAILY_BRIEFING_CLOUD") == "1" else "ths"
    return value


def normalize_keyword(value: str) -> str:
    text = str(value or "").strip()
    for suffix in ROMAN_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    if text.endswith("行业"):
        text = text[:-2]
    return text.strip()


def first_value(row: dict[str, Any], *needles: str, default: Any = None) -> Any:
    for needle in needles:
        if needle in row and row[needle] not in (None, ""):
            return row[needle]
    for key, value in row.items():
        for needle in needles:
            if needle in str(key) and value not in (None, ""):
                return value
    return default


def numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if isinstance(value, float) and math.isnan(value) else float(value)
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text in {"暂无", "--", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def pick_metric(
    row: dict[str, Any],
    patterns: Iterable[str],
    prefer_year: int | None = None,
    exclude: Iterable[str] = (),
) -> Any:
    candidates: list[tuple[float, Any]] = []
    for key, value in row.items():
        text = str(key)
        if not all(pattern.lower() in text.lower() for pattern in patterns):
            continue
        if any(pattern.lower() in text.lower() for pattern in exclude):
            continue
        if value in (None, "", "暂无", "--", "-"):
            continue
        year_match = re.search(r"\[(\d{4})(\d{4})?\]", text)
        year = int(year_match.group(1)) if year_match else 0
        score = year - len(text) * 0.001
        if prefer_year and year == prefer_year:
            score += 10000
        if year and year > CN_NOW.year:
            score -= 5000
        candidates.append((score, value))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def is_main_board(thscode: str) -> bool:
    code = thscode[-6:]
    return code.startswith(("60", "00"))


def normalize_stock_name(value: str) -> str:
    """Normalize names such as ``五 粮 液`` to the wencai spelling."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", text)


def output_dir(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
    elif os.getenv("INDUSTRY_ANALYSIS_OUTPUT_DIR"):
        path = Path(os.environ["INDUSTRY_ANALYSIS_OUTPUT_DIR"]).expanduser().resolve()
    elif os.getenv("DAILY_BRIEFING_DATA_DIR"):
        path = Path(os.environ["DAILY_BRIEFING_DATA_DIR"]).expanduser().resolve() / "industry-analysis"
    else:
        path = Path.home() / ".codex" / "daily-briefing-pro" / "outputs" / "industry-analysis"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_ths_connection(ths, attempts: int = 2) -> None:
    if getattr(ths, "_initialized", False):
        return
    last_error = "未登录"
    for attempt in range(max(1, int(attempts))):
        try:
            response = ths.connect(max_retries=1)
        except Exception as exc:
            last_error = str(exc)
        else:
            error = str(getattr(response, "error", "") or "")
            if not error and getattr(ths, "_initialized", False):
                return
            last_error = error or "未登录"
        if attempt + 1 < max(1, int(attempts)):
            time.sleep(1.0)
    raise IndustryError(f"同花顺连接失败：{last_error}")


def sector_directory_rows(
    getter: Any,
    kind: str,
    attempts: int = 3,
    retry_delay: float = 0.8,
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
            if error:
                errors.append(f"{kind}: {error}")
            else:
                errors.append(f"{kind}: 目录为空")
        if attempt + 1 < attempt_count:
            time.sleep(retry_delay * (attempt + 1))
    return [], errors


def resolve_sector(
    ths,
    keyword: str,
    attempts: int = 3,
    retry_delay: float = 0.8,
) -> dict[str, Any]:
    normalized = normalize_keyword(keyword)
    candidates: list[dict[str, Any]] = []
    directory_errors: list[str] = []
    for kind, getter in (("industry", ths.ths_industry), ("concept", ths.ths_concept)):
        rows, errors = sector_directory_rows(getter, kind, attempts=attempts, retry_delay=retry_delay)
        directory_errors.extend(errors)
        for row in rows:
            code = str(first_value(row, "代码", "板块代码", "code", "板块", default="") or "")
            name = str(first_value(row, "名称", "板块名称", "name", default="") or "")
            if not name:
                continue
            normalized_name = normalize_keyword(name)
            if normalized and normalized.lower() not in normalized_name.lower():
                continue
            score = 0
            if normalized_name == normalized:
                score = 100
            elif normalized_name.startswith(normalized):
                score = 80
            else:
                score = 60
            if kind == "industry":
                score += 5
            candidates.append({"block_code": code, "name": name, "kind": kind, "score": score})
    candidates.sort(key=lambda item: item["score"], reverse=True)
    if not candidates:
        detail = "；".join(directory_errors) or "目录返回空数据"
        raise IndustryError(f"未找到行业/概念板块：{keyword}（{detail}）")
    best = candidates[0]
    return {
        "name": best["name"],
        "keyword": keyword,
        "normalized_keyword": normalized,
        "block_code": best["block_code"],
        "kind": best["kind"],
        "candidates": candidates[:10],
    }


def resolve_members(ths, sector: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    response = ths.block_constituents(sector["block_code"])
    if response.error:
        raise IndustryError(f"板块成分查询失败：{response.error}")
    members = []
    for row in records(response.df):
        thscode = str(first_value(row, "代码", "证券代码", "THSCODE", default="") or "").upper()
        if len(thscode) != 10:
            continue
        members.append(
            {
                "thscode": thscode,
                "ticker": thscode[-6:],
                "name": normalize_stock_name(first_value(row, "名称", "证券名称", default="") or ""),
                "main_board": is_main_board(thscode),
            }
        )
    members.sort(key=lambda item: (not item["main_board"], item["ticker"]))
    return members[: max(1, int(limit))]


def collect_quotes(ths, members: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for member in members:
        # The multi-code response is not consistently populated by every THS
        # server version.  One request per code is slower by a few seconds but
        # avoids silently blank quote columns.
        for query_key in ("汇总", "基础数据", "扩展1"):
            response = ths.market_data_cn(member["thscode"], query_key)
            if response.error or response.df is None or len(response.df) == 0:
                continue
            row = records(response.df)[0]
            if first_value(row, "名称", "价格", "最新价", default=None) not in (None, ""):
                output[member["thscode"]] = row
                break
        time.sleep(0.15)
    return output


def collect_financials(ths, sector: dict[str, Any], members: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    names = "或".join(normalize_stock_name(member["name"]) for member in members if member["name"])
    if not names:
        return [], ["没有可用于 wencai 查询的成分股名称"]
    query = (
        f"{names}，"
        f"市盈率，总市值，市净率，股息率，"
        f"{PREV_YEAR}年营业收入，{PREV_YEAR}年归属于母公司所有者的净利润，"
        f"{PREV_YEAR}年销售毛利率，{PREV_YEAR}年销售净利率，"
        f"{PREV_YEAR}年净资产收益率ROE，"
        f"{PREV_YEAR}年营业收入同比增长率，{PREV_YEAR}年归属母公司股东的净利润同比增长率，"
        f"年初至今涨跌幅，所属同花顺行业，主营业务，非ST"
    )
    warnings: list[str] = []
    try:
        response = ths.wencai_nlp(query)
    except Exception as exc:
        return [], [f"wencai 行业财务查询异常：{exc}"]
    if response.error or response.df is None or len(response.df) == 0:
        warnings.append(f"wencai 行业财务查询无结果：{response.error or 'empty'}")
        # A narrower query often succeeds when the long one is rejected.
        time.sleep(0.6)
        try:
            response = ths.wencai_nlp(
                f"{names}，市盈率，总市值，{PREV_YEAR}年营业收入，{PREV_YEAR}年归属于母公司所有者的净利润"
            )
        except Exception as exc:
            return [], warnings + [f"wencai 精简查询异常：{exc}"]
    if response.error or response.df is None or len(response.df) == 0:
        warnings.append(f"wencai 精简查询仍无结果：{response.error or 'empty'}")
        return [], warnings

    by_code: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for row in records(response.df):
        code = str(first_value(row, "股票代码", "代码", "thscode", default="") or "")
        pure = code[-6:] if len(code) >= 6 else code
        name = str(first_value(row, "股票简称", "名称", default="") or "")
        item = {
            "name": name,
            "ticker": pure,
            "thscode": code if len(code) == 10 else "",
            "price": numeric(pick_metric(row, ("最新价",)) or pick_metric(row, ("价格",))),
            "change_pct": numeric(
                pick_metric(row, ("最新涨跌幅",))
                or pick_metric(row, ("涨跌幅",), exclude=("区间", "年初至今"))
            ),
            "pe": numeric(pick_metric(row, ("市盈率",))),
            "pb": numeric(pick_metric(row, ("市净率",))),
            "market_cap": numeric(pick_metric(row, ("总市值",))),
            "dividend_yield": numeric(pick_metric(row, ("股息率",))),
            "revenue": numeric(pick_metric(row, ("营业收入",), prefer_year=PREV_YEAR, exclude=("同比", "增长"))),
            "net_profit": numeric(
                pick_metric(row, ("归属于母公司所有者的净利润", "净利润"), prefer_year=PREV_YEAR, exclude=("同比", "增长", "率"))
            ),
            "gross_margin": numeric(pick_metric(row, ("毛利率",), prefer_year=PREV_YEAR)),
            "net_margin": numeric(pick_metric(row, ("净利率",), prefer_year=PREV_YEAR)),
            "roe": numeric(pick_metric(row, ("净资产收益率", "roe"), prefer_year=PREV_YEAR)),
            "revenue_yoy": numeric(pick_metric(row, ("营业收入", "同比"), prefer_year=PREV_YEAR)),
            "profit_yoy": numeric(pick_metric(row, ("净利润", "同比"), prefer_year=PREV_YEAR)),
            "ytd_change": numeric(pick_metric(row, ("年初至今", "区间涨跌幅"), exclude=("最新",))),
            "industry": first_value(row, "所属同花顺行业", default=None),
            "main_business": first_value(row, "主营业务", "主营产品名称", default=None),
            "raw": row,
        }
        if item["market_cap"] is not None:
            item["market_cap_yi"] = round(item["market_cap"] / 1e8, 2)
        if item["revenue"] is not None:
            item["revenue_yi"] = round(item["revenue"] / 1e8, 2)
        if item["net_profit"] is not None:
            item["net_profit_yi"] = round(item["net_profit"] / 1e8, 2)
        if pure:
            by_code[pure] = item
        if name:
            by_name[normalize_stock_name(name)] = item

    merged: list[dict[str, Any]] = []
    missing: list[str] = []
    for member in members:
        item = by_code.get(member["ticker"]) or by_name.get(normalize_stock_name(member["name"]))
        if not item:
            missing.append(member["name"] or member["thscode"])
            continue
        item = dict(item)
        item["thscode"] = member["thscode"]
        item["ticker"] = member["ticker"]
        item["name"] = member["name"] or item.get("name")
        merged.append(item)
    if missing:
        warnings.append("wencai 未返回这些成分股的财务数据：" + "、".join(missing))
    return merged, warnings


def collect_sector_snapshot(ths, sector: dict[str, Any]) -> dict[str, Any]:
    for query_key in ("扩展", "基础数据"):
        try:
            response = ths.market_data_block(sector["block_code"], query_key)
        except Exception:
            continue
        if not response.error and response.df is not None and len(response.df):
            return records(response.df)[0]
    return {}


def collect_news(ths, sector: dict[str, Any], members: list[dict[str, Any]], per_stock: int = 3) -> list[dict[str, Any]]:
    """Collect a small, attributable news sample for the report's catalyst section."""

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for member in members[:5]:
        try:
            response = ths.news(0x3805, member["ticker"], member["thscode"][:4])
        except Exception:
            continue
        if response.error or response.df is None:
            continue
        count = 0
        for row in records(response.df):
            title = str(first_value(row, "Title", "标题", default="") or "")
            if not title or title in seen:
                continue
            seen.add(title)
            items.append(
                {
                    "title": title,
                    "time": first_value(row, "Time", "时间", default=None),
                    "stock": member["name"],
                    "ticker": member["ticker"],
                    "category": "公告",
                    "raw": row,
                }
            )
            count += 1
            if count >= per_stock:
                break
        time.sleep(0.2)
    return items


def collect(keyword: str, limit: int) -> dict[str, Any]:
    try:
        from thsdk import THS
    except ImportError as exc:
        raise IndustryError("未安装 thsdk；请安装 requirements-cloud.txt") from exc

    started = time.time()
    warnings: list[str] = []
    with suppress_native_stdout(), THS() as ths:
        ensure_ths_connection(ths)
        sector = resolve_sector(ths, keyword)
        members = resolve_members(ths, sector, limit)
        if not members:
            raise IndustryError(f"板块 {sector['name']} 没有成分股")

        quotes = collect_quotes(ths, members)
        time.sleep(0.6)
        stocks, financial_warnings = collect_financials(ths, sector, members)
        warnings.extend(financial_warnings)

        # Attach quote values even when wencai omits a stock.
        stock_by_code = {item["ticker"]: item for item in stocks}
        for member in members:
            ticker = member["ticker"]
            if ticker not in stock_by_code:
                stock_by_code[ticker] = {
                    "name": member["name"],
                    "ticker": ticker,
                    "thscode": member["thscode"],
                    "raw": {},
                }
                stocks.append(stock_by_code[ticker])
            quote = quotes.get(member["thscode"], {})
            quote_values = {
                "price": numeric(first_value(quote, "最新价", "价格", default=None)),
                "change_pct": numeric(first_value(quote, "涨幅", default=None)),
                "market_cap_quote": numeric(first_value(quote, "总市值", default=None)),
                "turnover": numeric(first_value(quote, "总金额", default=None)),
                "quote_raw": quote,
            }
            for key, value in quote_values.items():
                if value not in (None, {}):
                    stock_by_code[ticker][key] = value
        stocks.sort(key=lambda item: (not is_main_board(item.get("thscode", "")), item.get("ticker", "")))

        snapshot = collect_sector_snapshot(ths, sector)
        news = collect_news(ths, sector, members)

    missing_sections = []
    if not stocks:
        missing_sections.append("stocks")
    if not snapshot:
        warnings.append("板块行情快照为空")
    if not news:
        warnings.append("未采集到成分股公告；报告需用公开信息补充催化")
    if not any(item.get("revenue") is not None for item in stocks):
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
        "missing_sections": missing_sections,
        "sources": ["同花顺 thsdk：板块目录/成分/行情", "同花顺 wencai：财务与估值", "同花顺公告"],
        "elapsed_seconds": round(time.time() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="行业/产业链分析数据采集（thsdk / 云端双通道）")
    parser.add_argument("industry", help="行业或概念名称，例如 白酒、半导体、机器人")
    parser.add_argument("--limit", type=int, default=15, help="核心标的数量，默认 15")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument(
        "--source",
        choices=("auto", "ths", "cloud"),
        default="auto",
        help="数据源；auto 在云端使用官方问财+扶摇，在本机使用 thsdk",
    )
    args = parser.parse_args()

    target_dir = output_dir(args.output_dir)
    safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", args.industry)
    output_file = target_dir / f"_industry_{safe}.json"
    try:
        source = resolve_source(args.source)
        if source == "cloud":
            plugin_root = Path(__file__).resolve().parents[3]
            if str(plugin_root) not in sys.path:
                sys.path.insert(0, str(plugin_root))
            from cloud_sources import collect_industry_cloud, preflight_industry_cloud

            result = (
                preflight_industry_cloud(args.industry)
                if args.preflight
                else collect_industry_cloud(args.industry, args.limit)
            )
        else:
            result = collect(args.industry, args.limit)
        if args.preflight and source != "cloud":
            result = {
                "ok": True,
                "mode": "preflight",
                "sector": result["sector"],
                "members_count": result["members_count"],
                "output_dir": str(target_dir),
            }
        with output_file.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, default=str)
        print(str(output_file))
        return 0
    except Exception as exc:
        result = {
            "error": str(exc),
            "industry": args.industry,
            "output_dir": str(target_dir),
            "time": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        }
        with output_file.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False)
        print(str(output_file))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
