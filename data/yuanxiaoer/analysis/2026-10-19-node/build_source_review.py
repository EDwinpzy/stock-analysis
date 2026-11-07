"""Reproduce the source inventory for this bounded analysis, without archival-state writes."""
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = OUT.parents[1]
TZ = dt.timezone(dt.timedelta(hours=8))

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

NODE = set("103863577 103868749 103868957 103871438 103880882 103881088 103881738 103883622 103890828 103891404".split())
PLAN = {"103862113", "103870823"}
SHAPE = {"103853033", "103853615", "103855366", "103856024"}
CONTEXT = {
    "103856475": "确认天津乙醇汽油，与交易无关，不能当作认可买点",
    "103858122": "读者问旧周期结束后电池与染料预期降低；本人肯定，属条件语境",
    "103859283": "未发酵方向可作趋势观察，未等于节点确认或买入",
    "103881706": "华正新材未涨停的反问；支持关注主动性，不推导为所有股票必须涨停",
    "103886143": "读者买银行后的调侃，不能当成推荐买新华",
    "103886613": "低吸用词被平台拦截的对话，不能当成卖出某股",
    "103891404": "浏览器引文确认代词指PCB，不能错配为ETF或银行",
    "103880657": "本人转述小作文及拉升现象；不验证小作文事实、不当成推荐",
}

def main():
    run = json.loads((BASE / "latest_run.json").read_text(encoding="utf-8"))
    state = json.loads((BASE / "distillation_state.json").read_text(encoding="utf-8"))
    posts, replies = [], []
    for path in sorted((BASE / "posts").glob("*.json")):
        p = json.loads(path.read_text(encoding="utf-8"))
        assert str(p["author_id"]) == "12089754"
        selected = [r for r in p.get("author_replies", []) if r["date"].startswith(("26-10-18", "26-10-19", "2026-10-18", "2026-10-19"))]
        in_window = p["date"].startswith(("2026-10-18", "2026-10-19"))
        if in_window or selected:
            posts.append({k: p.get(k) for k in ("id", "topic_id", "author_id", "title", "date", "url", "sha256", "fetched_at", "replies_complete", "replies_complete_since")})
        if in_window:
            posts[-1].update(main_post_in_window=True, text=p["text"], images=p["images"])
        for r in selected:
            rid = r["id"]
            kind = "node_framework" if rid in NODE else "operation_self_report" if rid in PLAN else "244_shape_separate" if rid in SHAPE else "context_only"
            replies.append({**r, "post_id": p["id"], "author_id": "12089754", "stable_url": f"https://www.tgb.cn/a/{p['id']}/{rid}#{rid}", "review_category": kind,
                "review_conclusion": CONTEXT.get(rid, "纳入周期/节点推理，性质和时间见报告" if rid in NODE else "作者计划或自述，未经成交验证" if rid in PLAN else "244形态规则单列，不与节点择时混用" if rid in SHAPE else "已审阅并保留；没有独立、可用于本次节点筛选的明确条件，不据此增加规则"),
                "review_content_sha256": digest({k: r.get(k) for k in ("id", "date", "text", "images")})})
    replies.sort(key=lambda r: (r["date"], r["id"]))
    assert len(replies) == len({r["id"] for r in replies}) == 90
    assert sum(bool(p.get("main_post_in_window")) for p in posts) == 1
    assert run["feed_complete"] and not run["errors"]
    manifest = json.loads((OUT / "image_manifest.json").read_text(encoding="utf-8"))
    for img in manifest:
        assert hashlib.sha256(Path(img["path"]).read_bytes()).hexdigest() == img["byte_sha256"]
        name = Path(img["path"]).name
        finding = "已逐张查看；非交易内容（标志/致谢）"
        if "8aosy2" in name:
            finding = "作者情绪统计截图；周一至周五为10/12–16，非10/13–17；自制温度非独立指标"
        elif "r4l01" in name or "be9roc" in name:
            finding = "日/周浪型图可见；小字分辨率不足，不恢复精确隐藏阈值或编码公式"
        elif "lifsb" in name:
            finding = "9月节点日历可见；日期与颜色不证明预测算法或事前发布时间"
        elif "bhvry" in name:
            finding = "10月节点日历可见；10/20–23灰色遮挡，不推断隐藏日期或未来节点"
        elif "wspbj" in name:
            finding = "159915创业板ETF公开行情截图；不证明成交或账户归属"
        elif "plm8" in name:
            finding = "低吸用词平台拦截截图；非具体卖出指令，背景仍有遮挡日历"
        img.update(visual_reviewed=True, finding=finding)
    result = {"scope": "2026-10-18 00:00–2026-10-19 18:37:10 Asia/Shanghai，可见公开原文及本人回复；不含付费或平台隐藏内容", "analysis_written_at": dt.datetime.now(TZ).isoformat(),
        "collection_checked_at": run["checked_at"], "feed_pages": run["feed_pages"], "feed_topics": run["feed_topics"], "feed_complete": run["feed_complete"], "errors": run["errors"],
        "browser_review": "作者主帖列表、本人回复列表1–2页（第2页越过到10/17）；最新帖评论1–5页、旧帖目标回复页，按作者DOM过滤且复核引用语境；未购买只看楼主功能",
        "main_post_count": 1, "own_reply_count": len(replies), "reply_counts_by_date": dict(Counter(r["date"][:8] for r in replies)), "latest_own_reply": replies[-1]["date"],
        "hash_recipe": "review_content_sha256=SHA256(UTF8 JSON{id,date,text,images},sort_keys=True,ensure_ascii=False,compact separators); byte_sha256为附件实际字节哈希，不等于采集器URL列表哈希", "posts": posts, "replies": replies, "images": manifest,
        "limits": ["两张原文浪型图小字无法完整辨认", "节点日历未来日期遮挡且全年节点计算公式未公开", "未用盘后数据回填盘中可知性，作者盘中统计不冒充收盘值", "旧帖历史待处理范围不在本报告中清空"],
        "archival_success_boundary_preserved": state["last_distilled_at"], "archival_state_changed": False, "latest_md_changed": False, "rule_evidence": "本期原文规则为仅语料；实际案例为部分支持，未证明普遍选股超额"}
    (OUT / "source_review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("main_post_count", "own_reply_count", "reply_counts_by_date", "latest_own_reply", "collection_checked_at", "archival_success_boundary_preserved")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
