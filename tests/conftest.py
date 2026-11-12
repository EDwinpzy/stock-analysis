from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "daily-briefing-pro"

for path in (
    PLUGIN,
    PLUGIN / "skills" / "market-query" / "scripts",
    PLUGIN / "skills" / "stock-analysis" / "scripts",
    PLUGIN / "skills" / "industry-analysis" / "scripts",
    PLUGIN / "skills" / "daily-briefing-pro" / "scripts",
):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)
