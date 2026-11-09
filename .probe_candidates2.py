# 第二轮：The Decoder 变体 + VentureBeat AI
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests

UA_BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
CANDIDATES = [
    ("The Decoder www", "https://www.thedecoder.com/feed/", UA_BROWSER),
    ("The Decoder rss", "https://thedecoder.com/rss/", UA_BROWSER),
    ("The Decoder feed 浏览器UA", "https://thedecoder.com/feed/", UA_BROWSER),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", UA_BROWSER),
    ("TechCrunch AI 已有对照", "https://techcrunch.com/category/artificial-intelligence/feed/", UA_BROWSER),
]
for name, url, headers in CANDIDATES:
    try:
        r = requests.get(url, headers=headers, timeout=15)
        feed = feedparser.parse(r.content)
        n = len(feed.entries)
        t = (feed.entries[0].get("title") or "")[:50] if n else "-"
        print(f"[{'OK' if n else 'X'}] {name:26s} HTTP {r.status_code} {n} 条 | {t}")
    except Exception as e:
        print(f"[X] {name:26s} 失败: {str(e)[:60]}")
