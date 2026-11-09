# 深色模式热榜截图
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("ui_screenshots")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto("http://localhost:8000/hot", wait_until="networkidle")
    page.evaluate("() => { localStorage.setItem('theme', 'dark'); }")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(500)
    assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"
    page.screenshot(path=str(OUT / "v2-dark-hot.png"), full_page=False)
    print("dark-hot OK")
    ctx.close()
    browser.close()
