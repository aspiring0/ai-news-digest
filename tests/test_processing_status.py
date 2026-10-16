"""B1 条目级 processing_status + B2 来源级三态（/api/sources/health v2）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app import db


def _row(url, title, source, score=66.0):
    now = datetime.now(timezone.utc)
    return {"url": url, "title": title, "source_name": source,
            "published_at": now, "fetched_at": now, "score": score}


# ---------------- B1：条目级 processing_status ----------------

def test_pending_for_untranslated_english(clean_db):
    db.insert_items([
        _row("https://p/1", "Some English Headline Needs Translation", "S"),
        _row("https://p/2", "中文标题无需翻译", "S"),
        _row("https://p/3", "Already Translated English Headline", "S"),
        _row("https://p/4", "v2.5", "S"),  # 无 3+ 拉丁词，不算待整理
    ])
    with db._connect() as conn:  # 模拟翻译完成（入库不写 title_cn，翻译走 UPDATE）
        conn.execute("UPDATE news_items SET title_cn = ? WHERE url = ?",
                     ("已翻译标题", "https://p/3"))
    with db._connect() as conn:
        rows = {r["url"]: db._row_to_dict(r) for r in
                conn.execute("SELECT * FROM news_items").fetchall()}
    assert rows["https://p/1"].get("processing_status") == "pending"
    assert "processing_status" not in rows["https://p/2"]
    assert "processing_status" not in rows["https://p/3"]
    assert "processing_status" not in rows["https://p/4"]


def test_hot_page_shows_processing_badge(client):
    with db._connect() as conn:
        conn.execute("DELETE FROM news_items")
    db.insert_items([_row("https://p/badge", "English Headline For Badge Test", "Test RSS", score=90)])
    r = client.get("/hot")
    assert r.status_code == 200
    assert "整理中" in r.text


# ---------------- B2：/api/sources/health v2 ----------------

def _set_health(health: dict):
    db.set_meta("source_health", json.dumps(health, ensure_ascii=False))


def test_sources_health_v2_states(client):
    with db._connect() as conn:
        conn.execute("DELETE FROM news_items")
    db.insert_items([
        _row("https://h/1", "English Untranslated Headline One", "整理中源"),
        _row("https://h/2", "中文正常源条目", "正常源"),
        _row("https://h/3", "English Paper Title Stays English", "arXiv"),
    ])
    _set_health({
        "整理中源": {"ok": True, "fetched": 1, "at": "t"},
        "正常源": {"ok": True, "fetched": 1, "at": "t"},
        "arXiv": {"ok": True, "fetched": 45, "at": "t"},
        "坏源": {"ok": False, "fetched": 0, "error": "429", "at": "t"},
    })
    r = client.get("/api/sources/health")
    assert r.status_code == 200
    srcs = {s["name"]: s for s in r.json()["sources"]}
    # 结构完整（key/name/state/item_count/detail）
    for s in srcs.values():
        assert set(s.keys()) == {"key", "name", "state", "item_count", "detail"}
    assert srcs["整理中源"]["state"] == "processing"       # 有未翻译英文条目
    assert srcs["正常源"]["state"] == "connected"
    assert srcs["正常源"]["item_count"] == 1
    assert srcs["arXiv"]["state"] == "connected"           # 论文按设计保持英文，不算整理中
    assert srcs["坏源"]["state"] == "failed"
    assert "429" in srcs["坏源"]["detail"]


def test_sources_health_zero_fetch_detail(client):
    _set_health({"空源": {"ok": True, "fetched": 0, "at": "t"}})
    srcs = {s["name"]: s for s in client.get("/api/sources/health").json()["sources"]}
    assert srcs["空源"]["state"] == "connected"
    assert srcs["空源"]["detail"] == "0 条"
