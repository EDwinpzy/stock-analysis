"""A股超短情绪温度模型 3.2 — 模型本体（公式与参考实现逐行一致）。

来源：用户提供的「A股超短情绪温度模型3.2_完整包」中的 reference_impl.py
（版本号 A-SHORT-SENTIMENT-3.2）。本文件只做搬运，不改动任何公式、权重或阈值；
数据面板的构建见 market_temperature_v32.py。

输入百分比口径：
  bomb_rate / p12 / p23 / p3p 使用 0~1 小数；
  yday_*_ret 使用百分点（4.53 表示 +4.53%）。
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional, Dict, Any
import numpy as np
import pandas as pd

EPS = 1e-12

def clip(x, lo, hi):
    return max(lo, min(hi, x))

def G(ret_pct: float) -> float:
    """昨日反馈非线性映射；输入单位：百分点，例如+4.53填4.53。"""
    return 50.0 + 50.0 * math.tanh(ret_pct / 3.0)

def empirical_percentile(history: pd.Series, x: float) -> float:
    h = pd.to_numeric(history, errors="coerce").dropna()
    if len(h) == 0 or pd.isna(x):
        return 50.0
    return 100.0 * float((h <= x).sum()) / float(len(h))

def regime(sh_close: float, sh_ma250: float) -> str:
    return "Bull" if sh_close >= sh_ma250 else "Bear"

def same_regime_percentile(
    hist_df: pd.DataFrame,
    col: str,
    x: float,
    reg: str,
    same_window: int = 250,
    all_window: int = 250,
    min_same: int = 60,
) -> float:
    if len(hist_df) == 0:
        return 50.0

    same = hist_df.loc[hist_df["regime"] == reg, col].tail(same_window)
    allh = hist_df[col].tail(all_window)

    p_all = empirical_percentile(allh, x)
    if len(same.dropna()) >= min_same:
        return empirical_percentile(same, x)

    n = len(same.dropna())
    lam = clip(n / float(min_same), 0.0, 1.0)
    p_same = empirical_percentile(same, x) if n > 0 else p_all
    return lam * p_same + (1.0 - lam) * p_all

def leader_component(cur: pd.Series, prev: Optional[pd.Series],
                     p3p_pct_cur: float, p3p_pct_prev: float) -> float:
    """
    完整模式优先使用：
    prev_leader_open_ret / prev_leader_close_ret / prev_leader_advance_ratio
    若缺失，退化为space变化 + 高位晋级方向。
    """
    needed = ["prev_leader_open_ret", "prev_leader_close_ret", "prev_leader_advance_ratio"]
    if all(k in cur.index and pd.notna(cur[k]) for k in needed):
        open_score = clip(20.0 * float(cur["prev_leader_open_ret"]), -100.0, 100.0)
        close_score = clip(15.0 * float(cur["prev_leader_close_ret"]), -100.0, 100.0)
        adv_score = clip(200.0 * float(cur["prev_leader_advance_ratio"]) - 100.0, -100.0, 100.0)
        return clip(0.25*open_score + 0.45*close_score + 0.30*adv_score, -100.0, 100.0)

    if prev is None:
        return 0.0
    space_delta = clip(float(cur["space"]) - float(prev["space"]), -1.0, 1.0)
    return clip(50.0*space_delta + 0.5*(p3p_pct_cur - p3p_pct_prev), -100.0, 100.0)

def repair_confirmed(prev_phase: str, F, L, R, A, B, prev_scores: Dict[str, float]) -> bool:
    if prev_phase not in ("冰点", "退潮"):
        return False
    dF = F - prev_scores.get("F", F)
    dL = L - prev_scores.get("L", L)
    dR = R - prev_scores.get("R", R)
    dA = A - prev_scores.get("A", A)
    M = 0.35*dF + 0.30*dL + 0.20*dR + 0.15*dA
    positives = sum(v > 0 for v in (dF, dL, dR, dA))
    return (M >= 5.0 and positives >= 3 and F >= 50.0 and B >= 20.0)

def phase_from_state(S, d1, M, F, L, R, A, B, J, prev_phase, repair_ok):
    # 1 修复
    if repair_ok:
        return "修复"
    # 2 高潮
    if S >= 82 and F >= 85 and A >= 65 and R >= 65 and J > -30:
        return "高潮"
    # 3 降温
    if prev_phase == "高潮" and (M < 0 or J <= -10 or d1 < 0):
        return "降温"
    # 4 冰点
    if S <= 55 and (F < 55 or B < 25 or R < 50):
        return "冰点"
    # 5 退潮
    if (prev_phase == "降温" and d1 < 0) or (S < 70 and M <= -5 and (F < 60 or R < 55)):
        return "退潮"
    # 6 升温
    if S >= 60 and M >= 3 and F >= 60 and L >= 50:
        return "升温"
    # 7 保持/初始化
    if prev_phase:
        return prev_phase
    if S <= 55:
        return "冰点"
    if S < 70:
        return "修复"
    if S < 82:
        return "升温"
    return "高潮"

def j_label(J):
    if J >= 30: return "强分歧→一致"
    if J >= 10: return "弱分歧→一致"
    if J > -10: return "无明显接缝"
    if J > -30: return "一致→分歧"
    return "强一致→分歧"

def momentum_label(d1, d2):
    if pd.isna(d1) or pd.isna(d2):
        return ""
    if d1 >= 5 and d2 >= 5: return "上攻加速"
    if 0 < d1 < 5 and d2 >= 5: return "向上拐点"
    if d1 > 0 and d2 <= -5: return "上涨钝化"
    if d1 <= -8 and d2 <= -5: return "退潮加速"
    if d1 < 0 and d2 >= 5: return "下跌收敛/退潮衰竭"
    if d1 < 0 and d2 <= -5: return "转弱加速"
    return "动能平稳"

def compute_model(df: pd.DataFrame) -> pd.DataFrame:
    """
    输入必须按交易日逐行，函数会自动排序。
    所有百分比列：
      bomb_rate / p12 / p23 / p3p 使用0~1
      yday_*_ret 使用百分点，例如4.53表示+4.53%
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    df["regime"] = [regime(c, m) for c, m in zip(df["sh_close"], df["sh_ma250"])]
    df["chain_ratio"] = df["consecutive"] / df["limit_up"].clip(lower=1)
    df["seal_rate"] = 1.0 - df["bomb_rate"]
    df["turnover_ma20"] = df["turnover"].rolling(20, min_periods=5).mean()
    df["turnover_ratio"] = df["turnover"] / df["turnover_ma20"]

    rows = []
    prev_phase = ""
    prev_scores = {}
    prev_S = np.nan
    prev_d1 = np.nan

    for i, cur in df.iterrows():
        hist = df.iloc[:i].copy()
        reg = cur["regime"]

        def P(col, x=None):
            val = float(cur[col] if x is None else x)
            return same_regime_percentile(hist, col, val, reg)

        # 基础因子
        F = 0.60*G(float(cur["yday_lianban_ret"])) + 0.40*G(float(cur["yday_limitup_ret"]))
        p_consecutive = P("consecutive")
        p_space = P("space")
        p_next_space = P("next_space")
        p_chain = P("chain_ratio")
        L = 0.35*p_consecutive + 0.25*p_space + 0.20*p_next_space + 0.20*p_chain

        D = 100.0 * math.exp(-float(cur["limit_down"]) / 18.0)
        p_seal = P("seal_rate")
        R = 0.55*D + 0.45*p_seal

        p_lu = P("limit_up")
        p_fb = P("first_board")
        A = 0.65*p_lu + 0.35*p_fb

        B = 100.0 * float(cur["advance_count"]) / max(float(cur["tradable_count"]), 1.0)

        p_vr = P("turnover_ratio")
        V = clip(50.0 + ((p_vr-50.0)*(B-50.0))/50.0, 0.0, 100.0)

        Q = 0.34*F + 0.24*L + 0.18*R + 0.15*A + 0.06*B + 0.03*V

        # 晋级方向百分位
        p12_pct = P("p12")
        p23_pct = P("p23")
        p3p_pct = P("p3p")

        if i > 0:
            prev = df.iloc[i-1]
            prev_hist = df.iloc[:i-1].copy()
            prev_reg = prev["regime"]
            def PrevP(col):
                return same_regime_percentile(prev_hist, col, float(prev[col]), prev_reg)
            p12_prev = PrevP("p12")
            p23_prev = PrevP("p23")
            p3p_prev = PrevP("p3p")
            seal_prev = PrevP("seal_rate")
        else:
            prev = None
            p12_prev = p23_prev = p3p_prev = seal_prev = 50.0

        D12 = p12_pct - p12_prev
        D23 = p23_pct - p23_prev
        D3p = p3p_pct - p3p_prev
        J_promotion = clip(0.45*D12 + 0.35*D23 + 0.20*D3p, -100.0, 100.0)
        J_follower = clip(p_seal - seal_prev, -100.0, 100.0)
        J_leader = leader_component(cur, prev, p3p_pct, p3p_prev)
        J = clip(0.35*J_leader + 0.25*J_follower + 0.40*J_promotion, -100.0, 100.0)
        C_J = 1.5 * math.tanh(J / 35.0)

        # 修复确认与结构动量
        dF = F - prev_scores.get("F", F)
        dL = L - prev_scores.get("L", L)
        dR = R - prev_scores.get("R", R)
        dA = A - prev_scores.get("A", A)
        M = 0.35*dF + 0.30*dL + 0.20*dR + 0.15*dA
        repair_ok = repair_confirmed(prev_phase, F, L, R, A, B, prev_scores)

        # 非线性修正
        C_hot = 1.5 if (Q >= 75 and F >= 90 and R >= 80 and A >= 75) else 0.0
        P_breadth = 4.0 * clip((25.0 - B) / 15.0, 0.0, 1.0)
        P_down = 3.0 * clip((float(cur["limit_down"]) - 8.0) / 18.0, 0.0, 1.0)
        bomb_pct = 100.0 * float(cur["bomb_rate"])
        P_bomb = 3.0 * clip((bomb_pct - 45.0) / 20.0, 0.0, 1.0)
        P_cool = 1.5 if (prev_phase == "高潮" and J <= -30) else 0.0
        P_inertia = 0.0
        if prev_phase == "退潮" and Q < 50:
            P_inertia = 2.0
        elif prev_phase == "冰点" and not repair_ok:
            P_inertia = 2.0

        S = clip(
            18.0 + 0.87*Q + C_hot + C_J
            - P_breadth - P_down - P_bomb - P_cool - P_inertia,
            0.0, 100.0
        )

        d1 = np.nan if pd.isna(prev_S) else S - prev_S
        d2 = np.nan if pd.isna(prev_d1) or pd.isna(d1) else d1 - prev_d1

        phase = phase_from_state(S, d1 if not pd.isna(d1) else 0.0, M, F, L, R, A, B, J, prev_phase, repair_ok)

        rows.append({
            "date": cur["date"],
            "regime": reg,
            "F": F, "L": L, "R": R, "A": A, "B": B, "V": V, "Q": Q,
            "J_leader": J_leader, "J_follower": J_follower, "J_promotion": J_promotion,
            "J": J, "J_label": j_label(J),
            "M": M, "repair_confirmed": repair_ok,
            "S": S, "delta1": d1, "delta2": d2,
            "phase": phase, "momentum": momentum_label(d1, d2),
            "C_hot": C_hot, "C_J": C_J,
            "P_breadth": P_breadth, "P_down": P_down, "P_bomb": P_bomb,
            "P_cool": P_cool, "P_inertia": P_inertia,
        })

        prev_phase = phase
        prev_scores = {"F": F, "L": L, "R": R, "A": A}
        prev_S = S
        prev_d1 = d1

    return pd.DataFrame(rows)

if __name__ == "__main__":
    # 示例：
    # df = pd.read_csv("sample_input.csv")
    # out = compute_model(df)
    # out.to_csv("model_output.csv", index=False, encoding="utf-8-sig")
    pass
