import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto("http://localhost:8000/hot", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(500)
    result = pg.evaluate("""() => {
        const gh = [...document.querySelectorAll('.item')].find(
            i => (i.dataset.url || '').startsWith('https://github.com/')
        );
        if (!gh) return null;
        const btns = [...gh.querySelectorAll('.gh-actions a')].map(a => ({
            text: a.textContent.trim(),
            href: (a.getAttribute('href') || '').slice(0, 80)
        }));
        return {url: gh.dataset.url, title: gh.querySelector('.title').textContent.slice(0, 40), btns};
    }""")
    if result:
        print(f"GitHub 条目: {result['url']}")
        print(f"标题: {result['title']}")
        for btn in result["btns"]:
            print(f"  [{btn['text']}] -> {btn['href']}")
        has_clone = any(b["text"] == "Clone" for b in result["btns"])
        has_fork = any(b["text"] == "Fork" for b in result["btns"])
        has_deploy = any("部署" in b["text"] or "Vercel" in b["href"] for b in result["btns"])
        print(f"\nClone: {'✓' if has_clone else '✗'}  Fork: {'✓' if has_fork else '✗'}  部署: {'✓' if has_deploy else '✗'}")
    else:
        print("热榜无 GitHub 条目")
    # 截图含按钮的区域
    pg.screenshot(path="ui_screenshots/clone-test.png", clip={"x": 0, "y": 0, "width": 1280, "height": 500})
    print("截图: ui_screenshots/clone-test.png")
    b.close()
