"""抓取器注册表：新增源时在这里加一行即可。"""
from . import (
    aihot,
    anthropic,
    ars_technica,
    azure_ai,
    cohere,
    deepmind,
    github_releases,
    github_trending,
    google_research,
    hn_ai,
    huggingface,
    ithome,
    marktechpost,
    meta_ai,
    microsoft_research,
    mistral,
    mit_ai,
    nvidia,
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
    xai,
)

# 每个元素是一个 fetcher 模块（须提供 fetch() / SOURCE_NAME / SCORE_CLASS）
# v0.3.3 新增 6 个直接源：Ars Technica AI / Hacker News AI / OpenAI /
# Google DeepMind / IT之家 / VentureBeat AI
# v0.3.4 再拆 3 个稳定上游：Tessl / GitHub Releases / MarkTechPost
# （Sierra/ARC Prize/Comfy 探测成功后即被源站限流 404，稳定性不足未收录）
# 拆上游续批（探测 2026-10-15）：+6 平台 RSS（Google Research / MSR /
# Azure AI / Mistral / NVIDIA / MIT）+4 无 RSS 厂商 HTML 抓取（Anthropic /
# Meta AI / xAI / Cohere）。HF papers / arXiv / Stanford HAI 网络不可达，
# 后期补。Anthropic 页面结构不稳定，列观察期重点。
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
    google_research,
    microsoft_research,
    azure_ai,
    mistral,
    nvidia,
    mit_ai,
    anthropic,
    meta_ai,
    xai,
    cohere,
]

__all__ = ["FETCHERS"]
