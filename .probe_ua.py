# UA 差异验证：三种 UA 对三个 404 源的表现
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests

URLS = [
    ("Sierra", "https://sierra.ai/blog/rss.xml"),
    ("ARC Prize", "https://arcprize.org/blog/rss.xml"),
    ("Comfy Blog", "https://blog.comfy.org/rss.xml"),
]
UAS = {
    "项目UA": "ai-news-oss/0.1 (+https://github.com/ai-news-oss)",
    "混合UA(Mozilla+身份)": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 ai-news-oss/0.1",
    "浏览器UA": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}
for name, url in URLS:
    row = []
    for label, ua in UAS.items():
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=15)
            n = len(feedparser.parse(r.content).entries)
            row.append(f"{label}={r.status_code}/{n}条")
        except Exception as e:
            row.append(f"{label}=ERR")
    print(f"{name:10s} " + " | ".join(row))
