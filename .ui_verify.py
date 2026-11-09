# UI 标准验证脚本 v3：用 DOM/计算样式/几何断言核对"真实构建对照清单"
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

BASE = " http://localhost:8000".strip()
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")


def find_news_and_open(page):
    """找一篇能出摘要的新闻文章，点「点开汇总」按钮（标题现在直接跳原文，不能点）。"""
    for path in ["/hot"] + [f"/timeline?page={i}" for i in (1, 2)]:
        page.goto(BASE + path, wait_until="networkidle")
        page.wait_for_timeout(300)
        loc = page.locator(
            'button.sum-btn[onclick*="aihot.news"], button.sum-btn[onclick*="techcrunch"], '
            'button.sum-btn[onclick*="qbitai"], button.sum-btn[onclick*="therundown"], button.sum-btn[onclick*="tldr.tech"]'
        )
        if loc.count() > 0:
            loc.first.click()
            page.wait_for_selector("#sum-modal:not(.hidden)", timeout=15000)
            try:
                page.wait_for_selector("#sum-body .sec h4", timeout=90000)
            except Exception:
                pass
            return
    raise RuntimeError("热榜与时间线前 2 页未找到新闻类文章")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")

    # ---------- 桌面 ----------
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    page.goto(BASE + "/hot", wait_until="networkidle")
    page.wait_for_timeout(600)

    # S1 内容宽 ~900px 居中 + 系统字体
    box = page.evaluate("""() => {
        const el = document.querySelector('.wrap') || document.body;
        const cs = getComputedStyle(document.body);
        return {x: el.getBoundingClientRect().x, w: el.getBoundingClientRect().width, font: cs.fontFamily};
    }""")
    check("S1 内容区约 900px 居中", 840 <= box["w"] <= 960 and abs(box["x"] - (1280 - box["w"]) / 2) < 4,
          f"宽={box['w']:.0f}px x={box['x']:.0f}")
    check("S1 系统字体", any(f in box["font"] for f in ("system-ui", "-apple-system", "Segoe UI", "PingFang")), box["font"][:60])

    # S2 顶栏：5 个纯文本 tab + 设置抽屉按钮
    hdr = page.evaluate("""() => {
        const brand = document.querySelector('header .brand');
        const nav = document.querySelector('header nav');
        const tabs = [...nav.querySelectorAll('a')].map(a => a.textContent.trim());
        const setBtn = document.querySelector('[data-open-settings]');
        const active = nav.querySelector('a.active');
        const inactive = nav.querySelector('a:not(.active)');
        return {brand: brand.textContent.trim(), tabs, hasSettingsTab: tabs.includes('设置'),
                hasSetBtn: !!setBtn,
                activeColor: active && getComputedStyle(active).color,
                inactiveColor: inactive && getComputedStyle(inactive).color};
    }""")
    check("S2 顶栏左侧标题『AI 资讯聚合』", hdr["brand"].replace(" ", "") in ("AI资讯聚合", "AI/资讯聚合"), hdr["brand"])
    check("S2 五个纯文本 tab（今日热榜/时间线/日报/分类/收藏）",
          hdr["tabs"] == ["今日热榜", "时间线", "日报", "分类", "收藏"], str(hdr["tabs"]))
    check("S2 设置不是 tab 而是按钮", (not hdr["hasSettingsTab"]) and hdr["hasSetBtn"])
    check("S2 当前 tab 高亮", hdr["activeColor"] != hdr["inactiveColor"], f"{hdr['activeColor']} vs {hdr['inactiveColor']}")

    # U1 utility bar
    util = page.evaluate("""() => ({
        updated: (document.getElementById('u-updated') || {}).textContent || '',
        hasPulse: !!document.querySelector('.u-update .pulse'),
        engine: (document.getElementById('u-engine') || {}).textContent || '',
    })""")
    check("U1 更新于 x（呼吸点）", "更新于" in util["updated"] and util["hasPulse"], util["updated"])
    check("U1 模型状态按钮（当前：…/设置模型）", ("当前：" in util["engine"]) or ("设置模型" in util["engine"]), util["engine"])

    # U3 源健康指示器 + 面板
    page.wait_for_timeout(800)
    h3 = page.evaluate("() => (document.getElementById('u-health') || {}).textContent || ''")
    check("U3 源健康指示器（源 N/M）", re.match(r"源 \d+/\d+", h3), h3)
    page.click("#u-health")
    page.wait_for_timeout(200)
    panel = page.evaluate("""() => {
        const p = document.querySelector('.health-panel');
        return p ? {rows: p.querySelectorAll('.health-row').length} : null;
    }""")
    check("U3 健康面板展开（逐源状态）", panel and panel["rows"] >= 10, f"{panel and panel['rows']} 行")
    page.click("#u-health")

    # L1 lead strip
    lead = page.evaluate("""() => {
        const l = document.querySelector('.lead');
        if (!l) return null;
        return {brand: l.querySelector('.lead-brand').textContent.trim(),
                title: l.querySelector('.lead-title').textContent.trim(),
                score: l.querySelector('.lead-score b').textContent.trim(),
                firstTitle: (document.querySelector('.item a.title') || {}).textContent || ''};
    }""")
    check("L1 lead strip（AI/NOW 标语+头条+分数盒）",
          lead and "AI / NOW" in lead["brand"] and lead["title"] == lead["firstTitle"] and lead["score"],
          f"标语={lead and lead['brand']} 分数={lead and lead['score']}")

    # C1 卡片结构：排名/分类badge/标题跳原文/汇总按钮
    card = page.evaluate("""() => {
        const it = document.querySelector('.item');
        const ranks = [...document.querySelectorAll('.item .rank')].map(r => r.textContent.trim());
        const title = it.querySelector('a.title');
        const sumBtn = [...it.querySelectorAll('button')].find(b => b.textContent.includes('点开汇总'));
        const badge = it.querySelector('.cat-badge');
        return {rankCount: ranks.length, firstRanks: ranks.slice(0, 3),
                href: title.getAttribute('href'), target: title.getAttribute('target'),
                hasSumBtn: !!sumBtn, badgeText: badge ? badge.textContent : null,
                badgeColored: badge ? !!badge.className.match(/cb-(model|app|policy|finance|robot|other)/) : false};
    }""")
    check("C1 排名 01/02/03… 全量", card["rankCount"] == 20 and card["firstRanks"] == ["01", "02", "03"],
          f"{card['rankCount']} 个，前 3：{card['firstRanks']}")
    check("C1 标题跳转原文（新窗口）", card["href"] and card["href"].startswith("http") and card["target"] == "_blank", card["href"])
    check("C1 「点开汇总 →」按钮", card["hasSumBtn"])
    check("C1 彩色分类 badge", card["badgeText"] and card["badgeColored"], card["badgeText"])

    # ST1 故事合并：多源事件应显示「N 源报道」徽标 + 可展开各源列表
    story = page.evaluate("""() => {
        const b = document.querySelector('.story-badge');
        if (!b) return null;
        const det = document.querySelector('.story-members');
        return {badge: b.textContent.trim(), members: det ? det.querySelectorAll('li').length : 0};
    }""")
    check("ST1 热榜故事合并（N 源报道徽标 + 各源列表）",
          story and "源报道" in story["badge"] and story["members"] >= 2,
          f"{story and story['badge']}，成员 {story and story['members']} 条")

    # U2 已读/未读：把首条标记已读后应无蓝点，开关打开只剩未读
    first_url = page.evaluate("() => (document.querySelector('.item[data-url]') || {}).getAttribute('data-url')")
    page.evaluate("u => localStorage.setItem('readUrls', JSON.stringify([u]))", first_url)
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(500)
    u2 = page.evaluate("""() => {
        const items = [...document.querySelectorAll('.item[data-url]')];
        return {unreadN: items.filter(i => i.classList.contains('unread')).length,
                total: items.length, hasToggle: !!document.getElementById('only-unread')};
    }""")
    check("U2 未读蓝点（已读无蓝点）", u2["hasToggle"] and 0 < u2["unreadN"] < u2["total"],
          f"未读 {u2['unreadN']}/{u2['total']}")
    page.check("#only-unread")
    page.wait_for_timeout(150)
    hidden = page.evaluate("""() => {
        const items = [...document.querySelectorAll('.item[data-url]')];
        return {visible: items.filter(i => i.style.display !== 'none').length,
                unread: items.filter(i => i.classList.contains('unread')).length};
    }""")
    check("U2 只看未读过滤生效", hidden["visible"] == hidden["unread"], f"可见 {hidden['visible']} = 未读 {hidden['unread']}")
    page.uncheck("#only-unread")
    page.wait_for_timeout(100)
    page.evaluate("() => localStorage.removeItem('readUrls')")

    # C2 来源筛选 chips
    chips = page.evaluate("""() => {
        const cs = [...document.querySelectorAll('#src-chips .chip')];
        return {total: cs.length, countsFilled: cs.every(c => c.querySelector('.chip-n').textContent !== '')};
    }""")
    check("C2 来源筛选 chips 带计数", chips["total"] >= 2 and chips["countsFilled"], f"{chips['total']} 个")
    page.locator("#src-chips .chip[data-src]:not([data-src=''])").first.click()
    page.wait_for_timeout(200)
    filtered = page.evaluate("""() => {
        const active = document.querySelector('#src-chips .chip.active');
        const visible = [...document.querySelectorAll('.item')].filter(i => i.style.display !== 'none');
        return {src: active.dataset.src, allMatch: visible.every(i => i.dataset.source === active.dataset.src), n: visible.length};
    }""")
    check("C2 chip 过滤生效", filtered["allMatch"] and filtered["n"] > 0, f"chip={filtered['src']} 可见={filtered['n']}")
    page.locator("#src-chips .chip[data-src='']").click()
    page.wait_for_timeout(150)

    # G1 GitHub 一键操作 + B1 屏蔽按钮（热榜无 GitHub 条目则去时间线找）
    g1 = page.evaluate("""() => {
        const find = () => [...document.querySelectorAll('.item')].find(i => (i.dataset.url||'').startsWith('https://github.com/'));
        let gh = find();
        return {hasGh: !!gh, ghActions: gh ? gh.querySelectorAll('.gh-actions a').length : 0,
                cloneBtn: gh ? !!gh.querySelector('[data-act="clone"]') : false,
                blockBtn: !!document.querySelector('.item .block-btn')};
    }""")
    check("G1 GitHub 一键 Clone/Fork/部署", g1["hasGh"] and g1["ghActions"] >= 3 and g1["cloneBtn"],
          f"按钮 {g1['ghActions']} 个")
    check("B1 条目屏蔽按钮（✕）", g1["blockBtn"])

    # PF2 热榜「为我精选」入口
    pfchip = page.evaluate("() => document.body.textContent.includes('为我精选') || document.body.textContent.includes('返回普通热榜')")
    check("PF2 热榜「为我精选」开关", pfchip)

    # P1 热榜分页
    pager = page.evaluate("""() => ({
        hasPager: !!document.querySelector('.pager'),
        cur: (document.querySelector('.pager .cur') || {}).textContent || ''
    })""")
    check("P1 热榜分页器（第 1 / N 页）", pager["hasPager"] and "第 1 /" in pager["cur"], pager["cur"])
    r2 = page.goto(BASE + "/hot?page=2", wait_until="networkidle")
    check("P1 /hot?page=2 可访问", r2 and r2.status == 200, f"HTTP {r2 and r2.status}")
    page.goto(BASE + "/hot", wait_until="networkidle")

    # M1 摘要弹窗：引擎条 + 01-04 编号四段 + bullet
    find_news_and_open(page)
    modal = page.evaluate("""() => {
        const card = document.querySelector('#sum-modal .modal-card');
        const heads = [...card.querySelectorAll('.sec h4')].map(h => h.textContent.trim());
        return {heads, engine: (card.querySelector('#sum-engine-text') || {}).textContent || '',
                engineChange: (card.querySelector('#sum-engine-change') || {}).textContent || '',
                bullets: card.querySelectorAll('.sec ul li').length,
                hasRegen: !!([...card.querySelectorAll('button')].find(b => b.textContent.includes('重新生成'))),
                closeTopRight: !!card.querySelector('.modal-close')};
    }""")
    four = modal["heads"] and any("01 这是什么" in h for h in modal["heads"]) and any("02 关键事实" in h for h in modal["heads"]) \
        and any("03 说人话" in h for h in modal["heads"]) and any("04 原文链接" in h for h in modal["heads"])
    check("M1 编号四段式 01-04", four, str(modal["heads"]))
    check("M1 引擎条（当前：/未配置 + 更换入口）", ("当前：" in modal["engine"] or "未配置" in modal["engine"]) and "›" in modal["engineChange"],
          modal["engine"])
    check("M1 关键事实为 bullet 列表", modal["bullets"] >= 1, f"{modal['bullets']} 条")
    check("M1 重新生成/关闭按钮", modal["hasRegen"] and modal["closeTopRight"])
    page.evaluate("closeSummary()")

    # D1 设置抽屉
    page.click("[data-open-settings]")
    page.wait_for_timeout(700)
    drawer = page.evaluate("""() => ({
        open: document.body.classList.contains('drawer-open'),
        src: (document.getElementById('settings-frame') || {}).getAttribute('src') || ''
    })""")
    check("D1 设置抽屉打开（iframe 挂载 /settings）", drawer["open"] and drawer["src"] == "/settings", str(drawer))
    page.evaluate("document.body.classList.remove('drawer-open')")

    # T1 主题页：分类 pill + 热度排序 + 紧凑行
    page.goto(BASE + "/topics", wait_until="networkidle")
    page.wait_for_timeout(500)
    tp = page.evaluate("""() => {
        const chips = [...document.querySelectorAll('#cat-chips .chip')];
        const items = [...document.querySelectorAll('#topic-list .item')];
        const scores = items.map(i => parseFloat(i.dataset.hot || '0'));
        return {chips: chips.length, countsFilled: chips.every(c => c.querySelector('.chip-n').textContent !== ''),
                sorted: scores.every((v, i) => i === 0 || scores[i-1] >= v),
                slim: !!document.querySelector('.slim-list'), n: items.length,
                hasH2Blocks: document.querySelectorAll('h2.cat').length};
    }""")
    check("T1 分类 pill（带计数）", tp["chips"] >= 2 and tp["countsFilled"], f"{tp['chips']} 个 pill")
    check("T1 按热度全局排序", tp["sorted"], f"{tp['n']} 条")
    check("T1 紧凑行（无 h2 大块）", tp["slim"] and tp["hasH2Blocks"] == 0)
    page.locator("#cat-chips .chip[data-cat]:not([data-cat=''])").first.click()
    page.wait_for_timeout(200)
    tp2 = page.evaluate("""() => {
        const active = document.querySelector('#cat-chips .chip.active');
        const visible = [...document.querySelectorAll('#topic-list .item')].filter(i => i.style.display !== 'none');
        return {cat: active.dataset.cat, allMatch: visible.every(i => i.dataset.cat === active.dataset.cat)};
    }""")
    check("T1 pill 过滤生效", tp2["allMatch"], f"分类={tp2['cat']}")

    # S5 时间线：日期分组头 + 倒序
    page.goto(BASE + "/timeline", wait_until="networkidle")
    page.wait_for_timeout(400)
    tl = page.evaluate("""() => {
        const heads = [...document.querySelectorAll('.date-head')].map(h => h.textContent.trim());
        const ts = [...document.querySelectorAll('.item[data-ts]')].map(e => e.getAttribute('data-ts'));
        const metaSample = (document.querySelector('.meta time.rel') || {}).textContent || '';
        return {heads, sorted: ts.every((v, i) => i === 0 || ts[i-1] >= v), n: ts.length, metaSample};
    }""")
    check("S5 时间线日期分组头带条数", any("条" in h for h in tl["heads"]), str(tl["heads"][:3]))
    check("S5 按时间倒序 + HH:MM", tl["sorted"] and re.search(r"\d{2}:\d{2}", tl["metaSample"]), tl["metaSample"])

    # S6 日报 / D2 导出 / S7 收藏
    page.goto(BASE + "/daily", wait_until="networkidle")
    daily = page.evaluate("""() => ({
        groups: document.querySelectorAll('h2.cat').length,
        items: document.querySelectorAll('.item').length,
        hasExport: !!document.getElementById('export-md'),
        md: (typeof exportDailyMd === 'function') ? exportDailyMd().slice(0, 30) : null,
    })""")
    check("S6 日报按主题分组 ≤20", daily["groups"] >= 1 and daily["items"] <= 20, f"{daily['groups']} 组 {daily['items']} 条")
    check("D2 日报一键导出 Markdown", daily["hasExport"] and daily["md"] and daily["md"].startswith("# AI 资讯日报"),
          daily["md"])
    page.goto(BASE + "/bookmarks", wait_until="networkidle")
    bm = page.evaluate("""() => ({
        empty: document.body.textContent.includes('还没有收藏'),
        items: document.querySelectorAll('.item').length
    })""")
    check("S7 收藏页（空态提示或有收藏条目）", bm["empty"] or bm["items"] > 0,
          "空态" if bm["empty"] else f"{bm['items']} 条收藏")

    # S8 设置页结构（直达）
    page.goto(BASE + "/settings", wait_until="networkidle")
    st = page.evaluate("""() => ({
        hasDefault: document.body.textContent.includes('默认解读引擎'),
        hasEnabled: document.body.textContent.includes('已启用'),
        hasOther: [...document.querySelectorAll('details.panel summary')].some(s => s.textContent.includes('其他平台')),
        otherClosed: ![...document.querySelectorAll('details.panel')].find(d => d.textContent.includes('其他平台')).open,
        hasKey: !!document.querySelector('input[type=password]'),
        hasBase: !!document.querySelector('.f-base'), hasModel: !!document.querySelector('.f-model'),
        hasDatalist: !!document.querySelector('#dl-models'),
        hasTest: document.body.textContent.includes('测试连接'), hasDel: document.body.textContent.includes('删除已保存 Key'),
        hasFetchModels: document.body.textContent.includes('一键获取模型'),
    })""")
    check("S8 默认引擎区/已启用/其他平台收起", st["hasDefault"] and st["hasEnabled"] and st["hasOther"] and st["otherClosed"])
    check("S8 key/base/模型 datalist/测试/删除/获取模型", st["hasKey"] and st["hasBase"] and st["hasModel"] and st["hasDatalist"] and st["hasTest"] and st["hasDel"] and st["hasFetchModels"])

    # CS1 自定义源面板 + 屏蔽管理面板
    page.goto(BASE + "/settings", wait_until="networkidle")
    page.wait_for_timeout(600)
    cs = page.evaluate("""() => ({
        hasCustom: document.body.textContent.includes('自定义 RSS 源'),
        hasBlocks: document.body.textContent.includes('屏蔽管理'),
        csList: !!document.getElementById('cs-list'),
    })""")
    check("CS1 自定义 RSS 源 / 屏蔽管理面板", cs["hasCustom"] and cs["hasBlocks"] and cs["csList"])

    # PF1 兴趣画像面板（学习/重置/手动编辑）
    pf = page.evaluate("""() => ({
        panel: document.body.textContent.includes('兴趣画像'),
        learn: !!document.getElementById('pf-learn'),
        reset: !!document.getElementById('pf-reset'),
        json: !!document.getElementById('pf-json'),
    })""")
    check("PF1 兴趣画像面板（学习/重置/编辑）", pf["panel"] and pf["learn"] and pf["reset"] and pf["json"])

    # A4 深色模式
    light_bg = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    page.click("#theme-toggle")
    page.wait_for_timeout(200)
    dark = page.evaluate("() => ({t: document.documentElement.dataset.theme, bg: getComputedStyle(document.body).backgroundColor})")
    check("A4 深色切换生效", dark["t"] == "dark" and dark["bg"] != light_bg, f"{light_bg} → {dark['bg']}")
    page.click("#theme-toggle")
    page.wait_for_timeout(150)
    ctx.close()

    # ---------- 移动端 ----------
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    page = ctx.new_page()
    page.goto(BASE + "/hot", wait_until="networkidle")
    page.wait_for_timeout(500)
    m1 = page.evaluate("() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})")
    check("S9 移动端热榜无横向溢出", m1["sw"] <= m1["iw"] + 1, f"scrollWidth={m1['sw']}")
    find_news_and_open(page)
    m2 = page.evaluate("""() => {
        const rb = document.querySelector('#sum-modal .modal-card').getBoundingClientRect();
        return {x: rb.x, right: rb.right, sw: document.documentElement.scrollWidth, vw: window.innerWidth};
    }""")
    check("S9 移动端弹窗不溢出", m2["x"] >= 0 and m2["right"] <= m2["vw"] + 1 and m2["sw"] <= m2["vw"] + 1,
          f"x={m2['x']:.0f} right={m2['right']:.0f}")
    ctx.close()
    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n===== {len(results) - len(fails)}/{len(results)} PASS =====")
sys.exit(1 if fails else 0)
