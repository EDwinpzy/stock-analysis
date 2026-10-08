"""展示层：温度等级标签与每日状态文本（对应 README 第 14、16 节）。

这些标签只影响显示，不回溯修改 S，也不参与评分。
"""

from __future__ import annotations

PHASE_ICON = {
    "修复": "🌱",
    "升温": "📈",
    "高潮": "🔥",
    "降温": "🍂",
    "退潮": "🌊",
    "冰点": "❄️",
}

REGIME_LABEL = {
    "Bull": "🐂 年线上牛市组",
    "Bear": "🐻 年线下熊市组",
}


def phase_display(phase: str) -> str:
    return f"{PHASE_ICON.get(phase, '')} {phase}".strip()


def regime_display(regime: str) -> str:
    return REGIME_LABEL.get(regime, regime)


def temperature_grade(S: float, phase: str) -> str:
    """按 README 第 14 节给出温度等级标签。

    冰点优先级最高：S<=55 且阶段已是冰点时，不再显示"退潮三级"。
    """
    if phase == "冰点":
        if S < 35:
            return "极限冰点"
        if S < 45:
            return "深度冰点"
        return "冰点"

    if phase == "高潮":
        if S >= 97:
            return "极限高潮"
        if S >= 90:
            return "强高潮"
        return "高潮"

    if phase == "升温":
        if S >= 80:
            return "主升三级"
        if S >= 70:
            return "主升二级"
        return "主升一级"

    if phase == "退潮":
        if S >= 60:
            return "一级退潮"
        if S >= 50:
            return "二级退潮"
        return "三级退潮"

    return phase


def render_state(state: dict) -> str:
    """渲染 README 第 16 节的每日推荐输出格式。"""
    def fmt(value, digits=1):
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:+.{digits}f}" if value > 0 else f"{value:.{digits}f}"
        return str(value)

    lines = [
        f"市场温度 S: {fmt(state.get('S'))}",
        f"Δ1: {fmt(state.get('delta1'))}",
        f"Δ2: {fmt(state.get('delta2'))}",
        f"六阶段: {state.get('phase', '—')}",
        f"牛熊环境: {state.get('regime', '—')}（{state.get('regime_label', '—')}）",
        f"接缝J: {fmt(state.get('J'))}（{state.get('j_label', '—')}）",
        f"赚钱反馈F: {fmt(state.get('F'))}",
        f"连板生态L: {fmt(state.get('L'))}",
        f"风险质量R: {fmt(state.get('R'))}",
        f"进攻扩散A: {fmt(state.get('A'))}",
        f"市场广度B: {fmt(state.get('B'))}",
        f"量能确认V: {fmt(state.get('V'))}",
        f"状态: {state.get('grade', '—')}｜{state.get('momentum') or '动能待定'}",
    ]
    return "\n".join(lines)
