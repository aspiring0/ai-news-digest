"""C1 中文搜索（LIKE 子串路径）+ B1 源健康连续异常告警。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app import db, fetch_all


# ---------------- C1：中文搜索 ----------------

def _seed_search():
    now = datetime.now(timezone.utc)
    db.insert_items([
        {"url": "https://s/cn1", "title": "Anthropic 发布 Claude 新模型", "source_name": "S",
         "fetched_at": now, "published_at": now, "score": 66.0, "summary": "多模态能力提升"},
        {"url": "https://s/cn2", "title": "Some English Title About Robots", "source_name": "S",
         "fetched_at": now, "published_at": now, "score": 66.0, "summary": "中文摘要：机器人技术进展"},
        {"url": "https://s/cn3", "title": "English Headline Unrelated To Query", "source_name": "S",
         "fetched_at": now, "published_at": now, "score": 66.0, "summary": "nothing relevant"},
    ])
    with db._connect() as conn:  # 模拟翻译结果
        conn.execute("UPDATE news_items SET title_cn = ? WHERE url = ?",
                     ("克劳德模型迎来重大升级", "https://s/cn2"))


def test_cjk_query_matches_chinese_title(clean_db):
    _seed_search()
    hits = db.search_items("Claude 新模型")
    assert any("cn1" in h["url"] for h in hits), "中文标题子串应命中"


def test_cjk_query_matches_translated_title(clean_db):
    _seed_search()
    hits = db.search_items("克劳德")
    assert any("cn2" in h["url"] for h in hits), "title_cn（翻译标题）子串应命中"


def test_cjk_query_matches_summary(clean_db):
    _seed_search()
    hits = db.search_items("机器人技术")
    assert any("cn2" in h["url"] for h in hits), "中文摘要子串应命中"


def test_cjk_query_special_chars_safe(clean_db):
    _seed_search()
    hits = db.search_items("100%进步_")  # % 和 _ 不炸、不当通配
    assert hits == []


def test_english_query_still_fts(clean_db):
    _seed_search()
    hits = db.search_items("Robots")
    assert any("cn2" in h["url"] for h in hits), "英文 FTS 路径不回归"


# ---------------- B1：源健康连续异常告警 ----------------

def _round(ok: bool, fetched: int = 0, error: str = "") -> dict:
    return {"坏源": {"ok": ok, "fetched": fetched, "error": error, "at": "t"}}


def test_alert_fires_once_at_threshold(clean_db):
    db.set_meta("source_fail_streaks", "{}")
    alerts = []
    for _ in range(4):  # 失败 4 轮：第 3 轮告警一次，第 4 轮不再重复
        streaks, a = fetch_all._evaluate_source_alerts(_round(False, 0, "429 Too Many Requests"))
        alerts.extend(a)
    assert len(alerts) == 1
    assert "坏源" in alerts[0] and "3 轮" in alerts[0]
    assert streaks["坏源"] == 4


def test_zero_fetch_but_ok_counts_as_bad(clean_db):
    db.set_meta("source_fail_streaks", "{}")
    _, a1 = fetch_all._evaluate_source_alerts(_round(True, 0))   # HF 型：ok 但 0 条
    _, a2 = fetch_all._evaluate_source_alerts(_round(True, 0))
    streaks, a3 = fetch_all._evaluate_source_alerts(_round(True, 0))
    assert not a1 and not a2 and len(a3) == 1
    assert "0 条" in a3[0]
    assert streaks["坏源"] == 3


def test_recovery_resets_streak(clean_db):
    db.set_meta("source_fail_streaks", "{}")
    for _ in range(3):
        fetch_all._evaluate_source_alerts(_round(False))
    streaks, _ = fetch_all._evaluate_source_alerts(_round(True, fetched=5))  # 恢复
    assert streaks["坏源"] == 0
    for _ in range(2):  # 再失败 2 轮不告警，第 3 轮重新告警
        _, a = fetch_all._evaluate_source_alerts(_round(False))
    assert a == []
    _, a = fetch_all._evaluate_source_alerts(_round(False))
    assert len(a) == 1


def test_run_once_wiring_alerts_via_push(clean_db, monkeypatch):
    import types

    db.set_meta("source_fail_streaks", "{}")
    bad_src = types.ModuleType("bad_src")
    bad_src.SOURCE_NAME = "总是坏"
    bad_src.SCORE_CLASS = "rss"
    bad_src.fetch = lambda: (_ for _ in ()).throw(ConnectionError("reset by peer"))

    sent = []
    import app.push as push_mod
    monkeypatch.setattr(push_mod, "get_config",
                        lambda: {"enabled": True, "channel": "webhook", "webhook_url": "http://x"})
    monkeypatch.setattr(push_mod, "send", lambda text, cfg=None: sent.append(text) or {"ok": True})
    monkeypatch.setattr(fetch_all, "FETCHERS", [bad_src])
    monkeypatch.setattr(fetch_all, "_notify_push", lambda: None)
    monkeypatch.setattr(fetch_all, "_notify_source_alerts",
                        lambda alerts: sent.extend(alerts))  # 直接捕获告警文本，绕开真实推送

    for _ in range(3):
        fetch_all.run_once()
    assert any("总是坏" in s and "3 轮" in s for s in sent), "第 3 轮应产生告警"
    assert json.loads(db.get_meta("source_fail_streaks"))["总是坏"] == 3
