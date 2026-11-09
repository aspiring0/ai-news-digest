import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page()
    pg.goto("http://localhost:8000/hot", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(500)
    pg.screenshot(path="ui_screenshots/translation-hot.png", clip={"x": 0, "y": 0, "width": 1280, "height": 700})
    print("OK")
    b.close()
