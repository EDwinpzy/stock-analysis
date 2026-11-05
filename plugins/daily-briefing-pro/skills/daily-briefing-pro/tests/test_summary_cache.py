import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from summary_cache import (
    NO_CLEAR_OPINION,
    cached_tgb_summaries_complete,
    get_cached_summary,
    load_summary_cache,
    normalize_ai_summary,
    save_summary_cache,
    set_cached_summary,
)


class SummaryCacheTests(unittest.TestCase):
    def test_legacy_undated_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tgb_ai_summaries.json"
            path.write_text(json.dumps({"博主甲": "旧观点"}), encoding="utf-8")

            cache = load_summary_cache(path)

            self.assertIsNone(get_cached_summary(cache, "2026-09-24", "tgb", "博主甲", "原文"))

    def test_cache_requires_matching_date_source_name_and_source_text(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tgb_ai_summaries.json"
            cache = load_summary_cache(path)
            set_cached_summary(cache, "2026-09-24", "tgb", "博主甲", "原文A", "观点A")
            save_summary_cache(cache, path)
            loaded = load_summary_cache(path)

            self.assertEqual(get_cached_summary(loaded, "2026-09-24", "tgb", "博主甲", "原文A"), "观点A")
            self.assertIsNone(get_cached_summary(loaded, "2026-09-23", "tgb", "博主甲", "原文A"))
            self.assertIsNone(get_cached_summary(loaded, "2026-09-24", "douyin", "博主甲", "原文A"))
            self.assertIsNone(get_cached_summary(loaded, "2026-09-24", "tgb", "博主甲", "原文B"))

    def test_no_clear_opinion_is_a_valid_normalized_summary(self):
        self.assertEqual(normalize_ai_summary("“无明确观点”。"), NO_CLEAR_OPINION)
        self.assertEqual(normalize_ai_summary("看多【半导体】，因需求回升。"), "看多【半导体】，因需求回升。")

    def test_cache_completeness_checks_every_content_bearing_blogger(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tgb_ai_summaries.json"
            data = {"bloggers": {"博主甲": {"posts": [{"content": "甲观点"}]}, "博主乙": {"top_replies": [{"content": "乙观点"}]}}}
            cache = load_summary_cache(path)
            set_cached_summary(cache, "2026-09-24", "tgb", "博主甲", "甲观点", "观点甲")
            self.assertFalse(cached_tgb_summaries_complete(cache, "2026-09-24", data))
            set_cached_summary(cache, "2026-09-24", "tgb", "博主乙", "乙观点", NO_CLEAR_OPINION)
            self.assertTrue(cached_tgb_summaries_complete(cache, "2026-09-24", data))


if __name__ == "__main__":
    unittest.main()
