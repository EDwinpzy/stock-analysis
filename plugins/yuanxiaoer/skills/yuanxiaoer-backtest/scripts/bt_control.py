"""对照基准检验：先确认你的基准没有系统性偏差，再解释任何回测结果。

如果"随便哪天买入"的基准本身就是 0，那么用信号日当对照组的回测
只是在测量市场漂移，而不是任何规则的贡献。

用法:
    python bt_control.py <行情目录>
    例: python bt_control.py D:/data/market_bs
"""
import sys

import numpy as np

import ashare_backtest as ab


def main(data_dir: str, hold: int = 3) -> None:
    print("loading universe ...")
    u = ab.load_universe(data_dir)
    print(f"codes={u.n_codes()}  bars={u.n_bars()}")

    rng = np.random.default_rng(7)
    codes = list(u.close.keys())
    dates = [u.dates(c) for c in codes]
    lo = min(d[0] for d in dates if len(d))
    hi = max(d[-1] for d in dates if len(d))
    print(f"period: {str(lo)[:10]} -> {str(hi)[:10]}")

    print()
    print("=== CONTROL 1: 随机交易日（同批股票）===")
    for entry in ("close", "next"):
        vals = []
        for code in codes:
            n = len(u.close[code])
            if n < hold + 6:
                continue
            for i in rng.integers(0, n - hold - 1, size=40):
                x = ab.net_return(u, code, str(u.dates(code)[int(i)])[:10], hold, entry)
                if x is not None:
                    vals.append(x)
        v = np.array(vals)
        print(f"  entry={entry:5s} n={len(v):7d} mean={v.mean():+6.2f}% "
              f"median={np.median(v):+6.2f}% win={(v > 0).mean() * 100:5.1f}%")

    print()
    print("=== CONTROL 2: 非涨停日（全市场 10% 抽样）===")
    ab.add_limit_up(u)
    f = u.frame
    for entry in ("close", "next"):
        vals = []
        for code, g in f.groupby("code"):
            g = g.reset_index(drop=True)
            m = (~g["is_lu"]).to_numpy()
            idxs = np.where(m)[0]
            idxs = idxs[rng.random(len(idxs)) < 0.10]
            ds = g["date"].to_numpy()
            for i in idxs:
                x = ab.net_return(u, code, str(ds[i])[:10], hold, entry)
                if x is not None:
                    vals.append(x)
        v = np.array(vals)
        print(f"  entry={entry:5s} n={len(v):7d} mean={v.mean():+6.2f}% "
              f"median={np.median(v):+6.2f}% win={(v > 0).mean() * 100:5.1f}%")

    print()
    print("=== CONTROL 3: 涨停日（常被误用为对照，实为最差入场点）===")
    for entry in ("close", "next"):
        vals = []
        sub = f[f["is_lu"]]
        for code, g in sub.groupby("code"):
            ds = g["date"].to_numpy()
            for d in ds:
                x = ab.net_return(u, code, str(d)[:10], hold, entry)
                if x is not None:
                    vals.append(x)
        v = np.array(vals)
        print(f"  entry={entry:5s} n={len(v):7d} mean={v.mean():+6.2f}% "
              f"median={np.median(v):+6.2f}% win={(v > 0).mean() * 100:5.1f}%")

    print()
    print("=== CONTROL 4: 等权全市场组合（市场中性化的分母）===")
    # per-stock return FIRST, then average by date. Reversing this order
    # computes pct_change on the cross-sectional mean price, which is not an
    # index and inflates the number by orders of magnitude.
    f2 = f.copy()
    f2["r1"] = f2.groupby("code")["close"].pct_change() * 100
    daily = f2.groupby("date")["r1"].mean().dropna()
    print(f"  n={len(daily)}  daily mean={daily.mean():+.4f}%  "
          f"{hold}d cumulative~{daily.mean() * hold:+.2f}%")

    print()
    print("解读：若随机日基准接近 0 而某规则显著为正，效应才可信。")
    print("     若涨停日基准显著为负（通常如此），拿它当对照会把所有规则量成负的。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3)
