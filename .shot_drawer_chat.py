import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page()
    pg.goto("http://localhost:8000/hot", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(500)
    # 打开聊天抽屉
    pg.click("#chat-fab")
    pg.wait_for_timeout(20000)  # 等简报
    pg.screenshot(path="ui_screenshots/chat-drawer-open.png")
    print("desktop OK")

    # 移动端
    ctx2 = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
    pg2 = ctx2.new_page()
    pg2.goto("http://localhost:8000/hot", wait_until="networkidle", timeout=30000)
    pg2.wait_for_timeout(400)
    pg2.click("#chat-fab")
    pg2.wait_for_timeout(500)
    pg2.screenshot(path="ui_screenshots/chat-drawer-mobile.png")
    print("mobile OK")
    b.close()
