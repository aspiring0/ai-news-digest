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

from . import classifier, db, providers, scheduler, summarizer
from .fetch_all import run_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ai-news-oss")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "..", "templates"))

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


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse(url="/hot")


@app.get("/hot")
def hot(request: Request):
    items = _mark_bookmarks(db.get_hot(limit=20))
    st = db.stats()
    return templates.TemplateResponse(
        request, "hot.html", {"items": items, "stats": st}
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
    """摘要：先查缓存；没有则走"抓正文→调模型→缓存"全链路。regenerate=1 强制重新生成。"""
    if regenerate:
        db.delete_summary(url)
    # 找标题（弹窗展示用）
    with db._connect() as conn:
        row = conn.execute("SELECT title FROM news_items WHERE url = ?", (url,)).fetchone()
    title = row["title"] if row else ""
    result = summarizer.summarize(url, title=title, regenerate=bool(regenerate))
    if not result:
        return JSONResponse(
            {"ok": False, "message": "摘要暂不可用（正文抓取失败或未配置模型）"},
            status_code=502,
        )
    return {"ok": True, "summary": result}


# ---------------- 设置页：provider 管理 ----------------

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
    if not api_key:
        # 修改 base_url 必须重输 key：后端强制每次保存都带 key
        return JSONResponse({"ok": False, "message": "保存时必须输入 key（修改 base_url 必须重新输入 key）"}, status_code=400)
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
