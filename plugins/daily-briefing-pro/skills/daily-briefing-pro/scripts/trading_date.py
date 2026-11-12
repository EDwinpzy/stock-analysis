"""Shared target-date rules for the daily briefing pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta


def get_recent_trade_date(
    date_str: str,
    *,
    now: datetime | None = None,
    cutoff_hour: int = 15,
) -> str:
    """Return the latest completed weekday for the target date.

    Before the A-share close, today's target rolls back one calendar day. This
    prevents a scheduled run from treating an incomplete trading session as a
    finished daily snapshot. Explicit historical target dates are not shifted
    based on the machine's current time. Exchange holidays are not inferred
    here; collectors keep their existing source-specific validation.
    """
    target = datetime.strptime(date_str, "%Y-%m-%d")
    current = now or datetime.now()

    if date_str == current.strftime("%Y-%m-%d") and current.hour < cutoff_hour:
        target -= timedelta(days=1)

    while target.weekday() >= 5:
        target -= timedelta(days=1)

    return target.strftime("%Y-%m-%d")
