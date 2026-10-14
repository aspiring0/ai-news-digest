"""全文搜索（FTS5）+ 热榜缓存。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db


def _now():
    return datetime.now(timezone.utc)


def _row(url, title, source, summary=None, score=66.0):
    return {"url": url, "title": title, "source_name": source,
            "published_at": _now() - timedelta(hours=1), "fetched_at": _now(),
            "score": score, "summary": summary}


# ---------------- 全文搜索 ----------------

def test_search_fts_chinese_and_english(clean_db):
    db.insert_items([
        _row("https://s/1", "刻蚀机之父尹志尧谈 AI 泡沫", "IT之家", summary="半导体设备观点"),
        _row("https://s/2", "Muse Wonder frontier model released", "TechCrunch AI"),
        _row("https://s/3", "量子位报道机器人量产", "量子位"),
    ])
    got = db.search_items("刻蚀机")
    assert len(got) == 1 and "刻蚀机" in got[0]["title"]
    got2 = db.search_items("Muse")
    assert len(got2) == 1 and got2[0]["url"] == "https://s/2"
    got3 = db.search_items("泡沫")
    assert len(got3) == 1  # 命中的是 summary 里的词也算（FTS 含 summary 列）


def test_search_fts_backfill_existing_rows(clean_db):
    """先入库、后建 FTS（模拟存量库升级）也能搜到。"""
    db.insert_items([_row("https://b/1", "Backfill-able Keplr entry", "S")])
    with db._connect() as conn:  # 模拟旧库：删掉 FTS 再重建
        conn.execute("DROP TABLE IF EXISTS news_items_fts")
    db.init_db()  # init 内含回填
    assert len(db.search_items("Backfill")) == 1


def test_search_sanitizes_fts_syntax(clean_db):
    """用户输入引号/通配符等 FTS 语法字符不应报错。"""
    db.insert_items([_row("https://q/1", "特殊字符标题 Quoted*Term", "S")])
    for q in ['"未闭合引号', 'AND OR NOT', 'a*b(c)', '正常词 Keplr']:
        got = db.search_items(q)  # 不抛异常即通过
        assert isinstance(got, list)


def test_search_page_renders(client):
    db.insert_items([_row("https://p/1", "页面搜索测试 Keplr Nova", "AIHOT")])
    r = client.get("/search?q=Keplr")
    assert r.status_code == 200
    assert "页面搜索测试" in r.text


# ---------------- 热榜缓存 ----------------

def test_hot_cache_invalidated_on_insert_and_block(clean_db):
    db.insert_items([_row("https://c/1", "缓存测试 Kepler Nova", "AIHOT", score=80)])
    items1, _ = db.get_hot_stories()
    assert any("缓存测试" in i["title"] for i in items1)
    # 新入库 → 失效 → 可见
    db.insert_items([_row("https://c/2", "缓存测试二 Zephyr Orbit", "AIHOT", score=85)])
    items2, _ = db.get_hot_stories()
    assert any("Zephyr" in i["title"] for i in items2), "入库后缓存应失效"
    # 屏蔽 → 失效 → 消失
    db.add_block("url", "https://c/2")
    items3, _ = db.get_hot_stories()
    assert not any("Zephyr" in i["title"] for i in items3), "屏蔽后缓存应失效"
    db.delete_block("url", "https://c/2")
    items4, _ = db.get_hot_stories()
    assert any("Zephyr" in i["title"] for i in items4), "解除屏蔽后应恢复"


def test_hot_cache_hit_and_profile_change(clean_db):
    calls = {"n": 0}
    orig = db._compute_ranked_stories

    def spy(*args, **kwargs):
        calls["n"] += 1
        return orig(*args, **kwargs)

    db._compute_ranked_stories = spy
    try:
        db.get_hot_stories()
        db.get_hot_stories()
        assert calls["n"] == 1, "相同参数第二次应命中缓存"
        p = {"likes": ["kepler"], "dislikes": [], "notes": ""}
        db.get_hot_stories(profile=p)
        assert calls["n"] == 2, "画像参数不同应重新计算"
        db.get_hot_stories(profile=p)
        assert calls["n"] == 2, "画像参数相同的重复调用应命中缓存"
    finally:
        db._compute_ranked_stories = orig
