"""抓取器注册表：新增源时在这里加一行即可。"""
from . import (
    aihot,
    github_trending,
    huggingface,
    producthunt,
    qbitai,
    rundown,
    superhuman,
    techcrunch,
    thebatch,
    tldr,
)

# 每个元素是一个 fetcher 模块（须提供 fetch() / SOURCE_NAME / SCORE_CLASS）
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
]

__all__ = ["FETCHERS"]
