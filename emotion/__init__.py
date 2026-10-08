"""A股超短情绪温度模型 3.2 —— 情绪引擎。"""

from .config import ENV_WEIGHTS_PATH, CONFIG_PATH, load_config, load_env_weights
from .core import compute_model
from .display import phase_display, regime_display, render_state, temperature_grade
from .engine import EmotionEngine, load_panel
from .score_adjust import adjust_stock_score

__all__ = [
    "EmotionEngine",
    "compute_model",
    "load_panel",
    "load_config",
    "load_env_weights",
    "adjust_stock_score",
    "temperature_grade",
    "phase_display",
    "regime_display",
    "render_state",
    "CONFIG_PATH",
    "ENV_WEIGHTS_PATH",
]

__version__ = "A-SHORT-SENTIMENT-3.2"
