"""故事合并：实体提取 / 聚类 / 多源加成 / 热榜故事分页。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db
from app.stories import extract_entities, group_stories, story_score


def _now():
    return datetime.now(timezone.utc)


def _item(url, title, source, hours_ago=1.0, score=66.0):
    return {
        "url": url, "title": title, "source_name": source,
        "published_at": _now() - timedelta(hours=hours_ago),
        "fetched_at": _now(), "score": score,
    }


# ---------------- 实体提取 ----------------

def test_extract_entities_filters_stopwords():
    ents = extract_entities("Meta releases its first frontier model, Muse Wonder")
    assert "muse" in ents and "wonder" in ents and "meta" in ents
    assert "releases" not in ents and "first" not in ents and "model" not in ents


def test_extract_entities_from_mixed_cn_en_title():
    ents = extract_entities("Meta 发布 Muse Wonder 系列前沿模型，登陆 Agent Arena")
    assert "muse" in ents and "wonder" in ents and "arena" in ents


def test_extract_entities_ignores_versions_and_short():
    ents = extract_entities("Claude 4.5 and GPT-5.1 bump: a 3.1 fix for Sam")
    assert "claude" in ents and "sam" in ents
    assert "4.5" not in ents and "3.1" not in ents and "and" not in ents


# ---------------- 聚类 ----------------

def test_muse_story_merges_across_languages_and_sources():
    """真实撞车样例：同一事件的中英文标题应聚成一个故事。"""
    items = [
        _item("https://a/1", "Meta 发布 Muse Wonder 系列前沿模型，登陆 Agent Arena", "AIHOT", 1, 66),
        _item("https://t/1", "Meta releases its first frontier model, Muse Wonder", "TechCrunch AI", 2, 64),
        _item("https://s/1", "OpenAI ships rival to Meta's Muse", "Superhuman", 3, 62),
        _item("https://x/1", "量子位独家：国产固态电池量产", "量子位", 2, 60),  # 无关
    ]
    stories = group_stories(items)
    assert len(stories) == 2, f"应聚成 2 个故事，实际 {len(stories)}"
    muse = max(stories, key=lambda s: len(s["members"]))
    assert len(muse["members"]) == 3, f"Muse 事件应合并 3 条，实际 {len(muse['members'])}"
    assert set(muse["sources"]) == {"AIHOT", "TechCrunch AI", "Superhuman"}
    assert muse["representative"]["url"] == "https://a/1"  # 最高分作代表


def test_cluster_respects_time_window():
    old = _item("https://old/1", "Muse Wonder launch event roundup", "A", hours_ago=100, score=70)
    new = _item("https://new/1", "Muse Wonder updated pricing announced", "B", hours_ago=1, score=66)
    stories = group_stories([old, new], window_hours=48)
    assert len(stories) == 2, "超出时间窗的同实体条目不应合并"


def test_two_entities_required():
    """只共享 1 个泛实体的两条不应合并。"""
    a = _item("https://a/2", "OpenAI announces new safety team", "A", 1)
    b = _item("https://b/2", "OpenAI rival raises funding round", "B", 2)
    stories = group_stories([a, b])
    assert len(stories) == 2, "共享单个实体（openai）不足以合并"


# ---------------- 多源加成 ----------------

def test_story_score_multi_source_bonus():
    items = [
        _item("https://a/3", "Muse Wonder debut, Muse Wonder specs", "A", 1, score=60.0),
    ]
    one = group_stories(items)[0]
    hot = one["representative"]["score"]
    assert abs(story_score(one) - hot) < 1e-6  # 单源无加成

    many = {**one, "sources": ["A", "B", "C", "D"]}
    assert abs(story_score(many) - hot * 1.45) < 1e-6  # 3 次额外源 ×15%


# ---------------- 热榜（故事级）分页与配额 ----------------

def test_get_hot_stories_quota_and_pagination(clean_db):
    rows = []
    # 故事 1：四源报道同一事件（Muse Wonder）
    for i, (src, u) in enumerate([("AIHOT", "m1"), ("TLDR AI", "m2"), ("Superhuman", "m3"), ("TechCrunch AI", "m4")]):
        rows.append(_item(f"https://{u}/{i}", f"Muse Wonder rollout hits milestone {i}", src, 1 + i, 66.0 - i))
    # 无关条目 ×2
    rows.append(_item("https://z/1", "量子位独家：固态电池产线投产", "量子位", 2, 64))
    rows.append(_item("https://z/2", "Kernel panic 分析指南", "Hacker News AI", 3, 62))
    db.insert_items(rows)

    page1, total = db.get_hot_stories(page=1, per_page=2)
    assert total == 3  # 1 个故事 + 2 条独立
    assert len(page1) == 2
    first = page1[0]
    assert first["_story"]["count"] == 4 and first["_story"]["sources"][0] == "AIHOT"
    # 多源加成让四源故事排最前
    assert "Muse" in first["title"]
    page2, _ = db.get_hot_stories(page=2, per_page=2)
    assert len(page2) == 1


def test_get_hot_stories_per_source_quota(clean_db):
    """故事级配额：同一来源的故事最多占 4 席（用代表条目的来源计）。"""
    rows = []
    for s in range(6):  # 6 个互不相同的故事（每条标题只含专属实体词），全部来自 AIHOT
        rows.append(_item(f"https://h/{s}", f"Kepler{s} Nova{s}", "AIHOT", 1 + s, 70.0 - s))
    db.insert_items(rows)
    page, total = db.get_hot_stories(page=1, per_page=20)
    # 配额后只剩 4 个可见故事（total 也是配额后口径，分页器不撒谎）
    assert total == 4
    assert len(page) == 4
    from collections import Counter
    comp = Counter(it["source_name"] for it in page)
    assert comp["AIHOT"] == 4, f"故事级配额应限 4，实际 {comp['AIHOT']}"
