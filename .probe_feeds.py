# 探测各 RSS/Atom 源的条目图片覆盖率
import io

import feedparser
import requests

FEEDS = {
    "AIHOT": "https://aihot.news/feed.xml",
    "TLDR AI": "https://tldr.tech/api/rss/ai",
    "Superhuman": "https://raw.githubusercontent.com/dqcenter/feedmint/main/feeds/superhuman-ai.xml",
    "The Rundown": "https://www.therundown.ai/feed",
    "量子位": "https://www.qbitai.com/feed",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Batch": "https://raw.githubusercontent.com/SebastianLavertheDe/blog-rss-feed/main/rss/deeplearning_batch_rss.xml",
    "Product Hunt": "https://www.producthunt.com/feed",
}


def entry_image(e):
    for t in e.get("media_thumbnail") or []:
        u = t.get("url")
        if u and str(u).startswith("http"):
            return u
    for m in e.get("media_content") or []:
        if str(m.get("medium")) == "image" or str(m.get("type", "")).startswith("image"):
            u = m.get("url")
            if u and str(u).startswith("http"):
                return u
    for enc in e.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("image"):
            u = enc.get("href")
            if u and str(u).startswith("http"):
                return u
    return None


HEADERS = {"User-Agent": "ai-news-oss/0.1"}
for name, url in FEEDS.items():
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        feed = feedparser.parse(resp.content)
        entries = feed.entries[:20]
        with_img = [e for e in entries if entry_image(e)]
        sample = entry_image(with_img[0])[:70] if with_img else "-"
        print(f"{name:14s} {len(with_img)}/{len(entries)} 带图  样本: {sample}")
    except Exception as ex:
        print(f"{name:14s} 失败: {str(ex)[:60]}")
