"""SQLite 存取：按 URL 去重、14 天清理、热榜/时间线查询。"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

from .scorer import hot_score

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "news.db"))
RETENTION_DAYS = 14


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """建表（不存在则建）。"""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_name TEXT NOT NULL,
                published_at TEXT,          -- ISO8601 UTC，可空
                fetched_at TEXT NOT NULL,   -- ISO8601 UTC
                score REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_published ON news_items(published_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fetched ON news_items(fetched_at)")
        # v0.3：键值 meta 表（健康检查记录上次抓取时间等）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        # v0.2 新增表：摘要缓存 / 收藏 / 模型 provider 设置
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS summary_cache (
                url TEXT PRIMARY KEY,
                summary TEXT NOT NULL,        -- 四段式中文摘要（JSON 字符串）
                provider_id TEXT NOT NULL,   -- 用哪个 provider 生成的
                model TEXT,                  -- 模型名
                created_at TEXT NOT NULL     -- ISO8601 UTC
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookmarks (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_name TEXT NOT NULL,
                bookmarked_at TEXT NOT NULL  -- ISO8601 UTC
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_settings (
                id TEXT PRIMARY KEY,         -- 如 deepseek / glm / custom-1
                name TEXT NOT NULL,          -- 显示名
                builtin INTEGER NOT NULL,    -- 1=内置 provider（base_url 走官方域名白名单）
                base_url TEXT NOT NULL,
                api_key TEXT NOT NULL,       -- 本机 SQLite 明文保存，仅自用
                model TEXT,                  -- 默认模型名
                is_default INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def insert_items(rows: list[dict]) -> tuple[int, int]:
    """批量入库；按 URL 去重（已存在则跳过）。返回 (新增数, 跳过数)。"""
    added, skipped = 0, 0
    with _connect() as conn:
        for r in rows:
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO news_items (url, title, source_name, published_at, fetched_at, score)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        r["url"],
                        r["title"],
                        r["source_name"],
                        _iso(r.get("published_at")),
                        _iso(r.get("fetched_at")),
                        r["score"],
                    ),
                )
                if cur.rowcount:
                    added += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
    return added, skipped


def cleanup() -> int:
    """删除 14 天前入库的数据。返回删除行数。"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM news_items WHERE fetched_at < ?", (cutoff,))
        return cur.rowcount


def _row_to_dict(row: sqlite3.Row) -> dict:
    published = _parse(row["published_at"])
    fetched = _parse(row["fetched_at"]) or datetime.now(timezone.utc)
    score = float(row["score"])
    return {
        "url": row["url"],
        "title": row["title"],
        "source_name": row["source_name"],
        "published_at": published,
        "fetched_at": fetched,
        "score": score,
        "hot_score": round(hot_score(score, published, fetched), 2),
    }


def get_hot(limit: int = 20) -> list[dict]:
    """热榜：全部条目按衰减热度分倒序取 top N（原始分不动）。"""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM news_items").fetchall()
    items = [_row_to_dict(r) for r in rows]
    items.sort(key=lambda x: x["hot_score"], reverse=True)
    return items[:limit]


def get_timeline(page: int = 1, per_page: int = 20) -> tuple[list[dict], int]:
    """时间线：按发布时间倒序分页（无发布时间的按入库时间）。返回 (条目, 总数)。"""
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM news_items ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ? OFFSET ?",
            (per_page, (page - 1) * per_page),
        ).fetchall()
    return [_row_to_dict(r) for r in rows], total


def stats() -> dict:
    """各源条数 + 总数（供调试/首页展示）。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT source_name, COUNT(*) AS c FROM news_items GROUP BY source_name ORDER BY c DESC"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
    return {"total": total, "by_source": [{"source": r["source_name"], "count": r["c"]} for r in rows]}


# ---------------- v0.3：键值 meta ----------------

def set_meta(key: str, value: str) -> None:
    """写键值（如 last_fetch_run）。"""
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def get_meta(key: str) -> str | None:
    """读键值，不存在返回 None。"""
    with _connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


# ---------------- v0.2：收藏 ----------------

def toggle_bookmark(url: str) -> bool:
    """收藏/取消收藏。返回 True=已收藏，False=已取消。"""
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM bookmarks WHERE url = ?", (url,)).fetchone()
        if exists:
            conn.execute("DELETE FROM bookmarks WHERE url = ?", (url,))
            return False
        item = conn.execute(
            "SELECT title, source_name FROM news_items WHERE url = ?", (url,)
        ).fetchone()
        if not item:
            raise KeyError("新闻不存在")
        conn.execute(
            "INSERT INTO bookmarks (url, title, source_name, bookmarked_at) VALUES (?, ?, ?, ?)",
            (url, item["title"], item["source_name"], _iso(datetime.now(timezone.utc))),
        )
        return True


def is_bookmarked(url: str) -> bool:
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM bookmarks WHERE url = ?", (url,)).fetchone() is not None


def get_bookmarks() -> list[dict]:
    """收藏列表：按收藏时间倒序。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM bookmarks ORDER BY bookmarked_at DESC"
        ).fetchall()
    return [
        {
            "url": r["url"],
            "title": r["title"],
            "source_name": r["source_name"],
            "bookmarked_at": _parse(r["bookmarked_at"]),
            "bookmarked": True,
        }
        for r in rows
    ]


# ---------------- v0.2：摘要缓存 ----------------

def get_summary(url: str) -> dict | None:
    """按 URL 取缓存摘要。返回 dict（四段式）或 None。"""
    import json

    with _connect() as conn:
        row = conn.execute("SELECT * FROM summary_cache WHERE url = ?", (url,)).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["summary"])
    except Exception:
        return None
    data["_cached"] = True
    data["_provider_id"] = row["provider_id"]
    data["_created_at"] = row["created_at"]
    return data


def save_summary(url: str, summary: dict, provider_id: str, model: str | None) -> None:
    """写入摘要缓存（覆盖旧值）。"""
    import json

    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO summary_cache (url, summary, provider_id, model, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                url,
                json.dumps(summary, ensure_ascii=False),
                provider_id,
                model,
                _iso(datetime.now(timezone.utc)),
            ),
        )


def delete_summary(url: str) -> None:
    """清除某 URL 的摘要缓存（重新生成前调用）。"""
    with _connect() as conn:
        conn.execute("DELETE FROM summary_cache WHERE url = ?", (url,))
