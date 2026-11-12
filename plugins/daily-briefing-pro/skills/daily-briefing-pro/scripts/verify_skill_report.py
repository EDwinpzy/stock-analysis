#!/usr/bin/env python3
"""Verify that a stock/industry HTML report and its source data are complete.

The report writer is an LLM, so the final gate must inspect the artifact, not
the intent.  This script checks the fixed chapter contract, table presence,
obvious placeholders and the required JSON keys produced by the collectors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from html import unescape
from pathlib import Path
from typing import Any


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


SECTION_RULES = {
    "stock": [
        ("核心结论", ("核心结论", "一句话结论")),
        ("概览与估值", ("概览", "估值")),
        ("产品与客户", ("产品", "客户")),
        ("基本面与壁垒", ("护城河", "壁垒", "不可替代")),
        ("消息资金筹码", ("消息", "资金", "筹码")),
        ("市场声音", ("市场声音", "机构研报", "博主")),
        ("前瞻指引", ("预期差", "催化")),
        ("风险全景", ("风险", "红旗")),
        ("行动建议", ("行动", "减仓")),
        ("数据来源", ("数据来源", "免责声明")),
    ],
    "industry": [
        ("行业概览", ("行业概览",)),
        ("竞争格局", ("竞争格局",)),
        ("核心标的", ("核心标的",)),
        ("客户订单", ("客户订单", "客户", "订单")),
        ("同行指标", ("同行", "核心指标")),
        ("投资逻辑", ("投资逻辑", "配置建议")),
        ("风险提示", ("风险提示", "风险")),
        ("核心结论", ("核心结论",)),
    ],
}

DATA_RULES = {
    "stock": [
        ("quote", "行情"),
        ("finance_raw", "财务"),
        ("peers_raw", "同业"),
        ("holders_raw", "股东"),
        ("big_orders", "资金流向"),
        ("news", "新闻"),
        ("product_raw", "产品业务"),
        ("chip_structure", "筹码"),
        ("blogger_opinions", "博主观点"),
        ("barrier_data", "壁垒"),
        ("research_reports", "研报"),
    ],
    "industry": [
        ("sector", "行业"),
        ("members", "成分股"),
        ("stocks", "核心标的"),
        ("sector_snapshot", "板块行情"),
        ("news", "公告"),
    ],
}

PLACEHOLDER_PATTERNS = (
    r"\bundefined\b",
    r"\bNaN\b",
    r"\bnull\b",
    r"UNSOURCED",
    r"数据获取失败",
    r"采集失败",
    r"公开数据未覆盖",
    r"暂无",
    r"暂无数据",
)

STOCK_QUOTE_FIELDS = {
    "price": "最新价",
    "change_pct": "涨跌幅",
    "change_amt": "涨跌额",
    "volume": "成交量",
    "amount": "成交额",
    "market_cap": "总市值",
    "circulating_cap": "流通市值",
    "pe_ttm": "市盈率TTM",
    "turnover_rate": "换手率",
    "amplitude": "振幅",
    "main_net_inflow": "主力净流入",
    "main_net_pct": "主力净量",
    "high": "最高价",
    "low": "最低价",
    "open_change": "开盘涨幅",
    "prev_close": "昨收价",
    "limit_up": "涨停价",
    "limit_down": "跌停价",
    "5d_change": "5日涨幅",
}

INDUSTRY_SNAPSHOT_FIELDS = (
    "涨幅",
    "5日涨幅",
    "10日涨幅",
    "20日涨幅",
    "主力净流入",
    "量比",
)

INDUSTRY_STOCK_FIELDS = {
    "price": "最新价",
    "change_pct": "涨跌幅",
    "pe": "PE",
    "pb": "PB",
    "market_cap_yi": "总市值",
    "revenue_yi": "营业收入",
    "net_profit_yi": "归母净利润",
    "gross_margin": "毛利率",
    "net_margin": "净利率",
    "roe": "ROE",
    "revenue_yoy": "营收同比",
    "profit_yoy": "净利同比",
    "ytd_change": "年内涨幅",
    "industry": "所属行业",
    "dividend_yield": "股息率",
    "main_business": "主营业务",
}


def visible_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text)


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip() in {
            "暂无",
            "暂无数据",
            "公开数据未覆盖",
            "-",
            "--",
        }
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    if isinstance(value, dict):
        if not value:
            return True
        if set(value) == {"error"}:
            return True
        return False
    return False


def _name_key(value: Any) -> str:
    """Compare display names across vendor spacing and full-width variants."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", text)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _latest_annual_number(
    mapping: dict[str, Any],
    prefix: str,
) -> float | None:
    candidates: list[tuple[int, float]] = []
    for key, value in mapping.items():
        text = str(key)
        if not text.startswith(prefix) or any(
            marker in text for marker in ("同比", "增长", "占")
        ):
            continue
        match = re.search(r"\[(\d{4})1231\]", text)
        parsed = _number(value)
        if match and parsed is not None:
            candidates.append((int(match.group(1)), parsed))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _formatted_value_present(text: str, key: str, value: float) -> bool:
    if key in {"涨幅", "5日涨幅", "10日涨幅", "20日涨幅"}:
        sign = "+" if value > 0 else ""
        variants = {f"{sign}{value:,.2f}%", f"{value:,.2f}%"}
    elif key == "主力净流入":
        variants = {f"{value / 1e8:,.2f} 亿"}
    elif key == "量比":
        variants = {f"{value:,.2f}", f"{value:g}"}
    else:
        variants = {f"{value:,.2f}", f"{value:g}"}
    return any(variant in text for variant in variants)


