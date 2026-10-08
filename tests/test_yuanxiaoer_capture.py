import unittest

from tools.fetch_yuanxiaoer_posts import (
    fetch_topics,
    parse_post,
    pending_items,
    image_digest,
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

    def test_pending_items_flags_unreviewed_post_images_until_hash_is_recorded(self):
        images = ["https://image.tgb.cn/img/chart.png"]
        post = {
            "id": "image-thread", "title": "topic", "date": "2026-10-08",
            "url": "https://example.test/image-thread", "sha256": "body-v1",
            "images": images, "author_replies": [],
        }
        state = {"processed_posts": {"image-thread": {"sha256": "body-v1"}}}

        pending = pending_items([post], state)

        self.assertEqual(len(pending), 1)
        self.assertFalse(pending[0]["body_pending"])
        self.assertTrue(pending[0]["image_pending"])
        self.assertEqual(pending[0]["post_image_sha256"], image_digest(images))
        self.assertEqual(pending[0]["unreviewed_images"], [{
            "location": "post", "reply_id": None, "urls": images,
            "sha256": image_digest(images), "status": "available",
        }])

        state["processed_posts"]["image-thread"]["post_image_sha256"] = image_digest(images)
        self.assertEqual(pending_items([post], state), [])

    def test_archived_post_image_revision_reopens_pending_work(self):
        old_images = ["https://image.tgb.cn/img/old.png"]
        revised_images = ["https://image.tgb.cn/img/new.png"]
        post = {
            "id": "archived-thread", "title": "old topic", "date": "2025-01-01",
            "url": "https://example.test/archived-thread", "sha256": "body-v1",
            "images": revised_images, "author_replies": [],
        }
        state = {"processed_posts": {"archived-thread": {
            "sha256": "body-v1", "post_image_sha256": image_digest(old_images),
        }}}

        pending = pending_items([post], state)

        self.assertEqual(len(pending), 1)
        self.assertFalse(pending[0]["body_pending"])
        self.assertTrue(pending[0]["image_pending"])
        self.assertEqual(pending[0]["unreviewed_images"][0]["urls"], revised_images)

    def test_archived_post_image_removal_reopens_pending_work(self):
        post = {
            "id": "archived-thread", "title": "old topic", "date": "2025-01-01",
            "url": "https://example.test/archived-thread", "sha256": "body-v1",
            "images": [], "author_replies": [],
        }
        state = {"processed_posts": {"archived-thread": {
            "sha256": "body-v1", "post_image_sha256": image_digest(["https://image.tgb.cn/img/old.png"]),
        }}}

        pending = pending_items([post], state)

        self.assertTrue(pending[0]["image_pending"])
        self.assertEqual(pending[0]["post_image_sha256"], image_digest([]))
        self.assertEqual(pending[0]["unreviewed_images"][0]["status"], "removed")

    def test_archived_reply_revision_reopens_pending_work(self):
        old_reply = {"id": "reply-old", "date": "25-01-01 10:00", "text": "old wording"}
        revised_reply = {"id": "reply-old", "date": "25-01-01 10:00", "text": "revised wording"}
        post = {
            "id": "archived-thread", "title": "old topic", "date": "2025-01-01",
            "url": "https://example.test/archived-thread", "sha256": "body-v1",
            "author_replies": [revised_reply],
        }
        state = {"processed_posts": {"archived-thread": {
            "sha256": "body-v1", "reply_ids": ["reply-old"],
            "reply_hashes": {"reply-old": reply_digest(old_reply)},
        }}}

        pending = pending_items([post], state)

        self.assertEqual(pending[0]["reply_ids"], ["reply-old"])

    def test_archived_reply_image_revision_is_listed_for_review(self):
        old_images = ["https://image.tgb.cn/img/old.png"]
        revised_images = ["https://image.tgb.cn/img/new.png"]
        reply = {"id": "reply-old", "date": "25-01-01 10:00", "text": "reply",
                 "images": revised_images}
        post = {
            "id": "archived-thread", "title": "old topic", "date": "2025-01-01",
            "url": "https://example.test/archived-thread", "sha256": "body-v1",
            "author_replies": [reply],
        }
        state = {"processed_posts": {"archived-thread": {
            "sha256": "body-v1", "reply_ids": ["reply-old"],
            "reply_hashes": {"reply-old": reply_digest(reply)},
            "reply_image_sha256": {"reply-old": image_digest(old_images)},
        }}}

        pending = pending_items([post], state)

        self.assertEqual(pending[0]["reply_ids"], ["reply-old"])
        self.assertEqual(pending[0]["unreviewed_images"][0]["location"], "reply")
        self.assertEqual(pending[0]["unreviewed_images"][0]["urls"], revised_images)

    def test_archived_reply_image_removal_reopens_pending_work(self):
        reply = {"id": "reply-old", "date": "25-01-01 10:00", "text": "reply", "images": []}
        post = {
            "id": "archived-thread", "title": "old topic", "date": "2025-01-01",
            "url": "https://example.test/archived-thread", "sha256": "body-v1",
            "author_replies": [reply],
        }
        state = {"processed_posts": {"archived-thread": {
            "sha256": "body-v1", "reply_ids": ["reply-old"],
            "reply_hashes": {"reply-old": reply_digest(reply)},
            "reply_image_sha256": {"reply-old": image_digest(["https://image.tgb.cn/img/old.png"])},
        }}}

        pending = pending_items([post], state)

        self.assertEqual(pending[0]["reply_ids"], ["reply-old"])
        self.assertEqual(pending[0]["reply_image_sha256"]["reply-old"], image_digest([]))
        self.assertEqual(pending[0]["unreviewed_images"][0]["status"], "removed")

    def test_pending_items_reopens_reviewed_reply_when_attachment_hash_changes(self):
        first_images = ["https://image.tgb.cn/img/first.png"]
        changed_images = ["https://image.tgb.cn/img/second.png"]
        reply = {"id": "reply-1", "date": "26-10-08 10:00", "text": "reply",
                 "images": changed_images}
        post = {
            "id": "old-thread", "title": "old topic", "date": "2025-01-01",
            "url": "https://example.test/old-thread", "sha256": "body-v1",
            "images": [], "author_replies": [reply],
        }
        state = {"processed_posts": {"old-thread": {
            "sha256": "body-v1", "reply_ids": ["reply-1"],
            "reply_hashes": {"reply-1": reply_digest(reply)},
            "reply_image_sha256": {"reply-1": image_digest(first_images)},
        }}}

        pending = pending_items([post], state)

        self.assertEqual(pending[0]["reply_ids"], ["reply-1"])
        self.assertEqual(pending[0]["reply_image_ids"], ["reply-1"])
        self.assertEqual(pending[0]["reply_image_sha256"]["reply-1"], image_digest(changed_images))

    def test_static_face_avatars_do_not_create_image_pending_work(self):
        post = {
            "id": "avatar-thread", "title": "topic", "date": "2026-10-08",
            "url": "https://example.test/avatar-thread", "sha256": "body-v1",
            "images": ["https://css.tgb.cn/images/face/012.png"],
            "author_replies": [{"id": "reply-avatar", "date": "26-10-08 10:00",
                                "text": "reply", "images": ["https://css.tgb.cn/images/face/013.png"]}],
        }
        state = {"processed_posts": {"avatar-thread": {
            "sha256": "body-v1", "reply_ids": ["reply-avatar"],
            "reply_hashes": {"reply-avatar": reply_digest(post["author_replies"][0])},
        }}}

        self.assertEqual(pending_items([post], state), [])


if __name__ == "__main__":
    unittest.main()
