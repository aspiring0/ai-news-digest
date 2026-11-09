# 线框图截图（上下两半，避免单图过长）
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("ui_drafts")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto((OUT / "wireframe.html").resolve().as_uri())
    page.wait_for_timeout(300)
    secs = page.locator("section.sec")
    n = secs.count()
    print(f"sections: {n}")
    # 整页一张
    page.screenshot(path=str(OUT / "wireframe-all.png"), full_page=True)
    # 前两块（全局+热榜）与后三块（弹窗+列表页+抽屉）
    secs.nth(0).screenshot(path=str(OUT / "wireframe-1.png"))
    secs.nth(1).screenshot(path=str(OUT / "wireframe-2.png"))
    y2 = secs.nth(2).bounding_box()["y"] - 10
    page.screenshot(path=str(OUT / "wireframe-3.png"),
                    clip={"x": 0, "y": y2, "width": 1440, "height": 3000})
    print("wireframe shots OK")
    ctx.close()
    browser.close()