def _source_fact_problems(text: str, kind: str, data: dict[str, Any]) -> list[str]:
    """Check a few high-impact facts against the collector JSON."""

    problems: list[str] = []
    if kind == "stock":
        quote = data.get("quote") if isinstance(data.get("quote"), dict) else {}
        finance = data.get("finance_raw") if isinstance(data.get("finance_raw"), dict) else {}
        holders = data.get("holders_raw") if isinstance(data.get("holders_raw"), dict) else {}
        name = str(quote.get("name") or "").strip()
        code = str(data.get("stock_code") or "").strip()
        price = _number(quote.get("price"))
        normalized_text = _name_key(text)
        if name and _name_key(name) not in normalized_text:
            problems.append(f"报告未出现采集证券名称：{name}")
        if code and code.split(".")[0] not in text:
            problems.append(f"报告未出现采集证券代码：{code.split('.')[0]}")
        if price is not None:
            variants = {
                f"{price:,.2f}",
                f"{price:.2f}",
                f"{price:,.3f}",
                f"{price:.3f}",
            }
            if not any(value in text for value in variants):
                problems.append(f"报告未出现与采集行情一致的最新价：{price:g}")
        if not finance:
            problems.append("采集 JSON 缺少财务原始字段")
        latest_revenue = _latest_annual_number(finance, "营业收入")
        latest_profit = _latest_annual_number(
            finance, "归属于母公司所有者的净利润"
        ) or _latest_annual_number(finance, "归母净利润")
        if latest_revenue is None:
            problems.append("采集 JSON 缺少最新年度营业收入")
        else:
            expected = f"{latest_revenue / 1e8:,.2f} 亿"
            if expected not in text:
                problems.append(f"报告未出现与采集 JSON 一致的最新营业收入：{expected}")
        if latest_profit is None:
            problems.append("采集 JSON 缺少最新年度归母净利润")
        else:
            expected = f"{latest_profit / 1e8:,.2f} 亿"
            if expected not in text:
                problems.append(f"报告未出现与采集 JSON 一致的最新归母净利润：{expected}")
        holder_text = str(
            holders.get("前十大流通股东名称")
            or holders.get("前十大股东")
            or ""
        )
        holder_names = [item.strip() for item in holder_text.split("||") if item.strip()]
        if holder_names and not any(_name_key(holder_name) in normalized_text for holder_name in holder_names[:3]):
            problems.append("报告未出现采集 JSON 中的前十大股东名称")
    else:
        sector = data.get("sector") if isinstance(data.get("sector"), dict) else {}
        sector_name = str(sector.get("name") or data.get("keyword") or "").strip()
        normalized_text = _name_key(text)
        if sector_name and _name_key(sector_name) not in normalized_text:
            problems.append(f"报告未出现采集板块名称：{sector_name}")
        stocks = [item for item in (data.get("stocks") or []) if isinstance(item, dict)]
        missing = [
            str(item.get("name") or item.get("ticker"))
            for item in stocks[:10]
            if (item.get("name") or item.get("ticker"))
            and _name_key(item.get("name") or item.get("ticker")) not in normalized_text
        ]
        if missing:
            problems.append("报告缺少采集标的：" + "、".join(missing[:5]))
        missing_tickers = [
            str(item.get("ticker"))
            for item in stocks[:10]
            if item.get("ticker") and str(item.get("ticker")) not in text
        ]
        if missing_tickers:
            problems.append("报告缺少采集证券代码：" + "、".join(missing_tickers[:5]))
        snapshot = (
            data.get("sector_snapshot")
            if isinstance(data.get("sector_snapshot"), dict)
            else {}
        )
        missing_snapshot = [
            key
            for key in INDUSTRY_SNAPSHOT_FIELDS
            if _number(snapshot.get(key)) is None
        ]
        if missing_snapshot:
            problems.append("采集 JSON 缺少板块指标：" + "、".join(missing_snapshot))
        else:
            for key in INDUSTRY_SNAPSHOT_FIELDS:
                parsed = _number(snapshot.get(key))
                if parsed is not None and not _formatted_value_present(
                    text,
                    key,
                    parsed,
                ):
                    problems.append(
                        f"报告未出现与采集 JSON 一致的板块{key}：{parsed:g}"
                    )
        incomplete_stocks = []
        for item in stocks:
            missing_fields = [
                label
                for key, label in INDUSTRY_STOCK_FIELDS.items()
                if is_empty(item.get(key))
            ]
            if missing_fields:
                incomplete_stocks.append(
                    f"{item.get('name') or item.get('ticker') or '未命名标的'}"
                    f"（{'、'.join(missing_fields)}）"
                )
        if incomplete_stocks:
            problems.append(
                "行业核心标的字段缺失：" + "；".join(incomplete_stocks[:5])
            )
        if "公开数据未覆盖" in text:
            problems.append("行业报告仍含“公开数据未覆盖”字段")
        missing_business = []
        missing_dividend = []
        for item in stocks:
            business_tokens = [
                _name_key(token)
                for token in re.split(r"\|\||、|；|;|/", str(item.get("main_business") or ""))
                if len(_name_key(token)) >= 2
            ]
            if business_tokens and not any(
                token in normalized_text for token in business_tokens
            ):
                missing_business.append(
                    str(item.get("name") or item.get("ticker") or "未命名标的")
                )
            dividend = _number(item.get("dividend_yield"))
            if dividend is not None and not any(
                variant in text
                for variant in (f"{dividend:,.2f}%", f"{dividend:.2f}%")
            ):
                missing_dividend.append(
                    str(item.get("name") or item.get("ticker") or "未命名标的")
                )
        if missing_business:
            problems.append(
                "报告缺少采集主营产品：" + "、".join(missing_business[:5])
            )
        if missing_dividend:
            problems.append(
                "报告缺少采集股息率：" + "、".join(missing_dividend[:5])
            )
    return problems


