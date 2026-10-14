"""抓取编排：一轮抓取 = 各源 fetch → 打分 → 入库 → 14 天清理 → 记录源健康。

单个源失败只记日志，不影响其他源。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from . import db
from .fetchers import FETCHERS
from .fetchers.base import parse_rss
from .scorer import static_score

logger = logging.getLogger("ai-news-oss")


def run_once() -> dict:
    """执行一轮完整抓取，返回各源结果统计（并写入 source_health 供 UI 健康面板）。"""
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
                        "summary": getattr(item, "summary", None),
                    }
                )
            summary[name] = {"ok": True, "fetched": len(items), "at": now.isoformat()}
            logger.info("[%s] 抓到 %d 条", name, len(items))
        except Exception as e:  # noqa: BLE001 - 单个源失败不中断整轮
            summary[name] = {"ok": False, "fetched": 0, "error": str(e), "at": now.isoformat()}
            logger.warning("[%s] 抓取失败: %s", name, e)

    # v0.3.8：用户在设置页添加的自定义 RSS 源（零代码扩源，同样参与健康记录）
    for cs in db.list_custom_sources():
        try:
            cs_items = parse_rss(cs["url"], cs["name"], limit=15)
            for pos, item in enumerate(cs_items):
                rows.append(
                    {
                        "url": item.url,
                        "title": item.title,
                        "source_name": item.source_name,
                        "published_at": item.published_at,
                        "fetched_at": now,
                        "score": static_score("rss", pos, item.score),
                        "summary": item.summary,
                    }
                )
            summary[cs["name"]] = {"ok": True, "fetched": len(cs_items), "at": now.isoformat()}
            logger.info("[%s] 抓到 %d 条（自定义源）", cs["name"], len(cs_items))
        except Exception as e:  # noqa: BLE001
            summary[cs["name"]] = {"ok": False, "fetched": 0, "error": str(e), "at": now.isoformat()}
            logger.warning("[%s] 自定义源抓取失败: %s", cs["name"], e)

    added, skipped = db.insert_items(rows)
    deleted = db.cleanup()
    db.set_meta("last_fetch_run", now.isoformat())  # v0.3：健康检查用
    db.set_meta(
        "source_health",
        json.dumps({k: v for k, v in summary.items() if not k.startswith("_")}, ensure_ascii=False),
    )
    summary["_total"] = {"added": added, "skipped": skipped, "cleaned": deleted}
    logger.info("入库：新增 %d，跳过 %d，清理 14 天前 %d", added, skipped, deleted)
    _notify_push()
    return summary


def _notify_push() -> None:
    """每轮抓取后推送热榜摘要（未启用则跳过；失败不影响抓取）。"""
    try:
        from .push import notify_round

        notify_round()
    except Exception as e:  # noqa: BLE001
        logger.warning("推送通知失败: %s", e)
