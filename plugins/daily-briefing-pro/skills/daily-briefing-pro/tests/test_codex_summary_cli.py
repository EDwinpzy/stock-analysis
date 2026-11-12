import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import codex_summary_cli as cli


class ApiSummaryTests(unittest.TestCase):
    def setUp(self):
        self._env_isolation = patch.dict(
            os.environ,
            {
                'DAILY_BRIEFING_AI_API_KEY': '',
                'DAILY_BRIEFING_AI_BASE_URL': '',
                'DAILY_BRIEFING_AI_MODEL': '',
                'DAILY_BRIEFING_AI_FALLBACK_MODEL': '',
                'DEEPSEEK_API_KEY': '',
                'DEEPSEEK_BASE_URL': '',
                'DEEPSEEK_MODEL': '',
                'DEEPSEEK_FALLBACK_MODEL': '',
                'OPENAI_API_KEY': '',
                'OPENAI_BASE_URL': '',
                'OPENAI_MODEL': '',
            },
            clear=False,
        )
        self._env_isolation.start()
        self.addCleanup(self._env_isolation.stop)

    def test_api_provider_configuration_prefers_generic_endpoint(self):
        config = cli.api_summary_config({
            'DAILY_BRIEFING_AI_API_KEY': 'test-generic-key',
            'DAILY_BRIEFING_AI_BASE_URL': 'https://summary.example/v1/',
            'DAILY_BRIEFING_AI_MODEL': 'summary-model',
            'DEEPSEEK_API_KEY': 'test-deepseek-key',
        })
        self.assertIsNotNone(config)
        self.assertEqual(config.provider, 'generic')
        self.assertEqual(config.base_url, 'https://summary.example/v1')
        self.assertEqual(config.model, 'summary-model')

    def test_deepseek_configuration_uses_its_base_url_and_model(self):
        config = cli.api_summary_config({
            'DEEPSEEK_API_KEY': 'test-deepseek-key',
            'DEEPSEEK_BASE_URL': 'https://deepseek.example/v1',
            'DEEPSEEK_MODEL': 'deepseek-test',
        })
        self.assertEqual(config, cli.ApiSummaryConfig(
            'deepseek', 'test-deepseek-key', 'https://deepseek.example/v1', 'deepseek-test'
        ))

    def test_api_key_makes_semantic_summary_available(self):
        available, source = cli.semantic_summary_status({'OPENAI_API_KEY': 'test-openai-key'})
        self.assertTrue(available)
        self.assertEqual(source, 'api-key:openai')

    def test_local_codex_fallback_is_removed(self):
        available, source = cli.semantic_summary_status({})

        self.assertFalse(available)
        self.assertEqual(source, 'missing-ai-api-key')
        self.assertFalse(hasattr(cli, 'codex_available'))
        self.assertFalse(hasattr(cli, 'codex_logged_in'))

    def test_api_summary_parses_fenced_json(self):
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {
                'choices': [{'message': {'content': '```json\n{"summaries": [{"index": 0, "summary": "中性"}]}\n```'}}]
            },
        )
        with patch.dict(
            os.environ,
            {
                'DAILY_BRIEFING_AI_API_KEY': 'test-key',
                'DAILY_BRIEFING_AI_BASE_URL': 'https://summary.example/v1',
                'DAILY_BRIEFING_AI_MODEL': 'summary-model',
            },
            clear=False,
        ), patch.object(cli.httpx, 'post', return_value=response) as post:
            answer = cli.call_api_json('输入', {'type': 'object'})
        self.assertEqual(answer['summaries'][0]['summary'], '中性')
        self.assertEqual(post.call_args.args[0], 'https://summary.example/v1/chat/completions')
        self.assertEqual(post.call_args.kwargs['json']['model'], 'summary-model')

    def test_api_summary_uses_fallback_model_after_404(self):
        responses = [
            SimpleNamespace(status_code=404, text='missing model'),
            SimpleNamespace(
                status_code=200,
                json=lambda: {'choices': [{'message': {'content': '可用'}}]},
            ),
        ]
        models = []

        def fake_post(*args, **kwargs):
            models.append(kwargs['json']['model'])
            return responses[len(models) - 1]

        with patch.dict(
            os.environ,
            {
                'DAILY_BRIEFING_AI_API_KEY': 'test-key',
                'DAILY_BRIEFING_AI_BASE_URL': 'https://summary.example/v1',
                'DAILY_BRIEFING_AI_MODEL': 'summary-model',
                'DAILY_BRIEFING_AI_FALLBACK_MODEL': 'fallback-model',
            },
            clear=False,
        ), patch.object(cli.httpx, 'post', side_effect=fake_post):
            answer = cli.call_api_text('输入')
        self.assertEqual(answer, '可用')
        self.assertEqual(models, ['summary-model', 'fallback-model'])

    def test_api_auth_failure_does_not_echo_response_body(self):
        response = SimpleNamespace(status_code=401, text='private upstream response')
        with patch.dict(
            os.environ,
            {'DAILY_BRIEFING_AI_API_KEY': 'test-key'},
            clear=False,
        ), patch.object(cli.httpx, 'post', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'credentials rejected') as result:
                cli.call_api_text('输入')
        self.assertNotIn('private upstream response', str(result.exception))

    def test_missing_api_key_is_unavailable(self):
        self.assertFalse(cli.semantic_summary_available())

    def test_empty_sources_preserve_positions(self):
        with patch.object(cli, 'call_codex_json', return_value={'summaries': [{'index': 1, 'summary': '中性：等待确认。'}]}):
            self.assertEqual(cli.summarize_tasks([('', ''), ('来源原文', '观点')]), ['', '中性：等待确认。'])

    def test_duplicate_or_missing_results_are_not_delivered(self):
        with patch.object(cli, 'call_codex_json', return_value={'summaries': [{'index': 0, 'summary': 'A'}, {'index': 0, 'summary': 'B'}]}):
            self.assertEqual(cli.summarize_tasks([('原文甲', ''), ('原文乙', '')]), ['', ''])

    def test_invalid_batch_is_split_to_keep_valid_items(self):
        calls = []

        def fake_batch(batch, schema):
            calls.append([index for index, _, _ in batch])
            if len(batch) > 1:
                raise cli.SummaryBatchError('Incomplete summary batch')
            index = batch[0][0]
            return {index: f'摘要{index}'}

        with patch.object(cli, '_summarize_batch', side_effect=fake_batch):
            result = cli.summarize_tasks([('原文甲', ''), ('原文乙', '')])

        self.assertEqual(result, ['摘要0', '摘要1'])
        self.assertEqual(calls, [[0, 1], [0], [1]])

    def test_legacy_call_name_delegates_to_api(self):
        with patch.object(cli, 'call_api_json', return_value={'answer': 'ok'}) as call:
            self.assertEqual(
                cli.call_codex_json('source', {'type': 'object'}, timeout=60),
                {'answer': 'ok'},
            )

        call.assert_called_once_with('source', {'type': 'object'}, timeout=60)

    def test_timeout_must_be_positive_integer(self):
        with self.assertRaisesRegex(ValueError, 'positive integer'):
            cli.call_codex_json('source', {'type': 'object'}, timeout=0)

    def test_semantic_worker_count_is_bounded(self):
        with patch.dict(os.environ, {'DAILY_BRIEFING_SEMANTIC_WORKERS': '99'}):
            self.assertEqual(cli._semantic_workers(), 6)
        with patch.dict(os.environ, {'DAILY_BRIEFING_SEMANTIC_WORKERS': '0'}):
            self.assertEqual(cli._semantic_workers(), 1)
        with patch.dict(os.environ, {'DAILY_BRIEFING_SEMANTIC_WORKERS': 'not-a-number'}):
            self.assertEqual(cli._semantic_workers(), 4)


if __name__ == '__main__':
    unittest.main()
