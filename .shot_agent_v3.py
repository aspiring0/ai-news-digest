import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page()
    pg.goto("http://localhost:8000/hot", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(500)
    # 点开聊天框（触发开屏简报）
    pg.click("#chat-fab")
    pg.wait_for_timeout(15000)  # 等简报生成
    pg.screenshot(path="ui_screenshots/agent-v3-chat.png", clip={"x": 640, "y": 0, "width": 640, "height": 900})
    print("chat OK")
    # 检查 Markdown 渲染
    has_table = pg.evaluate("() => !!document.querySelector('#chat-messages table')")
    has_bold = pg.evaluate("() => !!document.querySelector('#chat-messages b')")
    has_export = pg.evaluate("() => !!document.getElementById('chat-export')")
    print(f"table={has_table} bold={has_bold} export={has_export}")
    b.close()
