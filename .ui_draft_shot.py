# 设计草稿截图：三方向桌面 + 推荐方向移动端
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("ui_drafts")
DRAFTS = ["draft1-editorial.html", "draft2-dashboard.html", "draft3-mono.html"]

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 960}, device_scale_factor=2)
    page = ctx.new_page()
    for f in DRAFTS:
        page.goto((OUT / f).resolve().as_uri())
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / (f.replace(".html", ".png"))), full_page=True)
        print(f"[desktop] {f} OK")
    ctx.close()
    # 移动端抽查：草稿 1
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
    page = ctx.new_page()
    page.goto((OUT / DRAFTS[0]).resolve().as_uri())
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / "draft1-mobile.png"), full_page=True)
    print("[mobile] draft1 OK")
    ctx.close()
    browser.close()
print("done")
