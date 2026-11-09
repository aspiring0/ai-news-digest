# 抽屉打开态截图
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("ui_screenshots")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto("http://localhost:8000/hot", wait_until="networkidle")
    page.wait_for_timeout(400)
    page.click("[data-open-settings]")
    page.wait_for_timeout(1200)  # 等 iframe 加载渲染
    page.screenshot(path=str(OUT / "v3-drawer.png"))
    print("drawer OK")
    ctx.close()
    browser.close()
