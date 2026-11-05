"""Single allowlist for runtime files that are safe to migrate or seed."""

from __future__ import annotations

import fnmatch
from pathlib import Path

DURABLE_EXACT_FILES = frozenset(
    {
        "sentiment_panel_v32.csv",
        "sentiment_history.json",
        "node_cycle_history.json",
        "rotation_history.json",
        "tgb_ai_summaries.json",
        "douyin_ai_summaries.json",
        "news_ai_summaries.json",
        "survey_ai_summaries.json",
        "yanbao_ai_summaries.json",
        "stock_code_cache.json",
        "stock_daily_cache.json",
        "ai_summary_override.json",
        "strategy_ai.json",
        "used_quotes.json",
        "langwang_cycle.json",
    }
)
DURABLE_GLOB_PATTERNS = (
    "survey_raw_*.json",
    "douyin_transcripts/*.json",
    "douyin_transcripts/**/*.json",
)
DENIED_SUFFIXES = (
    "_today.json",
    "cookies.json",
)
DENIED_NAMES = frozenset(
    {
        ".env",
        "preflight.json",
        "douyin_state.json",
        "tgb_cookies.json",
        "douyin_cookies.json",
        "xueqiu_cookies.json",
    }
)


def is_durable_data_file(relative_path: str | Path) -> bool:
    """Return true only for long-lived model/cache inputs, never secrets or snapshots."""
    relative = Path(relative_path).as_posix()
    path = Path(relative)
    name = path.name
    lowered_parts = [part.casefold() for part in path.parts]
    if any(part in {"secrets", ".git"} for part in lowered_parts):
        return False
    if name.casefold() in DENIED_NAMES or name.casefold().endswith(DENIED_SUFFIXES):
        return False
    if "cookie" in name.casefold() or "secret" in name.casefold():
        return False
    if name in DURABLE_EXACT_FILES:
        return True
    return any(fnmatch.fnmatch(relative, pattern) for pattern in DURABLE_GLOB_PATTERNS)
