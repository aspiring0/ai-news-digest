# 补足行为门槛：真实调用 2 篇摘要（不同主题，进缓存不重复计费）
import sqlite3
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conn = sqlite3.connect("data/news.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT url, title, source_name FROM news_items "
    "WHERE source_name IN ('量子位', 'TechCrunch AI', 'AIHOT', 'IT之家') "
    "AND url NOT IN (SELECT url FROM summary_cache) "
    "ORDER BY published_at DESC LIMIT 2"
).fetchall()
for r in rows:
    print(f"点摘要: [{r['source_name']}] {r['title'][:40]}")
    u = "http://localhost:8000/api/summary?url=" + urllib.parse.quote(r["url"], safe="")
    with urllib.request.urlopen(u, timeout=180) as resp:
        d = json.loads(resp.read().decode("utf-8")) if (json := __import__("json")) else None
    print("  ->", "ok" if d and d.get("ok") else f"失败 {d}")
