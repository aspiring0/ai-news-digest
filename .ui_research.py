# UI 竞品调研：访问热门资讯平台，提取布局遥测 + 首屏截图
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("ui_screenshots/research")
OUT.mkdir(parents=True, exist_ok=True)

SITES = [
    ("aihot", "https://aihot.news"),
    ("hackernews", "https://news.ycombinator.com"),
    ("techcrunch", "https://techcrunch.com/category/artificial-intelligence/"),
    ("36kr", "https://36kr.com"),
    ("producthunt", "https://www.producthunt.com"),
    ("qbitai", "https://www.qbitai.com"),
]

TELEMETRY_JS = """
() => {
  const out = {};
  out.title = document.title.slice(0, 60);
  const b = getComputedStyle(document.body);
  out.bodyBg = b.backgroundColor; out.textColor = b.color;
  out.font = b.fontFamily.slice(0, 90); out.baseFontSize = b.fontSize;
  const header = document.querySelector('header')
    || document.querySelector('[class*="header" i]:not(script):not(style)')
    || document.querySelector('nav');
  if (header) {
    const cs = getComputedStyle(header); const r = header.getBoundingClientRect();
    out.header = {h: Math.round(r.height), bg: cs.backgroundColor, pos: cs.position};
    out.headerText = header.textContent.replace(/\\s+/g, ' ').trim().slice(0, 110);
  }
  const a = document.querySelector('main a') || document.querySelector('article a') || document.querySelector('a[href]');
  out.linkColor = a ? getComputedStyle(a).color : null;
  let widest = 0, widestEl = null;
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > widest && r.width <= 1500) { widest = r.width; widestEl = el; }
  });
  out.maxContentW = Math.round(widest);
  out.maxContentEl = widestEl ? (widestEl.tagName + '.' + String(widestEl.className).split(' ').slice(0,2).join('.')).slice(0, 60) : null;
  const freq = {};
  document.querySelectorAll('article, li, [class*="item"], [class*="card"], [class*="post"], tr.athing').forEach(el => {
    const cls = String(el.className || '').split(' ')[0];
    if (!cls && el.tagName === 'LI') return;
    const key = el.tagName + '.' + cls;
    freq[key] = (freq[key] || 0) + 1;
  });
  out.itemCandidates = Object.entries(freq).sort((x, y) => y[1] - x[1]).slice(0, 6);
  // 首屏条目样本：取出现次数最多的容器类的第一个元素文本
  let sampleText = null, sampleH = null;
  if (out.itemCandidates.length) {
    const [tag, cls] = out.itemCandidates[0][0].split('.');
    const sel = tag + (cls ? '.' + cls : '');
    const first = document.querySelector(sel);
    if (first) {
      sampleText = first.innerText.replace(/\\s+/g, ' ').trim().slice(0, 200);
      sampleH = Math.round(first.getBoundingClientRect().height);
    }
  }
  out.firstItem = {h: sampleH, text: sampleText};
  out.imgAboveFold = [...document.querySelectorAll('img')].filter(i => i.getBoundingClientRect().top < 900 && i.getBoundingClientRect().width > 40).length;
  out.scrollW = document.documentElement.scrollWidth;
  return out;
}
"""

report = {}
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
    page = ctx.new_page()
    for name, url in SITES:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            t = page.evaluate(TELEMETRY_JS)
            report[name] = {"url": url, "ok": True, **t}
            page.screenshot(path=str(OUT / f"{name}.png"))
            print(f"[OK] {name}: contentW={t.get('maxContentW')} item={t.get('itemCandidates', [['?']])[0][0]} x{t.get('itemCandidates', [['?','?']])[0][1]}")
        except Exception as e:
            report[name] = {"url": url, "ok": False, "error": str(e)[:150]}
            print(f"[FAIL] {name}: {str(e)[:100]}")
    ctx.close()
    browser.close()

(OUT / "telemetry.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("saved telemetry.json")
