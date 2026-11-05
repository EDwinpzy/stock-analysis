"""Shared freshness and failure checks for daily briefing data files."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Mapping


ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")


def extract_iso_dates(value: object) -> list[date]:
    """Extract valid ISO dates from a scalar or a date-range string."""
    if value is None:
        return []
    result = []
    for text in ISO_DATE_RE.findall(str(value)):
        try:
            result.append(datetime.strptime(text, "%Y-%m-%d").date())
        except ValueError:
            continue
    return result


def top_level_dates(data: Mapping[str, object]) -> list[date]:
    """Read only metadata dates; item dates are validated by their collectors."""
    actual_dates = []
    for key in ("asof", "data_date", "trade_date", "raw_date"):
        actual_dates = extract_iso_dates(data.get(key))
        if actual_dates:
            break
    if actual_dates:
        return sorted(set(actual_dates))

    values = []
    for key in ("date", "target_date"):
        values.extend(extract_iso_dates(data.get(key)))
    return sorted(set(values))


def data_error_reason(data: object) -> str:
    if not isinstance(data, Mapping):
        return "数据文件不是对象"
    for key in ("_error", "error"):
        value = data.get(key)
        if value:
            return str(value).splitlines()[0][:180]
    status = str(data.get("status", "")).lower()
    if status in {"error", "failed", "failure", "partial", "数据获取失败"}:
        return str(data.get("note") or data.get("message") or "数据获取失败")[:180]
    return ""


def dataset_state(
    data: object,
    requested_date: str,
    fallback_date: str | None = None,
    max_lag_days: int = 0,
) -> tuple[str, str]:
    """Return ``(state, reason)`` for a section's top-level JSON metadata.

    States are ``ok``, ``missing``, ``error``, ``stale``, ``future`` and
    ``unknown``. A fallback date is accepted only when it is explicitly passed
    by the full-brief caller; an older cache is never silently accepted.
    """
    if not isinstance(data, Mapping) or not data:
        return "missing", "数据文件缺失或为空"

    error = data_error_reason(data)
    if error:
        return "error", error

    try:
        requested = datetime.strptime(requested_date, "%Y-%m-%d").date()
    except ValueError:
        return "unknown", f"目标日期无效：{requested_date}"

    dates = top_level_dates(data)
    if not dates:
        return "unknown", "缺少数据日期元信息"

    latest = max(dates)
    earliest_allowed = requested
    if fallback_date:
        try:
            earliest_allowed = datetime.strptime(fallback_date, "%Y-%m-%d").date()
        except ValueError:
            earliest_allowed = requested
    if latest > requested:
        return "future", f"数据日期 {latest.isoformat()} 晚于目标日 {requested.isoformat()}"
    if latest < earliest_allowed:
        lag = (earliest_allowed - latest).days
        if lag > max_lag_days:
            return "stale", f"数据截至 {latest.isoformat()}，目标范围从 {earliest_allowed.isoformat()} 开始"
    return "ok", ""


def status_note(data: Mapping[str, object], state: str, reason: str) -> str:
    """Convert a state into concise user-facing metadata."""
    if state in {"missing", "error", "stale", "future", "unknown"}:
        return f"数据获取失败：{reason}"
    note = str(data.get("note") or "").strip()
    return note
