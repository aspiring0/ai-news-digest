# UI 审查辅助：页面截图（桌面 + 移动端 + 摘要弹窗）
# 用法: python .ui_shot.py <prefix>   prefix=before/after
import sqlite3
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = Path("ui_screenshots")
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "shot"
OUT.mkdir(exist_ok=True)

PAGES = [
    ("hot", "/hot"),
    ("timeline", "/timeline"),
    ("daily", "/daily"),
    ("topics", "/topics"),
    ("bookmarks", "/bookmarks"),
    ("settings", "/settings"),
]


def cached_urls():
    try:
        conn = sqlite3.connect("data/news.db")
        return [r[0] for r in conn.execute("SELECT url FROM summary_cache").fetchall()]
    except Exception:
        return []


def open_modal(page):
    """跨页面找一篇能出摘要的文章，点「点开汇总」按钮（标题直接跳原文，不能点）。"""
    cached = cached_urls()
    for path in ["/hot"] + [f"/timeline?page={i}" for i in range(1, 6)]:
        page.goto(BASE + path, wait_until="networkidle")
        for url in cached:
            loc = page.locator(f'button.sum-btn[onclick*="{url[:60]}"]')
            if loc.count() > 0:
                print(f"  [modal] 在 {path} 点击已缓存文章: {url[:70]}")
                loc.first.click()
                page.wait_for_selector("#sum-modal:not(.hidden)", timeout=15000)
                page.wait_for_selector("#sum-body .sec h4", timeout=120000)
                page.wait_for_timeout(400)
                return
        loc = page.locator(
            'button.sum-btn[onclick*="aihot.news"], button.sum-btn[onclick*="techcrunch"], '
            'button.sum-btn[onclick*="qbitai"], button.sum-btn[onclick*="therundown"], button.sum-btn[onclick*="tldr.tech"]'
        )
        if loc.count() > 0:
            onclick = loc.first.get_attribute("onclick")
            print(f"  [modal] 在 {path} 点击新闻文章: {(onclick or '?')[:90]}")
            loc.first.click()
            page.wait_for_selector("#sum-modal:not(.hidden)", timeout=15000)
            page.wait_for_selector("#sum-body .sec h4", timeout=120000)
            page.wait_for_timeout(400)
            return
    raise RuntimeError("热榜与时间线前 5 页均未找到可用的新闻文章")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")

    # 桌面：六页面整页截图
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    page = ctx.new_page()
    for name, path in PAGES:
        page.goto(BASE + path, wait_until="networkidle")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / f"{PREFIX}-{name}.png"), full_page=True)
        print(f"[desktop] {name} OK")
    # 摘要弹窗
    page.goto(BASE + "/hot", wait_until="networkidle")
    open_modal(page)
    page.screenshot(path=str(OUT / f"{PREFIX}-modal.png"))
    print("[desktop] modal OK")
    ctx.close()

    # 移动端：热榜 + 弹窗
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
    page = ctx.new_page()
    page.goto(BASE + "/hot", wait_until="networkidle")
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"{PREFIX}-mobile-hot.png"), full_page=True)
    print("[mobile] hot OK")
    open_modal(page)
    page.screenshot(path=str(OUT / f"{PREFIX}-mobile-modal.png"))
    print("[mobile] modal OK")
    ctx.close()

    browser.close()

print("done")
