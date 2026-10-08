"""市场温度 S、情绪速度 Δ1 与加速度 Δ2 的纯计算逻辑。

公式中的百分比字段统一使用小数值：55% 写作 0.55，-0.89% 写作 -0.0089。
成交量使用亿元，与原始校准样本的口径一致。
"""

from __future__ import annotations

from math import isfinite
from typing import Mapping


TEMPERATURE_INTERCEPT = 12.957328
TEMPERATURE_COEFFICIENTS = {
    "空间": 0.991500,
    "次高": 5.471872,
    "涨停": 0.096193,
    "跌停": -0.346943,
    "首板": 0.073257,
    "连板": 1.004360,
    "炸板率": -13.135493,
    "成交量": 0.000707,
    "红盘数": 0.001912,
    "昨连板": 71.351504,
    "昨涨停": 133.725254,
}


def _number(value: object, default: float = 0.0) -> float:
    """把 API/JSON 数值安全转换为有限浮点数。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if isfinite(number) else default


def calculate_temperature(inputs: Mapping[str, object]) -> float:
    """按 11 个校准参数计算并限制到 0～100 的市场温度。"""
    raw_score = calculate_raw_temperature(inputs)
    return max(0.0, min(100.0, raw_score))


def calculate_raw_temperature(inputs: Mapping[str, object]) -> float:
    """返回未做 0～100 截断的线性计算结果，便于审计公式。"""
    raw_score = TEMPERATURE_INTERCEPT
    for name, coefficient in TEMPERATURE_COEFFICIENTS.items():
        raw_score += coefficient * _number(inputs.get(name))
    return raw_score


def calculate_deltas(
    current: float,
    previous: float | None = None,
    previous_previous: float | None = None,
) -> tuple[float | None, float | None]:
    """返回 Δ1（速度）和 Δ2（加速度）。"""
    if previous is None:
        return None, None

    delta1 = current - previous
    if previous_previous is None:
        return delta1, None

    previous_delta1 = previous - previous_previous
    return delta1, delta1 - previous_delta1


def _momentum_label(delta1: float | None, delta2: float | None) -> str:
    if delta1 is None or delta2 is None:
        return "动能待定"
    if delta1 >= 5 and delta2 >= 5:
        return "上攻加速"
    if 0 < delta1 < 5 and delta2 >= 5:
        return "向上拐点"
    if delta1 > 0 and delta2 <= -5:
        return "上涨钝化"
    if delta1 <= -8 and delta2 <= -5:
        return "退潮加速"
    if delta1 < 0 and delta2 >= 5:
        return "下跌收敛"
    if delta1 < 0 and delta2 <= -5:
        return "转弱加速"
    return "动能平稳"


def classify_cycle(
    score: float,
    delta1: float | None = None,
    delta2: float | None = None,
) -> tuple[str, str]:
    """按优先级返回（主周期、动能标签）。"""
    score = _number(score)

    # 优先级必须固定，避免高潮/冰点与分歧/修复同时命中。
    if score >= 65 and delta1 is not None and delta1 < 0:
        phase = "⚠️ 高位分歧"
    elif score <= 50 and delta1 is not None and delta1 >= 8:
        phase = "🌱 冰点修复"
    elif score <= 30:
        phase = "🧊 冰点"
    elif score >= 80:
        phase = "🚀 高潮"
    elif score < 65 and delta1 is not None and delta1 <= -8:
        phase = "📉 退潮"
    elif score < 60 and delta1 is not None and delta1 >= 5:
        phase = "🔄 退潮修复"
    elif score > 50 and delta1 is not None and delta1 > 5:
        phase = "🔥 主升"
    else:
        phase = "➖ 混沌"

    return phase, _momentum_label(delta1, delta2)


def format_delta(value: float | None) -> str:
    """把 Δ1/Δ2 格式化为适合顶部卡片的带符号文本。"""
    if value is None:
        return "—"
    return f"{value:+.1f}"