def _stock_nested_problems(data: dict[str, Any]) -> list[str]:
    """Reject structurally present but semantically empty stock data blocks."""

    problems: list[str] = []
    quote = data.get("quote") if isinstance(data.get("quote"), dict) else {}
    missing_quote = [
        label for key, label in STOCK_QUOTE_FIELDS.items() if is_empty(quote.get(key))
    ]
    if missing_quote:
        problems.append("行情关键字段缺失：" + "、".join(missing_quote))

    peers = [item for item in (data.get("peers_raw") or []) if isinstance(item, dict)]
    expected_peers = _number(data.get("peers_expected_count")) or 0
    if expected_peers and len(peers) < expected_peers:
        problems.append(
            f"同业数量不足：{len(peers)} < {int(expected_peers)}"
        )
    if str(data.get("peers_scope") or "") == "eastmoney_f10_sample":
        problems.append("同业数据退化为东方财富 F10 样本，未覆盖完整行业板块")
    if peers and expected_peers:
        peer_keys = set().union(*(set(item) for item in peers))
        required_peer_labels = (
            "股票代码",
            "股票简称",
            "市盈率(pe)",
            "市净率(pb)",
            "总市值",
            "净资产收益率",
            "营业收入",
        )
        missing_peer_labels = [
            label for label in required_peer_labels if label not in peer_keys
        ]
        if missing_peer_labels:
            problems.append(
                "同业表字段缺失：" + "、".join(missing_peer_labels)
            )

    chip = (
        data.get("chip_structure")
        if isinstance(data.get("chip_structure"), dict)
        else {}
    )
    for key, label in (
        ("holder_count_trend", "股东户数趋势"),
        ("share_structure", "股本结构"),
        ("unlock_data", "解禁信息"),
        ("concentration", "股东集中度"),
        ("margin", "融资余额"),
    ):
        value = chip.get(key)
        if is_empty(value):
            problems.append(f"筹码子项为空：{label}")
    holder_trend = (
        chip.get("holder_count_trend")
        if isinstance(chip.get("holder_count_trend"), dict)
        else {}
    )
    dated_holders = [
        key
        for key in holder_trend
        if re.search(r"(?:股东户数|总户数).*?\[\d{8}\]", str(key))
    ]
    if len(dated_holders) < 2:
        problems.append("股东户数趋势不足两期")
    share_structure = (
        chip.get("share_structure")
        if isinstance(chip.get("share_structure"), dict)
        else {}
    )
    for fragment, label in (
        ("总股本", "总股本"),
        ("流通a股", "流通A股"),
        ("限售a股", "限售A股"),
    ):
        if not any(fragment in str(key) for key in share_structure):
            problems.append(f"股本结构缺少：{label}")
    concentration = (
        chip.get("concentration")
        if isinstance(chip.get("concentration"), dict)
        else {}
    )
    if is_empty(concentration.get("前十大股东持股比例合计")):
        problems.append("股东集中度缺少前十大股东持股比例合计")
    margin = chip.get("margin") if isinstance(chip.get("margin"), dict) else {}
    if not any("融资余额" in str(key) for key in margin):
        problems.append("融资余额子项缺少融资余额")

    barrier = (
        data.get("barrier_data")
        if isinstance(data.get("barrier_data"), dict)
        else {}
    )
    for key, label in (
        ("rd_raw", "研发专利"),
        ("customer_concentration", "客户集中度"),
        ("supplier_concentration", "供应商集中度"),
    ):
        if is_empty(barrier.get(key)):
            problems.append(f"壁垒子项为空：{label}")
    rd = barrier.get("rd_raw") if isinstance(barrier.get("rd_raw"), dict) else {}
    if not any(
        "研发投入占营业收入的比重" in str(key) or "研发投入占比" in str(key)
        for key in rd
    ):
        problems.append("研发专利缺少研发投入占比")
    if not any("专利数量" in str(key) for key in rd):
        problems.append("研发专利缺少专利数量")
    for key, label in (
        ("customer_concentration", "客户集中度"),
        ("supplier_concentration", "供应商集中度"),
    ):
        value = barrier.get(key)
        if isinstance(value, dict) and (
            is_empty(value.get("value")) or is_empty(value.get("period"))
        ):
            problems.append(f"{label}缺少数值或报告期")
    return problems


