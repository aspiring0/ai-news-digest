"""头条（top1）特殊处理：中文代表优先 + lead 内联摘要。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db
from app.stories import group_stories


def _now():
    return datetime.now(timezone.utc)


def _row(url, title, source, hours_ago, score):
    return {
        "url": url, "title": title, "source_name": source,
        "published_at": _now() - timedelta(hours=hours_ago),
        "fetched_at": _now(), "score": score,
    }


# ---------------- 1. 故事代表优先中文标题 ----------------

def test_representative_prefers_chinese_title():
    """英文条目分数更高时，代表仍应选中文标题成员（用户看得懂）。"""
    items = [
        _row("https://en/1", "Meta releases its first frontier model Muse Wonder", "TechCrunch AI", 1, 66),
        _row("https://cn/1", "Meta 发布 Muse Wonder 系列前沿模型", "AIHOT", 2, 64),
    ]
    st = group_stories(items)[0]
    assert st["representative"]["url"] == "https://cn/1", "代表应选中文标题条目"


def test_representative_falls_back_to_best_when_all_english():
    items = [
        _row("https://a/1", "OpenAI ships GPT update", "TLDR AI", 1, 66),
        _row("https://b/1", "GPT update reactions pour in", "Superhuman", 2, 64),
    ]
    stories = group_stories(items)
    reps = [s["representative"]["url"] for s in stories]
    assert "https://a/1" in reps  # 全英文时回到最高分


def test_chinese_representative_keeps_highest_score_within_chinese():
    items = [
        _row("https/cn-low/1".replace("/", ""), "量子位中文低分报道 Muse Wonder", "量子位", 3, 60),
        _row("https://cn/1", "Meta 发布 Muse Wonder 系列", "AIHOT", 2, 64),
    ]
    items[0]["url"] = "https://cn-low/1"
    st = group_stories(items)[0]
    assert st["representative"]["url"] == "https://cn/1", "中文成员里仍选最高分"


# ---------------- 2. 热榜路由注入 lead 摘要 ----------------

def _clean_items():
    """client fixture 共享库：先清空条目，避免其他测试残留抢占 top1。"""
    with db._connect() as conn:
        conn.execute("DELETE FROM news_items")


def test_hot_page_inlines_cached_summary(client):
    """top1 有摘要缓存时，lead 区应内联中文解释段落。"""
    _clean_items()
    db.insert_items([_row("https://top/1", "头条故事 Kepler Nova 事件", "AIHOT", 1, 90)])
    db.save_summary(
        "https://top/1",
        {"core": "一句话核心：测试事件", "plain": "这是为什么重要的解释段落，模型生成的中文内容。", "details": "", "link": "https://top/1"},
        provider_id="deepseek", model="deepseek-chat",
    )
    html = client.get("/hot").text
    assert "这是为什么重要的解释段落" in html, "lead 应内联缓存的 plain 摘要"
    assert "一句话核心：测试事件" in html


def test_hot_page_without_summary_keeps_guide_button(client):
    """无缓存时 lead 不内联摘要，仍显示引导按钮。"""
    _clean_items()
    db.insert_items([_row("https://top/2", "无摘要的故事 Kepler Beta", "AIHOT", 1, 90)])
    html = client.get("/hot").text
    assert "为什么重要 · 点开 AI 解读" in html
