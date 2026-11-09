# 探测候选上游源的 RSS 可用性（只加验证过的）
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests

HEADERS = {"User-Agent": "ai-news-oss/0.1 (+https://github.com/ai-news-oss)"}
CANDIDATES = [
    ("The Decoder", "https://thedecoder.com/feed/"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
    ("IT之家·AI", "https://www.ithome.com/category/ai/rss/"),
    ("IT之家(全站)", "https://www.ithome.com/rss/"),
    ("Hacker News AI", "https://hnrss.org/newest?q=AI&points=100"),
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml"),
    ("Anthropic News2", "https://www.anthropic.com/rss.xml"),
    ("Amazon Science", "https://www.amazon.science/rss"),
    ("Artificial Analysis", "https://artificialanalysis.ai/feed.xml"),
    ("xAI News", "https://x.ai/news/rss.xml"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
]

for name, url in CANDIDATES:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        ct = r.headers.get("content-type", "")
        feed = feedparser.parse(r.content)
        n = len(feed.entries)
        if n == 0 or "html" in ct.lower() and n == 0:
            print(f"[X] {name:22s} HTTP {r.status_code} 但无条目（{ct[:40]}）")
            continue
        t = (feed.entries[0].get("title") or "")[:52]
        print(f"[OK] {name:22s} HTTP {r.status_code} {n} 条 | {t}")
    except Exception as e:
        print(f"[X] {name:22s} 失败: {str(e)[:60]}")
