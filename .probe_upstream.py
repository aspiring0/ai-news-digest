# 探测：AIHOT 的上游信源结构 + 库内多源重复报道实例
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests

print("=== 1. AIHOT feed 的上游信源提取 ===")
resp = requests.get("https://aihot.news/feed.xml", headers={"User-Agent": "ai-news-oss/0.1"}, timeout=20)
feed = feedparser.parse(resp.content)
print(f"条目数: {len(feed.entries)}")
e0 = feed.entries[0]
print("第一条字段:", sorted(e0.keys()))
print("link:", e0.get("link"))
print("author:", e0.get("author"))
print("tags:", [t.get("term") for t in e0.get("tags", [])][:6])
print("summary 前 120 字:", (e0.get("summary") or "")[:120].replace("\n", " "))

# author 字段样例分布
authors = {}
for e in feed.entries:
    a = (e.get("author") or "").strip()
    if a:
        authors[a] = authors.get(a, 0) + 1
print(f"\nauthor 字段共 {len(authors)} 个不同值（上游信源候选）:")
for a, n in sorted(authors.items(), key=lambda x: -x[1])[:20]:
    print(f"  {a}  x{n}")

print("\n=== 2. 库内『同一事件多源重复』实例（今天的关键词撞车）===")
conn = sqlite3.connect("data/news.db")
conn.row_factory = sqlite3.Row
kw = ["Muse", "Cursor", "蒸馏", "Maia", "AMIE", "Meta"]
for k in kw:
    rows = conn.execute(
        "SELECT DISTINCT source_name, title FROM news_items WHERE title LIKE ? AND fetched_at > datetime('now','-1 day')",
        (f"%{k}%",),
    ).fetchall()
    if len(rows) >= 2:
        print(f"\n『{k}』被 {len(rows)} 个源报道:")
        for r in rows:
            print(f"  [{r['source_name']}] {r['title'][:44]}")

print("\n=== 3. URL 规范化去重机会（带跟踪参数的重复 URL）===")
rows = conn.execute("SELECT url FROM news_items").fetchall()
import urllib.parse
from collections import Counter
keys = Counter()
for r in rows:
    p = urllib.parse.urlparse(r["url"])
    key = p.netloc + p.path.rstrip("/")
    keys[key] += 1
dups = {k: v for k, v in keys.items() if v > 1}
print(f"路径级重复（同一路径不同参数）: {len(dups)} 组")
for k, v in list(dups.items())[:5]:
    print(f"  {k}  x{v}")
