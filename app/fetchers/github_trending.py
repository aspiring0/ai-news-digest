"""GitHub Trending：官方无 API，解析公开 HTML 页面。

页面结构（2026-10-13 实测）：每个 <article> 一块，
仓库链接形如 href="/owner/repo"，描述在正文文本里。
GitHub 页面结构可能变化，解析失败只记日志不抛异常。
"""
import logging
import re

import requests

from .base import HEADERS, FETCH_TIMEOUT, NewsItem

logger = logging.getLogger("ai-news-oss")

SOURCE_NAME = "GitHub Trending"
TRENDING_URL = "https://github.com/trending?since=daily"
SCORE_CLASS = "ph"  # 70 起按位置递减


def fetch(limit: int = 15) -> list[NewsItem]:
    items: list[NewsItem] = []
    try:
        resp = requests.get(TRENDING_URL, headers=HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
        articles = re.findall(r"<article[^>]*>(.*?)</article>", html, re.S)
        for art in articles[:limit]:
            # 取第一个"恰好两段路径"的站内链接，排除 login/apps/sponsors 等噪音
            repo_path = None
            for href in re.findall(r'href="(/[^"?#]+)"', art):
                if re.fullmatch(r"/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", href) and not href.startswith(
                    ("/login", "/apps/", "/sponsors/")
                ):
                    repo_path = href
                    break
            if not repo_path:
                continue
            owner_repo = repo_path.strip("/")
            # 描述：去掉标签后的第一段有效文本
            text = re.sub(r"<[^>]+>", " ", art)
            text = re.sub(r"\s+", " ", text).strip()
            # 去掉 "Star owner / repo" 前缀噪音
            desc = ""
            parts = text.split(owner_repo.replace("/", " / "))
            if len(parts) > 1:
                desc = parts[1].strip()
                # 截掉末尾的 "TypeScript 173,836 ... stars today" 统计噪音
                desc = re.split(r"\d[\d,]*\s+stars today", desc)[0].strip()
                desc = re.sub(r"\s{2,}", " ", desc)
            title = owner_repo + (f"：{desc[:80]}" if desc else "")
            items.append(
                NewsItem(
                    title=title,
                    url=f"https://github.com{repo_path}",
                    source_name=SOURCE_NAME,
                    published_at=None,  # trending 无发布时间，入库记抓取时间
                )
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("GitHub Trending 解析失败: %s", e)
    return items
