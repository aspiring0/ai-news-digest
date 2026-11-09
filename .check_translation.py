import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = sqlite3.connect("data/news.db")
total = c.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
translated = c.execute("SELECT COUNT(*) FROM news_items WHERE title_cn IS NOT NULL AND title_cn != ''").fetchone()[0]
print(f"总 {total} | 已翻译 {translated} | 待翻译 {total - translated}")
rows = c.execute("SELECT title, title_cn, description_cn FROM news_items WHERE title_cn IS NOT NULL AND title_cn != '' LIMIT 6").fetchall()
for r in rows:
    print(f"  原: {r[0][:55]}")
    print(f"  中: {r[1][:45]}")
    if r[2]:
        print(f"  描述: {r[2][:45]}")
    print()
