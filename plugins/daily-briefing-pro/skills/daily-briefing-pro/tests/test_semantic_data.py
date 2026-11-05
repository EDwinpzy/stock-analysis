import json
import sys
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_sentiment_survey as survey
import fetch_yanbao as yanbao
from summary_cache import get_cached_summary, load_summary_cache


DATE = "2026-10-13"


def report(content="经核验正文：设备投资增长，推动上游订单改善。"):
    return {
        "org": "测试机构",
        "title": "正文绑定测试",
        "stock": "测试公司",
        "code": "600000",
        "infoCode": "INFO-001",
        "source_url": "https://example.invalid/report",
        "verified": True,
        "content": content,
        "logic": "旧占位逻辑不应保留",
    }


def survey_sources(content="原文明确看好半导体板块，理由是订单改善。"):
    return (
        {
            "platform": "淘股吧",
            "date": DATE,
            "data_date": DATE,
            "status": "ok",
            "bloggers": {
                "作者甲": {
                    "posts": [{"title": "盘面观点", "content": content}],
                    "replies": [],
                }
            },
        },
        {"platform": "雪球", "date": DATE, "data_date": DATE, "status": "empty", "bloggers": {}},
    )


def semantic_row(index=0, **overrides):
    value = {
        "index": index,
        "direction": "看多",
        "sectors": ["半导体"],
        "is_market_view": False,
        "reason": "原文称订单改善，因此看好半导体板块。",
        "eligible": True,
    }
    value.update(overrides)
    return value


