# 探测"拆上游"候选：聚合器（TLDR/Rundown/TheBatch/AIHOT/PH/HN）内容的一手来源
# 只加验证过的；教训（fetchers/__init__.py:29）：探测通过 != 稳定，收录前需 48h 观察期
import concurrent.futures as cf
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests

HEADERS = {"User-Agent": "ai-news-oss/0.1 (+https://github.com/ai-news-oss)"}

CANDIDATES = [
    # 实验室/公司一手发布（目前只能靠 newsletter 转手的）
    ("Anthropic news", "https://www.anthropic.com/news/rss.xml"),
    ("Anthropic root", "https://www.anthropic.com/rss.xml"),
    ("Google Research", "https://research.google/blog/rss/"),
    ("Google blog 主站", "https://blog.google/rss/"),
    ("Meta AI blog", "https://ai.meta.com/blog/rss/"),
    ("Meta 新闻室 AI", "https://about.fb.com/news/category/ai/feed/"),
    ("Microsoft Research", "https://www.microsoft.com/en-us/research/feed/"),
    ("Azure AI blog", "https://azure.microsoft.com/en-us/blog/feed/"),
    ("Mistral news", "https://mistral.ai/news/rss.xml"),
    ("Mistral root", "https://mistral.ai/rss.xml"),
    ("NVIDIA blog", "https://blogs.nvidia.com/feed/"),
    ("Cohere blog", "https://cohere.com/blog/rss.xml"),
    ("xAI news", "https://x.ai/news/rss.xml"),
    # 学术一手
    ("arXiv cs.AI", "http://export.arxiv.org/rss/cs.AI"),
    ("arXiv cs.CL", "http://export.arxiv.org/rss/cs.CL"),
    ("arXiv cs.LG", "http://export.arxiv.org/rss/cs.LG"),
    ("MIT News AI", "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml"),
    ("Stanford HAI", "https://hai.stanford.edu/news/rss"),
    # HF 论文榜（无 RSS 惯例，试探）
    ("HF papers", "https://huggingface.co/papers/rss"),
]


def probe(item):
    name, url = item
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        ct = r.headers.get("content-type", "")
        feed = feedparser.parse(r.content)
        n = len(feed.entries)
        if n == 0:
            return f"[X] {name:20s} HTTP {r.status_code} 无条目（{ct[:40]}）"
        t = (feed.entries[0].get("title") or "")[:56]
        return f"[{'OK' if 'html' not in ct.lower() else '?'}] {name:20s} HTTP {r.status_code} {n:3d}条 | {t}"
    except Exception as e:
        return f"[X] {name:20s} 失败: {str(e)[:64]}"


with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for line in ex.map(probe, CANDIDATES):
        print(line, flush=True)
