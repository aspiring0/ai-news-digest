"""GitHub Star 飙升：用 GitHub 搜索 API 免 key 拉取本周新建 + star 增速最快的 AI 项目。

接口：GET https://api.github.com/search/repositories?q=created:>N天前+topic:ai&sort=stars
无需认证（公开搜索 API，限 10 次/分钟，4 小时一轮完全够用）。
"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from .base import HEADERS, FETCH_TIMEOUT, NewsItem

logger = logging.getLogger("ai-news-oss")

SOURCE_NAME = "Star 飙升"
API_URL = "https://api.github.com/search/repositories"
SCORE_CLASS = "ph"  # 与 ProductHunt/GitHub 同级


def fetch(limit: int = 15) -> list[NewsItem]:
    items: list[NewsItem] = []
    # 本周新建 + topic 含 AI/LLM/agent 的仓库，按 star 倒序
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            API_URL,
            params={
                "q": f"created:>{cutoff} topic:ai",
                "sort": "stars",
                "order": "desc",
                "per_page": limit,
            },
            headers={**HEADERS, "Accept": "application/vnd.github.v3+json"},
            timeout=FETCH_TIMEOUT,
        )
        resp.raise_for_status()
        repos = resp.json().get("items") or []
        now = datetime.now(timezone.utc)
        for r in repos[:limit]:
            full_name = r.get("full_name", "")
            stars = r.get("stargazers_count", 0)
            lang = r.get("language") or ""
            desc = (r.get("description") or "").strip()[:80]
            if not full_name:
                continue
            title = f"⭐ +{stars:,} {full_name}"
            if lang:
                title += f"（{lang}）"
            if desc:
                title += f" —— {desc}"
            items.append(
                NewsItem(
                    title=title,
                    url=f"https://github.com/{full_name}",
                    source_name=SOURCE_NAME,
                    published_at=now,
                )
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("GitHub Star 飙升拉取失败: %s", e)
    return items
