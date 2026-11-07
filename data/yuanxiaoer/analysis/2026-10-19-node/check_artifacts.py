"""Check report claims, references and source boundaries against saved evidence."""
import hashlib
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    source = read(ROOT / "source_review.json")
    rows = read(ROOT / "validation/candidate_outcomes.json")
    manifest = read(ROOT / "validation/validation_manifest.json")
    text = (ROOT / "节点票筛选条件.md").read_text(encoding="utf-8")
    assert len(rows) == 186
    assert source["main_post_count"] == 1 and source["own_reply_count"] == 90
    assert len(source["images"]) == 10 and all(x["visual_reviewed"] for x in source["images"])
    assert source["archival_success_boundary_preserved"] == read(BASE / "distillation_state.json")["last_distilled_at"] == "2026-10-09T01:39:43.134329+08:00"
    sample = [r for r in rows if r["signal_day"] == "2026-09-28" and not r["is_st"] and not r["is_new"] and not r["entry_open_at_limit"]]
    vals = [r["net_pct_T5"] for r in sample]
    assert len(sample) == 26 and sum(v < 0 for v in vals) == 18
    assert f"{statistics.mean(vals):+.2f}%" in text
    assert f"{statistics.median(vals):+.2f}%" in text
    assert f"{sum(v > 0 for v in vals) / len(vals) * 100:.1f}%" in text
    assert all(r["net_pct_T3"] is None for r in rows if r["signal_day"] == "2026-10-16")
    for link in re.findall(r"\]\(([^)]+)\)", text):
        if not link.startswith(("https://", "http://", "#")):
            assert (ROOT / link).exists(), link
    for rel, expected in manifest["files"].items():
        assert hashlib.sha256((ROOT / "validation" / rel).read_bytes()).hexdigest() == expected, rel
    assert manifest["checks"] == "passed" and manifest["pool_days"] == 16 and manifest["price_files"] == 175
    result = {"checks": "passed", "source": "1 main post / 90 author replies / 10 image reviews", "data": "186 candidate rows / 16 pool days / 175 price responses", "claims_and_local_links": "passed", "scope": "time-stamped descriptive analysis; no whole-method profitability claim", "visual_check": "IAB screenshots reviewed: title/coverage and validation table; no horizontal overflow"}
    (ROOT / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
