"""Archive public Yuanxiaoer posts and author replies for daily distillation."""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

USER_ID = 12089754
ROOT = Path(__file__).resolve().parents[1] / "data" / "yuanxiaoer"
TZ = timezone(timedelta(hours=8))
BASELINE = "2026-09-25"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def fetch_topics(get):
    """Enumerate every author-feed page; never assume page 1 is the whole feed."""
    topics, seen = [], set()
    page, page_count = 1, 1
    while page <= page_count:
        feed = get(f"https://m.tgb.cn/mBlogTopicAjax?userID={USER_ID}&sortFlag=W&pageNo={page}").json()
        dto = feed.get("dto", {})
        rows = dto.get("listTopic")
        if feed.get("status") is not True or not rows:
            raise ValueError(f"Invalid or empty author feed page {page}")
        page_count = max(page_count, int(dto.get("pageNum", 1)))
        if any(t.get("userID") != USER_ID for t in rows):
            raise ValueError(f"Unexpected author in feed page {page}")
        for topic in rows:
            if topic["newTopicID"] not in seen:
                seen.add(topic["newTopicID"])
                topics.append(topic)
        page += 1
    return topics, page_count


def reply_digest(reply):
    return hashlib.sha256(json.dumps({"text": reply["text"], "images": reply.get("images", [])},
                                    ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def pending_items(posts, state, baseline=BASELINE):
    """Only successful distillation acknowledgements can remove pending work."""
    pending = []
    done = state.get("processed_posts", {})
    for post in posts:
        previous = done.get(post["id"], {})
        body_pending = (post["date"][:10] >= baseline or bool(previous)) and previous.get("sha256") != post["sha256"]
        replies = []
        for reply in post["author_replies"]:
            date = "20" + reply["date"][:8] if len(reply["date"]) > 2 and reply["date"][2] == "-" else reply["date"][:10]
            if date < baseline:
                continue
            hashes = previous.get("reply_hashes", {})
            if reply["id"] not in previous.get("reply_ids", []) or (reply["id"] in hashes and hashes[reply["id"]] != reply_digest(reply)):
                replies.append(reply["id"])
        if body_pending or replies:
            pending.append({"id": post["id"], "title": post["title"], "date": post["date"],
                            "url": post["url"], "body_pending": body_pending, "reply_ids": replies,
                            "body_sha256": post["sha256"]})
    return pending


def parse_post(html, topic):
    soup = BeautifulSoup(html, "html.parser")
    author = soup.select_one("#ztgioMsg")
    body = soup.select_one(".tzitem_text")
    if not author or author.get("userid") != str(USER_ID) or not body:
        raise ValueError("Missing public body or unexpected author")
    for node in body.select(".topic-reward, script, style"):
        node.decompose()
    text = body.get_text("\n", strip=True)
    if len(text) < 200:
        raise ValueError("Body too short; possible preview or access restriction")
    replies = []
    for item in soup.select(".plItem"):
        marker = item.select_one('[userid="12089754"][contentid]')
        content, date = item.select_one(".pl_text"), item.select_one(".pl_time")
        if marker and content and date:
            replies.append({"id": marker["contentid"], "date": date.get_text(strip=True),
                            "text": content.get_text("\n", strip=True),
                            "images": [img.get("data-original", img.get("src")) for img in content.select("img")]})
    result = {"id": topic["newTopicID"], "topic_id": topic["topicID"],
              "author_id": USER_ID, "title": topic["subject"], "date": topic["postDate"],
              "url": "https://m.tgb.cn/a/" + topic["newTopicID"], "text": text,
              "images": [img.get("data-original", img.get("src")) for img in body.select("img")],
              "sha256": hashlib.sha256(text.encode()).hexdigest()}
    next_page = next((a.get("href") for a in soup.select("a[href]") if a.get_text(strip=True) == "下一页"), None)
    return result, replies, next_page


def collect(since, max_pages=120):
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    def get(url):
        response = session.get(url, timeout=25)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response
    topics, feed_pages = fetch_topics(get)
    now = datetime.now(TZ).isoformat()
    changes, errors = [], []
    for topic in topics:
        if topic["lastReplyDate"][:10] < since and topic["postDate"][:10] < since:
            continue
        tid = topic["newTopicID"]
        path = ROOT / "posts" / (tid + ".json")
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        try:
            url = "https://m.tgb.cn/a/" + tid + "?type=new"
            replies = {r["id"]: r for r in previous.get("author_replies", [])}
            post = None
            complete = False
            for page in range(max_pages):
                response = get(url)
                current, found, next_page = parse_post(response.text, topic)
                if post is None:
                    post = current
                for reply in found:
                    reply["source_url"] = url
                    replies[reply["id"]] = reply
                archive = ROOT / "raw" / datetime.now(TZ).date().isoformat() / (tid + f"-{page + 1}.html")
                archive.parent.mkdir(parents=True, exist_ok=True)
                archive.write_text(response.text, encoding="utf-8")
                scope_covers_since = previous.get("replies_complete_since", "0000-00-00") <= since
                if page == 0 and previous.get("replies_complete") and scope_covers_since and previous.get("last_reply_date") == topic["lastReplyDate"]:
                    complete = True
                    break
                if not next_page:
                    complete = True
                    break
                dates = [node.get_text(strip=True)[:8] for node in BeautifulSoup(response.text, "html.parser").select(".pl_time")]
                if dates and max("20" + date for date in dates) < since:
                    complete = True
                    break
                url = requests.compat.urljoin(url, next_page)
                time.sleep(0.2)
            post.update(author_replies=list(replies.values()), fetched_at=now, replies_complete=complete,
                        images_reviewed=False, text_access="public_body", last_reply_date=topic["lastReplyDate"],
                        replies_complete_since=since)
            new_reply_ids = sorted(set(replies) - {r["id"] for r in previous.get("author_replies", [])})
            if post["sha256"] != previous.get("sha256") or new_reply_ids:
                changes.append({"id": tid, "title": post["title"], "date": post["date"],
                                "url": post["url"], "new_reply_ids": new_reply_ids,
                                "body_changed": post["sha256"] != previous.get("sha256")})
            if previous and post["sha256"] != previous.get("sha256"):
                write_json(ROOT / "versions" / tid / (previous["sha256"] + ".json"), previous)
            write_json(path, post)
            if not complete:
                errors.append({"id": tid, "error": "Reply pagination limit reached; partial coverage"})
        except Exception as error:
            errors.append({"id": tid, "error": str(error)})
    posts = [json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "posts").glob("*.json")]
    state_path = ROOT / "distillation_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    pending = pending_items(posts, state)
    write_json(ROOT / "pending_distillation.json", {"checked_at": now, "baseline": BASELINE, "items": pending})
    result = {"checked_at": now, "since": since, "feed_scope": "All author-feed pages; new main posts and recent activity in old threads",
              "feed_pages": feed_pages, "feed_topics": len(topics), "feed_complete": True,
              "latest_post_date": max(t["postDate"] for t in topics), "changes": changes, "errors": errors,
              "pending_distillation": pending,
              "status": "partial" if errors else "success"}
    write_json(ROOT / "latest_run.json", result)
    return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    default_since = BASELINE
    state_path = ROOT / "distillation_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        default_since = min((datetime.now(TZ) - timedelta(days=14)).date().isoformat(), state["last_distilled_at"][:10])
    parser.add_argument("--since", default=default_since)
    parser.add_argument("--max-pages", type=int, default=120)
    args = parser.parse_args()
    try:
        report = collect(args.since, args.max_pages)
    except Exception as error:
        report = {"checked_at": datetime.now(TZ).isoformat(), "status": "failed", "errors": [str(error)]}
        write_json(ROOT / "latest_run.json", report)
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "success" else 1)