class YanbaoSemanticTests(unittest.TestCase):
    def test_only_verified_body_is_summarized_and_exact_cache_is_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            cache_path = Path(temp) / "yanbao.json"
            records = [report(), {**report(), "infoCode": "INFO-002", "verified": False, "content": "unverified"}]
            calls = []

            def summarize(tasks):
                calls.extend(tasks)
                return ["设备投资增速提升，帶动上游订单改善，报告看好测试公司。"]

            state = yanbao.enrich_report_logic(
                records, DATE, cache_path,
                available_fn=lambda: True,
                summarize_fn=summarize,
            )
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], records[0]["content"])
            self.assertEqual(records[0]["logic_status"], "semantic_generated")
            self.assertEqual(records[1]["logic"], "")
            self.assertEqual(state["missing_summaries"], 0)

            records_again = [report()]
            state_again = yanbao.enrich_report_logic(
                records_again, DATE, cache_path,
                available_fn=lambda: self.fail("matching cache should avoid a model call"),
                summarize_fn=lambda _: self.fail("matching cache should avoid a model call"),
            )
            self.assertEqual(records_again[0]["logic"], records[0]["logic"])
            self.assertEqual(records_again[0]["logic_status"], "semantic_cached")
            self.assertEqual(state_again["summarized_reports"], 1)

    def test_changed_report_body_invalidates_cached_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            cache_path = Path(temp) / "yanbao.json"
            first = [report()]
            yanbao.enrich_report_logic(first, DATE, cache_path,
                available_fn=lambda: True, summarize_fn=lambda _: ["正文A的语义总结"])

            changed = [report("经核验正文：原材料价格下降，缓解制造成本压力。")]
            calls = []
            yanbao.enrich_report_logic(changed, DATE, cache_path,
                available_fn=lambda: True,
                summarize_fn=lambda tasks: calls.extend(tasks) or ["正文B的语义总结"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(changed[0]["logic"], "正文B的语义总结")

    def test_unavailable_or_malformed_summary_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            cache_path = Path(temp) / "yanbao.json"
            records = [report()]
            state = yanbao.enrich_report_logic(records, DATE, cache_path,
                available_fn=lambda: False, summarize_fn=lambda _: self.fail("unavailable runner must not be called"))
            self.assertEqual(records[0]["logic"], "")
            self.assertEqual(records[0]["logic_status"], "semantic_generation_failed")
            self.assertEqual(state["missing_summaries"], 1)

            state = yanbao.enrich_report_logic([report()], DATE, cache_path,
                available_fn=lambda: True, summarize_fn=lambda _: [])
            self.assertEqual(state["missing_summaries"], 1)


class SurveySemanticTests(unittest.TestCase):
    def setUp(self):
        self.today_patch = patch.object(survey, "TODAY", DATE)
        self.today_patch.start()
        self.addCleanup(self.today_patch.stop)

    def test_semantic_result_is_counted_and_cached_against_exact_source(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "survey.json"
            tgb, xueqiu = survey_sources()
            calls = []

            def call_json(prompt, schema, timeout=180):
                calls.append((prompt, schema, timeout))
                return {"analyses": [semantic_row()]}

            rows = survey.analyze_sentiment(
                tgb, xueqiu, cache_path=path,
                available_fn=lambda: True, call_json_fn=call_json,
            )
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][2], 180)
            self.assertEqual(rows[0]["analysis_method"], "语义核验")
            self.assertEqual(rows[0]["direction"], "看多")
            self.assertEqual(survey.compute_statistics(rows)["total_analyses"], 1)
            cache = load_summary_cache(path)
            cached = get_cached_summary(cache, DATE, "survey", "淘股吧/作者甲", rows[0]["input_text"])
            self.assertIsNotNone(cached)

            reused = survey.analyze_sentiment(
                tgb, xueqiu, cache_path=path,
                available_fn=lambda: self.fail("matching cache should avoid availability probe"),
                call_json_fn=lambda *_args, **_kwargs: self.fail("matching cache should avoid model call"),
            )
            self.assertEqual(reused[0]["reason"], rows[0]["reason"])

    def test_changed_source_text_misses_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "survey.json"
            old_tgb, xueqiu = survey_sources()
            survey.analyze_sentiment(old_tgb, xueqiu, cache_path=path,
                available_fn=lambda: True,
                call_json_fn=lambda *_args, **_kwargs: {"analyses": [semantic_row()]})
            changed_tgb, _ = survey_sources("原文改为看空半导体，因订单下降。")
            calls = []
            survey.analyze_sentiment(changed_tgb, xueqiu, cache_path=path,
                available_fn=lambda: True,
                call_json_fn=lambda prompt, schema, timeout=180: calls.append(prompt) or {
                    "analyses": [semantic_row(direction="看空", reason="原文称订单下降。")]
                })
            self.assertEqual(len(calls), 1)

    def test_batches_at_twelve_and_validates_indices_and_field_types(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "survey.json"
            tgb = {
                "platform": "淘股吧", "date": DATE, "data_date": DATE, "status": "ok",
                "bloggers": {
                    f"作者{i}": {"posts": [{"title": "观点", "content": f"作者{i}明确讨论A股行业观点及产业订单变化。"}], "replies": []}
                    for i in range(13)
                },
            }
            calls = []

            def call_json(prompt, _schema, timeout=180):
                payload = json.loads(prompt.split("\n", 1)[1])
                calls.append(payload)
                return {"analyses": [semantic_row(index=row["index"]) for row in payload]}

            rows = survey.analyze_sentiment(tgb, {"platform": "雪球", "bloggers": {}}, cache_path=path,
                available_fn=lambda: True, call_json_fn=call_json)
            self.assertEqual([len(batch) for batch in calls], [12, 1])
            self.assertEqual(len(rows), 13)
            self.assertTrue(all(row["analysis_method"] == "语义核验" for row in rows))

            for malformed in (
                {"analyses": [semantic_row(index=0), semantic_row(index=0)]},
                {"analyses": [semantic_row(index=0, is_market_view="false")]},
                {"analyses": [semantic_row(index=2)]},
            ):
                with self.subTest(malformed=malformed):
                    one, empty = survey_sources()
                    failed = survey.analyze_sentiment(
                        one, empty, cache_path=Path(temp) / f"bad-{len(str(malformed))}.json",
                        available_fn=lambda: True,
                        call_json_fn=lambda *_args, _result=malformed, **_kwargs: _result,
                    )
                    self.assertEqual(failed[0]["analysis_method"], "未完成语义核验")
                    self.assertFalse(failed[0]["eligible"])
                    self.assertEqual(survey.compute_statistics(failed)["total_analyses"], 0)

    def test_batch_chunking_bounds_authors_and_source_characters_without_truncation(self):
        pending = [
            {"text": "甲" * 4},
            {"text": "乙" * 6},
            {"text": "丙" * 3},
            {"text": "丁" * 15},
            {"text": "戊" * 2},
        ]
        batches = survey._chunk_semantic_pending(pending, max_items=3, max_source_chars=10)
        self.assertEqual([[len(item["text"]) for item in batch] for batch in batches], [[4, 6], [3], [15], [2]])
        self.assertEqual([item["text"] for batch in batches for item in batch], [item["text"] for item in pending])

    def test_parallel_batches_checkpoint_cache_only_on_main_thread(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "survey.json"
            tgb = {
                "platform": "淘股吧", "date": DATE, "data_date": DATE, "status": "ok",
                "bloggers": {
                    f"作者{i}": {"posts": [{"title": "盘面观点", "content": f"作者{i}讨论A股资金面和行业订单变化，观点有明确理由。"}], "replies": []}
                    for i in range(7)
                },
            }
            lock = threading.Lock()
            active = 0
            max_active = 0
            calls = []
            save_threads = []
            original_save = survey.save_summary_cache

            def call_json(prompt, _schema, timeout=180):
                nonlocal active, max_active
                payload = json.loads(prompt.split("\n", 1)[1])
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                    calls.append((len(payload), timeout))
                try:
                    time.sleep(0.03)
                    return {"analyses": [semantic_row(index=item["index"]) for item in payload]}
                finally:
                    with lock:
                        active -= 1

            def save_on_main_thread(cache, cache_path):
                save_threads.append(threading.current_thread().name)
                return original_save(cache, cache_path)

            with patch.object(survey, "SURVEY_SEMANTIC_BATCH_MAX_ITEMS", 2), \
                 patch.object(survey, "SURVEY_SEMANTIC_BATCH_MAX_SOURCE_CHARS", 120), \
                 patch.object(survey, "SURVEY_SEMANTIC_WORKERS", 3), \
                 patch.object(survey, "SURVEY_SEMANTIC_BUDGET_SECONDS", 120), \
                 patch.object(survey, "SURVEY_SEMANTIC_CALL_TIMEOUT_SECONDS", 60), \
                 patch.object(survey, "save_summary_cache", side_effect=save_on_main_thread):
                rows = survey.analyze_sentiment(
                    tgb, {"platform": "雪球", "bloggers": {}}, cache_path=path,
                    available_fn=lambda: True, call_json_fn=call_json,
                )

            self.assertEqual(len(rows), 7)
            self.assertTrue(all(row["analysis_method"] == "语义核验" for row in rows))
            self.assertEqual([size for size, _timeout in calls], [2, 2, 2, 1])
            self.assertTrue(all(0 < timeout <= 60 for _size, timeout in calls))
            self.assertGreaterEqual(max_active, 2)
            self.assertLessEqual(max_active, 3)
            self.assertEqual(set(save_threads), {"MainThread"})
            cache = load_summary_cache(path)
            self.assertIsNotNone(get_cached_summary(cache, DATE, "survey", "淘股吧/作者0", rows[0]["input_text"]))

    def test_batch_errors_keep_safe_timeout_detail_and_hide_arbitrary_messages(self):
        tgb, xueqiu = survey_sources()
        with tempfile.TemporaryDirectory() as temp:
            timed_out = survey.analyze_sentiment(
                tgb, xueqiu, cache_path=Path(temp) / "timeout.json",
                available_fn=lambda: True,
                call_json_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("Codex semantic summary timed out after 53s")
                ),
            )
            self.assertIn("timed out after 53s", timed_out[0]["reason"])

            unsafe = survey.analyze_sentiment(
                tgb, xueqiu, cache_path=Path(temp) / "unsafe.json",
                available_fn=lambda: True,
                call_json_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("private source sentinel")
                ),
            )
            self.assertIn("RuntimeError", unsafe[0]["reason"])
            self.assertNotIn("private source sentinel", unsafe[0]["reason"])

    def test_unavailable_runner_does_not_fall_back_to_keyword_rules(self):
        tgb, xueqiu = survey_sources("文字里有看多和看空字样，但没有可核验的市场观点。")
        rows = survey.analyze_sentiment(tgb, xueqiu,
            available_fn=lambda: False,
            call_json_fn=lambda *_args, **_kwargs: self.fail("unavailable runner must not be called"))
        self.assertEqual(rows[0]["direction"], "未核验")
        self.assertEqual(rows[0]["analysis_method"], "未完成语义核验")
        self.assertEqual(survey.compute_statistics(rows)["total_analyses"], 0)


class TgbRosterTests(unittest.TestCase):
    def test_roster_requires_fifty_unique_real_records(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            valid = [{"uid": str(i), "name": f"核验作者{i}"} for i in range(50)]
            roster_path = root / "data" / "tgb_hot_users.json"
            roster_path.write_text(json.dumps(valid, ensure_ascii=False), encoding="utf-8")
            with patch.object(survey, "BASE_DIR", root):
                bloggers, error = survey._load_tgb_roster()
            self.assertEqual(len(bloggers), 50)
            self.assertEqual(error, "")

            roster_path.write_text(json.dumps(valid[:-1], ensure_ascii=False), encoding="utf-8")
            with patch.object(survey, "BASE_DIR", root):
                bloggers, error = survey._load_tgb_roster()
            self.assertEqual(bloggers, [])
            self.assertTrue(error)

    def test_invalid_roster_blocks_cookie_and_network_work(self):
        with patch.object(survey, "TGB_ROSTER_ERROR", "名单文件缺失"), patch.object(
            survey, "load_cookie_string", side_effect=AssertionError("should stop before network setup")
        ):
            result = survey.crawl_tgb()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "TGB_ROSTER_INVALID")
        self.assertEqual(result["coverage"]["failed_bloggers"], 50)


if __name__ == "__main__":
    unittest.main()
