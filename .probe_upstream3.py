# 第三批：博客型上游 RSS 探测
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
CANDIDATES = [
    ("MarkTechPost", ["https://www.marktechpost.com/feed/"]),
    ("LangChain Blog", ["https://blog.langchain.dev/rss/", "https://blog.langchain.dev/feed.xml"]),
    ("Redwood Research", ["https://redwoodresearch.org/blog/rss.xml", "https://redwoodresearch.org/feed"]),
    ("Sierra Blog", ["https://sierra.ai/blog/rss.xml", "https://sierra.ai/rss.xml"]),
    ("Epoch AI", ["https://epoch.ai/feed.xml", "https://epoch.ai/rss.xml", "https://epoch.ai/blog/feed.xml"]),
    ("ARC Prize", ["https://arcprize.org/blog/rss.xml", "https://arcprize.org/feed.xml", "https://arcprize.org/rss.xml"]),
    ("Comfy Blog", ["https://blog.comfy.org/rss.xml", "https://www.comfy.org/blog/feed", "https://comfy.org/rss.xml"]),
    ("Prime Intellect", ["https://www.primeintellect.ai/blog/rss.xml", "https://primeintellect.ai/rss.xml"]),
]
for name, urls in CANDIDATES:
    hit = False
    for u in urls:
        try:
            r = requests.get(u, headers=UA, timeout=15)
            f = feedparser.parse(r.content)
            if len(f.entries) > 0:
                t = (f.entries[0].get("title") or "")[:46]
                print(f"[OK] {name:20s} {len(f.entries)} 条 | {t}")
                hit = True
                break
        except Exception:
            continue
    if not hit:
        print(f"[X]  {name:20s} 不可用")
