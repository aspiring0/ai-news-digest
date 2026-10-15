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
    stale_cached = db.clear_stale_summaries()  # P3：孤儿摘要缓存随时间回收
    db.set_meta("last_fetch_run", now.isoformat())  # v0.3：健康检查用
    db.set_meta(
        "source_health",
        json.dumps({k: v for k, v in summary.items() if not k.startswith("_")}, ensure_ascii=False),
    )
    streaks, alerts = _evaluate_source_alerts(summary)  # B1：连续异常告警（函数内自持久化）
    if alerts:
        _notify_source_alerts(alerts)
    summary["_total"] = {"added": added, "skipped": skipped, "cleaned": deleted}
    logger.info("入库：新增 %d，跳过 %d，清理 14 天前 %d", added, skipped, deleted)
    logger.info("清理 30 天前摘要缓存 %d 条", stale_cached)
    _notify_push()

    # v0.5：抓取后批量翻译英文标题为中文（失败不阻塞）
    try:
        from .translator import translate_untranslated
        translate_untranslated()
    except Exception as e:  # noqa: BLE001
        logger.warning("批量翻译失败（下轮重试）: %s", e)

    return summary


# ---------------- B1：源健康连续异常告警 ----------------

FAIL_STREAK_ALERT_THRESHOLD = 3  # 连续 N 轮异常触发一次告警（每个异常期只报一次）


def _evaluate_source_alerts(summary: dict) -> tuple[dict, list[str]]:
    """按本轮结果更新各源连续异常计数并持久化到 meta（重启不清零）。

    异常定义：ok=False（真失败）或 ok=True 但 fetched=0（失败被源内
    部捕获后返回空列表，健康面板黄 ⚠ 那一类）。达到阈值生成一条告警
    文本；恢复（本轮正常）清零。
    """
    streaks = json.loads(db.get_meta("source_fail_streaks") or "{}")
    alerts: list[str] = []
    for name, info in summary.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        bad = (not info.get("ok")) or info.get("fetched", 0) == 0
        streaks[name] = streaks.get(name, 0) + 1 if bad else 0
        if bad and streaks[name] == FAIL_STREAK_ALERT_THRESHOLD:
            state = "抓取失败" if not info.get("ok") else "0 条（疑似被吞的失败）"
            alerts.append(f"源「{name}」连续 {FAIL_STREAK_ALERT_THRESHOLD} 轮{state}"
                          f"：{str(info.get('error') or '无错误详情')[:60]}")
    db.set_meta("source_fail_streaks", json.dumps(streaks, ensure_ascii=False))
    return streaks, alerts


def _notify_source_alerts(alerts: list[str]) -> None:
    """告警出口：推送渠道已启用则推送，否则降级 WARNING 日志（/api/logs 可见）。"""
    text = "⚠ 源健康告警\n" + "\n".join(alerts)
    try:
        from .push import get_config, send

        cfg = get_config()
        if cfg.get("enabled") and cfg.get("channel") != "off":
            result = send(text, cfg)
            logger.warning("源健康告警已推送（%s）：%s", cfg["channel"],
                           "；".join(alerts)[:120] if result.get("ok") else result.get("message"))
            return
    except Exception as e:  # noqa: BLE001 - 告警失败不影响抓取
        logger.warning("源健康告警推送异常: %s", e)
    logger.warning("源健康告警（未启用推送，仅日志）：%s", "；".join(alerts)[:200])


def _notify_push() -> None:
    """每轮抓取后推送热榜摘要（未启用则跳过；失败不影响抓取）。"""
    try:
        from .push import notify_round

        notify_round()
    except Exception as e:  # noqa: BLE001
        logger.warning("推送通知失败: %s", e)
