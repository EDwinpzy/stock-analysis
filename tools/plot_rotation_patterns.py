#!/usr/bin/env python3
"""板块轮动规律可视化（四联图）。

    A 相对资金流热力图   —— 剔除每日全市场均值后的板块冷热，真正的轮动地图
    B 排名洗牌速度       —— 每日行业排名变动幅度，量化"轮动有多快"
    C 三阶段主线迁移     —— 前/中/后段 TOP5 行业更替
    D 独立性 vs 相对收益 —— R2（同步度）× 相对累计净额

示例：
    python tools/plot_rotation_patterns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOW_CSV = PROJECT_ROOT / "data" / "sector_fund_flow_行业.csv"
OUTDIR = PROJECT_ROOT / "报告" / "板块资金流"

SW_LEVEL1 = [
    "农林牧渔", "基础化工", "钢铁", "有色金属", "电子", "家用电器", "食品饮料",
    "纺织服饰", "轻工制造", "医药生物", "公用事业", "交通运输", "房地产", "商贸零售",
    "社会服务", "综合", "建筑材料", "建筑装饰", "电力设备", "机械设备", "国防军工",
    "计算机", "传媒", "通信", "银行", "非银金融", "汽车", "煤炭", "石油石化",
    "环保", "美容护理",
]

RED = "#C62828"
GREEN = "#2E7D32"
INK = "#1A1D24"
MUTED = "#6B7280"
GRID = "#E5E7EB"


def p(*a):
    print(*a)


def load() -> pd.DataFrame:
    df = pd.read_csv(FLOW_CSV, index_col=0, parse_dates=True).sort_index() / 1e8
    return df[[c for c in SW_LEVEL1 if c in df.columns]]


def panel_a_rel_heatmap(rel: pd.DataFrame, ax) -> None:
    """相对资金流热力图：剔除每日全市场均值后的板块冷热。"""
    order = rel.sum().sort_values(ascending=False).index
    m = rel[order].T
    vmax = float(np.nanpercentile(np.abs(m.to_numpy()), 90)) or 1.0
    cmap = LinearSegmentedColormap.from_list(
        "flow", [GREEN, "#8BC34A", "#F2F4F7", "#FF8A65", RED], N=256
    )
    im = ax.imshow(
        m.to_numpy(), aspect="auto", cmap=cmap,
        norm=TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax), interpolation="nearest",
    )
    ax.set_xticks(range(len(m.columns)))
    ax.set_xticklabels([d.strftime("%m-%d") for d in m.columns], rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(len(m.index)))
    ax.set_yticklabels(m.index, fontsize=8.5)
    ax.set_xticks(np.arange(-0.5, len(m.columns), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(m.index), 1), minor=True)
    ax.grid(which="minor", color=GRID, linewidth=0.5)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = ax.figure.colorbar(im, ax=ax, pad=0.012, fraction=0.022)
    cb.set_label("相对主力净流入（亿元）", fontsize=8)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=7, colors=MUTED, length=0)
    ax.set_title(
        "A  相对资金流热力图（已剔除每日全市场均值）",
        fontsize=11, fontweight="bold", color=INK, loc="left", pad=8,
    )


def panel_b_churn(rel: pd.DataFrame, ax) -> None:
    """每日排名变动幅度 + TOP5 重叠度。"""
    ranks = rel.rank(axis=1, ascending=False)
    shift = ranks.diff().abs().mean(axis=1).iloc[1:]
    top5 = [set(rel.iloc[i].nlargest(5).index) for i in range(len(rel))]
    overlap = pd.Series(
        [len(top5[i] & top5[i + 1]) / 5 * 100 for i in range(len(top5) - 1)],
        index=rel.index[1:],
    )
    ax.bar(range(len(shift)), shift.to_numpy(), color=MUTED, width=0.7, alpha=0.85, label="排名变动(位)")
    ax.axhline(shift.mean(), color=RED, linewidth=1.4, linestyle="--",
               label=f"均值 {shift.mean():.1f} 位")
    ax.set_ylim(0, 16)
    ax.set_ylabel("行业排名平均变动（位）", fontsize=8.5)
    ax.set_xticks(range(len(shift)))
    ax.set_xticklabels([d.strftime("%m-%d") for d in shift.index], rotation=45, ha="right", fontsize=6.5)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax2 = ax.twinx()
    ax2.plot(range(len(overlap)), overlap.to_numpy(), color=INK, linewidth=1.4, alpha=0.8)
    # 重叠度普遍在 0~40%，把上限压到 60% 才看得出起伏，压到 100 会压成一条平线
    ax2.set_ylim(0, 60)
    ax2.set_yticks([0, 20, 40, 60])
    ax2.set_ylabel("TOP5 重叠度（%）", fontsize=8.5, color=MUTED)
    ax2.tick_params(colors=MUTED, labelsize=7, length=0)
    for s in ("top", "left", "right"):
        ax2.spines[s].set_visible(False)
    ax.legend(loc="upper right", fontsize=7.5, frameon=False, ncol=2)
    ax.set_title(
        f"B  轮动速度：排名天天洗牌（TOP5 重叠仅 {overlap.mean():.0f}%）",
        fontsize=11, fontweight="bold", color=INK, loc="left", pad=8,
    )


def panel_c_phases(rel: pd.DataFrame, ax) -> None:
    """三阶段 TOP5 行业更替。"""
    bounds = np.linspace(0, len(rel), 4, dtype=int)
    segs = list(zip(("前段", "中段", "后段"), bounds[:-1], bounds[1:]))
    width = 0.26
    for k, (nm, s, e) in enumerate(segs):
        t = rel.iloc[s:e].sum().sort_values(ascending=False).head(5)
        xs = np.arange(len(t)) + (k - 1) * width
        span = f"{rel.index[s].date()}~{rel.index[e-1].date()}"
        ax.bar(xs, t.to_numpy(), width=width * 0.92, label=f"{nm} {span}")
        for x, v in zip(xs, t.to_numpy()):
            ax.text(x, v + (12 if v >= 0 else -12), f"{v:+.0f}", ha="center",
                    va="bottom" if v >= 0 else "top", fontsize=6.5, color=MUTED)
    ax.axhline(0, color=INK, linewidth=0.9)
    ax.set_xticks(range(5))
    ax.set_xticklabels(["TOP1", "TOP2", "TOP3", "TOP4", "TOP5"], fontsize=8.5)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_ylabel("该阶段相对累计净额（亿元）", fontsize=8.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=7.5, frameon=False, loc="upper right")
    ax.set_title("C  主线三阶段迁移（每段最强 TOP5）", fontsize=11,
                 fontweight="bold", color=INK, loc="left", pad=8)


def panel_d_independence(flow: pd.DataFrame, rel: pd.DataFrame, ax) -> None:
    """同步度 R2（leave-one-out）× 相对累计净额。"""
    rows = {}
    for c in flow.columns:
        # 必须用原始流量算 R2：rel 每日截面和为 0，peer 会恒等于 -rel[c]，R2 恒为 1
        peer = flow.drop(columns=[c]).sum(axis=1)
        r2 = float(np.corrcoef(peer, flow[c])[0, 1] ** 2) if flow[c].std() > 0 else 0.0
        rows[c] = {"R2": r2, "rel": float(rel[c].sum())}
    d = pd.DataFrame(rows).T
    for name, r in d.iterrows():
        color = RED if r["rel"] >= 0 else GREEN
        ax.scatter(r["R2"], r["rel"], s=70, color=color, alpha=0.75,
                   edgecolors="white", linewidths=1.2, zorder=3)

    # 先固定 y 轴范围，再按轴内坐标标注，避免文字被挤到画布外
    ymin, ymax = d["rel"].min(), d["rel"].max()
    span = ymax - ymin
    pad = span * 0.22
    ax.set_ylim(ymin - pad, ymax + pad)

    def _label(name: str, target_y: float) -> None:
        """标签放在指定的数据坐标高度，用细引线连回原点，天然不会互相压字。"""
        ax.annotate(
            name,
            xy=(d.loc[name, "R2"], d.loc[name, "rel"]),
            xytext=(d.loc[name, "R2"], target_y),
            textcoords="data",
            fontsize=8, color=INK, ha="center", va="center", zorder=4,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7,
                            shrinkA=1, shrinkB=4),
        )

    # 三个最流入的点几乎重合，标签必须错层排开，否则必然叠字
    for i, name in enumerate(d["rel"].nlargest(3).index):
        _label(name, ymax + pad * (0.30 + 0.26 * i))
    for i, name in enumerate(d["rel"].nsmallest(2).index):
        _label(name, ymin - pad * (0.34 + 0.28 * i))

    ax.axhline(0, color=INK, linewidth=0.9)
    ax.axvline(0.5, color=MUTED, linewidth=0.9, linestyle=":")
    ax.set_xlim(-0.05, 0.95)
    top = ax.get_ylim()[1]
    bot = ax.get_ylim()[0]
    zone_y = ymax - span * 0.30  # 放到图内中上部，避开顶部的错层标签
    ax.text(0.53, zone_y, "跟随大盘区", fontsize=8, color=MUTED)
    ax.text(0.47, zone_y, "独立区", fontsize=8, color=MUTED, ha="right")
    ax.set_xlabel("同步度 R2（对剔除自身后的其余板块）", fontsize=8.5)
    ax.set_ylabel("区间相对累计净额（亿元）", fontsize=8.5)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title("D  独立性 vs 相对收益（左侧=独立资金面）", fontsize=11,
                 fontweight="bold", color=INK, loc="left", pad=8)


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    plt.rcParams.update({
        "font.family": ["Microsoft YaHei", "SimHei", "DengXian", "sans-serif"],
        "axes.unicode_minus": False, "figure.facecolor": "white", "axes.facecolor": "white",
        "savefig.facecolor": "white", "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": MUTED, "ytick.color": MUTED, "font.size": 9,
    })
    flow = load()
    rel = flow.sub(flow.mean(axis=1), axis=0)
    OUTDIR.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(19, 13))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.25, 1], hspace=0.32, wspace=0.22)
    panel_a_rel_heatmap(rel, fig.add_subplot(gs[0, :]))
    panel_b_churn(rel, fig.add_subplot(gs[1, 0]))
    panel_c_phases(rel, fig.add_subplot(gs[1, 1]))

    out1 = OUTDIR / "04-轮动规律-相对热力图与轮动速度.png"
    fig.savefig(out1, dpi=150, bbox_inches="tight")
    plt.close(fig)
    p(f"  [1/2] {out1.name}")

    fig2, ax = plt.subplots(figsize=(11, 7.5))
    panel_d_independence(flow, rel, ax)
    fig2.tight_layout()
    out2 = OUTDIR / "05-轮动规律-独立性vs相对收益.png"
    fig2.savefig(out2, dpi=150, bbox_inches="tight")
    plt.close(fig2)
    p(f"  [2/2] {out2.name}")
    p(f"\n已输出到 {OUTDIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
