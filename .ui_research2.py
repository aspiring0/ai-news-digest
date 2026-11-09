# 补采 aihot / producthunt 遥测
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("ui_screenshots/research")
SITES = [("aihot", "https://aihot.news"), ("producthunt", "https://www.producthunt.com")]

JS = """
() => {
  const out = {};
  out.title = document.title.slice(0, 60);
  const b = getComputedStyle(document.body);
  out.bodyBg = b.backgroundColor; out.textColor = b.color;
  out.font = b.fontFamily.slice(0, 90); out.baseFontSize = b.fontSize;
  const header = document.querySelector('header') || document.querySelector('[class*="header" i]:not(script):not(style)') || document.querySelector('nav');
  if (header) {
    const cs = getComputedStyle(header); const r = header.getBoundingClientRect();
    out.header = {h: Math.round(r.height), bg: cs.backgroundColor, pos: cs.position};
    out.headerText = header.textContent.replace(/\\s+/g, ' ').trim().slice(0, 110);
  }
  const a = document.querySelector('main a') || document.querySelector('a[href]');
  out.linkColor = a ? getComputedStyle(a).color : null;
  let widest = 0, widestEl = null;
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > widest && r.width <= 1500) { widest = r.width; widestEl = el; }
  });
  out.maxContentW = Math.round(widest);
  const freq = {};
  document.querySelectorAll('article, li, [class*="item"], [class*="card"], [class*="post"], [class*="news"], tr').forEach(el => {
    const cls = String(el.className || '').split(' ')[0];
    const key = el.tagName + '.' + (cls || '_');
    freq[key] = (freq[key] || 0) + 1;
  });
  out.itemCandidates = Object.entries(freq).sort((x, y) => y[1] - x[1]).slice(0, 8);
  // 采样：取候选里文本最长的前 2 个容器
  out.samples = [];
  for (const [key] of out.itemCandidates.slice(0, 4)) {
    const [tag, cls] = key.split('.');
    const first = document.querySelector(tag + (cls !== '_' ? '.' + cls : ''));
    if (first && first.innerText.trim()) {
      out.samples.push({sel: key, h: Math.round(first.getBoundingClientRect().height),
                        text: first.innerText.replace(/\\s+/g, ' ').trim().slice(0, 180)});
      if (out.samples.length >= 2) break;
    }
  }
  out.imgAboveFold = [...document.querySelectorAll('img')].filter(i => i.getBoundingClientRect().top < 900 && i.getBoundingClientRect().width > 40).length;
  out.scrollW = document.documentElement.scrollWidth;
  return out;
}
"""

data = json.loads((OUT / "telemetry.json").read_text(encoding="utf-8"))
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
    page = ctx.new_page()
    for name, url in SITES:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(5000)
            t = page.evaluate(JS)
            data[name] = {"url": url, "ok": True, **t}
            page.screenshot(path=str(OUT / f"{name}.png"))
            cands = t.get("itemCandidates") or []
            top = cands[0] if cands else ["none", 0]
            print(f"[OK] {name}: contentW={t.get('maxContentW')} topItem={top[0]} x{top[1]}")
        except Exception as e:
            print(f"[FAIL] {name}: {str(e)[:120]}")
    ctx.close()
    browser.close()
(OUT / "telemetry.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("updated telemetry.json")
