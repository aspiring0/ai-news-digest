"""抓取器注册表：新增源时在这里加一行即可。"""
from . import (
    aihot,
    ars_technica,
    deepmind,
    github_releases,
    github_trending,
    hn_ai,
    huggingface,
    ithome,
    marktechpost,
    openai_news,
    ossinsight,
    producthunt,
    qbitai,
    rundown,
    superhuman,
    techcrunch,
    tessl,
    thebatch,
    tldr,
    venturebeat,
)

# 每个元素是一个 fetcher 模块（须提供 fetch() / SOURCE_NAME / SCORE_CLASS）
# v0.3.3 新增 6 个直接源：Ars Technica AI / Hacker News AI / OpenAI /
# Google DeepMind / IT之家 / VentureBeat AI
# v0.3.4 再拆 3 个稳定上游：Tessl / GitHub Releases / MarkTechPost
# （Sierra/ARC Prize/Comfy 探测成功后即被源站限流 404，稳定性不足未收录）
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
    tessl,
    github_releases,
    marktechpost,
    ossinsight,
]

__all__ = ["FETCHERS"]
