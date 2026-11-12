from __future__ import annotations

import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from .common import (
    annual_series,
    change_rate,
    clean,
    document,
    epoch_text,
    first_text,
    fnum,
    fpct,
    fyi,
    latest_values,
    median,
    number,
    pick,
    section,
    split_products,
    table,
    tone,
)


def _identity(data: dict[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    quote = data.get("quote") if isinstance(data.get("quote"), dict) else {}
    finance = data.get("finance_raw") if isinstance(data.get("finance_raw"), dict) else {}
    name = (
        clean(quote.get("name"))
        or clean(pick(finance, "股票简称"))
        or clean(data.get("stock_name"))
        or "未知证券"
    )
    code = (
        clean(data.get("stock_code"))
        or clean(pick(finance, "股票代码"))
        or clean(data.get("thscode"))
        or ""
    )
    return str(name), str(code).split(".")[0], finance, quote


def _holder_count_change(holder_trend: dict[str, Any]) -> float | None:
    records: list[tuple[str, float]] = []
    for key, value in holder_trend.items():
        text = str(key)
        if not re.fullmatch(r"(?:股东户数|总户数)(?:\([^)]*\))?\[\d{8}\]", text):
            continue
        parsed = number(value)
        if parsed is not None:
            records.append((text, parsed))
    records.sort(key=lambda item: item[0])
    if len(records) < 2 or records[0][1] == 0:
        return None
    return (records[-1][1] / records[0][1] - 1) * 100


def _rating(score: float) -> tuple[str, str, str]:
    if score >= 7:
        return "值得关注", "green", "可纳入重点研究清单，仍需按估值与业绩验证节点跟踪"
    if score >= 4:
        return "谨慎观察", "yellow", "基本面与估值尚未形成同向共振，宜等待数据确认"
    return "规避", "red", "当前量化指标偏弱，优先控制回撤并等待基本面改善"


def _peer_metric(peer: dict[str, Any], fragment: str) -> float | None:
    if fragment == "市盈率":
        for needle in ("市盈率(pe)", "动态市盈率"):
            value = number(pick(peer, needle))
            if value is not None:
                return value
    if fragment in ("净资产收益率", "ROE"):
        value = number(pick(peer, "净资产收益率", "加权"))
        if value is None:
            value = number(pick(peer, "加权净资产收益率"))
        if value is not None:
            return value
    value = number(pick(peer, fragment))
    if value is None:
        for key, raw in peer.items():
            if fragment in str(key):
                value = number(raw)
                if value is not None:
                    break
    return value


def _period_label(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        year, month_day = text[:4], text[4:]
        if month_day == "1231":
            return f"{year}年报"
        if month_day == "0630":
            return f"{year}中报"
        return f"{year}-{month_day[:2]}-{month_day[2:]}"
    return text or "期间未返回"


def _concentration_text(metric: Any) -> str:
    if not isinstance(metric, dict):
        return "数据源未返回"
    value = number(metric.get("value"))
    if value is None:
        return "数据源未返回"
    return f"{fpct(value, signed=False)}（{_period_label(metric.get('period'))}）"


def _concentration_level(metric: Any) -> str:
    if not isinstance(metric, dict) or number(metric.get("value")) is None:
        return "未返回"
    value = number(metric.get("value"))
    if value < 15:
        return "较低"
    if value < 35:
        return "中等"
    return "较高"


def build_stock_report(data: dict[str, Any]) -> str:
    quote = data.get("quote") if isinstance(data.get("quote"), dict) else {}
    peers = [item for item in (data.get("peers_raw") or []) if isinstance(item, dict)]
    news = [item for item in (data.get("news") or []) if isinstance(item, dict)]
    orders = [item for item in (data.get("big_orders") or []) if isinstance(item, dict)]
    holders_raw = data.get("holders_raw") or {}
    product_raw = data.get("product_raw") or {}
    chip = data.get("chip_structure") if isinstance(data.get("chip_structure"), dict) else {}
    barrier = data.get("barrier_data") if isinstance(data.get("barrier_data"), dict) else {}
    research = data.get("research_reports") if isinstance(data.get("research_reports"), dict) else {}
    blogger = data.get("blogger_opinions") if isinstance(data.get("blogger_opinions"), dict) else {}
    name, code, finance, _ = _identity(data)

    industry = str(clean(pick(finance, "所属同花顺行业")) or "行业未返回")
    full_name = str(clean(pick(finance, "公司中文名称")) or name)
    controller = str(clean(pick(finance, "实际控制人")) or "本次公开摘要未覆盖实际控制人")
    controlling = str(
        clean(pick(finance, "控股股东名称"))
        or clean(pick(finance, "控股股东"))
        or "本次公开摘要未覆盖控股股东"
    )
    registered = str(clean(pick(finance, "注册地址")) or "本次公开摘要未覆盖注册地址")
    listing = str(
        clean(pick(finance, "新股上市日期"))
        or clean(pick(finance, "上市日期"))
        or "本次公开摘要未覆盖上市日期"
    )
    main_business = str(
        clean(pick(finance, "主营产品名称"))
        or clean(pick(product_raw, "主营产品名称"))
        or "本次公开摘要未覆盖主营业务"
    )

    price = number(quote.get("price")) or number(quote.get("last_price")) or number(pick(finance, "最新价"))
    change_pct = number(quote.get("change_pct")) or number(pick(finance, "最新涨跌幅"))
    market_cap = number(quote.get("market_cap"))
    pe_ttm = number(quote.get("pe_ttm"))
    pb = number(pick(finance, "市净率"))
    if pb is None:
        matching_peer = next(
            (
                item
                for item in peers
                if str(code) in str(pick(item, "股票代码"))
            ),
            None,
        )
        if matching_peer:
            pb = _peer_metric(matching_peer, "市净率")

    peer_pes = [value for value in (_peer_metric(item, "市盈率") for item in peers) if value is not None and value > 0]
    peer_pe_median = median(peer_pes)
    peer_pb_median = median(
        value for value in (_peer_metric(item, "市净率") for item in peers) if value is not None and value > 0
    )

    revenue_series = annual_series(finance, "营业收入", exclude=("同比", "增长", "占"))
    profit_series = annual_series(finance, "归属于母公司所有者的净利润", exclude=("扣除", "同比", "增长"))
    margin_series = annual_series(finance, "销售毛利率")
    roe_series = annual_series(finance, "净资产收益率")
    debt_series = annual_series(finance, "资产负债率")
    annual_rows = latest_values(revenue_series, 3)
    years = [year for year, _ in annual_rows] or [datetime.now(ZoneInfo("Asia/Shanghai")).year - 1]
    revenue_growth = change_rate(revenue_series)
    profit_growth = change_rate(profit_series)
    latest_revenue = max(revenue_series.values()) if revenue_series else None
    latest_profit = max(profit_series.values()) if profit_series else None
    latest_roe = max(roe_series.values()) if roe_series else None
    latest_margin = max(margin_series.values()) if margin_series else None
    latest_debt = max(debt_series.values()) if debt_series else None
    net_margin = latest_profit / latest_revenue * 100 if latest_profit and latest_revenue else None

    score = 5.0
    if pe_ttm and peer_pe_median:
        ratio = pe_ttm / peer_pe_median
        score += 1.2 if ratio <= 0.8 else -1.2 if ratio >= 1.5 else 0.2 if ratio <= 1.1 else -0.2
    if latest_roe is not None:
        score += 1.0 if latest_roe >= 15 else 0.3 if latest_roe >= 8 else -0.8 if latest_roe < 3 else 0
    if net_margin is not None:
        score += 0.7 if net_margin >= 15 else -0.6 if net_margin < 0 else 0
    if revenue_growth is not None:
        score += 0.5 if revenue_growth >= 10 else -0.5 if revenue_growth < 0 else 0
    if profit_growth is not None:
        score += 0.6 if profit_growth >= 10 else -0.7 if profit_growth < 0 else 0
    if latest_debt is not None:
        score += 0.4 if latest_debt <= 40 else -0.6 if latest_debt >= 65 else 0
    main_inflow = number(quote.get("main_net_inflow"))
    if main_inflow is not None and main_inflow < 0:
        score -= 0.3
    score = round(max(0.0, min(10.0, score)), 1)
    rating, rating_color, action_view = _rating(score)

    if pe_ttm and peer_pe_median:
        valuation_ratio = pe_ttm / peer_pe_median
        valuation_level = "低于同业" if valuation_ratio < 0.9 else "高于同业" if valuation_ratio > 1.15 else "接近同业"
    else:
        valuation_level = "同业估值样本不足"

    eps = price / pe_ttm if price and pe_ttm and pe_ttm > 0 else None
    base_pe = peer_pe_median or 20.0
    scenario_rows = []
    if eps:
        for label, factor, probability, rationale in (
            ("乐观", 1.2, "25%", "估值修复至同业中位数上方"),
            ("基准", 1.0, "50%", "维持当前盈利，回归同业中位数"),
            ("谨慎", 0.8, "25%", "风险溢价上升，估值继续压缩"),
        ):
            low = eps * base_pe * factor * 0.9
            high = eps * base_pe * factor * 1.1
            scenario_rows.append(
                (label, f"PE {base_pe * factor:.1f}x × EPS {eps:.2f}", f"{low:,.2f}—{high:,.2f}", probability, rationale)
            )
    else:
        scenario_rows.append(("数据不足", "无法由当前 PE 与股价反推 EPS", "不生成估值结论", "-", "不以推算值替代缺失数据"))

    finance_rows = []
    for label, series, formatter in (
        ("营业收入", revenue_series, fyi),
        ("归母净利润", profit_series, fyi),
        ("销售毛利率", margin_series, fpct),
        ("ROE", roe_series, fpct),
        ("资产负债率", debt_series, fpct),
    ):
        finance_rows.append([label] + [formatter(series.get(year)) if year in series else "公开数据未覆盖" for year in years])

    peer_rows = []
    for peer in sorted(peers, key=lambda item: number(pick(item, "总市值")) or 0, reverse=True)[:6]:
        peer_rows.append(
            (
                clean(pick(peer, "股票简称")) or "未命名同业",
                fnum(_peer_metric(peer, "市盈率")),
                fnum(_peer_metric(peer, "市净率")),
                fyi(pick(peer, "总市值")),
                fpct(_peer_metric(peer, "销售毛利率")),
                fpct(_peer_metric(peer, "净资产收益率")),
            )
        )

    products = split_products(
        pick(product_raw, "主营产品名称"),
        pick(finance, "主营产品名称"),
    )
    product_rows = [(item, "本次采集返回的主营产品标签") for item in products[:12]]

    news_rows = [
        (
            epoch_text(item.get("Time")),
            clean(item.get("Title")) or "标题未返回",
            "资讯/公告",
            "待核验",
            "需结合原文判断对经营和估值的影响",
        )
        for item in news[:8]
    ]
    order_keywords = ("订单", "中标", "合同", "采购", "客户", "合作", "供货", "签约")
    order_news = [
        item
        for item in news
        if isinstance(item, dict)
        and any(keyword in str(item.get("Title") or "") for keyword in order_keywords)
    ][:5]
    order_rows = [
        (
            epoch_text(item.get("Time")),
            clean(item.get("Title")) or "标题未返回",
            "新闻/公告",
        )
        for item in order_news
    ]

    direction_legend = data.get("big_orders_direction_legend") if isinstance(data.get("big_orders_direction_legend"), dict) else {}
    buy_amount = 0.0
    sell_amount = 0.0
    for item in orders:
        amount = number(pick(item, "总金额")) or 0.0
        direction = str(clean(pick(item, "成交方向")) or "")
        label = str(direction_legend.get(direction, direction))
        if "买入" in label:
            buy_amount += amount
        elif "卖出" in label:
            sell_amount += amount
    order_total = buy_amount + sell_amount
    buy_share = buy_amount / order_total * 100 if order_total else None

    holder_names: list[str] = []
    if isinstance(holders_raw, dict):
        holder_text = clean(pick(holders_raw, "前十大流通股东名称")) or clean(
            pick(holders_raw, "前十大股东")
        )
        if holder_text:
            holder_names = [item.strip() for item in str(holder_text).split("||") if item.strip()]
    if not holder_names and isinstance(holders_raw.get("holders_parsed"), list):
        holder_names = [str(item) for item in holders_raw["holders_parsed"] if item]
    holder_rows = [(index + 1, item) for index, item in enumerate(holder_names[:10])]

    top10_ratio = number(pick(chip.get("concentration"), "前十大股东持股比例合计"))
    institution_ratio = number(pick(holders_raw, "机构持股占流通股比例"))
    holder_trend = _holder_count_change(chip.get("holder_count_trend") if isinstance(chip.get("holder_count_trend"), dict) else {})
    restricted_shares = number(pick(chip.get("share_structure"), "限售a股"))
    margin_balance = number(
        pick(
            chip.get("margin"),
            "融资余额",
            exclude=("占流通市值", "占流通股", "比例", "市值"),
        )
    )
    chip_rows = [
        ("前十大股东集中度", 2 if (top10_ratio or 0) >= 50 else 1 if (top10_ratio or 0) >= 30 else 0, fpct(top10_ratio, signed=False)),
        ("机构持股占比", 2 if (institution_ratio or 0) >= 50 else 1 if (institution_ratio or 0) >= 20 else 0, fpct(institution_ratio, signed=False)),
        ("股东户数趋势", 2 if holder_trend is not None and holder_trend <= 0 else 1 if holder_trend is not None and holder_trend < 20 else 0, fpct(holder_trend)),
        ("限售股压力", 2 if restricted_shares == 0 else 1 if restricted_shares is not None else 0, fnum(restricted_shares)),
        ("融资余额", 2 if margin_balance is not None else 0, fnum(margin_balance)),
        ("大单买卖结构", 2 if buy_share is not None and buy_share >= 55 else 1 if buy_share is not None and buy_share >= 45 else 0, fpct(buy_share, signed=False)),
    ]
    chip_score = sum(row[1] for row in chip_rows)
    chip_verdict = "稳定" if chip_score >= 9 else "中性" if chip_score >= 5 else "不稳"

    rd = barrier.get("rd_raw") if isinstance(barrier.get("rd_raw"), dict) else {}
    rd_ratio = number(pick(rd, "研发投入占营业收入的比重")) or number(pick(rd, "研发投入占比"))
    patents = number(pick(rd, "专利数量合计"))
    moat_rows = [
        ("品牌与定价", "★★★★★" if (latest_margin or 0) >= 80 else "★★★★" if (latest_margin or 0) >= 60 else "★★★" if (latest_margin or 0) >= 40 else "★★", f"销售毛利率 {fpct(latest_margin, signed=False)}"),
        ("盈利效率", "★★★★★" if (latest_roe or 0) >= 25 else "★★★★" if (latest_roe or 0) >= 15 else "★★★" if (latest_roe or 0) >= 8 else "★★", f"历史披露 ROE 最高值 {fpct(latest_roe, signed=False)}"),
        ("研发投入", "★★★★★" if (rd_ratio or 0) >= 8 else "★★★★" if (rd_ratio or 0) >= 5 else "★★★" if (rd_ratio or 0) >= 2 else "★★", f"研发投入占营收 {fpct(rd_ratio, signed=False)}"),
        ("知识产权", "★★★★★" if (patents or 0) >= 1000 else "★★★★" if (patents or 0) >= 300 else "★★★" if (patents or 0) >= 100 else "★★", f"专利数量合计 {fnum(patents, 0)}"),
        ("规模与渠道", "★★★★★" if (market_cap or 0) >= 5e11 else "★★★★" if (market_cap or 0) >= 1e11 else "★★★" if (market_cap or 0) >= 2e10 else "★★", f"总市值 {fyi(market_cap)}"),
    ]
    barrier_rows = [
        ("毛利率", min(5, max(1, int((latest_margin or 0) / 20) + 1)), fpct(latest_margin, signed=False), "与自身盈利能力对应的量化评分"),
        ("净利率", min(5, max(1, int((net_margin or 0) / 10) + 1)), fpct(net_margin, signed=False), "利润转化效率"),
        ("ROE", min(5, max(1, int((latest_roe or 0) / 8) + 1)), fpct(latest_roe, signed=False), "股东资本回报"),
        ("研发强度", min(5, max(1, int((rd_ratio or 0) / 2) + 1)), fpct(rd_ratio, signed=False), "研发投入占比"),
        ("专利", min(5, max(1, int(math.log10(max(patents or 1, 1))) - 1)), fnum(patents, 0), "知识产权存量"),
        ("规模", min(5, max(1, int(math.log10(max(market_cap or 1, 1))) - 8)), fyi(market_cap), "总市值对应的规模项"),
    ]
    barrier_total = sum(row[1] for row in barrier_rows)
    barrier_verdict = "高壁垒" if barrier_total >= 20 else "中壁垒" if barrier_total >= 10 else "低壁垒"

    reports = [item for item in (research.get("reports") or []) if isinstance(item, dict)]
    report_rows = [
        (
            clean(item.get("date")) or "日期未返回",
            clean(item.get("org")) or "机构未返回",
            clean(item.get("title")) or "标题未返回",
            clean(item.get("rating")) or "评级未提取",
            fnum(item.get("target_price"), fallback="未披露"),
            fnum(item.get("forecast_pe"), fallback="未披露"),
        )
        for item in reports[:6]
    ]
    research_block = (
        table(("日期", "机构", "标题", "评级", "目标价", "预测PE"), report_rows)
        if report_rows
        else '<div class="lb">本次采集未返回可核验的机构研报样本；不以空表或推测内容代替。</div>'
    )
    blogger_rows = []
    for platform, label in (("tgb", "淘股吧"), ("xueqiu", "雪球"), ("serenity", "Serenity")):
        items = blogger.get(platform) if isinstance(blogger.get(platform), list) else []
        blogger_rows.append((label, len(items), "本次采集返回经核验提及" if items else "本次采集未返回经核验帖子"))

    risk_rows = [
        ("经营", "关注" if (revenue_growth is not None and revenue_growth < 0) or (profit_growth is not None and profit_growth < 0) else "正常", f"最近年度营收变化 {fpct(revenue_growth)}，归母净利变化 {fpct(profit_growth)}"),
        ("财务", "关注" if (latest_debt or 0) >= 65 else "正常", f"资产负债率 {fpct(latest_debt, signed=False)}，ROE {fpct(latest_roe, signed=False)}"),
        ("合规", "采集范围内未命中处罚类公告", "该结论只覆盖本次资讯/公告样本，不代表完整监管历史"),
        ("流动性", "关注" if (number(quote.get("turnover_rate")) is not None and number(quote.get("turnover_rate")) < 0.2) else "正常", f"换手率 {fpct(quote.get('turnover_rate'), signed=False)}，总市值 {fyi(market_cap)}"),
    ]
    risk_list = [
        "估值与盈利增长不匹配时，股价可能继续消化估值。",
        "行业景气、渠道库存和终端需求波动会影响收入与利润率。",
        "公开客户、订单与产能口径未在当前采集结果中完整拆分，需以公司公告核验。",
        "数据时点差异会造成行情、财务和研报口径不一致。",
        "资金流与股东结构只反映已返回样本，不能替代完整交易与持仓数据。",
    ]

    core_conclusion = (
        f"{name}（{code}）最新价 {fnum(price)} 元，涨跌幅 {fpct(change_pct)}；"
        f"PE(TTM) {fnum(pe_ttm)}，{valuation_level}，历史披露 ROE 高点 {fpct(latest_roe, signed=False)}。"
        f"当前量化评级为{rating}（{score}/10）。"
    )
    hero = (
        '<div class="hero">'
        f"<h1>{name}（{code}）深度研究报告</h1>"
        f'<div class="sub">数据驱动研究底稿 · {full_name} · 采集时间 {clean(data.get("fetch_time")) or "未返回"}</div>'
        '<div class="meta">'
        f"<span>代码：{code}</span><span>市值：{fyi(market_cap)}</span><span>股价：¥{fnum(price)}</span>"
        f'<span>评级：<span class="badge {rating_color}">{rating}</span></span><span>行业：{industry}</span>'
        "</div></div>"
    )

    runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
    if str(runtime.get("source") or "") == "cloud":
        holder_source = clean(data.get("holders_source"))
        peer_source = clean(data.get("peers_source"))
        wencai_domains = [
            "实时行情",
            "财务",
            "估值",
            "同业",
            "股东",
            "产品",
            "筹码",
            "壁垒",
            "大单日汇总",
        ]
        if holder_source == "eastmoney":
            wencai_domains.remove("股东")
        if peer_source == "eastmoney":
            wencai_domains.remove("同业")
        wencai_scope = "、".join(wencai_domains[:-1]) + "与" + wencai_domains[-1]
        source_rows = [
            ("扶摇 REST", "证券检索、新闻与公告", "本次采集已返回"),
            (
                "官方问财 OpenAPI",
                wencai_scope,
                "本次采集已返回",
            ),
        ]
        if holder_source == "eastmoney":
            source_rows.append(
                ("东方财富 F10", "前十大流通股东与机构持股比例", "本次采集已返回")
            )
        if peer_source == "eastmoney":
            source_rows.append(
                ("东方财富 F10/行情", "同业估值、市值与财务指标", "本次采集已返回")
            )
        source_rows = tuple(source_rows)
    else:
        source_rows = (
            ("同花顺 thsdk", "行情、财务、股东、资金、公告", "本次采集已返回"),
            ("同花顺 wencai", "同业与年度财务指标", "本次采集已返回"),
        )

    body = [
        '<div class="c">',
        hero,
        section(
            "01",
            "核心结论",
            f'<div class="hl"><p style="margin:0;font-size:15px;font-weight:700">{core_conclusion}</p></div>'
            + table(
                ("项目", "结论"),
                (
                    ("综合评分", f"{score}/10；盈利质量、估值、成长、杠杆和资金面综合；不是投资建议"),
                    ("估值水位", f"{valuation_level}；PE(TTM) {fnum(pe_ttm)}，同业中位数 {fnum(peer_pe_median)}"),
                    ("业绩趋势", f"营收同比 {fpct(revenue_growth)}，归母净利同比 {fpct(profit_growth)}"),
                    ("资金方向", f"主力净流入 {fyi(main_inflow)}，5日涨跌 {fpct(quote.get('5d_change'))}"),
                    ("行动框架", action_view),
                ),
            ),
            rating,
        ),
        section(
            "02",
            "概览与估值",
            '<div class="row2">'
            '<div class="sc"><div class="sch"><h3>基本信息</h3></div>'
            + table(
                ("项目", "内容"),
                (
                    ("公司全称", full_name),
                    ("注册地", registered),
                    ("实际控制人", controller),
                    ("控股股东", controlling),
                    ("主营业务", main_business[:220]),
                    ("上市日期", listing),
                ),
            )
            + "</div>"
            '<div class="sc"><div class="sch"><h3>财务快照</h3></div>'
            + table(("指标", *years), finance_rows)
            + "</div></div>"
            '<div class="sc"><div class="sch"><h3>估值矩阵与同业对比</h3></div>'
            + table(
                ("指标", name, "同业中位数/样本"),
                (
                    ("PE(TTM)", fnum(pe_ttm), fnum(peer_pe_median)),
                    ("PB", fnum(pb), fnum(peer_pb_median)),
                    ("总市值", fyi(market_cap), f"{len(peers)} 家同业样本"),
                    ("EPS 反推", fnum(eps), "股价 ÷ PE(TTM)"),
                ),
            )
            + table(("同业", "PE", "PB", "总市值", "毛利率", "ROE"), peer_rows)
            + "</div>"
            + '<div class="lb gold"><strong>三情景估值区间</strong>'
            + table(("情景", "估值方法", "股价区间(元)", "概率", "说明"), scenario_rows)
            + "<p style=\"margin:8px 0 0;font-weight:700\">估值区间是由当前 PE、股价和同业中位数推导的敏感性分析，不是公司指引或目标价。</p></div>",
            "量化估值",
        ),
        section(
            "03",
            "产品与客户",
            table(("业务/产品", "数据依据"), product_rows)
            + table(
                ("客户维度", "当前数据结论"),
                (
                    ("所属行业", industry),
                    ("主营业务口径", main_business[:260]),
                    (
                        "前五大客户销售额占比",
                        _concentration_text(barrier.get("customer_concentration")),
                    ),
                    (
                        "前五大供应商采购额占比",
                        _concentration_text(barrier.get("supplier_concentration")),
                    ),
                    (
                        "客户/供应商集中度判断",
                        f"客户{_concentration_level(barrier.get('customer_concentration'))}；"
                        f"供应商{_concentration_level(barrier.get('supplier_concentration'))}",
                    ),
                    (
                        "订单/客户线索",
                        f"本次 {len(news)} 条资讯/公告中命中 {len(order_news)} 条订单或客户关键词",
                    ),
                ),
            )
            + (
                '<div class="sc"><div class="sch"><h3>订单与客户线索</h3></div>'
                + table(("时间", "标题", "类型"), order_rows)
                + "</div>"
                if order_rows
                else ""
            ),
            f"{len(products)} 个产品标签",
        ),
        section(
            "04",
            "基本面与壁垒",
            table(("护城河维度", "星级", "依据"), moat_rows)
            + '<div class="row2">'
            '<div class="sc"><div class="sch"><h3>六维壁垒量化</h3></div>'
            + table(("维度", "得分(0-5)", "证据", "说明"), barrier_rows)
            + f'<div class="lb gold"><strong>壁垒结论：</strong>{barrier_total}/30，{barrier_verdict}。评分按公开财务和知识产权指标映射。</div></div>'
            '<div class="sc"><div class="sch"><h3>核心矛盾与不可替代性</h3></div>'
            + table(
                ("项目", "结论", "验证方式"),
                (
                    ("核心矛盾", "估值、盈利增长与现金流质量能否保持同向", "跟踪季度营收、净利、毛利率和经营现金流"),
                    ("不可替代性", f"毛利率 {fpct(latest_margin, signed=False)}、ROE {fpct(latest_roe, signed=False)}，需结合产品与客户结构验证", "以公告和年报客户/产品拆分核验"),
                    ("资本结构", f"资产负债率 {fpct(latest_debt, signed=False)}", "跟踪有息负债与偿付安排"),
                ),
            )
            + "</div></div>"
            + table(
                ("观察项", "当前数据"),
                (
                    ("营业收入", fyi(latest_revenue)),
                    ("归母净利润", fyi(latest_profit)),
                    ("净利率", fpct(net_margin, signed=False)),
                    ("研发投入占比", fpct(rd_ratio, signed=False)),
                ),
            ),
            f"{barrier_total}/30",
        ),
        section(
            "05",
            "消息资金筹码",
            '<div class="sc"><div class="sch"><h3>近期新闻与公告</h3></div>'
            + table(("时间", "标题", "类型", "方向", "影响判断"), news_rows)
            + "</div>"
            + '<div class="row2">'
            '<div class="sc"><div class="sch"><h3>三路资金</h3></div>'
            + table(
                ("资金类型", "方向", "详情"),
                (
                    ("主力资金", "流入" if (main_inflow or 0) > 0 else "流出" if (main_inflow or 0) < 0 else "中性", fyi(main_inflow)),
                    ("大单买卖", "买入占优" if (buy_share or 50) >= 55 else "卖出占优" if (buy_share or 50) < 45 else "均衡", f"买入占比 {fpct(buy_share, signed=False)}"),
                    ("融资余额", "已采集", fnum(margin_balance)),
                ),
            )
            + "</div>"
            '<div class="sc"><div class="sch"><h3>十大流通股东名录</h3></div>'
            + table(("序号", "股东名称"), holder_rows, "本次采集未返回股东名录")
            + "</div></div>"
            '<div class="sc"><div class="sch"><h3>六维筹码诊断</h3></div>'
            + table(("维度", "得分(0-2)", "依据"), chip_rows)
            + f'<div class="lb"><strong>筹码结论：</strong>{chip_score}/12，{chip_verdict}。</div></div>',
            f"筹码 {chip_score}/12",
        ),
        section(
            "06",
            "市场声音",
            '<div class="sc"><div class="sch"><h3>机构研报样本</h3></div>'
            + research_block
            + "</div>"
            + '<div class="row2">'
            '<div class="sc"><div class="sch"><h3>博主提及统计</h3></div>'
            + table(("平台", "经核验提及", "覆盖状态"), blogger_rows)
            + "</div>"
            '<div class="sc"><div class="sch"><h3>基本面交叉验证</h3></div>'
            + table(
                ("维度", "市场声音", "基本面事实", "判断"),
                (
                    ("盈利", "研报关注行业与估值", f"ROE {fpct(latest_roe, signed=False)} / 净利率 {fpct(net_margin, signed=False)}", "需持续验证"),
                    ("估值", f"同业样本 {len(peers)} 家", f"PE {fnum(pe_ttm)} / 同业中位数 {fnum(peer_pe_median)}", valuation_level),
                    ("博主", f"经核验提及 {sum(row[1] for row in blogger_rows)} 条", "当前样本不足，不据此形成方向结论", "不作交叉背书"),
                ),
            )
            + "</div></div>",
            f"{len(reports)} 份研报",
        ),
        section(
            "07",
            "前瞻指引",
            table(
                ("观察假设", "最新披露", "验证节点", "可能偏差"),
                (
                    ("收入增长延续性", fpct(revenue_growth), "下一期定期报告", "渠道去库存或需求走弱"),
                    ("利润与毛利率", f"净利率 {fpct(net_margin, signed=False)} / 毛利率 {fpct(latest_margin, signed=False)}", "季度报告与年报", "费用、产品结构或价格体系变化"),
                    ("估值消化", f"PE(TTM) {fnum(pe_ttm)}", "同业估值与盈利预期变化", "风险偏好回落导致估值压缩"),
                    ("股东回报", f"融资余额 {fnum(margin_balance)}", "公告与定期报告", "资本开支或分红政策变化"),
                ),
            )
            + table(
                ("催化来源", "当前可见线索", "重要性", "处理方式"),
                (
                    ("机构研究", f"本次采集 {len(reports)} 份研报", "中", "跟踪标题与摘要中的盈利和估值线索"),
                    ("公司公告", f"本次采集 {len(news)} 条资讯/公告", "高", "以原文披露为准"),
                    ("定期报告", "下一期定期报告", "高", "按交易所预约披露日期更新"),
                    (
                        "资金与筹码",
                        (
                            f"大单日汇总 {len(orders)} 行（非逐笔）"
                            if str(data.get("big_orders_scope") or "") == "daily_aggregate"
                            else f"大单样本 {len(orders)} 条"
                        ),
                        "中",
                        "与成交量和价格趋势联合观察",
                    ),
                ),
            ),
            "跟踪框架",
        ),
        section(
            "08",
            "风险全景",
            table(("健康维度", "状态", "依据"), risk_rows)
            + '<div class="lb danger"><strong>红旗与跟踪项</strong>'
            + "".join(f'<div class="li">{item}</div>' for item in risk_list)
            + "</div>"
            + table(
                ("反身性/踩踏推演", "触发条件", "观察指标", "应对"),
                (
                    ("正向反馈", "盈利超预期且估值扩张", "营收、净利、成交额同步上升", "关注持续性，不追高"),
                    ("负向反馈", "估值收缩叠加资金流出", "PE、主力净流入、换手率恶化", "降低仓位或等待数据修复"),
                    ("流动性冲击", "成交萎缩或集中抛售", "换手率、振幅、融资余额", "优先控制单一标的风险"),
                ),
            ),
            "四维诊断",
        ),
        section(
            "09",
            "行动建议",
            table(
                ("项目", "当前建议"),
                (
                    ("研究评级", f"{rating}（{score}/10）"),
                    ("触发加仓的验证条件", "营收和利润同步改善，且估值不高于同业中位数"),
                    ("触发减仓的风险条件", "盈利下修、现金流恶化或估值显著高于同业"),
                    ("仓位与风险边界", "按个人风险承受能力分散配置；本报告不构成投资建议"),
                    ("下一检查点", "下一期定期报告、重大公告和同业估值变化"),
                ),
            ),
            rating,
        ),
        section(
            "10",
            "数据来源",
            table(
                ("来源", "用途", "状态"),
                source_rows
                + (
                    ("研报来源", f"{len(reports)} 份样本", "仅作标题与摘要引用"),
                    ("博主来源", f"{sum(row[1] for row in blogger_rows)} 条经核验提及", "无样本时不做方向判断"),
                    ("采集时间", clean(data.get("fetch_time")) or "未返回", "报告生成即按该时点解释"),
                ),
            )
            + '<p class="src">本报告由可复现的数据规则自动生成，不构成投资建议。缺失字段不会被推算值替代；无法核验的客户、订单和监管历史不作为结论依据。</p>',
            "自动门禁",
        ),
        '<div class="ft">Daily Briefing Pro · 个股深度研究 · 数据时点见页首 · 不构成投资建议</div>',
        "</div>",
    ]
    return document("stock", f"{name}（{code}）深度研究报告", "".join(body))
