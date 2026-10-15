"""中文标题/描述：DB 列迁移 / 批量翻译 / 前端展示。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db


def _now():
    return datetime.now(timezone.utc)


def _row(url, title, source, score=66.0):
    return {"url": url, "title": title, "source_name": source,
            "published_at": _now() - timedelta(hours=1), "fetched_at": _now(), "score": score}


# ---------------- DB 列迁移 ----------------

def test_translation_columns_exist(clean_db):
    with db._connect() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(news_items)")}
    assert "title_cn" in cols
    assert "description_cn" in cols


# ---------------- 批量翻译入库存 ----------------

def test_translate_batch_saves_results(clean_db, monkeypatch):
    db.insert_items([
        _row("https://t/1", "OpenAI releases GPT-5 with breakthrough reasoning", "TLDR AI"),
        _row("https://t/2", "Meta Muse Wonder model debuts on Agent Arena", "TechCrunch AI"),
    ])

    import app.translator as tr

    def fake_translate_batch(titles):
        return {
            "OpenAI releases GPT-5 with breakthrough reasoning":
                ("OpenAI 发布 GPT-5，推理能力突破", "GPT-5 在多步推理任务上大幅超越前代"),
            "Meta Muse Wonder model debuts on Agent Arena":
                ("Meta Muse Wonder 模型上线 Agent Arena", "Meta 最新模型在 Agent 评测平台首秀"),
        }

    monkeypatch.setattr(tr, "_call_llm_translate", fake_translate_batch)
    tr.translate_untranslated()

    with db._connect() as conn:
        r1 = conn.execute("SELECT title_cn, description_cn FROM news_items WHERE url='https://t/1'").fetchone()
        assert r1["title_cn"] == "OpenAI 发布 GPT-5，推理能力突破"
        assert "推理" in r1["description_cn"]
        r2 = conn.execute("SELECT title_cn FROM news_items WHERE url='https://t/2'").fetchone()
        assert "Muse Wonder" in r2["title_cn"]


def test_translate_skips_already_translated(clean_db, monkeypatch):
    db.insert_items([_row("https://s/1", "Already translated English title", "S")])
    with db._connect() as conn:
        conn.execute("UPDATE news_items SET title_cn='已有翻译' WHERE url='https://s/1'")

    import app.translator as tr
    called = {"n": 0}
    monkeypatch.setattr(tr, "_call_llm_translate", lambda titles: (called.__setitem__("n", called["n"] + 1), {})[1])
    tr.translate_untranslated()
    assert called["n"] == 0, "已翻译的条目应跳过"


def test_translate_skips_chinese_titles(clean_db, monkeypatch):
    db.insert_items([_row("https://c/1", "这是中文标题不需要翻译", "量子位")])
    import app.translator as tr
    called = {"n": 0}
    monkeypatch.setattr(tr, "_call_llm_translate", lambda titles: (called.__setitem__("n", called["n"] + 1), {})[1])
    tr.translate_untranslated()
    assert called["n"] == 0, "中文标题不需要翻译"


def test_translate_handles_llm_failure(clean_db, monkeypatch):
    """LLM 调用失败不应阻塞抓取流程。"""
    db.insert_items([_row("https://f/1", "Some English title", "S")])
    import app.translator as tr

    def fail(titles):
        raise RuntimeError("模型超时")

    monkeypatch.setattr(tr, "_call_llm_translate", fail)
    tr.translate_untranslated()  # 不应抛异常
    with db._connect() as conn:
        r = conn.execute("SELECT title_cn FROM news_items WHERE url='https://f/1'").fetchone()
        assert r["title_cn"] is None, "失败时保持空，下轮重试"


def test_translate_same_title_updates_only_mapped_url(clean_db, monkeypatch):
    """P3：同标题不同 URL 的两行，翻译回写只落在映射到的 URL 上。

    旧行为 UPDATE ... WHERE title=? 会把两行同标题行一起改写（误伤）。
    现在 SELECT 保留 url 并构建 title→url 映射（字典后写覆盖前写：行序
    按 COALESCE(published_at, fetched_at) DESC，映射最终落在较早发布的
    那行），UPDATE 按 url 精确定位；未映射到的行保持空，下一轮重试。
    """
    title = "Same English Headline Published Twice"
    db.insert_items([
        {"url": "https://dup/new", "title": title, "source_name": "源A",
         "published_at": _now() - timedelta(hours=1), "fetched_at": _now(), "score": 60.0},
        {"url": "https://dup/old", "title": title, "source_name": "源B",
         "published_at": _now() - timedelta(hours=2), "fetched_at": _now(), "score": 60.0},
    ])

    import app.translator as tr

    monkeypatch.setattr(tr, "_call_llm_translate", lambda titles: {title: ("中文标题", "中文描述")})
    tr.translate_untranslated()

    with db._connect() as conn:
        new = conn.execute("SELECT title_cn FROM news_items WHERE url='https://dup/new'").fetchone()
        old = conn.execute("SELECT title_cn, description_cn FROM news_items WHERE url='https://dup/old'").fetchone()
    assert old["title_cn"] == "中文标题", "映射到的 url 行应被更新"
    assert old["description_cn"] == "中文描述"
    assert new["title_cn"] is None, "同标题的另一行不应被误伤"


# ---------------- 前端展示 ----------------

def test_hot_page_shows_chinese_title(client, monkeypatch):
    db.insert_items([
        _row("https://h/1", "English original title Keplr Nova", "AIHOT", 90),
    ])
    with db._connect() as conn:
        conn.execute(
            "UPDATE news_items SET title_cn='中文标题开普勒', description_cn='一句话中文描述' WHERE url='https://h/1'"
        )
    html = client.get("/hot").text
    assert "中文标题开普勒" in html
    assert "English original title" in html  # 英文原题仍可见（副行）
