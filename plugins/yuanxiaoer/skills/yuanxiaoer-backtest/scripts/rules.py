"""圆小二规则的信号生成器。

每条规则标注回测状态，来自全市场 5,221 只 / 2025-04~2026-09 的验证。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 回测状态（次日开盘买入、扣成本、公平对照、市场中性化后）
VERDICT = {
    "recommendation": "effective",     # 5日+3.75% 中性超额+2.75pp CI[+0.07,+5.68]
    "boll_cross_up": "effective",      # 4日真实超额+0.49pp CI[+0.22,+0.76]
    "boards_2to5": "invalid",          # -0.56% 逐高度全负
    "nodemark": "invalid",             # -0.21% 相对基准-0.56pp
    "sell_signal": "unproven",         # 四个持有期CI全部含0
}


def boll_ready(close: pd.Series, n: int = 20, k: float = 2.0,
               flat_days: int = 40, slope_min: float = 0.005):
    """布林走平的"准备就绪"条件。返回 (mid, ready)。"""
    ma = close.rolling(n).mean()
    sd = close.rolling(n).std(ddof=0)
    mid, up, lo = ma, ma + k * sd, ma - k * sd
    width = (up - lo) / mid
    wma = width.rolling(flat_days).mean()
    wstd = width.rolling(flat_days).std(ddof=0)
    is_flat = width < wma * 1.15
    is_quiet = wstd < 0.06
    turned_up = (ma.diff(5) / ma.shift(5)) > slope_min
    return mid, (is_flat & is_quiet & turned_up)


def boll_cross_up(u, require_volume: bool = True) -> dict:
    """布林走平上穿中轨 + 放量（可选）。

    ✅ 有效：4日真实超额 +0.49pp，CI [+0.22,+0.76]。
    语料唯一写成机械规则的地方，tid 2nHJIdDk8pM（2025-12-12）。
    """
    sig = {}
    for code, g in u.frame.groupby("code"):
        g = g.reset_index(drop=True)
        c = g["close"]
        mid, ready = boll_ready(c)
        cross = (c > mid) & (c.shift(1) <= mid.shift(1))
        ok = cross & ready
        if require_volume:
            vma = g["volume"].rolling(20).mean()
            ok = ok & (g["volume"] > vma * 1.5)
        hit = ok.fillna(False).to_numpy()
        ds = g["date"].to_numpy()
        dates = [str(ds[k])[:10] for k in np.where(hit)[0]]
        if dates:
            sig[code] = dates
    return sig


def board_zone(u, lo: int = 2, hi: int = 5) -> dict:
    """连板高度区间。❌ 无效：可执行口径 -0.56%，逐高度全负。"""
    f = u.frame
    if "streak" not in f.columns:
        raise ValueError("call add_limit_up(u) first")
    sub = f[(f["streak"] >= lo) & (f["streak"] <= hi) & f["is_lu"]]
    sig = {}
    for code, g in sub.groupby("code"):
        sig[code] = [str(x)[:10] for x in g["date"]]
    return sig


def nodemark(u, min_streak: int = 3) -> dict:
    """节点标博弈：龙头断板日诞生的首板/二板。❌ 无效：-0.21%。

    语料 144 篇强调最多的概念，作为买点无优势。
    """
    f = u.frame
    if "streak" not in f.columns:
        raise ValueError("call add_limit_up(u) first")
    lead_break = set()
    for code, g in f.groupby("code"):
        arr = g["streak"].to_numpy()
        ds = g["date"].to_numpy()
        for k in range(1, len(arr)):
            if arr[k - 1] >= min_streak and arr[k] == 0:
                lead_break.add(str(ds[k])[:10])
    sub = f[(f["streak"].isin([1, 2])) & f["is_lu"]]
    sig = {}
    for code, g in sub.groupby("code"):
        dates = [str(x)[:10] for x in g["date"] if str(x)[:10] in lead_break]
        if dates:
            sig[code] = dates
    return sig


RULES = {
    "boll_cross_up": boll_cross_up,
    "boards_2to5": board_zone,
    "nodemark": nodemark,
}
