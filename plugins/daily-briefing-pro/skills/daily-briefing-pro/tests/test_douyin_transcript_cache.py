from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_douyin as fetch


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
        loaded = fetch.load_video_transcript(self.video)
        self.assertEqual(loaded['transcript'], '真实转录文本')
        self.assertEqual(loaded['transcript_source'], 'verified_video_cache')
        self.assertTrue(loaded['transcript_cache_hit'])
        self.assertNotIn('private.mp4', next(Path(self.temp.name).glob('*.json')).read_text(encoding='utf-8'))
        with patch.object(fetch, 'transcribe_video', side_effect=AssertionError('should reuse valid cache')):
            fallback = fetch.get_video_transcript_with_fallback(self.video)
            self.assertEqual(fallback['transcript'], '真实转录文本')
            self.assertTrue(fallback['transcript_cache_hit'])

    def test_cache_keeps_the_real_transcript_producer(self):
        fetch.save_video_transcript(
            self.video,
            {'transcript': '真实转录文本', 'transcript_source': 'cloud-asr'},
        )

        loaded = fetch.load_video_transcript(self.video)

        self.assertEqual(loaded['transcript_source'], 'cloud-asr')
        self.assertEqual(loaded['original_transcript_source'], 'cloud-asr')
        self.assertTrue(loaded['transcript_cache_hit'])

    def test_daily_collector_defaults_to_auto_even_with_cloud_keys(self):
        with patch.dict(fetch.os.environ, {'GROQ_API_KEY': 'unused-test-key'}, clear=True), \
             patch.object(fetch, 'transcribe_video', return_value={'transcript': '真实转录'}) as transcribe:
            fetch.get_video_transcript_with_fallback(self.video)
        transcribe.assert_called_once_with(self.video, 'auto')

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

if __name__ == '__main__':
    unittest.main()
