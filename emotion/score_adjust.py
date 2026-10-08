"""个股评分的市场环境调整（3.2 核心模型之外的扩展层）。

核心温度模型只描述"市场处在什么状态"。本模块把市场状态转成个股评分前的一道
环境权重，对应 README 里说的"接缝修正会成为股票分析项目里的环境因子"。

设计原则：
  * 只做乘数，不做加减分，避免把环境判断伪装成个股自身质量；
  * 多风格按权重做几何混合，避免同一只票被重复加成；
  * 总乘数被 clamp 在 [0.7, 1.3]，环境可以调整排序，但不能主导评分；
  * 每个调整都可以逐项解释，禁止黑箱。
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

from .config import load_env_weights


def _as_weight_map(styles: Mapping[str, float] | Iterable[str] | None) -> dict:
    if not styles:
        return {}
    if isinstance(styles, Mapping):
        return {str(k): max(0.0, min(1.0, float(v))) for k, v in styles.items()}
    return {str(k): 1.0 for k in styles}


def _seam_tilt(J: float, env: dict) -> float:
    """把接缝 J 映射为 [-tilt_cap, +tilt_cap] 的倾斜值，中点为 0。"""
    seam = env.get("seam_tilt") or {}
    up = float(seam.get("J_strong_conv", 30))
    down = float(seam.get("J_strong_div", -30))
    cap = float(seam.get("tilt_cap", 0.08))
    if J >= 0:
        ratio = min(J / up, 1.0) if up else 0.0
    else:
        ratio = -min(J / down, 1.0) if down else 0.0
    return cap * ratio


def _ice_repair_bonus(state: dict, env: dict) -> tuple[float, list[str]]:
    """冰点修复候选的加成，只在多个条件同时成立时给。"""
    cond = env.get("ice_repair_conditions") or {}
    if state.get("phase") != "冰点":
        return 1.0, []

    reasons, ok = [], True
    if float(state.get("S", 0.0)) > float(cond.get("max_temperature", 55)):
        ok = False
    if ok and float(state.get("J", 0.0)) < float(cond.get("J_gte", 10)):
        ok = False
        reasons.append("J未转正")
    if ok and cond.get("require_promotion_improving", True):
        if float(state.get("J_promotion", 0.0)) <= 0:
            ok = False
            reasons.append("晋级方向未改善")
    if ok and cond.get("require_leader_alive", True):
        if float(state.get("J_leader", 0.0)) < 0:
            ok = False
            reasons.append("龙头仍承压")

    if not ok:
        return 1.0, reasons
    return float(cond.get("bonus", 1.25)), ["满足冰点修复条件"]


def adjust_stock_score(
    base_score: float,
    styles: Mapping[str, float] | Sequence[str] | None,
    state: Mapping[str, object],
    env_config: dict | None = None,
) -> dict:
    """按当日市场状态调整个股基础评分。

    Args:
        base_score: 个股自身评分（0~100）。
        styles: 该股所属的风格标签，例如 ``{"leader": 1.0, "theme": 0.6}``，
            或简写 ``["leader", "theme"]``。
        state: ``EmotionEngine.get_market_state()`` 的返回值。
        env_config: 可选，覆盖 ``config/environment_weights.json``。

    Returns:
        含 ``adjusted_score`` / ``multiplier`` / ``breakdown`` / ``notes`` 的字典。
    """
    env = env_config or load_env_weights()
    clamp = env.get("clamp") or {}
    lo = float(clamp.get("multiplier_min", 0.7))
    hi = float(clamp.get("multiplier_max", 1.3))
    score_lo = float(clamp.get("score_min", 0.0))
    score_hi = float(clamp.get("score_max", 100.0))

    phase = str(state.get("phase") or "")
    table = (env.get("phase_multipliers") or {}).get(phase)
    if not table:
        return {
            "adjusted_score": round(float(base_score), 2),
            "multiplier": 1.0,
            "breakdown": {},
            "notes": [f"未知阶段「{phase}」，不调整"],
        }

    weights = _as_weight_map(styles)
    breakdown: dict[str, float] = {}
    log_multiplier = 0.0
    total_weight = sum(weights.values()) or 1.0

    for style, weight in weights.items():
        if weight <= 0:
            continue
        mult = float(table.get(style, 1.0))
        log_multiplier += (weight / total_weight) * math.log(mult)
        breakdown[style] = round(mult, 3)

    ice_bonus, ice_notes = _ice_repair_bonus(state, env)
    if ice_bonus != 1.0 and "ice_repair" in weights:
        w = weights["ice_repair"] / total_weight
        log_multiplier += w * math.log(ice_bonus)
        breakdown["ice_repair"] = round(float(table.get("ice_repair", 1.0)) * ice_bonus, 3)
    elif "ice_repair" not in weights:
        ice_notes = []

    multiplier = math.exp(log_multiplier)

    tilt = _seam_tilt(float(state.get("J", 0.0)), env)
    seam = env.get("seam_tilt") or {}
    pos = set(seam.get("positive_styles") or [])
    neg = set(seam.get("negative_styles") or [])
    if abs(tilt) > 1e-9:
        hits = [s for s in weights if s in (pos if tilt > 0 else neg)]
        if hits:
            multiplier *= 1.0 + tilt
            breakdown["接缝倾斜"] = round(1.0 + tilt, 3)

    raw = multiplier
    multiplier = max(lo, min(hi, multiplier))
    adjusted = max(score_lo, min(score_hi, float(base_score) * multiplier))

    notes = []
    label = state.get("j_label")
    if label:
        notes.append(f"接缝：{label}")
    notes.extend(ice_notes)
    if raw != multiplier:
        notes.append(f"乘数已限幅到 {multiplier:.2f}")

    return {
        "adjusted_score": round(adjusted, 2),
        "multiplier": round(multiplier, 3),
        "breakdown": breakdown,
        "notes": notes,
    }
