import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import codex_summary_cli as cli


class CodexSummaryTests(unittest.TestCase):
    def test_disabled_fallback_requires_api(self):
        with patch.dict(os.environ, {'DAILY_BRIEFING_CODEX_FALLBACK': '0', 'OPENAI_API_KEY': '', 'DEEPSEEK_API_KEY': ''}):
            self.assertFalse(cli.semantic_summary_available())

    def test_empty_sources_preserve_positions(self):
        with patch.object(cli, 'call_codex_json', return_value={'summaries': [{'index': 1, 'summary': '中性：等待确认。'}]}):
            self.assertEqual(cli.summarize_tasks([('', ''), ('来源原文', '观点')]), ['', '中性：等待确认。'])

    def test_duplicate_or_missing_results_are_not_delivered(self):
        with patch.object(cli, 'call_codex_json', return_value={'summaries': [{'index': 0, 'summary': 'A'}, {'index': 0, 'summary': 'B'}]}):
            self.assertEqual(cli.summarize_tasks([('原文甲', ''), ('原文乙', '')]), ['', ''])

    def test_cli_is_ephemeral_schema_bound_and_does_not_log_source(self):
        def fake_run(command, **kwargs):
            self.assertIn('--ephemeral', command)
            self.assertEqual(command[command.index('--model') + 1], 'gpt-6-luna')
            self.assertIn('model_reasoning_effort="max"', command)
            self.assertIn('--sandbox', command)
            self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
            self.assertEqual(kwargs['timeout'], 180)
            path = Path(command[command.index('--output-last-message') + 1])
            path.write_text(json.dumps({'answer': 'ok'}), encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout='', stderr='private source')
        with patch.object(cli.shutil, 'which', return_value='codex'), patch.object(cli.subprocess, 'run', side_effect=fake_run):
            self.assertEqual(cli.call_codex_json('source', {'type': 'object'}), {'answer': 'ok'})

    def test_custom_timeout_is_enforced_without_echoing_input(self):
        def fake_run(command, **kwargs):
            self.assertEqual(kwargs['timeout'], 60)
            raise cli.subprocess.TimeoutExpired(command, 60, output='private source')

        with patch.object(cli.shutil, 'which', return_value='codex'), patch.object(cli.subprocess, 'run', side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, 'timed out after 60s') as result:
                cli.call_codex_json('private source', {'type': 'object'}, timeout=60)
        self.assertNotIn('private source', str(result.exception))

    def test_timeout_must_be_positive_integer(self):
        with self.assertRaisesRegex(ValueError, 'positive integer'):
            cli.call_codex_json('source', {'type': 'object'}, timeout=0)

    def test_non_object_jsonl_events_are_ignored(self):
        def fake_run(command, **kwargs):
            path = Path(command[command.index('--output-last-message') + 1])
            path.write_text('{}', encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout='[]\n"text"\n', stderr='')

        with patch.object(cli.shutil, 'which', return_value='codex'), patch.object(cli.subprocess, 'run', side_effect=fake_run):
            self.assertEqual(cli.call_codex_json('source', {'type': 'object'}), {})

    def test_tool_use_rejects_even_valid_json(self):
        def fake_run(command, **kwargs):
            Path(command[command.index('--output-last-message') + 1]).write_text('{}', encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout=json.dumps({'item': {'type': 'command_execution'}}), stderr='')
        with patch.object(cli.shutil, 'which', return_value='codex'), patch.object(cli.subprocess, 'run', side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, 'tool use'):
                cli.call_codex_json('source', {'type': 'object'})

    def test_failed_cli_does_not_expose_stderr(self):
        with patch.object(cli.shutil, 'which', return_value='codex'), patch.object(cli.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='secret')):
            with self.assertRaises(RuntimeError) as result:
                cli.call_codex_json('source', {'type': 'object'})
            self.assertNotIn('secret', str(result.exception))


if __name__ == '__main__':
    unittest.main()
