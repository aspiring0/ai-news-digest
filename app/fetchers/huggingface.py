"""HuggingFace 热门模型：公开 API，无需 key。

接口：GET https://huggingface.co/api/models?sort=likes&direction=-1
返回按 likes 倒序的模型列表（2026-10-13 实测可用）。
"""
import logging

import requests

from .base import HEADERS, FETCH_TIMEOUT, NewsItem, to_utc
from datetime import datetime

logger = logging.getLogger("ai-news-oss")

SOURCE_NAME = "HuggingFace"
API_URL = "https://huggingface.co/api/models"
SCORE_CLASS = "hf"  # 72 起按位置递减


def fetch(limit: int = 15) -> list[NewsItem]:
    items: list[NewsItem] = []
    try:
        resp = requests.get(
            API_URL,
            params={"sort": "likes", "direction": "-1", "limit": limit},
            headers=HEADERS,
            timeout=FETCH_TIMEOUT,
        )
        resp.raise_for_status()
        for m in resp.json():
            model_id = m.get("id", "")
            if not model_id:
                continue
            likes = m.get("likes", 0)
            # 发布时间：API 的 lastModified 字段（ISO 格式）
            published = None
            lm = m.get("lastModified")
            if lm:
                try:
                    published = to_utc(datetime.fromisoformat(lm.replace("Z", "+00:00")))
                except ValueError:
                    pass
            items.append(
                NewsItem(
                    title=f"{model_id}（{likes} likes）",
                    url=f"https://huggingface.co/{model_id}",
                    source_name=SOURCE_NAME,
                    published_at=published,
                )
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("HuggingFace API 失败: %s", e)
    return items
