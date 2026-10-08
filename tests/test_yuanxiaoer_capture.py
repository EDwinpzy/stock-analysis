import unittest

from tools.fetch_yuanxiaoer_posts import (
    fetch_topics,
    parse_post,
    pending_items,
    reply_digest,
)


class CaptureTests(unittest.TestCase):
    topic = {"newTopicID": "test", "topicID": 1, "subject": "test", "postDate": "2026-10-08"}

    def html(self, author=12089754):
        return (
            f'<span id="ztgioMsg" userid="{author}"></span>'
            '<div class="tzitem_text">' + '正文' * 120 + '</div>'
            '<div class="plItem"><div userid="99" contentid="1"></div>'
            '<div class="pl_text">读者意见</div><span class="pl_time">26-10-08 10:00</span></div>'
            '<div class="plItem"><div userid="12089754" contentid="2"></div>'
            '<div class="pl_text">本人观点</div><span class="pl_time">26-10-08 10:01</span></div>'
        )

    def test_only_author_replies(self):
        post, replies, next_page = parse_post(self.html(), self.topic)
        self.assertEqual([r["id"] for r in replies], ["2"])
        self.assertEqual(post["author_id"], 12089754)
        self.assertIsNone(next_page)

    def test_wrong_author_rejected(self):
        with self.assertRaises(ValueError):
            parse_post(self.html(99), self.topic)

    def test_login_page_rejected(self):
        with self.assertRaises(ValueError):
            parse_post('<html>登录可查看全文</html>', self.topic)

    def test_fetch_topics_enumerates_every_feed_page(self):
        topic_a = {"newTopicID": "a", "userID": 12089754, "postDate": "2026-10-08"}
        topic_b = {"newTopicID": "b", "userID": 12089754, "postDate": "2026-10-07"}
        topic_c = {"newTopicID": "c", "userID": 12089754, "postDate": "2026-10-06"}
        pages = {
            1: {"status": True, "dto": {"pageNum": 2, "listTopic": [topic_a]}},
            2: {"status": True, "dto": {"pageNum": 3, "listTopic": [topic_b]}},
            3: {"status": True, "dto": {"pageNum": 3, "listTopic": [topic_c]}},
        }
        requested = []

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def json(self):
                return self.payload

        def get(url):
            requested.append(url)
            page = int(url.rsplit("pageNo=", 1)[1])
            return Response(pages[page])

        topics, page_count = fetch_topics(get)

        self.assertEqual([topic["newTopicID"] for topic in topics], ["a", "b", "c"])
        self.assertEqual(page_count, 3)
        self.assertEqual(len(requested), 3)
        self.assertTrue(requested[-1].endswith("pageNo=3"))

    def test_fetch_topics_rejects_wrong_author_on_later_page(self):
        pages = [
            {"status": True, "dto": {"pageNum": 2, "listTopic": [
                {"newTopicID": "a", "userID": 12089754},
            ]}},
            {"status": True, "dto": {"pageNum": 2, "listTopic": [
                {"newTopicID": "foreign", "userID": 99},
            ]}},
        ]

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def json(self):
                return self.payload

        with self.assertRaisesRegex(ValueError, "Unexpected author"):
            fetch_topics(lambda url: Response(pages[int(url.rsplit("pageNo=", 1)[1]) - 1]))

    def test_fetch_topics_rejects_incomplete_feed_page(self):
        pages = [
            {"status": True, "dto": {"pageNum": 2, "listTopic": [
                {"newTopicID": "a", "userID": 12089754},
            ]}},
            {"status": True, "dto": {"pageNum": 2, "listTopic": []}},
        ]

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def json(self):
                return self.payload

        with self.assertRaisesRegex(ValueError, "page 2"):
            fetch_topics(lambda url: Response(pages[int(url.rsplit("pageNo=", 1)[1]) - 1]))

    def test_pending_items_survive_reruns_until_distillation_is_recorded(self):
        post = {
            "id": "thread-1", "title": "topic", "date": "2026-10-08",
            "url": "https://example.test/thread-1", "sha256": "body-v1",
            "author_replies": [
                {"id": "reply-1", "date": "26-10-08 10:00", "text": "new author reply"},
            ],
        }

        first_run = pending_items([post], {})
        second_run = pending_items([post], {})

        self.assertEqual(second_run, first_run)
        self.assertEqual(len(second_run), 1)
        self.assertTrue(second_run[0]["body_pending"])
        self.assertEqual(second_run[0]["reply_ids"], ["reply-1"])

        successful_state = {"processed_posts": {
            "thread-1": {"sha256": "body-v1", "reply_ids": ["reply-1"],
                         "reply_hashes": {"reply-1": reply_digest(post["author_replies"][0])}},
        }}
        self.assertEqual(pending_items([post], successful_state), [])

    def test_pending_items_uses_successful_state_for_reply_deduplication(self):
        old_reply = {"id": "reply-old", "date": "26-10-07 10:00", "text": "already distilled"}
        new_reply = {"id": "reply-new", "date": "26-10-08 10:00", "text": "new reply"}
        post = {
            "id": "thread-old", "title": "old topic", "date": "2026-09-20",
            "url": "https://example.test/thread-old", "sha256": "body-v1",
            "author_replies": [old_reply, new_reply],
        }
        state = {"processed_posts": {
            "thread-old": {"sha256": "body-v1", "reply_ids": ["reply-old"],
                           "reply_hashes": {"reply-old": reply_digest(old_reply)}},
        }}

        pending = pending_items([post], state)

        self.assertEqual(len(pending), 1)
        self.assertFalse(pending[0]["body_pending"])
        self.assertEqual(pending[0]["reply_ids"], ["reply-new"])

    def test_baseline_old_post_is_not_new_main_post(self):
        old_post = {
            "id": "old-thread", "title": "old topic", "date": "2026-09-20",
            "url": "https://example.test/old-thread", "sha256": "body-v1",
            "author_replies": [],
        }

        self.assertEqual(pending_items([old_post], {}), [])


if __name__ == "__main__":
    unittest.main()
