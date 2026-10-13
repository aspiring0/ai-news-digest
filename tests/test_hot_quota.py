"""热榜多样性配额：get_hot 每源最多 max_per_source 条。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db


def _now():
    return datetime.now(timezone.utc)


def test_get_hot_caps_per_source(clean_db):
    """同一来源即使包揽最高分，最多也只占 4 席。"""
    rows = []
    # HuggingFace 6 条高分新条目（衰减前 72 起）
    for i in range(6):
        rows.append({
            "url": f"https://hf.example/{i}", "title": f"HF 高分条目 {i}",
            "source_name": "HuggingFace", "published_at": _now() - timedelta(minutes=10),
            "fetched_at": _now(), "score": 72.0 - i,
        })
    # AIHOT 3 条中分条目
    for i in range(3):
        rows.append({
            "url": f"https://aihot.example/{i}", "title": f"AIHOT 条目 {i}",
            "source_name": "AIHOT", "published_at": _now() - timedelta(hours=2),
            "fetched_at": _now(), "score": 66.0 - i * 2,
        })
    # 其他来源 2 条
    for i in range(2):
        rows.append({
            "url": f"https://other.example/{i}", "title": f"其他条目 {i}",
            "source_name": "量子位", "published_at": _now() - timedelta(hours=1),
            "fetched_at": _now(), "score": 64.0 - i * 2,
        })
    db.insert_items(rows)

    hot = db.get_hot(limit=20)
    from collections import Counter
    comp = Counter(i["source_name"] for i in hot)
    assert comp["HuggingFace"] == 4, f"HuggingFace 应被配额限制为 4，实际 {comp['HuggingFace']}"
    assert comp["AIHOT"] == 3
    assert comp["量子位"] == 2
    assert len(hot) == 9
    # 榜单仍按热度倒序
    scores = [i["hot_score"] for i in hot]
    assert scores == sorted(scores, reverse=True)


def test_get_hot_quota_disabled_for_large_limit(clean_db):
    """limit 足够大时不丢数据（配额只影响榜单展示，不删库）。"""
    rows = [{
        "url": f"https://x.example/{i}", "title": f"条目 {i}",
        "source_name": "单源", "published_at": _now() - timedelta(minutes=i),
        "fetched_at": _now(), "score": 70.0,
    } for i in range(8)]
    db.insert_items(rows)
    hot = db.get_hot(limit=20, max_per_source=99)
    assert len(hot) == 8
