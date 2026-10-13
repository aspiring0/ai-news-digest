"""抓取编排：一轮抓取 = 各源 fetch → 打分 → 入库 → 14 天清理。

单个源失败只记日志，不影响其他源。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import db
from .fetchers import FETCHERS
from .scorer import static_score

logger = logging.getLogger("ai-news-oss")


def run_once() -> dict:
    """执行一轮完整抓取，返回各源结果统计。"""
    db.init_db()
    now = datetime.now(timezone.utc)
    summary: dict[str, dict] = {}
    rows: list[dict] = []

    for mod in FETCHERS:
        name = getattr(mod, "SOURCE_NAME", mod.__name__)
        score_class = getattr(mod, "SCORE_CLASS", "rss")
        try:
            items = mod.fetch()
            for pos, item in enumerate(items):
                upstream = item.score  # AIHOT 等可自带上游分
                rows.append(
                    {
                        "url": item.url,
                        "title": item.title,
                        "source_name": item.source_name,
                        "published_at": item.published_at,  # 缺失则查询时用 fetched_at
                        "fetched_at": now,
                        "score": static_score(score_class, pos, upstream),
                    }
                )
            summary[name] = {"fetched": len(items), "ok": True}
            logger.info("[%s] 抓到 %d 条", name, len(items))
        except Exception as e:  # noqa: BLE001 - 单个源失败不中断整轮
            summary[name] = {"fetched": 0, "ok": False, "error": str(e)}
            logger.warning("[%s] 抓取失败: %s", name, e)

    added, skipped = db.insert_items(rows)
    deleted = db.cleanup()
    db.set_meta("last_fetch_run", now.isoformat())  # v0.3：健康检查用
    summary["_total"] = {"added": added, "skipped": skipped, "cleaned": deleted}
    logger.info("入库：新增 %d，跳过 %d，清理 14 天前 %d", added, skipped, deleted)
    return summary
