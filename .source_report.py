# 各源实时状况：条数 + 最新一条时间
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import sqlite3

conn = sqlite3.connect("data/news.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT source_name, COUNT(*) AS n,
           MAX(COALESCE(published_at, fetched_at)) AS latest
    FROM news_items GROUP BY source_name ORDER BY n DESC
""").fetchall()
total = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
print(f"总条数 {total}，有数据源 {len(rows)} 个")
for r in rows:
    print(f"  {r['source_name']}\t{r['n']}\t{r['latest'][:16]}")
