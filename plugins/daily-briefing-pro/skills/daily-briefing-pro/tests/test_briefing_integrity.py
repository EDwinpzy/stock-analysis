import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from briefing_integrity import MODULES, validate_data
from data_quality import dataset_state
from fetch_rotation import expected_trade_date, prediction_asof, refresh_industry_data
from fetch_news import classify_news
from fetch_sentiment_survey import compute_statistics
from build_briefing import summary_direction, render_index_card
import pick_quote

DATE, TRADE = '2026-10-10', '2026-10-09'
QUOTE = '<a href="https://www.berkshirehathaway.com/letters/2001pdf.pdf">verified</a>'


def complete_fixture():
    data = {filename: {'date': DATE, 'status': 'ok', key: [{}]} for filename, (_, key, _) in MODULES.items()}
    data['panic_today.json']['score'] = 84.1
    data['rotation_today.json']['asof'] = TRADE
    data['douyin_today.json'].update(bloggers=[{'videos': [{'transcript': '完整转录', 'warning': ''}]}], expected_video_count=1)
    data['tgb_today.json']['coverage'] = {'expected_bloggers': 4, 'complete_bloggers': 4, 'failed_bloggers': 0}
    data['sentiment_survey_today.json'].update(analysis_method='语义核验', platform_coverage={p: {'expected_bloggers': 50, 'complete_bloggers': 50, 'failed_bloggers': 0} for p in ('淘股吧', '雪球')})
    data['yanbao_latest.json']['reports'] = [{'verified': True, 'logic': '已核验逻辑', 'source_url': 'https://example.com/report'}]
    data['node_cycle_today.json'] = {'status': 'ok', 'rows': [{}], 'axis_dates': [TRADE]}
    data['indices_today.json'] = {'date': DATE, 'indices': {n: {'close': 100.0, 'chg': 0.1, 'data_date': TRADE} for n in ('上证', '科创50', '纳斯达克', 'KOSPI')}}
    return data


class IntegrityTests(unittest.TestCase):
    def test_legacy_skip_environment_cannot_bypass_missing_transcription(self):
        data = complete_fixture()
        del data['douyin_today.json']
        with patch.dict('os.environ', {'BRIEFING_SKIP_TRANSCRIPTION': '1'}):
            failures = validate_data(data, DATE, TRADE, QUOTE)
        self.assertTrue(any('抖音' in message for message in failures))

    def test_every_module_passes_with_complete_dated_data(self):
        self.assertEqual(validate_data(complete_fixture(), DATE, TRADE, QUOTE), [])

    def test_each_missing_module_blocks_delivery(self):
        for filename in (*MODULES, 'node_cycle_today.json', 'indices_today.json'):
            with self.subTest(module=filename):
                data = complete_fixture()
                del data[filename]
                self.assertTrue(validate_data(data, DATE, TRADE, QUOTE))

    def test_partial_status_cannot_be_masked_by_current_request_date(self):
        self.assertEqual(dataset_state({'date': DATE, 'status': 'partial'}, DATE)[0], 'error')
        self.assertEqual(dataset_state({'date': DATE, 'data_date': TRADE, 'asof': '2026-09-15'}, DATE, TRADE)[0], 'stale')

    def test_incomplete_transcription_and_cohort_are_rejected(self):
        for filename, mutation in [('douyin_today.json', {'bloggers': [{'videos': [{'transcript': ''}]}]}), ('sentiment_survey_today.json', {'analysis_method': '规则待核验'})]:
            data = complete_fixture()
            data[filename].update(mutation)
            self.assertTrue(validate_data(data, DATE, TRADE, QUOTE))

    def test_invalid_indices_quote_and_last_research_report_are_rejected(self):
        data = complete_fixture()
        data['indices_today.json']['indices']['KOSPI']['close'] = 0
        data['yanbao_latest.json']['reports'] += [{'verified': False}]
        reasons = validate_data(data, DATE, TRADE, '<p>no source</p>')
        self.assertGreaterEqual(len(reasons), 3)

    def test_keywords_do_not_turn_unrelated_punishment_into_market_bearishness(self):
        self.assertEqual(classify_news('矿长因损毁文物受到处罚'), '中性')

    def test_index_card_preserves_two_decimal_close(self):
        html = render_index_card('上证', {'close': 3813.79, 'chg': 0.05})
        self.assertIn('3,813.79', html)
        self.assertIn('0.05%', html)

    def test_explicit_semantic_direction_wins_over_words_inside_summary(self):
        self.assertEqual(summary_direction('【中性】若突破才考虑，当前不能看多'), '中性')
        self.assertEqual(summary_direction('【看空】风险较高'), '看空')

    def test_excluded_samples_do_not_inflate_market_statistics(self):
        samples = [{'platform': '雪球', 'blogger': 'A', 'direction': '看多', 'sectors': [], 'is_market_view': True, 'eligible': False}, {'platform': '淘股吧', 'blogger': 'B', 'direction': '中性', 'sectors': [], 'is_market_view': True}]
        result = compute_statistics(samples)
        self.assertEqual(result['total_analyses'], 1)
        self.assertEqual(result['by_market']['bull'], 0)


class RotationFreshnessTests(unittest.TestCase):
    def test_holidays_and_pre_close_use_exchange_calendar(self):
        cn = timezone(timedelta(hours=8))
        days = ['2026-09-30', '2026-10-08', TRADE]
        self.assertEqual(expected_trade_date('2026-10-07', days, datetime(2026, 10, 10, 12, tzinfo=cn)), '2026-09-30')
        self.assertEqual(expected_trade_date(TRADE, days, datetime(2026, 10, 9, 15, tzinfo=cn)), '2026-10-08')

    def test_prediction_requires_date_from_current_stdout(self):
        self.assertIsNone(prediction_asof('old output exists'))
        self.assertEqual(prediction_asof('predict as of 2026-10-09'), TRADE)

    def test_partial_refresh_does_not_modify_training_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'data').mkdir()
            (root / 'data/ths_industry_info.csv').write_text('code,name\n881001,测试行业\n', encoding='utf-8')
            path = root / 'data/ths_industry_daily.csv'
            original = 'date,code,name,close\n2026-09-15,881001,测试行业,100\n'
            path.write_text(original, encoding='utf-8')
            with patch('akshare.stock_board_industry_index_ths', side_effect=ValueError('fetch failed')), patch('fetch_rotation.time.sleep'):
                with self.assertRaises(ValueError):
                    refresh_industry_data(root, TRADE)
            self.assertEqual(path.read_text(encoding='utf-8'), original)


class QuoteTests(unittest.TestCase):
    def test_only_verified_sources_and_idempotent_daily_selection(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = root / 'quotes.json'
            library.write_text(json.dumps([{'id': 1, 'quote': 'unverified'}, {'id': 2, 'quote': 'verified', 'verified': True, 'source_url': 'https://example.com/source'}]), encoding='utf-8')
            with patch.object(pick_quote, 'QUOTES_FILE', str(library)), patch.object(pick_quote, 'USED_FILE', str(root / 'used.json')), patch.object(sys, 'argv', ['pick_quote.py', '--date', DATE]):
                self.assertEqual(pick_quote.pick_quote()[0]['id'], 2)
                self.assertEqual(pick_quote.pick_quote()[0]['id'], 2)


if __name__ == '__main__':
    unittest.main()
