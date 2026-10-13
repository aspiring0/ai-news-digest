"""GitHub Releases：跟踪重点 AI 工具的版本发布（GitHub 官方 Atom feed，无需 key）。

AIHOT 上游「Codex：GitHub Releases」的直连版；顺带跟踪 Claude Code。
"""
import logging

from .base import NewsItem, parse_rss

logger = logging.getLogger("ai-news-oss")

SOURCE_NAME = "GitHub Releases"
SCORE_CLASS = "rss"

# (repo, 显示名) —— release 标题形如 "v0.157.0"，拼成可读标题
REPOS = [
    ("openai/codex", "OpenAI Codex CLI"),
    ("anthropics/claude-code", "Claude Code"),
]


def fetch(limit: int = 10) -> list[NewsItem]:
    items: list[NewsItem] = []
    for repo, label in REPOS:
        url = f"https://github.com/{repo}/releases.atom"
        entries = parse_rss(url, SOURCE_NAME, limit=limit)
        for it in entries:
            it.title = f"{label} 发布 {it.title.strip()}"
            items.append(it)
        if entries:
            logger.info("[GitHub Releases] %s 最新 %s", repo, entries[0].title.strip())
    return items[:limit]
