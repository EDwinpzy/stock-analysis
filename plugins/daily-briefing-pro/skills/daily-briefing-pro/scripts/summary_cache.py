"""Date- and source-bounded AI summary cache helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


CACHE_SCHEMA_VERSION = 1
NO_CLEAR_OPINION = "无明确观点"


def normalize_ai_summary(value: Any) -> str:
    """Normalize model output while retaining an explicit no-opinion result."""
    summary = str(value or "").strip().strip("\"'“”‘’「」『』")
    normalized = re.sub(r"[\s，。！？!?,.;；:：、\"'“”‘’「」『』]+", "", summary)
    if normalized in {"无明确观点", "无明确投资观点", "没有明确观点", "没有明确投资观点"}:
        return NO_CLEAR_OPINION
    return summary


def empty_summary_cache() -> dict[str, Any]:
    return {"schema_version": CACHE_SCHEMA_VERSION, "dates": {}}


def load_summary_cache(path: Path) -> dict[str, Any]:
    """Load only the versioned cache format; legacy undated files are ignored."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return empty_summary_cache()

    if not isinstance(value, dict) or value.get("schema_version") != CACHE_SCHEMA_VERSION:
        return empty_summary_cache()
    dates = value.get("dates")
    if not isinstance(dates, dict):
        return empty_summary_cache()
    return {"schema_version": CACHE_SCHEMA_VERSION, "dates": dates}


def _content_digest(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def get_cached_summary(
    cache: dict[str, Any],
    target_date: str,
    source: str,
    name: str,
    raw_text: str,
) -> str | None:
    dates = cache.get("dates")
    day = dates.get(target_date) if isinstance(dates, dict) else None
    source_cache = day.get(source) if isinstance(day, dict) else None
    record = source_cache.get(name) if isinstance(source_cache, dict) else None
    if not isinstance(record, dict) or record.get("input_sha256") != _content_digest(raw_text):
        return None
    cached_value = record.get("summary")
    if not isinstance(cached_value, str):
        return None
    summary = normalize_ai_summary(cached_value)
    return summary or None


def set_cached_summary(
    cache: dict[str, Any],
    target_date: str,
    source: str,
    name: str,
    raw_text: str,
    summary: str,
) -> None:
    normalized = normalize_ai_summary(summary)
    if not raw_text.strip() or not normalized:
        return
    dates = cache.setdefault("dates", {})
    day = dates.setdefault(target_date, {})
    source_cache = day.setdefault(source, {})
    source_cache[name] = {
        "input_sha256": _content_digest(raw_text),
        "summary": normalized,
    }


def save_summary_cache(cache: dict[str, Any], path: Path, *, max_dates: int = 60) -> None:
    """Atomically write a bounded set of date partitions."""
    dates = cache.get("dates")
    if not isinstance(dates, dict):
        dates = {}
    ordered_dates = sorted(dates)
    retained = {day: dates[day] for day in ordered_dates[-max_dates:]}
    payload = {"schema_version": CACHE_SCHEMA_VERSION, "dates": retained}

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def tgb_content_text(blogger: dict[str, Any]) -> str:
    parts = []
    for post in blogger.get("posts", []) or []:
        if isinstance(post, dict) and post.get("content"):
            parts.append(str(post["content"]))
    for reply in (blogger.get("top_replies", []) or [])[:10]:
        if isinstance(reply, dict) and reply.get("content"):
            parts.append(str(reply["content"]))
    return "\n".join(parts)


def cached_tgb_summaries_complete(
    cache: dict[str, Any], target_date: str, tgb_data: dict[str, Any]
) -> bool:
    bloggers = tgb_data.get("bloggers")
    if not isinstance(bloggers, dict):
        return False
    for name, blogger in bloggers.items():
        if not isinstance(blogger, dict):
            continue
        raw_text = tgb_content_text(blogger)
        if raw_text and get_cached_summary(cache, target_date, "tgb", str(name), raw_text) is None:
            return False
    return True