def verify_report(path: Path, kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "error": f"报告不存在：{path}"}
    html = path.read_text(encoding="utf-8", errors="replace")
    text = visible_text(html)
    missing = []
    matched = {}
    for label, aliases in SECTION_RULES[kind]:
        candidates = (label, *aliases)
        hits = [alias for alias in candidates if alias in text]
        matched[label] = hits
        if not hits:
            missing.append(label)
    tables = len(re.findall(r"(?is)<table\b", html))
    rows = len(re.findall(r"(?is)<tr\b", html))
    empty_tables = len(re.findall(r"当前数据快照没有可列示记录", html))
    placeholders = {}
    for pattern in PLACEHOLDER_PATTERNS:
        count = len(re.findall(pattern, text, flags=re.IGNORECASE))
        if count:
            placeholders[pattern] = count
    min_tables = 6 if kind == "stock" else 5
    problems = []
    if missing:
        problems.append("缺少章节：" + "、".join(missing))
    if tables < min_tables:
        problems.append(f"表格数量不足：{tables} < {min_tables}")
    if rows < min_tables * 3:
        problems.append(f"表格数据行不足：{rows} < {min_tables * 3}")
    if empty_tables:
        problems.append(f"存在空数据表：{empty_tables}")
    if placeholders:
        problems.append("存在占位/错误值：" + json.dumps(placeholders, ensure_ascii=False))
    if data is not None:
        problems.extend(_source_fact_problems(text, kind, data))
    return {
        "ok": not problems,
        "type": kind,
        "report": str(path),
        "characters": len(text),
        "tables": tables,
        "table_rows": rows,
        "empty_tables": empty_tables,
        "sections": matched,
        "missing_sections": missing,
        "placeholders": placeholders,
        "problems": problems,
    }


