import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page()
    pg.goto("http://localhost:8000/hot", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(500)

    # 打开聊天
    pg.click("#chat-fab")
    pg.wait_for_timeout(20000)  # 等简报 + 建议
    pg.screenshot(path="ui_screenshots/agent-final.png", clip={"x": 640, "y": 0, "width": 640, "height": 900})

    # 检查功能
    result = pg.evaluate("""() => ({
        hasExport: !!document.getElementById('chat-export'),
        hasSessions: !!document.getElementById('chat-sessions-btn'),
        hasSuggest: !document.getElementById('chat-suggest').classList.contains('hidden'),
        hasTokens: !document.getElementById('chat-tokens').classList.contains('hidden'),
        hasBriefing: !!document.querySelector('#chat-messages .chat-msg.bot'),
        msgs: document.querySelectorAll('#chat-messages .chat-msg').length,
    })""")
    print("功能检查:", result)

    # 测试斜杠命令
    pg.fill("#chat-input", "/")
    pg.wait_for_timeout(300)
    cmd_visible = pg.evaluate("() => !document.getElementById('chat-cmd-hint').classList.contains('hidden')")
    print(f"斜杠命令补全: {cmd_visible}")

    # 打开会话列表
    pg.click("#chat-sessions-btn")
    pg.wait_for_timeout(500)
    sessions_visible = pg.evaluate("() => !document.getElementById('chat-sessions').classList.contains('hidden')")
    print(f"会话列表: {sessions_visible}")

    b.close()
