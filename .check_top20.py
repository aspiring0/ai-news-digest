# 复算热榜 top20 构成（与 scorer.py 相同公式）
import sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect("data/news.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT url, title, source_name, published_at, fetched_at, score FROM news_items").fetchall()


def parse(s):
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


now = datetime.now(timezone.utc)
items = []
for r in rows:
    base = parse(r["published_at"]) or parse(r["fetched_at"])
    age_h = max(0.0, (now - base).total_seconds() / 3600)
    hot = r["score"] * (0.5 ** (age_h / 48))
    items.append((hot, r["source_name"], r["title"], r["score"], age_h))

items.sort(reverse=True)
from collections import Counter
comp = Counter(s for _, s, _, _, _ in items[:20])
print("=== 热榜 top20 来源构成 ===")
for s, c in comp.most_common():
    print(f"  {s}: {c}")
print("\n=== top20 明细（热度/来源/静态分/年龄h/标题） ===")
for hot, src, title, sc, age in items[:20]:
    print(f"  {hot:6.1f}  {src:14s} 静态{sc:5.1f} 龄{age:6.1f}h  {title[:38]}")
print("\n=== AIHOT 条目最高排名 ===")
aihot = [(i, it) for i, it in enumerate(items, 1) if it[1] == "AIHOT"][0]
print(f"  第 {aihot[0]} 名：{aihot[1][2][:40]}（热度 {aihot[1][0]:.1f}）")