def verify_data(path: Path, kind: str) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "error": f"数据文件不存在：{path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"JSON 无法解析：{exc}"}
    findings = {}
    missing = []
    for key, label in DATA_RULES[kind]:
        value = data.get(key)
        empty = is_empty(value)
        findings[label] = {"key": key, "present": key in data, "empty": empty}
        if key not in data or empty:
            missing.append(label)
    warnings = data.get("warnings") or []
    problems = []
    if missing:
        problems.append("缺少或为空：" + "、".join(missing))
    if kind == "industry":
        snapshot = (
            data.get("sector_snapshot")
            if isinstance(data.get("sector_snapshot"), dict)
            else {}
        )
        missing_snapshot = [
            key
            for key in INDUSTRY_SNAPSHOT_FIELDS
            if _number(snapshot.get(key)) is None
        ]
        if missing_snapshot:
            problems.append("板块指标缺失：" + "、".join(missing_snapshot))
        stocks = [
            item
            for item in (data.get("stocks") or [])
            if isinstance(item, dict)
        ]
        incomplete_stocks = []
        for item in stocks:
            missing_fields = [
                label
                for key, label in INDUSTRY_STOCK_FIELDS.items()
                if is_empty(item.get(key))
            ]
            if missing_fields:
                incomplete_stocks.append(
                    f"{item.get('name') or item.get('ticker') or '未命名标的'}"
                    f"（{'、'.join(missing_fields)}）"
                )
        if incomplete_stocks:
            problems.append(
                "核心标的字段缺失：" + "；".join(incomplete_stocks[:5])
            )
    else:
        problems.extend(_stock_nested_problems(data))
    if data.get("error"):
        problems.append("采集器报错：" + str(data["error"]))
    return {
        "ok": not problems,
        "type": kind,
        "data": str(path),
        "fields": findings,
        "missing_or_empty": missing,
        "warnings": warnings,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验个股/行业报告与源数据完整性")
    parser.add_argument("target", help="HTML 报告或采集 JSON")
    parser.add_argument("--type", choices=("stock", "industry"), required=True)
    parser.add_argument("--data-json", default="", help="同时校验采集 JSON")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认）")
    args = parser.parse_args(argv)

    target = Path(args.target).expanduser().resolve()
    if target.suffix.lower() == ".json":
        result = verify_data(target, args.type)
    else:
        report_data = None
        data_result = None
        if args.data_json:
            data_path = Path(args.data_json).expanduser().resolve()
            data_result = verify_data(data_path, args.type)
            if data_path.is_file():
                try:
                    report_data = json.loads(data_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    report_data = None
        result = verify_report(target, args.type, data=report_data)
        if data_result is not None:
            result["data_check"] = data_result
            result["ok"] = bool(result.get("ok")) and bool(data_result.get("ok"))
            if not data_result.get("ok"):
                result.setdefault("problems", []).extend(data_result.get("problems", []))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
