"""规则回测驱动：双口径 + 公平对照 + 市场中性化 + 置信区间。

用法:
    python backtest_rule.py <行情目录> <规则名> [持有天数]
    规则名: boll_cross_up | boards_2to5 | nodemark

例:
    python backtest_rule.py D:/data/market_bs boll_cross_up 4
"""
import sys

import numpy as np

import ashare_backtest as ab
import rules as R


def main(data_dir: str, rule_name: str, hold: int = 3) -> None:
    if rule_name not in R.RULES:
        print(f"unknown rule: {rule_name}")
        print(f"available: {list(R.RULES)}")
        raise SystemExit(1)

    print("loading universe ...")
    u = ab.load_universe(data_dir)
    ab.add_limit_up(u)
    print(f"codes={u.n_codes()}  bars={u.n_bars()}")

    sig_fn = R.RULES[rule_name]
    print(f"generating signals: {rule_name}  (verdict: {R.VERDICT[rule_name]})")
    sig = sig_fn(u)
    n_sig = sum(len(v) for v in sig.values())
    codes = list(sig)
    if n_sig == 0:
        print("no signals")
        return
    print(f"signals: {n_sig} across {len(codes)} codes")

    dates = [u.dates(c) for c in codes if len(u.dates(c))]
    lo = min(min(sig[c]) for c in sig if sig[c])
    hi = max(max(sig[c]) for c in sig if sig[c])
    print(f"signal period: {lo} -> {hi}")

    # the reporting loop iterates 1/3/5/10 days, so the market series must
    # cover every horizon we print, not just the headline hold.
    mkt = ab.market_return(u, max(10, hold))

    print()
    print("=== 规则信号 vs 同批股票同期随机日（次日开盘，扣成本）===")
    print(f"{'持有':>4} {'n':>7} {'收益':>8} {'胜率':>7} {'对照':>8} {'超额':>8} {'95% CI':>20} {'判定':>8}")
    for h in sorted({1, 3, 5, 10, hold}):
        treat = []
        exc_mkt = []
        for code, ds in sig.items():
            for d in ds:
                x = ab.net_return(u, code, d, h, "next")
                if x is None:
                    continue
                treat.append(x)
                m = mkt[h].get(d)
                if m is not None:
                    exc_mkt.append(x - m)
        if not treat:
            continue
        ctrl = ab.random_day_control(u, codes, lo, hi, h, per_code=100)
        t = np.array(treat)
        c = np.array(ctrl)
        edge = t.mean() - c.mean()
        nb = 4000
        rng = np.random.default_rng(23)
        bt = rng.choice(t, (nb, len(t))).mean(axis=1)
        bc = rng.choice(c, (nb, len(t))).mean(axis=1) if len(c) else np.zeros(nb)
        ci = np.percentile(bt - bc, [2.5, 97.5])
        sig_ok = (ci[0] > 0 or ci[1] < 0)
        mkt_edge = np.mean(exc_mkt) if exc_mkt else float("nan")
        print(f"{h:>4}d {len(t):>7} {t.mean():>+7.2f}% {(t > 0).mean() * 100:>6.1f}% "
              f"{c.mean() if len(c) else float('nan'):>+7.2f}% {edge:>+7.2f}pp "
              f"[{ci[0]:>+6.2f},{ci[1]:>+6.2f}] {'显著' if sig_ok else '不显著':>8}"
              f"   (中性超额 {mkt_edge:+.2f}pp)")

    print()
    print("=== 安慰剂 + 置换检验（形态特异性）===")
    res = ab.permutation_test(u, sig, hold)
    if res:
        print(f"  规则买入   {res['treat_mean']:+.2f}%  (n={res['n_t']})")
        print(f"  股票内零分布 {res['null_mean']:+.2f}%  (n={res['n_null']})")
        print(f"  真实超额   {res['edge']:+.2f}pp  95%CI [{res['ci'][0]:+.2f}, {res['ci'][1]:+.2f}]  "
              f"{'显著' if res['significant'] else '不显著'}")
        print("  提示：若安慰剂与规则收益接近，说明效应主要是 beta 而非形态。")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 3)
