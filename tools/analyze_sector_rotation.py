#!/usr/bin/env python3
"""板块轮动 × 资金流结构分析。

回答五个问题：
    1. 这是轮动还是撤离？          —— 绝对水平 vs 截面相对水平
    2. 轮动的速度有多快？          —— 排名自相关、TOP5 重叠
    3. 资金流是动量还是反转？      —— 行业自身滞后自相关
    4. 板块资金流有多少是市场 beta？—— 对全市场流量回归后的残差
    5. 资金主线有没有阶段性迁移？  —— 三段式对比

输入：
    data/sector_fund_flow_行业.csv
    data/panel_history.csv          （可选，提供成交额/涨跌家数做交叉验证）

示例：
    python tools/analyze_sector_rotation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOW_CSV = PROJECT_ROOT / "data" / "sector_fund_flow_行业.csv"
PANEL_CSV = PROJECT_ROOT / "data" / "panel_history.csv"

SW_LEVEL1 = [
    "农林牧渔", "基础化工", "钢铁", "有色金属", "电子", "家用电器", "食品饮料",
    "纺织服饰", "轻工制造", "医药生物", "公用事业", "交通运输", "房地产", "商贸零售",
    "社会服务", "综合", "建筑材料", "建筑装饰", "电力设备", "机械设备", "国防军工",
    "计算机", "传媒", "通信", "银行", "非银金融", "汽车", "煤炭", "石油石化",
    "环保", "美容护理",
]


def p(*args) -> None:
    print(*args)


def rule(title: str) -> None:
    p("")
    p("=" * 70)
    p(title)
    p("=" * 70)


def load() -> tuple[pd.DataFrame, pd.DataFrame | None]:
    flow = pd.read_csv(FLOW_CSV, index_col=0, parse_dates=True).sort_index()
    flow = flow[[c for c in SW_LEVEL1 if c in flow.columns]]
    panel = None
    if PANEL_CSV.exists():
        panel = pd.read_csv(PANEL_CSV, parse_dates=["date"]).set_index("date")
        panel = panel.reindex(flow.index)
    return flow, panel


def q1_rotation_or_exodus(flow: pd.DataFrame) -> dict:
    """绝对水平 vs 截面相对水平：区分整体撤离和内部搬家。"""
    rule("问题1：这是轮动还是撤离？")
    yi = flow / 1e8
    daily_total = yi.sum(axis=1)
    net = float(daily_total.sum())
    pos_industries = int((yi.sum() > 0).sum())

    p(f"区间总净额      : {net:+,.1f} 亿")
    p(f"净流出交易日    : {int((daily_total < 0).sum())}/{len(daily_total)} 天")
    p(f"行业净流入个数  : {pos_industries}/{yi.shape[1]} 个")
    p(f"单日全市场极值  : 最大 {daily_total.max():+,.0f} 亿 / 最小 {daily_total.min():+,.0f} 亿")

    rel = yi.sub(yi.mean(axis=1), axis=0)
    rel_net = rel.sum()
    p("")
    p("截面相对净额（剔除每日全市场均值后，看板块间是否互相接力）:")
    p(f"  相对净流入行业  : {int((rel_net > 0).sum())} 个")
    p(f"  相对净流出行业  : {int((rel_net < 0).sum())} 个")
    p(f"  相对净额标准差  : {rel_net.std():,.1f} 亿")
    top = rel_net.sort_values(ascending=False)
    p("")
    p("  相对最强（真·逆势吸筹）:")
    for name, v in top.head(5).items():
        p(f"    {name:<8} {v:+,.1f} 亿   (绝对 {yi[name].sum():+,.1f} 亿)")
    p("  相对最弱:")
    for name, v in top.tail(5).items():
        p(f"    {name:<8} {v:+,.1f} 亿   (绝对 {yi[name].sum():+,.1f} 亿)")

    verdict = "撤离主导（绝对水位全面下沉）" if net < 0 and pos_industries <= yi.shape[1] * 0.3 else "存在实质轮动"
    p("")
    p(f"结论: {verdict}")
    return {"net": net, "rel": rel, "yi": yi, "pos_industries": pos_industries}


def q2_rotation_speed(flow: pd.DataFrame, rel: pd.DataFrame) -> dict:
    """排名自相关 + 冠军更替，衡量轮动节奏。"""
    rule("问题2：轮动速度有多快？")
    ranks = rel.rank(axis=1, ascending=False)
    acs = [
        float(ranks.iloc[i].corr(ranks.iloc[i + 1], method="spearman"))
        for i in range(len(ranks) - 1)
    ]
    p(f"行业相对排名 lag-1 Spearman 自相关: 均值 {np.mean(acs):+.3f}（中位 {np.median(acs):+.3f}）")
    p("  >0.5 排名稳定（轮动慢）   约 0 排名天天洗牌（轮动快）")

    top5 = [set(rel.iloc[i].nlargest(5).index) for i in range(len(rel))]
    overlap = [len(top5[i] & top5[i + 1]) / 5 for i in range(len(top5) - 1)]
    p(f"每日 TOP5 与前一日重合度: 均值 {np.mean(overlap):.1%}（中位 {np.median(overlap):.1%}）")

    champ = rel.idxmax(axis=1)
    runs, run = [], 1
    for i in range(1, len(champ)):
        run = run + 1 if champ.iloc[i] == champ.iloc[i - 1] else 1
        runs.append(run)
    p(f"单日冠军连续在榜: 最长 {max(runs)} 天，平均 {np.mean(runs):.1f} 天")
    shift = ranks.diff().abs().mean(axis=1)
    p(f"单日行业排名平均变动: {shift.mean():.2f} 位（满分 15.0）")
    return {"rank_ac": float(np.mean(acs)), "overlap": float(np.mean(overlap))}


def q3_momentum_or_reversal(flow: pd.DataFrame) -> dict:
    """行业内资金流自身 lag-1 自相关：正=动量延续，负=均值回复。"""
    rule("问题3：资金流是动量延续还是反转？")
    yi = flow / 1e8
    acs = pd.Series({c: float(yi[c].autocorr(lag=1)) for c in yi.columns}).sort_values(ascending=False)
    p(f"行业日度资金流 lag-1 自相关: 均值 {acs.mean():+.3f}，为正的行业 {int((acs > 0).sum())}/{len(acs)} 个")
    p("")
    p("  延续性最强（资金有惯性）:")
    for name, v in acs.head(5).items():
        p(f"    {name:<8} {v:+.3f}")
    p("  反转最强（一日游）:")
    for name, v in acs.tail(5).items():
        p(f"    {name:<8} {v:+.3f}")

    rel = yi.sub(yi.mean(axis=1), axis=0)
    rel_ac = [
        float(rel.iloc[i].corr(rel.iloc[i + 1], method="spearman"))
        for i in range(len(rel) - 1)
    ]
    rel_ac_mean = float(np.mean(rel_ac))
    # |值| 很接近 0 表示昨天的强弱排名对今天几乎没有预测力
    if abs(rel_ac_mean) < 0.15:
        label = "无记忆（昨天的强弱对今天无预测力）"
    else:
        label = "动量延续（买昨天强的）" if rel_ac_mean > 0 else "反转（卖昨天强的）"
    p("")
    p(f"相对资金流排名 lag-1 Spearman: {rel_ac_mean:+.3f}  →  {label}")
    return {"autocorr": float(acs.mean()), "rel_ac": rel_ac_mean}


def q4_market_beta(flow: pd.DataFrame, panel: pd.DataFrame | None) -> dict:
    """行业对全市场流量回归，残差 = 板块自己的资金行为。"""
    rule("问题4：板块资金流里有多少是市场 beta？")
    yi = flow / 1e8
    mkt = yi.sum(axis=1)
    p("注：31 个行业加总恒等于全市场，故各行业 beta 之和≈1，单个 beta 均值≈0.03。")
    p("    有意义的是同步度 R2 和「相对口径」，不是 beta 绝对值。")

    # 自我贡献校正：某行业占全市场流量比重越大，它与"全市场"的相关越可能是循环的。
    # 用 leave-one-out（剔除自身后的其余 30 个行业之和）重算，才是对外的真实同步度。
    self_weight = (yi.abs().sum() / yi.abs().sum().sum()).sort_values(ascending=False)
    p("")
    p("自我贡献最大行业: " + "、".join(f"{n}({v:.1%})" for n, v in self_weight.head(3).items()))
    rows = []
    for c in yi.columns:
        peer = yi.drop(columns=[c]).sum(axis=1)  # 剔除自身
        x, y = peer.values, yi[c].values
        var = x.var()
        if var == 0:
            continue
        beta = float(np.cov(y, x, bias=True)[0, 1] / var)
        r2 = float(np.corrcoef(x, y)[0, 1] ** 2) if y.std() > 0 else 0.0
        rows.append({
            "行业": c, "beta": beta, "R2": r2,
            "自我占比": float(yi[c].abs().sum() / yi.abs().sum().sum()),
            # 相对口径：行业流量 - 全市场日均，衡量它比"平均板块"多赚/多亏多少
            "相对累计": float((yi[c] - yi.mean(axis=1)).sum()),
        })
    b = pd.DataFrame(rows).set_index("行业").sort_values("R2", ascending=False)
    p(f"行业 beta 均值 {b['beta'].mean():.2f}，R2 均值 {b['R2'].mean():.2f}")
    p("  R2 已做 leave-one-out 校正：R2 高 = 跟随其余板块同进同退；R2 低 = 有独立节奏")
    p("")
    p("  同步度最高:")
    for name, r in b.sort_values("R2", ascending=False).head(5).iterrows():
        p(f"    {name:<8} R2={r['R2']:.2f}   自我占比={r['自我占比']:.1%}   相对累计={r['相对累计']:+,.0f} 亿")
    p("  同步度最低（资金面独立，最可能有真实 Alpha）:")
    for name, r in b.sort_values("R2").head(5).iterrows():
        p(f"    {name:<8} R2={r['R2']:.2f}   自我占比={r['自我占比']:.1%}   相对累计={r['相对累计']:+,.0f} 亿")

    out = {"beta_mean": float(b["beta"].mean()), "r2_mean": float(b["R2"].mean())}
    if panel is not None:
        rule("交叉验证：板块流量 vs 市场成交额/涨跌家数")
        mkt_corr = {}
        for col, label in (("turnover", "成交额"), ("advance_count", "涨跌家数"),
                           ("limit_up", "涨停数"), ("sh_close", "上证收盘")):
            if col in panel:
                s = pd.to_numeric(panel[col], errors="coerce")
                if s.notna().sum() > 5:
                    mkt_corr[label] = float(mkt.corr(s))
        for label, c in mkt_corr.items():
            p(f"全市场日度流量 与 {label} 相关系数: {c:+.3f}")
        if mkt_corr:
            p("  绝对值高 → 板块资金流主要反映市场整体水位，而非独立板块行为")
    return out


def q5_phases(flow: pd.DataFrame) -> dict:
    """把区间切三段，看资金主线的迁移。"""
    rule("问题5：资金主线有没有阶段性迁移？")
    yi = flow / 1e8
    tops = []
    bounds = np.linspace(0, len(yi), 4, dtype=int)
    for nm, start, end in zip(("前段", "中段", "后段"), bounds[:-1], bounds[1:]):
        s = yi.iloc[start:end]
        t = s.sum(axis=0).sort_values(ascending=False)
        tops.append(set(t.head(5).index))
        direction = "流入" if t.sum() > 0 else "流出"
        p(f"{nm} {s.index[0].date()}~{s.index[-1].date()}  净{direction} {t.sum():+,.0f} 亿")
        p("   TOP5: " + "、".join(f"{i}({v:+,.0f})" for i, v in t.head(5).items()))
    shared = len(tops[0] & tops[2])
    p("")
    p(f"前段∩后段 TOP5 重叠: {shared}/5  →  {'主线延续' if shared >= 3 else '主线已切换'}")
    return {"shared": shared}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    flow, panel = load()
    p(f"数据: {len(flow)} 个交易日 × {flow.shape[1]} 个一级行业"
      f"（{flow.index[0].date()} ~ {flow.index[-1].date()}）")

    r1 = q1_rotation_or_exodus(flow)
    r2 = q2_rotation_speed(flow, r1["rel"])
    r3 = q3_momentum_or_reversal(flow)
    r4 = q4_market_beta(flow, panel)
    r5 = q5_phases(flow)

    rule("小结")
    p(f"1. 总量: {r1['net']:+,.0f} 亿，{r1['pos_industries']}/{r1['yi'].shape[1]} 个行业为正"
      f"  →  {'撤离主导' if r1['net'] < 0 else '增量主导'}")
    speed = "轮动偏慢" if r2["rank_ac"] > 0.4 else "轮动偏快/洗牌"
    p(f"2. 速度: 排名自相关 {r2['rank_ac']:+.2f}，TOP5 重叠 {r2['overlap']:.0%}  →  {speed}")
    if abs(r3["rel_ac"]) < 0.15:
        mem = "无记忆（昨日强弱无预测力）"
    else:
        mem = "动量延续" if r3["rel_ac"] > 0 else "相对反转"
    p(f"3. 动量: 资金流自相关 {r3['autocorr']:+.2f}，相对排名自相关 {r3['rel_ac']:+.2f}"
      f"  →  {mem}")
    beta_verdict = "高度同步大盘" if r4["r2_mean"] > 0.5 else "含独立板块行为"
    p(f"4. Beta: 均值 {r4['beta_mean']:.2f}，R2 {r4['r2_mean']:.2f}  →  {beta_verdict}")
    p(f"5. 主线: 前段/后段 TOP5 重叠 {r5['shared']}/5  →  {'延续' if r5['shared'] >= 3 else '已切换'}")
    p("")
    p("（样本仅 30 个交易日，以上为描述性统计，不做显著性推断）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
