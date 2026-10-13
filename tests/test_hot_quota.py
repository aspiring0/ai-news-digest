"""热榜多样性配额 + 分页：get_hot 每源最多 max_per_source 条，支持翻页。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db


def _now():
    return datetime.now(timezone.utc)


def _row(url, source, score, age_min, title):
    return {
        "url": url, "title": title, "source_name": source,
        "published_at": _now() - timedelta(minutes=age_min),
        "fetched_at": _now(), "score": score,
    }


def test_get_hot_caps_per_source(clean_db):
    """同一来源即使包揽最高分，最多也只占 4 席。"""
    rows = [_row(f"https://hf.example/{i}", "HuggingFace", 72.0 - i, 10, f"HF {i}") for i in range(6)]
    rows += [_row(f"https://aihot.example/{i}", "AIHOT", 66.0 - i * 2, 120, f"AIHOT {i}") for i in range(3)]
    rows += [_row(f"https://other.example/{i}", "量子位", 64.0 - i * 2, 60, f"其他 {i}") for i in range(2)]
    db.insert_items(rows)

    hot, total = db.get_hot(page=1, per_page=20)
    from collections import Counter
    comp = Counter(i["source_name"] for i in hot)
    assert comp["HuggingFace"] == 4, f"HuggingFace 应被配额限制为 4，实际 {comp['HuggingFace']}"
    assert comp["AIHOT"] == 3
    assert comp["量子位"] == 2
    assert len(hot) == 9 and total == 9
    scores = [i["hot_score"] for i in hot]
    assert scores == sorted(scores, reverse=True)


def test_get_hot_pagination(clean_db):
    """配额后的完整榜单支持翻页：page1=20 条，page2=余量。"""
    rows = []
    for s in range(6):  # 6 个来源 × 5 条 = 30 条，配额后 6×4=24 条
        for i in range(5):
            rows.append(_row(f"https://s{s}/item{i}", f"来源{s}", 70.0 - i, 10 + s, f"条目 s{s}-{i}"))
    db.insert_items(rows)

    p1, total = db.get_hot(page=1, per_page=20)
    p2, _ = db.get_hot(page=2, per_page=20)
    assert total == 24
    assert len(p1) == 20 and len(p2) == 4
    assert p1[-1]["hot_score"] >= p2[0]["hot_score"]  # 跨页仍是热度倒序
    p9, _ = db.get_hot(page=99, per_page=20)
    assert p9 == []


def test_get_hot_quota_disabled_for_large_limit(clean_db):
    """per_page 足够大时不丢数据（配额只影响榜单展示，不删库）。"""
    rows = [_row(f"https://x.example/{i}", "单源", 70.0, i, f"条目 {i}") for i in range(8)]
    db.insert_items(rows)
    hot, total = db.get_hot(page=1, per_page=20, max_per_source=99)
    assert len(hot) == 8 and total == 8
