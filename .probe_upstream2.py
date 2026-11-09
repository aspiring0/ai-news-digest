# 完整上游清单 + 第二批 RSS 变体探测（全部免 key）
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

print("=== 1. AIHOT 完整上游清单（author 字段去重）===")
resp = requests.get("https://aihot.news/feed.xml", headers=UA, timeout=20)
feed = feedparser.parse(resp.content)
authors = {}
for e in feed.entries:
    m = re.search(r"\((.+)\)", e.get("author") or "")
    if m:
        authors[m.group(1).strip()] = authors.get(m.group(1).strip(), 0) + 1
print(f"共 {len(authors)} 个上游:")
for a, n in sorted(authors.items(), key=lambda x: -x[1]):
    print(f"  {a}  x{n}")

print("\n=== 2. 第二批 RSS 变体探测 ===")
CANDIDATES = [
    ("Tessl blog", ["https://www.tessl.io/blog/rss.xml", "https://tessl.io/blog/feed", "https://www.tessl.io/rss.xml"]),
    ("Vapi blog", ["https://vapi.ai/blog/rss.xml", "https://vapi.ai/rss.xml", "https://blog.vapi.ai/feed"]),
    ("Meshy blog", ["https://www.meshy.ai/blog/rss.xml", "https://www.meshy.ai/rss.xml", "https://meshy.ai/feed"]),
    ("Artificial Analysis", ["https://artificialanalysis.ai/blog/feed.xml", "https://artificialanalysis.ai/feed", "https://artificialanalysis.ai/rss.xml"]),
    ("Amazon Science", ["https://www.amazon.science/blog/rss", "https://www.amazon.science/feed", "https://www.amazon.science/publications/rss"]),
    ("Anthropic", ["https://www.anthropic.com/news.xml", "https://www.anthropic.com/feed.xml", "https://raw.githubusercontent.com/anthropics/anthropic-docs/main/CHANGELOG.md"]),
    ("xAI news", ["https://x.ai/news.xml", "https://x.ai/feed.xml"]),
    ("GitHub openai/codex releases", ["https://github.com/openai/codex/releases.atom"]),
    ("GitHub anthropics/claude-code releases", ["https://github.com/anthropics/claude-code/releases.atom"]),
    ("GitHub openai/openai-cookbook releases", ["https://github.com/openai/openai-cookbook/releases.atom"]),
]
for name, urls in CANDIDATES:
    hit = False
    for u in urls:
        try:
            r = requests.get(u, headers=UA, timeout=15)
            f = feedparser.parse(r.content)
            if len(f.entries) > 0:
                t = (f.entries[0].get("title") or "")[:48]
                print(f"[OK] {name:34s} {u}")
                print(f"     {len(f.entries)} 条 | {t}")
                hit = True
                break
        except Exception:
            continue
    if not hit:
        print(f"[X]  {name:34s} 全部变体不可用")
