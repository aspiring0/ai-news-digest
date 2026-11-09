# 线上界面 vs 色彩规范 实测比对
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto("http://localhost:8000/hot", wait_until="networkidle")
    page.wait_for_timeout(400)
    got = page.evaluate("""() => {
        const cs = el => getComputedStyle(el);
        const badge = document.querySelector('.cat-badge');
        const rank1 = document.querySelector('.rank.r1, .rank.r2, .rank.r3');
        const rank4 = document.querySelector('.rank.dim');
        const brand = document.querySelector('.brand');
        return {
            bodyBg: cs(document.body).backgroundColor,
            brandFont: cs(brand).fontFamily.split(',')[0] + ' / ' + cs(brand).fontSize,
            titleFont: cs(document.querySelector('.item a.title')).fontFamily.split(',')[0],
            badge: badge ? cs(badge).color + ' bg=' + cs(badge).backgroundColor : null,
            rankTop: rank1 ? cs(rank1).color + ' ' + cs(rank1).fontFamily.split(',')[0] : null,
            rankDim: rank4 ? cs(rank4).color : null,
            itemBorder: cs(document.querySelector('.item')).borderBottom,
            hasPager: !!document.querySelector('.pager'),
        };
    }""")
    print("浅色主题实测：")
    for k, v in got.items():
        print(f"  {k}: {v}")
    # 深色抽查
    page.evaluate("() => { localStorage.setItem('theme','dark'); }")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(300)
    dark = page.evaluate("""() => ({
        bodyBg: getComputedStyle(document.body).backgroundColor,
        badge: getComputedStyle(document.querySelector('.cat-badge')).color,
    })""")
    print("深色主题实测：")
    for k, v in dark.items():
        print(f"  {k}: {v}")
    browser.close()

SPEC = {
    "bodyBg": ("rgb(250, 249, 246)", got["bodyBg"]),
    "brandFont-serif": ("Georgia", got["brandFont"]),
    "titleFont-serif": ("Georgia", got["titleFont"]),
    "rankTop-amber": ("rgb(180, 83, 9)", got["rankTop"]),
    "rankDim": ("rgb(214, 211, 209)", got["rankDim"]),
    "itemBorder-hairline": ("rgb(231, 229, 228)", got["itemBorder"]),
    "darkBg": ("rgb(22, 19, 15)", dark["bodyBg"]),
}
print("\n与色彩规范比对：")
ok = 0
for name, (want, gotv) in SPEC.items():
    hit = want in str(gotv)
    ok += hit
    print(f"  {'PASS' if hit else 'FAIL'}  {name}: 规范 {want} ⊂ 实测 {gotv}")
print(f"\n===== {ok}/{len(SPEC)} 一致 =====")
