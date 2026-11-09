# 色彩规范截图
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("ui_drafts")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto((OUT / "wireframe.html").resolve().as_uri())
    page.wait_for_timeout(300)
    page.locator("section.sec").nth(5).screenshot(path=str(OUT / "wireframe-color.png"))
    print("color spec OK")
    ctx.close()
    browser.close()
