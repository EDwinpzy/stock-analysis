from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_sentiment_survey as survey


class SurveyCheckpointTests(unittest.TestCase):
    def test_complete_dated_platform_can_resume(self):
        data = {'date': survey.TODAY, 'data_date': survey.TODAY, 'status': 'ok',
                'coverage': {'expected_bloggers': 50, 'complete_bloggers': 50, 'failed_bloggers': 0}}
        with tempfile.TemporaryDirectory() as temp, patch.object(survey, 'DATA_DIR', Path(temp)), patch.object(sys, 'argv', ['survey', '--resume']):
            survey._save_platform_checkpoint('淘股吧', data)
            self.assertEqual(survey._load_platform_checkpoint('淘股吧'), data)
            data['data_date'] = '2000-01-01'
            survey._save_platform_checkpoint('淘股吧', data)
            self.assertIsNone(survey._load_platform_checkpoint('淘股吧'))

    def test_partial_coverage_cannot_be_reused_as_complete(self):
        data = {'date': survey.TODAY, 'data_date': survey.TODAY, 'status': 'partial',
                'coverage': {'expected_bloggers': 50, 'complete_bloggers': 49, 'failed_bloggers': 1}}
        with tempfile.TemporaryDirectory() as temp, patch.object(survey, 'DATA_DIR', Path(temp)), patch.object(sys, 'argv', ['survey', '--resume']):
            survey._save_platform_checkpoint('雪球', data)
            self.assertIsNone(survey._load_platform_checkpoint('雪球'))


if __name__ == '__main__':
    unittest.main()
