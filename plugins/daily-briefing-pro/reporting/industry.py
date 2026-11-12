from __future__ import annotations

import re
from typing import Any

from .common import (
    clean,
    document,
    esc,
    epoch_text,
    fnum,
    fpct,
    fyi,
    kv_grid,
    median,
    number,
    section,
    split_products,
    table,
    tone,
)


def _raw_metric(stock: dict[str, Any], *fragments: str) -> float | None:
    raw = stock.get("raw") if isinstance(stock.get("raw"), dict) else {}
    for key, value in raw.items():
        text = str(key)
        if all(fragment in text for fragment in fragments):
            parsed = number(value)
            if parsed is not None:
                return parsed
    return None


def _snapshot_value(key: str, value: Any) -> Any:
    parsed = number(value)
    if parsed is None:
        return value
    if key in {"涨幅", "5日涨幅", "10日涨幅", "20日涨幅"}:
        return fpct(parsed)
    if key == "主力净流入":
        return fyi(parsed)
    if key in {"最新价", "涨跌", "开盘价", "最高价", "最低价", "昨收"}:
        return f"{parsed:,.2f}"
    if key in {"成交量", "总金额"}:
        return f"{parsed:,.0f}"
    if key == "量比":
        return f"{parsed:,.2f}"
    return f"{parsed:,.2f}" if isinstance(value, float) else f"{parsed:,.0f}"


def _metrics(stock: dict[str, Any]) -> dict[str, Any]:
    pe = number(stock.get("pe"))
    if pe is None:
        pe = _raw_metric(stock, "市盈率")
    pb = number(stock.get("pb"))
    if pb is None:
        pb = _raw_metric(stock, "市净率")
    cap = number(stock.get("market_cap_yi"))
    revenue = number(stock.get("revenue_yi"))
    profit = number(stock.get("net_profit_yi"))
    revenue_yoy = number(stock.get("revenue_yoy")) or _raw_metric(stock, "营业收入", "同比增长")
    profit_yoy = number(stock.get("profit_yoy")) or _raw_metric(stock, "净利润", "同比增长")
    ytd = number(stock.get("ytd_change")) or _raw_metric(stock, "区间涨跌幅")
    return {
        "name": str(clean(stock.get("name")) or "未命名标的"),
        "ticker": str(clean(stock.get("ticker")) or ""),
        "price": number(stock.get("price")),
        "change_pct": number(stock.get("change_pct")),
        "pe": pe,
        "pb": pb,
        "market_cap": cap,
        "revenue": revenue,
        "profit": profit,
        "gross_margin": number(stock.get("gross_margin")),
        "net_margin": number(stock.get("net_margin")),
        "roe": number(stock.get("roe")),
        "revenue_yoy": revenue_yoy,
        "profit_yoy": profit_yoy,
        "ytd": ytd,
        "industry": str(clean(stock.get("industry")) or "行业未返回"),
        "main_business": str(clean(stock.get("main_business")) or ""),
        "dividend_yield": number(stock.get("dividend_yield")),
    }


def _quality(stock: dict[str, Any]) -> float:
    score = 0.0
    score += 1.5 if (stock["profit_yoy"] or 0) > 0 else 0
    score += 1.0 if (stock["revenue_yoy"] or 0) > 0 else 0
    score += 1.0 if (stock["roe"] or 0) >= 8 else 0
    score += 0.6 if (stock["gross_margin"] or 0) >= 30 else 0
    score += 1.2 if stock["pe"] is not None and 0 < stock["pe"] <= 35 else 0
    score += 0.7 if (stock["profit"] or 0) > 0 else 0
    return round(score, 2)


def _core_note(stock: dict[str, Any]) -> str:
    growth = (
        f"营收同比 {fpct(stock['revenue_yoy'])}、净利同比 {fpct(stock['profit_yoy'])}"
        if stock["revenue_yoy"] is not None or stock["profit_yoy"] is not None
        else "营收与净利同比暂未返回"
    )
    valuation = (
        f"PE {fnum(stock['pe'])}x、PB {fnum(stock['pb'])}"
        if stock["pe"] is not None or stock["pb"] is not None
        else "估值指标暂未返回"
    )
    risk = (
        "利润为负，需优先核验亏损原因"
        if stock["profit"] is not None and stock["profit"] < 0
        else "关注增速与估值的匹配度"
    )
    return f"{growth}；{valuation}。风险提示：{risk}。"


