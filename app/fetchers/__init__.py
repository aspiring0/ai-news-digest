"""抓取器注册表：新增源时在这里加一行即可。"""
from . import (
    aihot,
    ars_technica,
    deepmind,
    github_trending,
    hn_ai,
    huggingface,
    ithome,
    openai_news,
    producthunt,
    qbitai,
    rundown,
    superhuman,
    techcrunch,
    thebatch,
    tldr,
    venturebeat,
)

# 每个元素是一个 fetcher 模块（须提供 fetch() / SOURCE_NAME / SCORE_CLASS）
# v0.3.3 新增 6 个直接源（原 AIHOT 的上游）：Ars Technica AI / Hacker News AI /
# OpenAI / Google DeepMind / IT之家 / VentureBeat AI
FETCHERS = [
    aihot,
    tldr,
    superhuman,
    rundown,
    qbitai,
    techcrunch,
    thebatch,
    huggingface,
    producthunt,
    github_trending,
    ars_technica,
    hn_ai,
    openai_news,
    deepmind,
    ithome,
    venturebeat,
]

__all__ = ["FETCHERS"]
