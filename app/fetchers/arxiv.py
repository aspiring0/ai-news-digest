"""arXiv 论文流：cs.AI / cs.CL / cs.LG 三分类 RSS，各取限量。

设计要点（接入决策 D1-D5，2026-10-15）：
- paper 打分类（55 起，低于新闻源）：论文是"新"但非"热榜事件"，不挤占新闻位
- 翻译配额排除论文源（translator 按 source_name NOT LIKE 'arXiv%' 过滤）——
  60 条/轮的翻译预算不该被 ~45 条/日的论文标题吃掉，论文保持英文展示
- 稳定性：arXiv RSS 曾整日返回"昨日空快照"——空返回按 parse_rss 语义静默
  （源健康显示 ok + 0 条标黄），连续两轮 0 条人工复查
"""
from __future__ import annotations

import re

from .base import NewsItem, parse_rss

SOURCE_NAME = "arXiv"
FEED_URLS = (
    "https://export.arxiv.org/rss/cs.AI",
    "https://export.arxiv.org/rss/cs.CL",
    "https://export.arxiv.org/rss/cs.LG",
)
PER_CATEGORY_LIMIT = 15
SCORE_CLASS = "paper"

# 保险：部分条目标题带 "(arXiv:2510.12345v1 [cs.AI] UPDATED)" 后缀
_ARXIV_SUFFIX_RE = re.compile(r"\s*\(arXiv:[^)]+\)\s*$")


def _clean_title(t: str) -> str:
    return _ARXIV_SUFFIX_RE.sub("", t).strip()


def fetch() -> list[NewsItem]:
    items: list[NewsItem] = []
    for url in FEED_URLS:
        items.extend(parse_rss(url, SOURCE_NAME, limit=PER_CATEGORY_LIMIT))
    # 跨分类去重：crosslist 论文会在多个分类 feed 重复出现（parse_rss 只做源内去重语义，这里按 URL 合并）
    seen: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        if it.url in seen:
            continue
        seen.add(it.url)
        it.title = _clean_title(it.title)
        out.append(it)
    return out
