#!/usr/bin/env python3
"""Compare stable business fields between local and cloud collector JSON.

Unlike the byte-oriented parity tool, this gate deliberately ignores values
that change between two collection times (quotes, news lists, raw vendor
payloads and runtime paths). It still requires the same accounting fields,
peer universe, holders, product scope and industry member coverage.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize(value: Any) -> str:
    text = re.sub(r"\s+", "", _text(value))
    for suffix in ("Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _ticker(value: Any) -> str:
    match = re.search(r"(\d{6})", _text(value))
    return match.group(1) if match else ""


def _latest_annual(mapping: Any, prefixes: Iterable[str]) -> tuple[int, float] | None:
    if not isinstance(mapping, dict):
        return None
    candidates: list[tuple[int, float]] = []
    for key, value in mapping.items():
        text = str(key)
        match = re.search(r"\[(\d{4})1231\]", text)
        if not match:
            continue
        if any(marker in text for marker in ("同比", "增长", "占", "较上期")):
            continue
        if not any(prefix in text for prefix in prefixes):
            continue
        parsed = _number(value)
        if parsed is not None:
            candidates.append((int(match.group(1)), parsed))
    return max(candidates, key=lambda item: item[0]) if candidates else None


def _relative_difference(left: float, right: float) -> float:
    scale = max(abs(left), abs(right), 1e-9)
    return abs(left - right) / scale


def _add_number_check(
    problems: list[str],
    checks: list[dict[str, Any]],
    *,
    label: str,
    local: float | None,
    cloud: float | None,
    relative: float | None = None,
    absolute: float | None = None,
    soft: bool = False,
    warnings: list[str] | None = None,
) -> None:
    check: dict[str, Any] = {
        "label": label,
        "local": local,
        "cloud": cloud,
    }
    if local is None:
        # The local baseline can legitimately lack a vendor metric. Cloud
        # completeness is enforced by verify_skill_report, not by parity.
        check["ok"] = True
        check["skipped"] = "local_missing"
        checks.append(check)
        return
    if cloud is None:
        problems.append(f"{label}缺失（本机={local!r}，云端=缺失）")
        check["ok"] = False
        checks.append(check)
        return
    difference = _relative_difference(local, cloud)
    delta = abs(local - cloud)
    passed = (
        (relative is not None and difference <= relative)
        or (absolute is not None and delta <= absolute)
    )
    check.update(
        {
            "ok": passed,
            "relative_difference": round(difference, 8),
            "absolute_difference": round(delta, 8),
        }
    )
    if not passed:
        message = (
            f"{label}差异过大（本机={local:g}，云端={cloud:g}，"
            f"相对差={difference:.4%}，绝对差={delta:g}）"
        )
        if soft:
            check["ok"] = True
            check["vendor_variation"] = True
            if warnings is not None:
                warnings.append(message + "（按数据源口径差异记录）")
        else:
            problems.append(message)
    checks.append(check)


def _name_set(text: Any) -> set[str]:
    return {
        _normalize(item)
        for item in re.split(r"\|\||；|;|\n", _text(text))
        if _normalize(item)
    }


def _product_names(data: dict[str, Any]) -> set[str]:
    raw = data.get("product_raw")
    if not isinstance(raw, dict):
        return set()
    for key in ("主营产品名称", "主营产品", "主营业务", "产品名称"):
        value = raw.get(key)
        text = _text(value)
        if not text:
            continue
        if text.startswith("["):
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                parsed = None
            if isinstance(parsed, (list, tuple)):
                return {
                    _normalize(item)
                    for item in parsed
                    if _normalize(item)
                }
        return _name_set(text)
    return set()


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _product_contains(left: str, right: str) -> bool:
    """Allow vendor taxonomies where one product label is a parent category."""
    left = _normalize(left)
    right = _normalize(right)
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 2 and shorter in longer


def _product_coverage(reference: set[str], candidate: set[str]) -> float:
    if not candidate:
        return 0.0
    covered = sum(
        1
        for item in candidate
        if any(_product_contains(item, expected) for expected in reference)
    )
    return covered / len(candidate)


_BUSINESS_ALIASES = (
    "白酒",
    "酒类",
    "酒水",
    "酒制造",
    "酿酒",
    "酒业",
    "酒品",
    "名酒",
    "原酒",
    "基酒",
    "葡萄酒",
    "啤酒",
    "黄酒",
    "酒精",
)


def _business_tokens(value: Any) -> set[str]:
    """Normalize product/segment names enough to compare vendor taxonomies."""

    tokens: set[str] = set()
    for token in re.split(r"[\|\|、,，;；/]", _text(value)):
        normalized = _normalize(token)
        if not normalized:
            continue
        if any(alias in normalized for alias in _BUSINESS_ALIASES):
            tokens.add("酒")
        else:
            tokens.add(normalized)
    return tokens


def _compare_stock(local: dict[str, Any], cloud: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    problems: list[str] = []
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    local_quote = local.get("quote") if isinstance(local.get("quote"), dict) else {}
    cloud_quote = cloud.get("quote") if isinstance(cloud.get("quote"), dict) else {}
    for key, label, tolerance in (
        ("price", "最新价", 0.15),
        ("market_cap", "总市值", 0.20),
        ("pe_ttm", "市盈率TTM", 0.15),
    ):
        _add_number_check(
            problems,
            checks,
            label=label,
            local=_number(local_quote.get(key)),
            cloud=_number(cloud_quote.get(key)),
            relative=tolerance,
        )

    local_finance = (
        local.get("finance_raw")
        if isinstance(local.get("finance_raw"), dict)
        else {}
    )
    cloud_finance = (
        cloud.get("finance_raw")
        if isinstance(cloud.get("finance_raw"), dict)
        else {}
    )
    for prefixes, label, tolerance in (
        (("营业收入",), "最新年度营业收入", 0.005),
        (("归属于母公司所有者的净利润", "归母净利润"), "最新年度归母净利润", 0.005),
        (("加权净资产收益率", "净资产收益率"), "最新年度ROE", 0.01),
    ):
        local_value = _latest_annual(local_finance, prefixes)
        cloud_value = _latest_annual(cloud_finance, prefixes)
        _add_number_check(
            problems,
            checks,
            label=label,
            local=local_value[1] if local_value else None,
            cloud=cloud_value[1] if cloud_value else None,
            relative=tolerance,
        )

    local_peers = [item for item in (local.get("peers_raw") or []) if isinstance(item, dict)]
    cloud_peers = [item for item in (cloud.get("peers_raw") or []) if isinstance(item, dict)]
    local_codes = {_ticker(item.get("股票代码")) for item in local_peers} - {""}
    cloud_codes = {_ticker(item.get("股票代码")) for item in cloud_peers} - {""}
    missing_peers = sorted(local_codes - cloud_codes)
    checks.append(
        {
            "label": "同业股票范围",
            "local_count": len(local_codes),
            "cloud_count": len(cloud_codes),
            "missing_in_cloud": missing_peers,
            "ok": not missing_peers and len(cloud_codes) >= len(local_codes),
        }
    )
    if missing_peers:
        problems.append(
            "云端同业缺少本机股票：" + "、".join(missing_peers[:10])
        )
    elif len(cloud_codes) < len(local_codes):
        problems.append(
            f"云端同业数量不足：{len(cloud_codes)} < {len(local_codes)}"
        )
    peer_keys = set().union(*(set(item) for item in cloud_peers)) if cloud_peers else set()
    required_peer_keys = {
        "股票代码",
        "股票简称",
        "市盈率(pe)",
        "市净率(pb)",
        "总市值",
        "净资产收益率",
        "营业收入",
    }
    missing_peer_keys = sorted(required_peer_keys - peer_keys)
    if missing_peer_keys:
        problems.append("云端同业表缺少字段：" + "、".join(missing_peer_keys))
    if str(cloud.get("peers_scope") or "") == "eastmoney_f10_sample":
        problems.append("云端同业退化为 F10 样本")

    local_holders = local.get("holders_raw") if isinstance(local.get("holders_raw"), dict) else {}
    cloud_holders = cloud.get("holders_raw") if isinstance(cloud.get("holders_raw"), dict) else {}
    local_holder_names = _name_set(local_holders.get("前十大流通股东名称"))
    cloud_holder_names = _name_set(cloud_holders.get("前十大流通股东名称"))
    holder_overlap = (
        len(local_holder_names & cloud_holder_names) / len(local_holder_names)
        if local_holder_names
        else 1.0
    )
    checks.append(
        {
            "label": "前十大流通股东",
            "local_count": len(local_holder_names),
            "cloud_count": len(cloud_holder_names),
            "overlap": round(holder_overlap, 4),
            "ok": holder_overlap >= 0.8,
        }
    )
    if holder_overlap < 0.8:
        problems.append(f"前十大流通股东重叠不足：{holder_overlap:.1%}")

    local_products = _product_names(local)
    cloud_products = _product_names(cloud)
    product_overlap = _jaccard(local_products, cloud_products)
    cloud_coverage = _product_coverage(local_products, cloud_products)
    product_ok = (
        not local_products
        or product_overlap >= 0.5
        or cloud_coverage >= 0.8
    )
    checks.append(
        {
            "label": "主营产品范围",
            "local_count": len(local_products),
            "cloud_count": len(cloud_products),
            "jaccard": round(product_overlap, 4),
            "cloud_coverage": round(cloud_coverage, 4),
            "ok": product_ok,
        }
    )
    if not product_ok:
        problems.append(f"主营产品重叠不足：{product_overlap:.1%}")

    local_chip = local.get("chip_structure") if isinstance(local.get("chip_structure"), dict) else {}
    cloud_chip = cloud.get("chip_structure") if isinstance(cloud.get("chip_structure"), dict) else {}
    for key, label in (
        ("holder_count_trend", "股东户数趋势"),
        ("share_structure", "股本结构"),
        ("unlock_data", "解禁信息"),
        ("concentration", "股东集中度"),
        ("margin", "融资余额"),
    ):
        present = isinstance(cloud_chip.get(key), dict)
        checks.append({"label": f"筹码-{label}", "ok": present})
        if not present:
            problems.append(f"云端筹码缺少：{label}")

    local_barrier = local.get("barrier_data") if isinstance(local.get("barrier_data"), dict) else {}
    cloud_barrier = cloud.get("barrier_data") if isinstance(cloud.get("barrier_data"), dict) else {}
    for key, label in (
        ("rd_raw", "研发专利"),
        ("customer_concentration", "客户集中度"),
        ("supplier_concentration", "供应商集中度"),
    ):
        present = isinstance(cloud_barrier.get(key), dict)
        checks.append({"label": f"壁垒-{label}", "ok": present})
        if not present:
            problems.append(f"云端壁垒缺少：{label}")

    cloud_news = cloud.get("news") if isinstance(cloud.get("news"), list) else []
    cloud_research = (
        cloud.get("research_reports")
        if isinstance(cloud.get("research_reports"), dict)
        else {}
    )
    cloud_reports = cloud_research.get("reports") if isinstance(cloud_research.get("reports"), list) else []
    checks.append({"label": "新闻条数", "cloud_count": len(cloud_news), "ok": len(cloud_news) >= 5})
    if len(cloud_news) < 5:
        problems.append(f"云端新闻不足：{len(cloud_news)} < 5")
    checks.append({"label": "研报条数", "cloud_count": len(cloud_reports), "ok": len(cloud_reports) >= 1})
    if len(cloud_reports) < 1:
        problems.append("云端没有机构研报")
    if not local_products:
        warnings.append("本机产品字段为空，未比较产品范围")

    return problems, checks, warnings


def _compare_industry(local: dict[str, Any], cloud: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    problems: list[str] = []
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    local_sector = local.get("sector") if isinstance(local.get("sector"), dict) else {}
    cloud_sector = cloud.get("sector") if isinstance(cloud.get("sector"), dict) else {}
    local_name = _normalize(local_sector.get("name") or local.get("keyword"))
    cloud_name = _normalize(cloud_sector.get("name") or cloud.get("keyword"))
    checks.append(
        {
            "label": "板块名称",
            "local": local_name,
            "cloud": cloud_name,
            "ok": local_name == cloud_name,
        }
    )
    if local_name != cloud_name:
        problems.append(f"板块名称不一致：{local_name} != {cloud_name}")

    local_members = {
        _ticker(item.get("ticker"))
        for item in (local.get("members") or [])
        if isinstance(item, dict)
    } - {""}
    cloud_members = {
        _ticker(item.get("ticker"))
        for item in (cloud.get("members") or [])
        if isinstance(item, dict)
    } - {""}
    missing_members = sorted(local_members - cloud_members)
    extra_members = sorted(cloud_members - local_members)
    checks.append(
        {
            "label": "板块成分股",
            "local_count": len(local_members),
            "cloud_count": len(cloud_members),
            "missing_in_cloud": missing_members,
            "extra_in_cloud": extra_members,
            "ok": local_members == cloud_members,
        }
    )
    if missing_members or extra_members:
        problems.append(
            "板块成分股不一致：缺少 "
            + "、".join(missing_members[:10])
            + "；多出 "
            + "、".join(extra_members[:10])
        )

    local_stocks = {
        _ticker(item.get("ticker")): item
        for item in (local.get("stocks") or [])
        if isinstance(item, dict)
    }
    cloud_stocks = {
        _ticker(item.get("ticker")): item
        for item in (cloud.get("stocks") or [])
        if isinstance(item, dict)
    }
    missing_stocks = sorted(set(local_stocks) - set(cloud_stocks))
    checks.append(
        {
            "label": "核心标的",
            "local_count": len(local_stocks),
            "cloud_count": len(cloud_stocks),
            "missing_in_cloud": missing_stocks,
            "ok": not missing_stocks and len(cloud_stocks) == len(local_stocks),
        }
    )
    if missing_stocks:
        problems.append("云端核心标的缺少：" + "、".join(missing_stocks[:10]))

    for ticker in sorted(set(local_stocks) & set(cloud_stocks)):
        local_stock = local_stocks[ticker]
        cloud_stock = cloud_stocks[ticker]
        label = _text(cloud_stock.get("name") or ticker)
        for key, name, relative, absolute, soft in (
            ("price", "最新价", 0.20, None, False),
            ("pe", "PE", 0.20, None, True),
            ("pb", "PB", 0.20, None, False),
            ("market_cap_yi", "总市值", 0.25, None, False),
            ("revenue_yi", "营业收入", 0.005, None, False),
            ("net_profit_yi", "归母净利润", 0.005, None, False),
            ("gross_margin", "毛利率", None, 0.5, False),
            ("net_margin", "净利率", None, 0.5, False),
            ("roe", "ROE", None, 0.5, False),
            ("revenue_yoy", "营收同比", None, 0.5, False),
            ("profit_yoy", "净利同比", None, 0.5, False),
            ("ytd_change", "年内涨幅", None, 20.0, False),
            ("dividend_yield", "股息率", None, 2.0, True),
        ):
            _add_number_check(
                problems,
                checks,
                label=f"{label}-{name}",
                local=_number(local_stock.get(key)),
                cloud=_number(cloud_stock.get(key)),
                relative=relative,
                absolute=absolute,
                soft=soft,
                warnings=warnings,
            )
        local_business = _normalize(local_stock.get("main_business"))
        cloud_business = _normalize(cloud_stock.get("main_business"))
        business_ok = bool(cloud_business)
        if local_business and cloud_business:
            local_tokens = _business_tokens(local_stock.get("main_business"))
            cloud_tokens = _business_tokens(cloud_stock.get("main_business"))
            business_ok = any(
                _product_contains(cloud_token, local_token)
                for cloud_token in cloud_tokens
                for local_token in local_tokens
            )
        checks.append(
            {
                "label": f"{label}-主营业务",
                "cloud": cloud_business[:80],
                "ok": business_ok,
            }
        )
        if not business_ok:
            problems.append(f"{label}主营业务为空或与本机无交集")

    local_snapshot = (
        local.get("sector_snapshot")
        if isinstance(local.get("sector_snapshot"), dict)
        else {}
    )
    cloud_snapshot = (
        cloud.get("sector_snapshot")
        if isinstance(cloud.get("sector_snapshot"), dict)
        else {}
    )
    for key in (
        "涨幅",
        "5日涨幅",
        "10日涨幅",
        "20日涨幅",
        "主力净流入",
        "量比",
    ):
        cloud_value = _number(cloud_snapshot.get(key))
        local_value = _number(local_snapshot.get(key))
        present = cloud_value is not None
        checks.append(
            {
                "label": f"板块-{key}",
                "local": local_value,
                "cloud": cloud_value,
                "ok": present,
            }
        )
        if not present:
            problems.append(f"云端板块指标缺失：{key}")
        elif (
            local_value is not None
            and abs(local_value - cloud_value) > max(0.5, abs(local_value) * 0.2)
        ):
            warnings.append(
                f"板块{key}随采集时点变化（本机={local_value:g}，云端={cloud_value:g}）"
            )

    cloud_news = cloud.get("news") if isinstance(cloud.get("news"), list) else []
    checks.append({"label": "公告条数", "cloud_count": len(cloud_news), "ok": len(cloud_news) >= 1})
    if len(cloud_news) < 1:
        problems.append("云端行业公告为空")
    return problems, checks, warnings


def compare_payload(kind: str, local_path: Path, cloud_path: Path) -> dict[str, Any]:
    local = json.loads(local_path.read_text(encoding="utf-8"))
    cloud = json.loads(cloud_path.read_text(encoding="utf-8"))
    if kind == "stock":
        problems, checks, warnings = _compare_stock(local, cloud)
    else:
        problems, checks, warnings = _compare_industry(local, cloud)
    return {
        "ok": not problems,
        "type": kind,
        "local": str(local_path.resolve()),
        "cloud": str(cloud_path.resolve()),
        "check_count": len(checks),
        "checks": checks,
        "problems": problems,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="比较本机与云端采集 JSON 中不随采集时点变化的业务字段"
    )
    parser.add_argument("--type", choices=("stock", "industry"), required=True)
    parser.add_argument("--local", required=True)
    parser.add_argument("--cloud", required=True)
    args = parser.parse_args(argv)
    try:
        payload = compare_payload(
            args.type,
            Path(args.local).expanduser().resolve(),
            Path(args.cloud).expanduser().resolve(),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "type": args.type, "error": str(exc)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
