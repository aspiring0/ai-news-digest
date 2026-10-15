"""P3 清理批测试：入库失败日志 / 摘要缓存过期清理（含 run_once 接线）。"""
from __future__ import annotations

import logging
import types
from datetime import datetime, timedelta, timezone

from app import db


# ---------------- P3-1：insert_items 静默吞异常 → 记 warning ----------------

def test_insert_items_logs_swallowed_failure(clean_db, caplog):
    """入库失败被跳过时不再静默：skipped 计数保留，同时记含 url 的 warning。

    曾因完全静默导致测试排错困难。注意触发方式：INSERT OR IGNORE 会把
    NOT NULL 违例也静默吞掉（rowcount=0 走 else 跳过路径，不进 except），
    所以这里用缺 "score" 键的行让 try 块内直接抛 KeyError，才真正覆盖
    except 分支。
    """
    bad_row = {
        "url": "https://example.com/missing-score",
        "title": "缺 score 键的行（try 内 KeyError）",
        "source_name": "Test RSS",
        "published_at": None,
        # score 故意缺失 → r["score"] 抛 KeyError → except 分支
    }
    with caplog.at_level(logging.WARNING, logger="ai-news-oss"):
        added, skipped = db.insert_items([bad_row])
    assert (added, skipped) == (0, 1), "坏行应计为 skipped"
    msgs = [r.getMessage() for r in caplog.records]
    assert any("入库失败跳过" in m and "https://example.com/missing-score" in m for m in msgs), (
        "应有含 url 的入库失败 warning 日志"
    )


# ---------------- P3-2：summary_cache 过期清理 ----------------

def test_clear_stale_summaries_deletes_old_keeps_new(clean_db):
    """删除 N 天前的摘要缓存：旧删新留；孤儿缓存（条目已清）随时间回收。"""
    db.save_summary("https://example.com/old", {"t": "旧摘要"}, "test", "m")
    db.save_summary("https://example.com/new", {"t": "新摘要"}, "test", "m")
    # save_summary 内部取 now，无法构造旧时间戳 → 直接 SQL UPDATE 改 created_at
    stale_created = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    with db._connect() as conn:
        conn.execute("UPDATE summary_cache SET created_at = ? WHERE url = ?", (stale_created, "https://example.com/old"))

    deleted = db.clear_stale_summaries(days=30)

    assert deleted == 1, "应只删 31 天前的那条"
    assert db.get_summary("https://example.com/old") is None, "旧缓存应被删"
    assert db.get_summary("https://example.com/new") is not None, "新缓存应保留"


def test_run_once_cleans_stale_summary_cache(clean_db, monkeypatch):
    """run_once 在 db.cleanup() 之后顺带清理过期摘要缓存（接线不断）。"""
    db.save_summary("https://example.com/stale", {"t": "孤儿缓存"}, "test", "m")
    db.save_summary("https://example.com/fresh", {"t": "在用缓存"}, "test", "m")
    stale_created = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    with db._connect() as conn:
        conn.execute("UPDATE summary_cache SET created_at = ? WHERE url = ?", (stale_created, "https://example.com/stale"))

    ok_src = types.ModuleType("fake_ok")
    ok_src.SOURCE_NAME = "好源"
    ok_src.SCORE_CLASS = "rss"
    ok_src.fetch = lambda: []
    import app.fetch_all as fa

    monkeypatch.setattr(fa, "FETCHERS", [ok_src])
    fa.run_once()

    assert db.get_summary("https://example.com/stale") is None, "run_once 后过期缓存应被清掉"
    assert db.get_summary("https://example.com/fresh") is not None, "新鲜缓存不应被误删"
