"""定时调度：每 N 小时抓取一次（默认 4 小时）。"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from .fetch_all import run_once

logger = logging.getLogger("ai-news-oss")

INTERVAL_HOURS = int(os.environ.get("FETCH_INTERVAL_HOURS", "4"))

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def start() -> None:
    """启动定时任务（调用前建议先手动跑一次 run_once）。"""
    scheduler.add_job(
        run_once,
        "interval",
        hours=INTERVAL_HOURS,
        id="fetch_news",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("定时抓取已启动：每 %d 小时一次", INTERVAL_HOURS)
