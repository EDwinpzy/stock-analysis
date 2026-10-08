#!/usr/bin/env python3
"""板块资金流可视化：最近 N 个交易日 × 申万一级行业的日度主力净流入。

输入：
    data/sector_fund_flow_行业.csv   （由 tools/fetch_sector_fund_flow.py 生成）

输出（默认写到 报告/板块资金流/）：
    01-行业日度热力图.png    主图：行业 × 交易日 资金流热力图
    02-行业累计净流入.png    行业 30 天累计主力净流入排行
    03-全市场每日资金流.png  全市场每日主力净流入 + 累计曲线

示例：
    python tools/plot_sector_fund_flow.py
    python tools/plot_sector_fund_flow.py --days 20
    python tools/plot_sector_fund_flow.py --per-sector   # 31 个一级行业各出一张
    python tools/plot_sector_fund_flow.py --outdir 报告/板块资金流
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "sector_fund_flow_行业.csv"
DEFAULT_OUTDIR = PROJECT_ROOT / "报告" / "板块资金流"

# 申万一级行业 31 个（数据源为东财板块名，个别带层级后缀的取一级口径）
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
PAPER = "#FFFFFF"


def _setup_style() -> None:
    """统一字体与视觉基线，中文优先微软雅黑。"""
    plt.rcParams.update({
        "font.family": ["Microsoft YaHei", "SimHei", "DengXian", "sans-serif"],
        "axes.unicode_minus": False,
        "figure.facecolor": PAPER,
        "axes.facecolor": PAPER,
        "savefig.facecolor": PAPER,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.edgecolor": GRID,
        "axes.grid": False,
        "font.size": 10,
    })


def _flow_cmap() -> LinearSegmentedColormap:
    """红涨绿跌的发散色阶：中性浅灰 -> 绿 -> 灰 -> 红。"""
    return LinearSegmentedColormap.from_list(
        "flow", [GREEN, "#8BC34A", "#F2F4F7", "#FF8A65", RED], N=256
    )


def _fmt_yi(value: float, digits: int = 0) -> str:
    """元 -> 亿元，带正负号。"""
    yi = value / 1e8
    return f"{yi:+,.{digits}f}" if yi >= 0 else f"{yi:,.{digits}f}"


def load_matrix(csv_path: Path, days: int | None) -> tuple[pd.DataFrame, list[str], list[str]]:
    """读 CSV，截取最近 days 个交易日，抽取申万一级行业列。"""
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True).sort_index()
    if days:
        df = df.tail(days)
    available = [c for c in SW_LEVEL1 if c in df.columns]
    missing = [c for c in SW_LEVEL1 if c not in df.columns]
    return df, available, missing


def plot_heatmap(
    matrix: pd.DataFrame, out_path: Path, top: int | None = None, annot: bool = False
) -> None:
    """主图：行业 × 交易日 资金流热力图，按月累计净额排序，稳健色阶。"""
    total = matrix.sum(axis=0)  # 日期是 index、行业是 columns，axis=0 才是每行业累计
    order = total.sort_values(ascending=False).index
    ordered = matrix[order]
    if top:
        ordered = ordered.head(top)

    # 转置成 行业(行) × 交易日(列)，热力图才是"纵轴行业、横轴日期"
    yi = (ordered / 1e8).T
    # 稳健色阶：用 90 分位截断，避免个别天量级行业压平整图颜色
    finite = yi.to_numpy()
    vmax = float(np.nanpercentile(np.abs(finite), 90)) or 1.0
    cmap = _flow_cmap()
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)

    fig, ax = plt.subplots(figsize=(16, 10))
    im = ax.imshow(
        yi.to_numpy(), aspect="auto", cmap=cmap, norm=norm, interpolation="nearest"
    )
    ax.set_xticks(range(len(yi.columns)))
    ax.set_xticklabels(
        [d.strftime("%m-%d") for d in yi.columns], rotation=45, ha="right", fontsize=8.5
    )
    ax.set_yticks(range(len(yi.index)))
    ax.set_yticklabels(yi.index, fontsize=10)
    ax.set_xticks(np.arange(-0.5, len(yi.columns), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(yi.index), 1), minor=True)
    ax.grid(which="minor", color=GRID, linewidth=0.6)
    ax.tick_params(which="minor", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    if annot:
        thresh = vmax * 0.45
        for i in range(yi.shape[0]):
            for j in range(yi.shape[1]):
                v = yi.iat[i, j]
                if abs(v) >= thresh:
                    ax.text(
                        j, i, f"{v:.0f}", ha="center", va="center", fontsize=6.5,
                        color="white" if abs(v) >= vmax * 0.7 else INK,
                    )

    cbar = fig.colorbar(im, ax=ax, pad=0.015, fraction=0.025)
    cbar.set_label("当日主力净流入（亿元）", fontsize=10)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(labelsize=8.5, colors=MUTED, length=0)

    span = f"{yi.columns[0].date()} ~ {yi.columns[-1].date()}"
    net = float(yi.to_numpy().sum())
    ax.set_title(
        f"一级行业日度资金流热力图 · {len(yi.index)} 行业 × {len(yi.columns)} 交易日\n"
        f"区间 {span}｜全市场主力累计净{('流入' if net >= 0 else '流出')} {abs(net):,.1f} 亿元",
        fontsize=15, fontweight="bold", color=INK, pad=16, loc="left",
    )
    fig.text(
        0.125, 0.015,
        "红=主力净流入  绿=主力净流出｜按区间累计净额降序排列｜色阶按 90 分位稳健截断",
        fontsize=8.5, color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [1/3] {out_path.name}  ({yi.shape[0]}×{yi.shape[1]})")


def plot_cumulative_rank(matrix: pd.DataFrame, out_path: Path) -> pd.Series:
    """副图1：行业区间累计主力净流入排行（正红负绿）。"""
    total = (matrix.sum(axis=0) / 1e8).sort_values()
    colors = [RED if v >= 0 else GREEN for v in total]

    fig, ax = plt.subplots(figsize=(10, 9))
    ax.barh(range(len(total)), total.to_numpy(), color=colors, height=0.72)
    ax.set_yticks(range(len(total)))
    ax.set_yticklabels(total.index, fontsize=10)
    ax.axvline(0, color=INK, linewidth=0.9)
    ax.xaxis.grid(True, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)

    span = f"{matrix.index[0].date()} ~ {matrix.index[-1].date()}"
    span_days = len(matrix.index)
    for i, v in enumerate(total.to_numpy()):
        off = 6 if v >= 0 else -6
        ax.text(
            v + off, i, _fmt_yi(v * 1e8), va="center",
            ha="left" if v >= 0 else "right", fontsize=8, color=MUTED,
        )

    pos = int((total > 0).sum())
    inflow_yi = float(total[total > 0].sum())
    outflow_yi = float(total[total <= 0].sum())
    ax.set_title(
        f"一级行业区间累计主力净流入 · 近{span_days}个交易日\n{span}",
        fontsize=14, fontweight="bold", color=INK, pad=26, loc="left",
    )
    ax.text(
        0, 1.012,
        f"{pos}/{len(total)} 个行业净流入（合计 {inflow_yi:+,.0f} 亿）｜"
        f"{len(total)-pos} 个净流出（合计 {outflow_yi:+,.0f} 亿）",
        transform=ax.transAxes, fontsize=9, color=MUTED,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [2/3] {out_path.name}")
    return total, pos, inflow_yi, outflow_yi


def plot_daily_flow(
    daily: pd.Series, out_path: Path, title: str, sub: str = ""
) -> None:
    """每日主力净流入柱状图 + 区间累计折线（全市场图与各行业图共用同一套样式）。"""
    cum = daily.cumsum()
    cols = [RED if v >= 0 else GREEN for v in daily.to_numpy()]

    fig, ax = plt.subplots(figsize=(15, 5.5))
    ax.bar(range(len(daily)), daily.to_numpy(), color=cols, width=0.66)
    ax.axhline(0, color=INK, linewidth=0.9)
    ax.set_xticks(range(len(daily)))
    ax.set_xticklabels(
        [d.strftime("%m-%d") for d in daily.index], rotation=45, ha="right", fontsize=8.5
    )
    ax.yaxis.grid(True, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.set_ylabel("当日主力净流入（亿元）", fontsize=10)

    ax2 = ax.twinx()
    ax2.plot(range(len(cum)), cum.to_numpy(), color=INK, linewidth=1.8, zorder=5)
    ax2.plot(
        range(len(cum)), cum.to_numpy(), "o", color=INK, markersize=3.4, zorder=6
    )
    ax2.fill_between(range(len(cum)), 0, cum.to_numpy(), color=INK, alpha=0.06, zorder=1)
    ax2.set_ylabel("区间累计主力净额（亿元）", fontsize=10)
    ax2.tick_params(colors=MUTED, labelsize=8.5, length=0)
    for spine in ("top", "left", "right"):
        ax2.spines[spine].set_visible(False)
    ax2.set_ylim(min(0, cum.min() * 1.25), max(0, cum.max() * 1.25) or 1)

    net = float(cum.iloc[-1])
    # 标题走 fig.text：ax.set_title 的 pad 会把标题顶出画布，且无法和副标题稳定共存
    top = 0.86 if sub else 0.90
    fig.tight_layout(rect=(0, 0, 1, top))
    left = ax.get_position().x0
    if sub:
        fig.text(
            left, 0.955,
            f"{title} · 近{len(daily)}个交易日｜"
            f"主力累计净{('流入' if net >= 0 else '流出')} {abs(net):,.1f} 亿元",
            fontsize=14, fontweight="bold", color=INK, va="top", ha="left",
        )
        fig.text(left, 0.895, sub, fontsize=9, color=MUTED, va="top", ha="left")
    else:
        fig.text(
            left, 0.97,
            f"{title} · 近{len(daily)}个交易日｜"
            f"主力累计净{('流入' if net >= 0 else '流出')} {abs(net):,.1f} 亿元",
            fontsize=14, fontweight="bold", color=INK, va="top", ha="left",
        )
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_market_daily(matrix: pd.DataFrame, out_path: Path) -> None:
    """副图2：全市场每日主力净流入柱状图 + 累计曲线。"""
    daily = matrix.sum(axis=1) / 1e8  # 每日全市场 = 该交易日所有一级行业求和
    plot_daily_flow(daily, out_path, "全市场板块资金流")
    print(f"  [3/3] {out_path.name}")


def plot_per_sector(matrix: pd.DataFrame, outdir: Path) -> None:
    """每个一级行业出一张"日度柱状 + 累计折线"图，样式与全市场图一致。"""
    subdir = outdir / "各行业每日资金流"
    subdir.mkdir(parents=True, exist_ok=True)
    total = matrix.sum(axis=0) / 1e8
    order = total.sort_values(ascending=False).index  # 与热力图同序，从流入到流出

    # 文件名序号用累计净额排名，方便按序翻看
    rank = {name: i + 1 for i, name in enumerate(order)}
    for name in order:
        daily = matrix[name] / 1e8
        net = float(daily.sum())
        pos_days = int((daily > 0).sum())
        sub = (
            f"累计净额排名 {rank[name]}/{len(order)}　|　"
            f"{pos_days}/{len(daily)} 天净流入　|　"
            f"单日最大流入 {daily.max():+,.1f} 亿　单日最大流出 {daily.min():+,.1f} 亿"
        )
        path = subdir / f"{rank[name]:02d}-{name}.png"
        plot_daily_flow(daily, path, f"{name} · 资金流", sub=sub)
    print(f"  [4/4] 各行业每日资金流/  {len(order)} 张")


def main() -> int:
    parser = argparse.ArgumentParser(description="板块资金流可视化")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="行业板块资金流 CSV")
    parser.add_argument("--days", type=int, default=0, help="只画最近 N 个交易日（0=全部）")
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="输出目录")
    parser.add_argument("--annot", action="store_true", help="热力图显示数值标注")
    parser.add_argument(
        "--per-sector", action="store_true", help="额外为每个一级行业出一张日度资金流图"
    )
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"错误：找不到 {csv_path}\n请先运行：python tools/fetch_sector_fund_flow.py --days 30")
        return 1

    _setup_style()
    matrix, available, missing = load_matrix(csv_path, args.days or None)
    if not available:
        print(f"错误：CSV 中未找到任何申万一级行业列，实际列示例：{matrix.columns[:5].tolist()}")
        return 1
    if missing:
        print(f"  提示：{len(missing)} 个一级行业不在数据中：{', '.join(missing)}")

    level1 = matrix[available]
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"数据 {csv_path.name}：{len(level1.index)} 个交易日 × {len(level1.columns)} 个一级行业")

    plot_heatmap(level1, outdir / "01-行业日度热力图.png", annot=args.annot)
    totals, pos, inflow_yi, outflow_yi = plot_cumulative_rank(
        level1, outdir / "02-行业累计净流入.png"
    )
    plot_market_daily(level1, outdir / "03-全市场每日资金流.png")
    if args.per_sector:
        plot_per_sector(level1, outdir)

    top_in = totals.sort_values(ascending=False).head(5)
    top_out = totals.sort_values().head(5)
    print(
        f"\n{pos}/{len(totals)} 个行业区间净流入，合计 {inflow_yi:+,.1f} 亿；"
        f"其余合计 {outflow_yi:+,.1f} 亿"
    )
    print("\n=== 区间累计主力净流入 TOP5 ===")
    for name, v in top_in.items():
        print(f"  {name:<8} {_fmt_yi(v*1e8):>10} 亿")
    print("=== 区间累计主力净流出 TOP5 ===")
    for name, v in top_out.items():
        print(f"  {name:<8} {_fmt_yi(v*1e8):>10} 亿")
    print(f"\n已输出到 {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
