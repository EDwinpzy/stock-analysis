from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_douyin as fetch
import analyze_douyin as analyze


class TranscriptCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(fetch, 'TRANSCRIPT_CACHE_DIR', Path(self.temp.name))
        self.patch.start()
        self.video = {'url': 'https://www.douyin.com/video/7696027544524534244', 'create_time': 1791840000, 'title': '来源标题'}

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_completed_video_survives_parent_retry_without_media_paths(self):
        fetch.save_video_transcript(self.video, {'transcript': '真实转录文本', 'video_path': '/temporary/private.mp4'})
        self.assertEqual(fetch.load_video_transcript(self.video)['transcript'], '真实转录文本')
        self.assertNotIn('private.mp4', next(Path(self.temp.name).glob('*.json')).read_text(encoding='utf-8'))
        with patch.object(fetch, 'transcribe_video', side_effect=AssertionError('should reuse valid cache')):
            self.assertEqual(fetch.get_video_transcript_with_fallback(self.video)['transcript'], '真实转录文本')

    def test_daily_collector_defaults_to_local_even_with_cloud_keys(self):
        with patch.dict(fetch.os.environ, {'GROQ_API_KEY': 'unused-test-key'}, clear=True), \
             patch.object(fetch, 'transcribe_video', return_value={'transcript': '真实转录'}) as transcribe:
            fetch.get_video_transcript_with_fallback(self.video)
        transcribe.assert_called_once_with(self.video['url'], 'local')

    def test_different_publication_timestamp_cannot_reuse_cache(self):
        fetch.save_video_transcript(self.video, {'transcript': '真实转录文本'})
        self.assertIsNone(fetch.load_video_transcript({**self.video, 'create_time': 1}))

    def test_warnings_and_empty_transcripts_are_not_cached(self):
        fetch.save_video_transcript(self.video, {'transcript': '部分转录', 'warning': '失败'})
        fetch.save_video_transcript(self.video, {'transcript': ''})
        self.assertIsNone(fetch.load_video_transcript(self.video))
        self.assertEqual(list(Path(self.temp.name).glob('*.json')), [])

    def test_urls_cannot_escape_cache_directory(self):
        fetch.save_video_transcript({'url': '../../outside'}, {'transcript': 'text'})
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_cpu_threads_are_bounded_without_changing_model(self):
        model = Mock()
        model.transcribe.return_value = {'text': '真实转录'}
        whisper = SimpleNamespace(load_model=Mock(return_value=model))
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False), set_num_threads=Mock())
        with patch.dict(sys.modules, {'whisper': whisper, 'torch': torch}), patch.object(analyze.os, 'cpu_count', return_value=16):
            self.assertEqual(analyze.extract_text_from_audio_local(Path('test.mp3'), 'small'), '真实转录')
        torch.set_num_threads.assert_called_once_with(4)
        whisper.load_model.assert_called_once_with('small')
        model.transcribe.assert_called_once_with('test.mp3', language='zh')


if __name__ == '__main__':
    unittest.main()
