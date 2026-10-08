"""EmotionEngine —— 情绪引擎门面。

对外的五个方法就是当初约定好的接口：

    calculate_temperature()   当日市场温度 S
    calculate_J()             接缝强度 J 及其三个分量
    detect_cycle()            六阶段 + 动能状态
    get_market_state()        当日完整状态快照
    adjust_stock_score()      用市场状态调整个股评分

引擎是无状态的批处理器：喂进一段按交易日排列的历史面板，它会算出整条温度序列；
之后任意一天的状态都可以取出来用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .config import DEFAULT_DATA_DIR, load_config, load_env_weights, model_version
from .core import compute_model
from .display import phase_display, regime_display, render_state, temperature_grade
from .score_adjust import adjust_stock_score as _adjust_stock_score

REQUIRED_COLUMNS = [
    "date", "sh_close", "sh_ma250", "tradable_count", "advance_count", "turnover",
    "limit_up", "limit_down", "first_board", "consecutive", "space", "next_space",
    "bomb_rate", "yday_limitup_ret", "yday_lianban_ret", "p12", "p23", "p3p",
]

OPTIONAL_COLUMNS = [
    "prev_leader_open_ret", "prev_leader_close_ret", "prev_leader_advance_ratio",
]


def load_panel(path: str | Path) -> pd.DataFrame:
    """读取历史面板 CSV，并校验模型需要的字段。"""
    frame = pd.read_csv(Path(path), dtype={"date": str})
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"面板缺少必需字段: {', '.join(missing)}")
    frame = frame[REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in frame.columns]]
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").reset_index(drop=True)


class EmotionEngine:
    """A股超短情绪温度模型 3.2 的调用入口。"""

    def __init__(
        self,
        history: pd.DataFrame | None = None,
        config_path: str | Path | None = None,
        env_weights: dict | None = None,
    ) -> None:
        self.config = load_config(config_path)
        self.version = model_version(config_path)
        self._env_weights = env_weights
        self._output: pd.DataFrame | None = None
        self._history: pd.DataFrame | None = None
        if history is not None:
            self.load_history(history)

    # ---------- 数据装载 ----------

    def load_history(self, history: pd.DataFrame) -> "EmotionEngine":
        missing = [c for c in REQUIRED_COLUMNS if c not in history.columns]
        if missing:
            raise ValueError(f"历史面板缺少必需字段: {', '.join(missing)}")
        frame = history.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        self._history = frame.sort_values("date").reset_index(drop=True)
        self._output = None  # 使缓存失效
        return self

    def load_csv(self, path: str | Path) -> "EmotionEngine":
        return self.load_history(load_panel(path))

    def load_sample(self) -> "EmotionEngine":
        """载入项目自带的真实历史面板（data/panel_history.csv）。"""
        return self.load_csv(DEFAULT_DATA_DIR / "panel_history.csv")

    # ---------- 计算 ----------

    @property
    def history(self) -> pd.DataFrame:
        if self._history is None:
            raise RuntimeError("尚未载入历史面板，请先调用 load_history() / load_csv()")
        return self._history

    def compute(self, rebuild: bool = False) -> pd.DataFrame:
        """跑完整条序列；结果会缓存，重复调用不重算。"""
        if self._output is None or rebuild:
            self._output = compute_model(self.history)
        return self._output

    def _row(self, day: str | None) -> pd.Series:
        output = self.compute()
        if day is None:
            return output.iloc[-1]
        stamp = pd.Timestamp(day)
        hit = output.loc[output["date"] == stamp]
        if hit.empty:
            raise KeyError(f"面板中没有 {day} 这一天（可用范围 {output['date'].iloc[0].date()} ~ {output['date'].iloc[-1].date()}）")
        return hit.iloc[-1]

    # ---------- 约定的五个接口 ----------

    def calculate_temperature(self, day: str | None = None) -> float:
        """当日市场温度 S。"""
        return round(float(self._row(day)["S"]), 2)

    def calculate_J(self, day: str | None = None) -> dict:
        """接缝强度 J：龙头承压 35% + 跟风稳定 25% + 晋级方向 40%。"""
        row = self._row(day)
        return {
            "value": round(float(row["J"]), 2),
            "label": str(row["J_label"]),
            "leader": round(float(row["J_leader"]), 2),
            "follower": round(float(row["J_follower"]), 2),
            "promotion": round(float(row["J_promotion"]), 2),
            "temperature_adjust": round(float(row["C_J"]), 3),
        }

    def detect_cycle(self, day: str | None = None) -> dict:
        """六阶段与动能状态。"""
        row = self._row(day)
        phase = str(row["phase"])
        momentum = str(row["momentum"]) if row["momentum"] else ""
        return {
            "phase": phase,
            "display": phase_display(phase),
            "momentum": momentum,
            "grade": temperature_grade(float(row["S"]), phase),
            "repair_confirmed": bool(row["repair_confirmed"]),
            "M": round(float(row["M"]), 2),
        }

    def get_market_state(self, day: str | None = None) -> dict:
        """当日完整状态快照（含全部因子、修正项与展示标签）。"""
        row = self._row(day)
        cycle = self.detect_cycle(day)
        seam = self.calculate_J(day)

        def num(key, digits=2):
            value = row[key]
            return None if pd.isna(value) else round(float(value), digits)

        return {
            "date": str(row["date"])[:10],
            "model": self.version,
            "S": round(float(row["S"]), 2),
            "delta1": num("delta1"),
            "delta2": num("delta2"),
            "phase": cycle["phase"],
            "phase_display": cycle["display"],
            "grade": cycle["grade"],
            "momentum": cycle["momentum"],
            "repair_confirmed": cycle["repair_confirmed"],
            "regime": str(row["regime"]),
            "regime_label": regime_display(str(row["regime"])),
            "J": seam["value"],
            "j_label": seam["label"],
            "J_leader": seam["leader"],
            "J_follower": seam["follower"],
            "J_promotion": seam["promotion"],
            "F": num("F", 1),
            "L": num("L", 1),
            "R": num("R", 1),
            "A": num("A", 1),
            "B": num("B", 1),
            "V": num("V", 1),
            "Q": num("Q", 1),
            "M": num("M"),
            "corrections": {
                "C_hot": num("C_hot"),
                "C_J": num("C_J", 3),
                "P_breadth": num("P_breadth"),
                "P_down": num("P_down"),
                "P_bomb": num("P_bomb"),
                "P_cool": num("P_cool"),
                "P_inertia": num("P_inertia"),
            },
        }

    def adjust_stock_score(
        self,
        base_score: float,
        styles: Mapping[str, float] | Sequence[str] | None = None,
        day: str | None = None,
        state: Mapping[str, object] | None = None,
    ) -> dict:
        """用当日市场状态调整个股评分。

        可以直接给 ``state``（避免重复计算），也可以给 ``day`` 由引擎取状态。
        """
        market = dict(state) if state is not None else self.get_market_state(day)
        return _adjust_stock_score(base_score, styles, market, self._env_weights or load_env_weights())

    # ---------- 展示 ----------

    def render(self, day: str | None = None) -> str:
        """输出 README 第 16 节的每日状态文本。"""
        return render_state(self.get_market_state(day))

    def history_frame(self) -> pd.DataFrame:
        """把温度序列整理成便于导出的表。"""
        output = self.compute()
        keep = [
            "date", "regime", "F", "L", "R", "A", "B", "V", "Q", "J", "J_label",
            "M", "S", "delta1", "delta2", "phase", "momentum",
        ]
        frame = output[keep].copy()
        frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
        return frame
