"""IT之家：中文科技媒体。AI 分类 RSS 已下线（404），改用全站 feed + AI 关键词过滤。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "IT之家"
FEED_URL = "https://www.ithome.com/rss/"
SCORE_CLASS = "rss"

# AI 相关关键词（小写比较）；命中任意一个才保留
AI_KEYWORDS = (
    "ai", "人工智能", "大模型", "智能体", "机器人",
    "gpt", "chatgpt", "claude", "gemini", "llm", "sora",
    "openai", "deepseek", "qwen", "kimi", "文心", "智谱",
)


def _is_ai(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in AI_KEYWORDS)


def fetch() -> list[NewsItem]:
    items = parse_rss(FEED_URL, SOURCE_NAME, limit=60)
    return [it for it in items if _is_ai(it.title)][:15]
