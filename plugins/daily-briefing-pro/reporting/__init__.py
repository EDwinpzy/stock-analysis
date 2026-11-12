"""Deterministic report builders for the Daily Briefing Pro plugin."""

from .industry import build_industry_report
from .stock import build_stock_report

__all__ = ["build_industry_report", "build_stock_report"]
