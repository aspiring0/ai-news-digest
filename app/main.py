"""FastAPI 入口：热榜 / 时间线 / 收藏 / 日报 / 主题 / 设置；启动时先抓一次，再开定时任务。"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import classifier, db, profile as profile_mod, providers, scheduler, summarizer
from .fetch_all import run_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ai-news-oss")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "..", "templates"))
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")

PER_PAGE = 20
LOCAL_TZ = ZoneInfo(os.environ.get("TZ", "Asia/Shanghai"))


def _mark_bookmarks(items: list[dict]) -> list[dict]:
    """给条目打上收藏标记（批量查一次）。"""
    with db._connect() as conn:
        urls = {r[0] for r in conn.execute("SELECT url FROM bookmarks").fetchall()}
    for it in items:
        it["bookmarked"] = it["url"] in urls
    return items


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表 + 先跑一次抓取（库里有数据页面才不空），再开定时任务
    db.init_db()
    logger.info("启动抓取（首次）…")
    try:
        summary = run_once()
        logger.info("首次抓取完成：%s", summary.get("_total"))
    except Exception as e:  # noqa: BLE001 - 首次失败不阻塞服务启动
        logger.warning("首次抓取失败，稍后定时任务会重试: %s", e)
    scheduler.start()
    yield
    scheduler.scheduler.shutdown(wait=False)


app = FastAPI(title="AI 资讯聚合（开源版）", lifespan=lifespan)

# ---- PWA 静态资源（manifest/sw/icons） ----
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/manifest.json", include_in_schema=False)
def manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse(url="/hot")


@app.get("/hot")
def hot(request: Request, page: int = 1, personal: int = 0):
    """热榜（故事级）：同一事件多源合并为一席。personal=1 应用兴趣画像（为我精选）。"""
    page = max(1, page)
    prof = profile_mod.load_profile() if personal else None
    items, total = db.get_hot_stories(page=page, per_page=PER_PAGE, profile=prof)
    items = _mark_bookmarks(items)
    st = db.stats()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    # 头条特殊处理（v0.3.7）：top1 有摘要缓存时，lead 区内联中文解释
    lead_summary = None
    if page == 1 and items:
        cached = db.get_summary(items[0]["url"])
        if cached:
            plain = cached.get("plain", "")
            lead_summary = {
                "core": cached.get("core", ""),
                "plain": (plain[:160] + "…") if len(plain) > 160 else plain,
            }
    return templates.TemplateResponse(
        request,
        "hot.html",
        {
            "items": items, "stats": st, "page": page,
            "total_pages": total_pages, "total": total,
            "lead_summary": lead_summary,
            "personal": bool(personal),
            "has_profile": profile_mod.load_profile() is not None,
        },
    )


@app.get("/timeline")
def timeline(request: Request, page: int = 1):
    page = max(1, page)
    items, total = db.get_timeline(page=page, per_page=PER_PAGE)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return templates.TemplateResponse(
        request,
        "timeline.html",
        {
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@app.get("/bookmarks")
def bookmarks_page(request: Request):
    items = db.get_bookmarks()
    return templates.TemplateResponse(request, "bookmarks.html", {"items": items})


@app.post("/api/bookmark")
def api_bookmark(payload: dict):
    """收藏/取消收藏。body: {"url": ...}。返回 {"bookmarked": bool}。"""
    url = (payload.get("url") or "").strip()
    if not url:
        return JSONResponse({"ok": False, "message": "url 不能为空"}, status_code=400)
    try:
        state = db.toggle_bookmark(url)
    except KeyError:
        return JSONResponse({"ok": False, "message": "新闻不存在"}, status_code=404)
    if state:
        db.log_interaction("bookmark", url)  # 兴趣画像原料
    return {"ok": True, "bookmarked": state}


@app.get("/daily")
def daily(request: Request):
    """日报：今天（本地时区自然天）按 hot_score 取 top 20，按主题分组。"""
    now_local = datetime.now(LOCAL_TZ)
    day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = day_start_local.astimezone(ZoneInfo("UTC")).isoformat()
    end_utc = (day_start_local + timedelta(days=1)).astimezone(ZoneInfo("UTC")).isoformat()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM news_items WHERE COALESCE(published_at, fetched_at) >= ?"
            " AND COALESCE(published_at, fetched_at) < ?",
            (start_utc, end_utc),
        ).fetchall()
    items = _mark_bookmarks([db._row_to_dict(r) for r in rows])
    items.sort(key=lambda x: x["hot_score"], reverse=True)
    items = items[:20]
    grouped = classifier.group_by_category(items)
    return templates.TemplateResponse(
        request,
        "daily.html",
        {
            "items": items,
            "grouped": grouped,
            "date_str": day_start_local.strftime("%Y-%m-%d"),
        },
    )


@app.get("/topics")
def topics(request: Request):
    """主题分类：近 3 天条目按关键词规则分组。"""
    cutoff = (datetime.now(ZoneInfo("UTC")) - timedelta(days=3)).isoformat()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM news_items WHERE COALESCE(published_at, fetched_at) >= ?",
            (cutoff,),
        ).fetchall()
    items = _mark_bookmarks([db._row_to_dict(r) for r in rows])
    items.sort(key=lambda x: x["hot_score"], reverse=True)
    grouped = classifier.group_by_category(items)
    return templates.TemplateResponse(request, "topics.html", {"grouped": grouped})


@app.get("/api/summary")
def api_summary(request: Request, url: str, regenerate: int = 0):
    """摘要：先查缓存；没有则走"抓正文→调模型→缓存"全链路。regenerate=1 强制重新生成。

    安全：仅支持站内条目（资讯库或收藏中的 URL）——防止把服务端当代理
    抓任意 URL（SSRF，含内网）；regenerate 的缓存删除也只对站内条目生效。
    """
    url = url.strip()
    if not db.is_known_url(url):
        return JSONResponse(
            {"ok": False, "message": "仅支持对站内条目生成摘要（该链接不在资讯库或收藏中）"},
            status_code=400,
        )
    if regenerate:
        db.delete_summary(url)
    # 找标题与 RSS 摘要（正文抓取失败时兜底，v0.3.6）
    with db._connect() as conn:
        row = conn.execute("SELECT title, summary FROM news_items WHERE url = ?", (url,)).fetchone()
    title = row["title"] if row else ""
    rss_summary = (row["summary"] if row else None) or ""
    result = summarizer.summarize(url, title=title, rss_summary=rss_summary, regenerate=bool(regenerate))
    if not result:
        return JSONResponse(
            {"ok": False, "message": "摘要暂不可用（正文抓取失败或未配置模型）"},
            status_code=502,
        )
    db.log_interaction("summary", url, title)  # 兴趣画像原料（v0.3.9 底座）
    return {"ok": True, "summary": result}


@app.get("/api/sources/health")
def api_sources_health():
    """各源最近一轮抓取健康状态（供 utility bar 指示与面板）。"""
    import json as _json

    raw = db.get_meta("source_health")
    sources = _json.loads(raw) if raw else {}
    return {"ok": True, "sources": sources}


# ---------------- v0.3.8：自定义 RSS 源 / 屏蔽 ----------------

@app.get("/api/custom-sources")
def api_custom_sources():
    return {"ok": True, "sources": db.list_custom_sources()}


@app.post("/api/custom-sources")
def api_add_custom_source(payload: dict):
    try:
        db.add_custom_source((payload.get("name") or "").strip(), (payload.get("url") or "").strip())
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    return {"ok": True}


@app.delete("/api/custom-sources/{sid}")
def api_del_custom_source(sid: int):
    db.delete_custom_source(sid)
    return {"ok": True}


@app.get("/api/blocks")
def api_blocks():
    return {"ok": True, "blocks": db.list_blocks()}


@app.post("/api/blocks")
def api_add_block(payload: dict):
    try:
        kind = (payload.get("kind") or "").strip()
        value = (payload.get("value") or "").strip()
        db.add_block(kind, value)
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    db.log_interaction("block", value)
    return {"ok": True}


@app.delete("/api/blocks")
def api_delete_block(payload: dict):
    db.delete_block((payload.get("kind") or "").strip(), (payload.get("value") or "").strip())
    return {"ok": True}


# ---------------- v0.3.9：兴趣画像（自我进化） ----------------

@app.get("/api/profile")
def api_get_profile():
    return {"ok": True, "profile": profile_mod.load_profile()}


@app.post("/api/profile")
def api_save_profile(payload: dict):
    try:
        saved = profile_mod.save_profile(payload)
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    return {"ok": True, "profile": saved}


@app.delete("/api/profile")
def api_clear_profile():
    profile_mod.clear_profile()
    return {"ok": True}


@app.post("/api/profile/distill")
def api_distill_profile():
    result = profile_mod.distill()
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return result


# ---------------- v0.4.2：推送通知 ----------------

@app.get("/api/push")
def api_get_push():
    from . import push as push_mod

    cfg = push_mod.get_config()
    # 凭据打码返回（与 provider key 同级别保密）
    masked = dict(cfg)
    for k in ("telegram_token", "wecom_key"):
        if masked.get(k):
            masked[k] = masked[k][:4] + "****"
    return {"ok": True, "config": masked}


@app.post("/api/push")
def api_save_push(payload: dict):
    from . import push as push_mod

    old = push_mod.get_config()
    data = dict(payload)
    # 打码值不覆盖已存凭据
    for k in ("telegram_token", "wecom_key"):
        if data.get(k) and "****" in str(data[k]):
            data[k] = old.get(k, "")
    try:
        saved = push_mod.save_config(data)
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    return {"ok": True, "config": {k: v for k, v in saved.items() if k not in ("telegram_token", "wecom_key")}}


@app.post("/api/push/test")
def api_test_push():
    from . import push as push_mod

    cfg = push_mod.get_config()
    if cfg.get("channel") == "off":
        return JSONResponse({"ok": False, "message": "先选择渠道并保存"}, status_code=400)
    return push_mod.send(push_mod.build_digest(cfg), cfg)


# ---------------- 设置页：provider 管理 ----------------

@app.get("/search")
def search_page(request: Request, q: str = ""):
    """全文搜索（标题/来源/RSS 摘要）。"""
    items = db.search_items(q) if (q or "").strip() else []
    items = _mark_bookmarks(items)
    return templates.TemplateResponse(request, "search.html", {"items": items, "q": q})


@app.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "providers": providers.list_providers(),
            "builtin": providers.BUILTIN_PROVIDERS,
        },
    )


@app.post("/api/providers")
def api_save_provider(payload: dict):
    """新增/更新 provider。body: {id, base_url, api_key, model?, builtin?, name?}。

    安全：修改已保存 provider 的 base_url 时，必须重新输入 key（api_key 不能为空且与旧值不同则视为已重输；
    这里强制要求每次保存都必须带 key——前端在 base_url 变更时清空 key 输入框）。
    """
    pid = (payload.get("id") or "").strip()
    base_url = (payload.get("base_url") or "").strip()
    api_key = (payload.get("api_key") or "").strip()
    if not pid or not base_url:
        return JSONResponse({"ok": False, "message": "id 和 base_url 不能为空"}, status_code=400)
    # api_key 允许留空：沿用已保存的 key（save_provider 内部校验：
    # 新增必须给 key；修改 base_url 必须重输 key）
    try:
        providers.save_provider(
            pid,
            base_url,
            api_key,
            model=(payload.get("model") or "").strip() or None,
            builtin=bool(payload.get("builtin", True)),
            name=(payload.get("name") or "").strip() or None,
        )
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    return {"ok": True}


@app.delete("/api/providers/{provider_id}")
def api_delete_provider(provider_id: str):
    providers.delete_provider(provider_id)
    return {"ok": True}


@app.post("/api/providers/{provider_id}/default")
def api_set_default(provider_id: str):
    try:
        providers.set_default(provider_id)
    except KeyError:
        return JSONResponse({"ok": False, "message": "provider 不存在"}, status_code=404)
    return {"ok": True}


@app.post("/api/providers/test")
def api_test_provider(payload: dict):
    """测试连接（不保存）。body: {id, base_url, api_key, model?}。"""
    result = providers.test_connection(
        (payload.get("base_url") or "").strip(),
        (payload.get("api_key") or "").strip(),
        (payload.get("model") or "").strip() or None,
        provider_id=(payload.get("id") or "custom").strip(),
    )
    return result


@app.post("/api/providers/models")
def api_list_models(payload: dict):
    """一键获取模型列表（后端代理，避免浏览器跨域）。body: {id, base_url, api_key?}。"""
    return providers.list_models(
        (payload.get("base_url") or "").strip(),
        (payload.get("api_key") or "").strip(),
        provider_id=(payload.get("id") or "custom").strip(),
    )


@app.post("/api/refetch")
def api_refetch():
    """手动触发一轮抓取（同步执行，约 10-30s），完成后前端刷新页面。"""
    summary = run_once()
    total = summary.get("_total", {})
    return {"ok": True, "added": total.get("added", 0), "skipped": total.get("skipped", 0)}


@app.get("/api/stats", include_in_schema=False)
def api_stats():
    return db.stats()


@app.get("/api/health")
def api_health():
    """健康检查：部署验证用。返回 ok/版本/库内条数/上次抓取时间。"""
    from . import __version__

    total = db.stats()["total"]
    return {
        "ok": True,
        "version": __version__,
        "news_count": total,
        "last_fetch": db.get_meta("last_fetch_run"),
    }
