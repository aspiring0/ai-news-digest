import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page()
    pg.goto("http://localhost:8000/hot", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(500)

    # 找到"讨论"按钮
    btns = pg.locator(".discuss-btn")
    print(f"讨论按钮数: {btns.count()}")

    # 点击第一条的讨论按钮
    if btns.count() > 0:
        btns.first.click()
        pg.wait_for_timeout(20000)  # 等 Agent 回复
        pg.screenshot(path="ui_screenshots/discuss-chat.png")
        print("截图 OK")

        # 检查功能
        has_ctx = pg.evaluate("() => document.body.textContent.includes('正在讨论')")
        has_reply = pg.evaluate("() => !!document.querySelector('.cd-msg.cd-bot .cd-bot-content')")
        print(f"上下文提示: {has_ctx}, Agent 回复: {has_reply}")
    else:
        print("未找到讨论按钮")
    b.close()