def build_industry_report(data: dict[str, Any]) -> str:
    sector = data.get("sector") if isinstance(data.get("sector"), dict) else {}
    members = [item for item in (data.get("members") or []) if isinstance(item, dict)]
    stocks = [_metrics(item) for item in (data.get("stocks") or []) if isinstance(item, dict)]
    snapshot = data.get("sector_snapshot") if isinstance(data.get("sector_snapshot"), dict) else {}
    news = [item for item in (data.get("news") or []) if isinstance(item, dict)]
    name = str(clean(sector.get("name")) or clean(data.get("keyword")) or "未命名板块")
    block_code = str(clean(sector.get("block_code")) or "未返回")
    fetch_time = str(clean(data.get("fetch_time")) or "未返回")

    positive_pe = [item["pe"] for item in stocks if item["pe"] is not None and item["pe"] > 0]
    pe_median = median(positive_pe)
    rev_med = median(item["revenue_yoy"] for item in stocks)
    profit_med = median(item["profit_yoy"] for item in stocks)
    roe_med = median(item["roe"] for item in stocks)
    margin_med = median(item["gross_margin"] for item in stocks)
    total_cap = sum(item["market_cap"] for item in stocks if item["market_cap"] is not None)
    top3_cap_share = (
        sum(sorted((item["market_cap"] for item in stocks if item["market_cap"] is not None), reverse=True)[:3])
        / total_cap
        * 100
        if total_cap
        else None
    )
    positive_growth = sum(1 for item in stocks if (item["profit_yoy"] or 0) > 0)
    loss_count = sum(1 for item in stocks if item["profit"] is not None and item["profit"] < 0)
    ranked = sorted(stocks, key=lambda item: (_quality(item), item["market_cap"] or 0), reverse=True)
    top = ranked[:5]
    by_cap = sorted(stocks, key=lambda item: item["market_cap"] or -1, reverse=True)
    strongest = max(stocks, key=lambda item: item["profit_yoy"] or -1e9) if stocks else None
    cheapest = min(
        (item for item in stocks if item["pe"] is not None and item["pe"] > 0 and (item["profit"] or 0) > 0),
        key=lambda item: item["pe"],
        default=None,
    )
    if pe_median is not None and pe_median <= 25 and (profit_med or 0) > 0:
        rating = "谨慎乐观"
    elif pe_median is not None and pe_median > 55:
        rating = "中性偏谨慎"
    else:
        rating = "中性"

    change = number(snapshot.get("涨幅"))
    change_5d = number(snapshot.get("5日涨幅"))
    change_10d = number(snapshot.get("10日涨幅"))
    change_20d = number(snapshot.get("20日涨幅"))
    main_flow = number(snapshot.get("主力净流入"))
    volume_ratio = number(snapshot.get("量比"))

    overview = [
        ("板块名称", name),
        ("板块代码", block_code),
        ("板块类型", clean(sector.get("kind")) or "industry"),
        ("成分股数", len(members)),
        ("核心标的数", len(stocks)),
        ("板块涨幅", fpct(change)),
        ("5日/10日/20日", f"{fpct(change_5d)} / {fpct(change_10d)} / {fpct(change_20d)}"),
        ("主力净流入", fyi(main_flow)),
        ("量比", fnum(volume_ratio)),
    ]
    catalyst_rows = [
        ("盈利兑现", f"净利同比正增长 {positive_growth}/{len(stocks)} 家，中位数 {fpct(profit_med)}", strongest["name"] if strongest else "公开数据未覆盖", fpct(strongest["profit_yoy"]) if strongest else "公开数据未覆盖"),
        ("收入增长", f"营收同比中位数 {fpct(rev_med)}", max(stocks, key=lambda item: item["revenue_yoy"] or -1e9)["name"] if stocks else "公开数据未覆盖", fpct(max((item["revenue_yoy"] or 0) for item in stocks)) if stocks else "公开数据未覆盖"),
        ("估值分化", f"正 PE 中位数 {fnum(pe_median)}x，亏损标的 {loss_count} 家", cheapest["name"] if cheapest else "公开数据未覆盖", f"PE {fnum(cheapest['pe'])}x" if cheapest else "公开数据未覆盖"),
    ]
    pipeline = [
        ("上游投入", f"{len(members)} 家样本覆盖", "原材料、设备与研发投入"),
        ("核心环节", "行业主体", "产品、设计与制造"),
        ("配套环节", "协同环节", "软件、器件、服务与渠道"),
        ("需求侧", "客户与订单", "公告与合同线索"),
        ("终端应用", "下游行业", "需求景气与库存周期"),
    ]
    pipeline_html = '<div class="cf">' + "".join(
        f'<div class="cfi"><div class="cfn">{label}</div><div class="cfd">{value}<br>{sub}</div></div>'
        for label, value, sub in pipeline
    ) + "</div>"

    competition_rows = [
        (item["name"], item["ticker"], fnum(item["price"]), fpct(item["change_pct"]), fnum(item["pe"]), fyi((item["market_cap"] or 0) * 1e8), item["industry"].split("-")[-1])
        for item in by_cap[:10]
    ]
    tier_rows = [
        ("第一梯队", f"市值 ≥ {fyi(2e11)}", "、".join(item["name"] for item in by_cap[:3])),
        ("第二梯队", f"市值 {fyi(5e10)}—{fyi(2e11)}", "、".join(item["name"] for item in by_cap if (item["market_cap"] or 0) * 1e8 >= 5e10 and (item["market_cap"] or 0) * 1e8 < 2e11)[:8] or "无样本"),
        ("弹性梯队", f"市值 < {fyi(5e10)}", "、".join(item["name"] for item in by_cap if (item["market_cap"] or 0) * 1e8 < 5e10)[:8] or "无样本"),
    ]

    kv_values = [
        ("板块当日涨幅", fpct(change), f"{name} · 数据时点 {fetch_time}", tone(change)),
        ("正 PE 中位数", f"{fnum(pe_median)}x", "剔除负 PE 与缺失值", ""),
        ("营收同比中位数", fpct(rev_med), "最新年度财务样本", tone(rev_med)),
        ("净利同比中位数", fpct(profit_med), "最新年度财务样本", tone(profit_med)),
        ("ROE 中位数", fpct(roe_med, signed=False), "盈利质量参照", ""),
        ("毛利率中位数", fpct(margin_med, signed=False), "产品结构参照", ""),
        ("核心标的总市值", fyi(total_cap * 1e8), f"{len(stocks)} 只核心标的", ""),
        ("亏损标的数", f"{loss_count} / {len(stocks)}", "净利润为负的样本", "dn" if loss_count else ""),
    ]

    detail_rows = [
        (
            item["name"],
            item["ticker"],
            fnum(item["price"]),
            fpct(item["change_pct"]),
            fnum(item["pe"]),
            fnum(item["pb"]),
            fyi((item["market_cap"] or 0) * 1e8),
            fpct(item["revenue_yoy"]),
            fpct(item["profit_yoy"]),
            fpct(item["roe"], signed=False),
            fpct(item["gross_margin"], signed=False),
            fpct(item["dividend_yield"], signed=False),
            "、".join(split_products(item["main_business"])) or "公开数据未覆盖",
        )
        for item in ranked
    ]
    core_cards = "".join(
        '<div class="sc"><div class="sch">'
        f'<h3>{esc(item["name"])}（{esc(item["ticker"])}）</h3><span class="tag">{esc(item["industry"])}</span>'
        "</div>"
        + kv_grid(
            (
                ("市值", fyi((item["market_cap"] or 0) * 1e8), "总市值", ""),
                ("PE / PB", f"{fnum(item['pe'])} / {fnum(item['pb'])}", "估值", ""),
                ("营收 / 净利", f"{fnum(item['revenue'])} / {fnum(item['profit'])} 亿", "最新年度", ""),
                ("净利同比", fpct(item["profit_yoy"]), "最新年度", tone(item["profit_yoy"])),
                ("ROE", fpct(item["roe"], signed=False), "盈利质量", ""),
                ("毛利率", fpct(item["gross_margin"], signed=False), "产品结构", ""),
                ("股息率", fpct(item["dividend_yield"], signed=False), "近12个月现金分红", ""),
                ("主营业务", "、".join(split_products(item["main_business"])) or "公开数据未覆盖", "公开披露口径", ""),
                ("年内涨幅", fpct(item["ytd"]), "区间行情", tone(item["ytd"])),
                ("量化排序", f"{_quality(item):.2f}", "收入/利润/ROE/估值综合", ""),
            )
        )
        + f'<p style="color:var(--t2);font-size:12px;line-height:1.7;margin:10px 0 0">{esc(_core_note(item))}</p>'
        + "</div>"
        for item in top
    )

    announcement_rows = [
        (item["stock"], item["ticker"], clean(item.get("title")) or "标题未返回", clean(item.get("category")) or "公告", epoch_text(item.get("time")))
        for item in news[:10]
    ]
    order_rows = []
    for item in news:
        title = str(clean(item.get("title")) or "")
        if any(word in title for word in ("订单", "合同", "中标", "客户", "供应", "合作", "项目")):
            order_rows.append(
                (
                    item.get("stock"),
                    title[:100],
                    "公告标题语义命中，待原文核验",
                    "本次公告采集",
                )
            )
    if not order_rows:
        order_rows = [
            (
                "公开样本",
                "本次公告样本未提取到可核验的客户订单条款；不据此推断订单规模",
                "未形成订单结论",
                "数据边界",
            )
        ]

    score_rows = [
        (index + 1, item["name"], f"{_quality(item):.2f}", fpct(item["profit_yoy"]), fpct(item["revenue_yoy"]), fpct(item["roe"], signed=False), fnum(item["pe"]))
        for index, item in enumerate(ranked[:10])
    ]
    configure_rows = [
        ("稳健配置", "财务质量与估值相对均衡", "、".join(item["name"] for item in ranked[:3])),
        ("高弹性观察", "利润增速居前但估值或波动较高", "、".join(item["name"] for item in sorted(stocks, key=lambda item: item["profit_yoy"] or -1e9, reverse=True)[:3])),
        ("估值观察", "正 PE 且盈利为正的低估值样本", cheapest["name"] if cheapest else "无样本"),
        (
            "风险观察",
            "亏损或正 PE 偏高、需要优先核验的样本",
            "、".join(
                item["name"]
                for item in sorted(
                    stocks,
                    key=lambda item: (
                        item["profit"] is not None and item["profit"] < 0,
                        item["pe"] if item["pe"] is not None else 1e9,
                    ),
                    reverse=True,
                )[:3]
            )
            or "无样本",
        ),
    ]
    rotation_rows = [
        (
            "短线强弱",
            f"板块 5 日涨幅 {fpct(change_5d)}",
            "、".join(item["name"] for item in by_cap[:3]) or "无样本",
            "观察成交与涨幅是否同步",
        ),
        (
            "轮动持续性",
            f"板块 10 日涨幅 {fpct(change_10d)}，主力净流入 {fyi(main_flow)}",
            "、".join(item["name"] for item in ranked[:3]) or "无样本",
            "观察资金是否继续扩散",
        ),
        (
            "阶段趋势",
            f"板块 20 日涨幅 {fpct(change_20d)}，量比 {fnum(volume_ratio)}",
            "、".join(item["name"] for item in sorted(stocks, key=lambda item: item["ytd"] or -1e9, reverse=True)[:3]) or "无样本",
            "区分趋势延续与高位分化",
        ),
    ]
    risks = [
        ("盈利风险", f"净利同比中位数 {fpct(profit_med)}，亏损样本 {loss_count} 家", "关注季报与年报兑现"),
        ("估值风险", f"正 PE 中位数 {fnum(pe_median)}x，样本分化明显", "避免以单一年度利润外推"),
        ("需求风险", f"板块 20 日涨幅 {fpct(change_20d)}，量比 {fnum(volume_ratio)}", "跟踪成交量与库存"),
        ("订单风险", "公告样本未提取到完整客户订单条款", "以公司公告原文核验"),
        ("集中度风险", f"前三大市值标的占样本总市值 {fpct(top3_cap_share, signed=False)}", "观察龙头波动对板块的传导"),
        ("波动风险", f"5/10/20 日涨幅分别为 {fpct(change_5d)} / {fpct(change_10d)} / {fpct(change_20d)}", "跟踪振幅与回撤"),
        ("数据风险", f"采集时间 {fetch_time}", "行情、财务和公告时点可能不同"),
    ]

    sources = [str(item).strip() for item in (data.get("sources") or []) if str(item).strip()]
    if sources:
        source_rows = tuple(
            (
                item.split("：", 1)[0],
                item.split("：", 1)[1].split("（", 1)[0] if "：" in item else "本次采集数据",
            )
            for item in sources
        )
    else:
        source_rows = (
            ("同花顺 thsdk", "板块、成分、行情与公告"),
            ("同花顺 wencai", "财务、估值与同比指标"),
        )

    body = [
        '<div class="c">',
        '<div class="np-mast">'
        f'<div class="np-mast-kicker">INDUSTRY DEEP DIVE · {name}</div>'
        f'<div class="np-mast-title">{name}行业深度分析</div>'
        f'<div class="np-mast-sub"><span>{fetch_time}</span><span>|</span><span>板块 {block_code}</span><span>|</span><span>覆盖标的 <b>{len(stocks)}</b> 只</span><span>|</span><span>评级 <b>{rating}</b></span></div>'
        "</div>",
        '<div class="g">',
        section(
            "01",
            "行业概览",
            kv_grid(kv_values)
            + table(("指标", "数值"), overview)
            + '<div class="sc"><div class="sch"><h3>核心数据与催化</h3></div>'
            + table(("催化", "数据", "代表标的", "最新值"), catalyst_rows)
            + "</div>"
            + pipeline_html
            + f'<p class="src">说明：产业链环节为通用分析框架；样本数据来自 {name} 板块当前采集，不代表完整产业链所有公司。</p>',
            f"{len(stocks)} 只样本",
        ),
        section(
            "02",
            "竞争格局",
            table(("标的", "代码", "价格", "涨跌幅", "PE", "总市值", "细分行业"), competition_rows)
            + table(("梯队", "划分", "样本"), tier_rows),
            f"前三 {len(by_cap[:3])} 家",
        ),
        section(
            "03",
            "核心标的",
            core_cards
            + table(("标的", "代码", "价格", "涨跌", "PE", "PB", "总市值", "营收同比", "净利同比", "ROE", "毛利率", "股息率", "主营业务"), detail_rows),
            "量化排序",
        ),
        section(
            "04",
            "客户订单信息",
            table(("标的", "客户/订单线索", "状态", "来源"), order_rows)
            + table(("公司", "代码", "公告标题", "类别", "时间"), announcement_rows),
            f"{len(news)} 条公告",
        ),
        section(
            "05",
            "同行指标",
            table(("标的", "代码", "营收(亿)", "净利(亿)", "毛利率", "ROE", "营收同比", "净利同比", "PE", "PB", "市值(亿)", "股息率"), [
                (item["name"], item["ticker"], fnum(item["revenue"]), fnum(item["profit"]), fpct(item["gross_margin"], signed=False), fpct(item["roe"], signed=False), fpct(item["revenue_yoy"]), fpct(item["profit_yoy"]), fnum(item["pe"]), fnum(item["pb"]), fnum(item["market_cap"]), fpct(item["dividend_yield"], signed=False))
                for item in stocks
            ])
            + table(
                ("板块指标", "数值"),
                [(key, _snapshot_value(key, value)) for key, value in snapshot.items()],
            ),
            "全量对比",
        ),
        section(
            "06",
            "投资逻辑",
            table(("排名", "标的", "量化分", "净利同比", "营收同比", "ROE", "PE"), score_rows)
            + table(("配置层", "筛选逻辑", "代表标的"), configure_rows)
            + table(("阶段", "当前证据", "代表标的", "观察方式"), rotation_rows)
            + '<div class="lb"><strong>核心结论：</strong>当前行业评级为 '
            + rating
            + f"，正 PE 中位数 {fnum(pe_median)}x，净利同比中位数 {fpct(profit_med)}。"
            "优先观察盈利兑现与估值匹配的标的，不用单一指标替代投资判断。</div>",
            "量化规则",
        ),
        section(
            "07",
            "风险提示",
            table(("风险维度", "当前证据", "跟踪方式"), risks)
            + '<div class="lb warn">'
            + "".join(f'<div class="li">{item[0]}：{item[1]}；{item[2]}。</div>' for item in risks)
            + "</div>",
            f"{len(risks)} 项",
        ),
        section(
            "08",
            "核心结论",
            '<div class="lb gold"><strong>一句话结论：</strong>'
            + f'{name} 当前评级为 {rating}，正 PE 中位数 {fnum(pe_median)}x，净利同比中位数 {fpct(profit_med)}；'
            + f'前三大市值标的占样本总市值 {fpct(top3_cap_share, signed=False)}。</div>'
            + kv_grid(
                (
                    ("行业评级", rating, "由估值、增速和盈利质量共同决定", "gold"),
                    ("首选观察", top[0]["name"] if top else "无样本", "量化排序第一，非投资建议", "gold"),
                    ("估值洼地", cheapest["name"] if cheapest else "无样本", f"PE {fnum(cheapest['pe'])}x" if cheapest else "无正 PE 样本", ""),
                    ("最大弹性", strongest["name"] if strongest else "无样本", f"净利同比 {fpct(strongest['profit_yoy'])}" if strongest else "数据未返回", "up" if strongest and (strongest["profit_yoy"] or 0) > 0 else "dn"),
                )
            )
            + table(
                ("来源", "用途"),
                source_rows
                + (
                    ("采集时间", fetch_time),
                    ("性质", "数据驱动研究底稿，不构成投资建议"),
                ),
            )
            + '<p class="src">所有表格均来自本次采集 JSON；客户订单只在公告标题明确命中相关语义时列示，无法核验的订单金额不推算。</p>',
            "自动门禁",
        ),
        "</div></div>",
        '<div class="ft">Daily Briefing Pro · 行业深度分析 · 不构成投资建议</div>',
    ]
    return document("industry", f"{name}行业深度分析", "".join(body))
