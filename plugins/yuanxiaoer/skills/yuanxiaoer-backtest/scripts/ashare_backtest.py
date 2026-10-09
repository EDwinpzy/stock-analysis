"""A股回测核心库：口径正确的价格加载、成本模型、信号与统计工具。

设计原则（来自圆小二项目五次回测修正）：
1. 买入价默认次日开盘——信号在收盘后确认，不能用当日收盘价。
2. 成本模型内置双边佣金、过户费、印花税，含最低佣金。
3. 对照组默认同批股票同期随机交易日，而非信号日或涨停日。
4. 统计默认给置信区间，不只给均值。

数据格式：<data_dir>/<交易所>_<代码>.json，每行一个 list，列为
["date","open","high","low","close","volume","amount","turn","pctChg"]
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---- 成本模型（2025-26 A股散户实际水平）----
COMMISSION = 0.00025      # 佣金 万2.5
MIN_COMMISSION = 5.0       # 最低 5 元
TRANSFER_FEE = 0.00001     # 过户费 十万分之一
STAMP_TAX = 0.0005         # 印花税 千分之五，仅卖出


def limit_pct(code: str) -> float:
    """按板块返回涨停幅度。"""
    c = str(code)
    if c.startswith(("30", "68")):
        return 20.0        # 创业板 / 科创板
    if c.startswith(("83", "87", "43", "92")):
        return 30.0        # 北交所
    return 10.0            # 主板


def limit_up_streak(is_lu) -> np.ndarray:
    """连续涨停计数，断板归零。"""
    out, c = [], 0
    for x in is_lu:
        c = c + 1 if x else 0
        out.append(c)
    return np.array(out)


@dataclass
class Universe:
    """按股票切片的行情容器，避免全市场逐行查找的二次复杂度。"""
    open: dict
    high: dict
    low: dict
    close: dict
    date: dict          # code -> list[str]
    index: dict         # code -> {date_str: i}
    frame: pd.DataFrame

    def n_bars(self) -> int:
        return len(self.frame)

    def n_codes(self) -> int:
        return len(self.close)

    def i(self, code: str, d: str) -> int | None:
        return self.index[code].get(str(d)[:10])

    def dates(self, code: str) -> list:
        return self.date[code]


def load_universe(data_dir: str, min_bars: int = 60) -> Universe:
    """加载 baostock 格式日线目录。"""
    frames = []
    for fn in os.listdir(data_dir):
        if not fn.endswith(".json"):
            continue
        code = fn[:-5].split("_", 1)[1]
        rows = json.load(open(os.path.join(data_dir, fn), encoding="utf-8"))
        if len(rows) < min_bars:
            continue
        d = pd.DataFrame(
            rows,
            columns=["date", "open", "high", "low", "close",
                     "volume", "amount", "turn", "pctChg"],
        )
        d["code"] = code
        frames.append(d[["code", "date", "open", "high", "low", "close", "volume"]])
    if not frames:
        raise ValueError(f"no usable bars in {data_dir}")
    a = pd.concat(frames, ignore_index=True)
    for c in ("open", "high", "low", "close", "volume"):
        a[c] = pd.to_numeric(a[c], errors="coerce")
    a = a.dropna(subset=["close", "open"]).sort_values(["code", "date"])
    a = a.reset_index(drop=True)

    o, h, lo, cl, dt, ix = {}, {}, {}, {}, {}, {}
    for code, g in a.groupby("code"):
        g = g.reset_index(drop=True)
        o[code] = g["open"].to_numpy()
        h[code] = g["high"].to_numpy()
        lo[code] = g["low"].to_numpy()
        cl[code] = g["close"].to_numpy()
        dt[code] = g["date"].to_numpy()
        ix[code] = {d: k for k, d in enumerate(dt[code])}
    return Universe(o, h, lo, cl, dt, ix, a)


def add_limit_up(u: Universe, tol: float = 0.3) -> pd.DataFrame:
    """给 frame 加涨停标记与连板计数。"""
    f = u.frame.copy()
    f["lim"] = f["code"].map(limit_pct)
    f["prev_close"] = f.groupby("code")["close"].shift(1)
    f["chg"] = (f["close"] / f["prev_close"] - 1) * 100
    f["is_lu"] = f["chg"] >= (f["lim"] - tol)
    f["streak"] = f.groupby("code")["is_lu"].transform(
        lambda s: pd.Series(limit_up_streak(s.to_numpy()), index=s.index))
    u.frame = f
    return f


def net_return(u: Universe, code: str, d: str, hold: int,
               entry: str = "next", capital: float = 100000.0) -> float | None:
    """扣除双边成本后的持有期净收益（%）。

    entry="next" 用次日开盘买入（默认，可执行口径）。
    entry="close" 用信号日收盘买入，仅用于复现历史报告，不应用于新结论。
    """
    i = u.i(code, d)
    if i is None:
        return None
    ei = i if entry == "close" else i + 1
    si = ei + hold
    if si >= len(u.close[code]):
        return None
    p0 = float(u.close[code][ei] if entry == "close" else u.open[code][ei])
    p1 = float(u.close[code][si])
    if p0 <= 0:
        return None
    buy_cost = max(capital * COMMISSION, MIN_COMMISSION) + capital * TRANSFER_FEE
    sell_value = capital * p1 / p0
    sell_cost = (max(sell_value * COMMISSION, MIN_COMMISSION)
                 + sell_value * TRANSFER_FEE
                 + sell_value * STAMP_TAX)
    return ((sell_value - sell_cost) - (capital + buy_cost)) / (capital + buy_cost) * 100


def market_return(u: Universe, max_hold: int) -> dict:
    """按日预计算等权全市场的 h 日累计收益，用于市场中性化。"""
    f = u.frame
    f = f.assign(r1=f.groupby("code")["close"].pct_change())
    daily = f.groupby("date")["r1"].mean().dropna()
    ds = daily.index.to_numpy()
    dv = daily.to_numpy()
    out = {}
    for h in range(1, max_hold + 1):
        cum = {}
        for k in range(len(ds) - h):
            cum[str(ds[k])[:10]] = (np.prod(1 + dv[k + 1:k + h + 1]) - 1) * 100
        out[h] = cum
    return out


def random_day_control(u: Universe, codes: list, lo: str, hi: str,
                       hold: int, seed: int = 7, per_code: int = 200,
                       entry: str = "next"):
    """对照：同批股票在同期内的随机交易日。

    这是"不做这个选择"的公平基准。信号日与涨停日都是被污染的基准。
    """
    rng = np.random.default_rng(seed)
    vals = []
    for code in codes:
        ds = u.dates(code)
        n = len(ds)
        if n < hold + 6:
            continue
        picks = rng.integers(6, n - hold - 1, size=per_code)
        for i in picks:
            d = str(ds[i])[:10]
            if d < lo or d > hi:
                continue
            x = net_return(u, code, d, hold, entry)
            if x is not None:
                vals.append(x)
    return np.array(vals)


def placebo_neighbourhood(u: Universe, code: str, d: str, hold: int,
                          span: int = 30, repeats: int = 3,
                          seed: int = 11, entry: str = "next"):
    """安慰剂：同股、信号日 ±span 交易日内随机买入。"""
    rng = np.random.default_rng(seed)
    i = u.i(code, d)
    n = len(u.close[code])
    if i is None or n < hold + 6:
        return np.array([])
    lo, hi = max(0, i - span), min(n - 1, i + span)
    vals = []
    for _ in range(repeats):
        j = int(rng.integers(lo, hi + 1))
        if j == i:
            continue
        x = net_return(u, code, str(u.dates(code)[j])[:10], hold, entry)
        if x is not None:
            vals.append(x)
    return np.array(vals)


def bootstrap_ci(treatment, control, iters: int = 4000, seed: int = 23):
    """两侧都重采样到相同数量的均值差置信区间。

    注意：必须用较小一侧的长度重采样两侧，否则控制组样本多时
    置信区间会被压成一条线（这是实测中出现过的一个 bug）。
    """
    t = np.asarray([v for v in treatment if v is not None])
    c = np.asarray([v for v in control if v is not None])
    if len(t) == 0 or len(c) == 0:
        return {"edge": None, "ci": None, "significant": False,
                "n_t": len(t), "n_c": len(c)}
    rng = np.random.default_rng(seed)
    n = len(t)
    bt = rng.choice(t, (iters, n)).mean(axis=1)
    bc = rng.choice(c, (iters, n)).mean(axis=1)
    lo, hi = np.percentile(bt - bc, [2.5, 97.5])
    edge = t.mean() - c.mean()
    return {"edge": float(edge), "ci": [float(lo), float(hi)],
            "significant": bool(lo > 0 or hi < 0),
            "n_t": int(n), "n_c": int(len(c))}


def permutation_test(u: Universe, signals: dict, hold: int,
                     span: int = 30, iters: int = 4000, seed: int = 11,
                     entry: str = "next"):
    """股票内随机置换检验：打乱每只股票的信号日期，构造零分布。"""
    rng = np.random.default_rng(seed)
    treat = []
    null = []
    for code, ds in signals.items():
        n = len(u.close[code])
        if n < hold + 6:
            continue
        for d in ds:
            x = net_return(u, code, d, hold, entry)
            if x is not None:
                treat.append(x)
            for _ in range(3):
                j = int(rng.integers(0, n - hold - 2))
                y = net_return(u, code, str(u.dates(code)[j])[:10], hold, entry)
                if y is not None:
                    null.append(y)
    t = np.array(treat)
    nl = np.array(null)
    if len(t) == 0 or len(nl) == 0:
        return None
    bs = rng.choice(t, (iters, len(t))).mean(axis=1) - rng.choice(nl, (iters, len(t))).mean(axis=1)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"treat_mean": float(t.mean()), "null_mean": float(nl.mean()),
            "edge": float(t.mean() - nl.mean()),
            "ci": [float(lo), float(hi)],
            "significant": bool(lo > 0 or hi < 0),
            "n_t": len(t), "n_null": len(nl)}


def describe(name: str, vals, control=None) -> dict:
    v = np.asarray([x for x in vals if x is not None])
    if len(v) == 0:
        return {"name": name, "n": 0}
    out = {"name": name, "n": int(len(v)), "mean": float(v.mean()),
           "median": float(np.median(v)), "win": float((v > 0).mean() * 100)}
    if control is not None and len(control):
        out["control"] = float(np.mean(control))
        out["edge_vs_control"] = out["mean"] - out["control"]
    return out
