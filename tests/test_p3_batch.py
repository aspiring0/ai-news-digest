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
