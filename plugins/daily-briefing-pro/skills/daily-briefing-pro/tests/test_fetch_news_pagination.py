import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_news


class _Response:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def _item(code, day):
    return {
        "code": code,
        "showTime": f"{day} 18:00:00",
        "title": f"news-{code}",
        "summary": f"summary-{code}",
        "stockList": [],
    }


class EastmoneyNewsPaginationTests(unittest.TestCase):
    def test_previous_day_news_is_fetched_after_newer_page(self):
        pages = [
            {
                "sortEnd": "cursor-1",
                "fastNewsList": [_item("new-1", "2026-11-06")],
            },
            {
                "sortEnd": "cursor-2",
                "fastNewsList": [
                    _item("target-1", "2026-11-05"),
                    _item("target-2", "2026-11-05"),
                ],
            },
        ]
        urls = []

        def fake_urlopen(request, **_kwargs):
            urls.append(request.full_url)
            return _Response({"code": 1, "data": pages[len(urls) - 1]})

        with patch.object(fetch_news.urllib.request, "urlopen", side_effect=fake_urlopen):
            with patch.object(fetch_news, "get_cached_summary", return_value=None):
                result = fetch_news.fetch_eastmoney_news(
                    limit=2,
                    target_date="2026-11-05",
                )

        self.assertEqual([item["title"] for item in result], ["news-target-1", "news-target-2"])
        self.assertEqual(len(urls), 2)
        self.assertIn("sortEnd=cursor-1", urls[1])
        self.assertIn("pageSize=200", urls[0])

    def test_stops_when_page_is_older_than_target(self):
        page = {
            "sortEnd": "cursor-1",
            "fastNewsList": [_item("older-1", "2026-11-04")],
        }

        with patch.object(
            fetch_news.urllib.request,
            "urlopen",
            return_value=_Response({"code": 1, "data": page}),
        ) as urlopen:
            result = fetch_news.fetch_eastmoney_news(
                limit=2,
                target_date="2026-11-05",
            )

        self.assertEqual(result, [])
        self.assertEqual(urlopen.call_count, 1)

    def test_without_target_date_keeps_single_page_contract(self):
        page = {
            "sortEnd": "cursor-1",
            "fastNewsList": [_item("latest-1", "2026-11-06")],
        }

        with patch.object(
            fetch_news.urllib.request,
            "urlopen",
            return_value=_Response({"code": 1, "data": page}),
        ) as urlopen:
            with patch.object(fetch_news, "get_cached_summary", return_value=None):
                result = fetch_news.fetch_eastmoney_news(limit=1)

        self.assertEqual([item["title"] for item in result], ["news-latest-1"])
        self.assertEqual(urlopen.call_count, 1)
        self.assertIn("pageSize=1", urlopen.call_args.args[0].full_url)


if __name__ == "__main__":
    unittest.main()
