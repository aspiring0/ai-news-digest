"""SQLite 存取：URL 去重、14 天清理、热榜/时间线查询、全文搜索、收藏快照、自定义源、屏蔽。"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .classifier import classify
from .scorer import hot_score

logger = logging.getLogger("ai-news-oss")  # 与其他模块同名 logger，统一日志出口

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "news.db"))
RETENTION_DAYS = 14

# 数据版本：入库/清理时 +1，用于热榜缓存失效
_data_version = 0
_hot_cache: dict = {"key": None, "ranked": None}


@contextmanager
def _connect():
    """连接工厂：busy_timeout + 事务（成功 commit / 异常 rollback）+ 用后必关。

    原实现返回裸连接、`with sqlite3.Connection` 只 commit 不 close（回收
    依赖 GC，审计 P2-2）；且无 busy_timeout，调度线程与请求线程并发写会
    直接 database is locked。改造后全部 `with _connect() as conn:` 调用点
    语义不变，额外获得 5s 忙等与确定性关闭。
    """
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        with conn:  # 成功 commit，异常 rollback
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """建表（不存在则建）。"""
    with _connect() as conn:
        # WAL：库级持久属性，一次设置即可（读写不互斥，写入方并发更稳）
        conn.execute("PRAGMA journal_mode=WAL")
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
        # v0.3.6：RSS 摘要兜底（存量库补列）
        cols = {r[1] for r in conn.execute("PRAGMA table_info(news_items)")}
        if "summary" not in cols:
            conn.execute("ALTER TABLE news_items ADD COLUMN summary TEXT")
        # v0.5：中文标题/描述（LLM 批量翻译，存量库补列）
        if "title_cn" not in cols:
            conn.execute("ALTER TABLE news_items ADD COLUMN title_cn TEXT")
        if "description_cn" not in cols:
            conn.execute("ALTER TABLE news_items ADD COLUMN description_cn TEXT")
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
                bookmarked_at TEXT NOT NULL,  -- ISO8601 UTC
                snapshot TEXT                 -- v0.3.8：收藏时的正文快照（原文失效后仍可读）
            )
            """
        )
        # v0.3.8：存量库给 bookmarks 补 snapshot 列
        bcols = {r[1] for r in conn.execute("PRAGMA table_info(bookmarks)")}
        if "snapshot" not in bcols:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN snapshot TEXT")
        # v0.3.8：自定义 RSS 源（设置页 UI 添加，零代码扩源）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                added_at TEXT NOT NULL
            )
            """
        )
        # v0.3.8：屏蔽（不感兴趣）：kind ∈ url / source / category
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blocks (
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (kind, value)
            )
            """
        )
        # v0.3.9 底座：行为日志（兴趣画像蒸馏的原料）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                action TEXT NOT NULL,        -- summary / bookmark / block
                url TEXT,
                title TEXT,
                source_name TEXT
            )
            """
        )
        # v0.4.1：全文搜索（FTS5，标题/来源/RSS 摘要），触发器保持同步 + 存量回填
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS news_items_fts USING fts5"
            "(title, source_name, summary, url UNINDEXED)"
        )
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS news_items_fts_ai AFTER INSERT ON news_items BEGIN
              INSERT INTO news_items_fts(rowid, title, source_name, summary, url)
              VALUES (new.rowid, new.title, new.source_name, new.summary, new.url);
            END;
            CREATE TRIGGER IF NOT EXISTS news_items_fts_ad AFTER DELETE ON news_items BEGIN
              DELETE FROM news_items_fts WHERE rowid = old.rowid;
            END;
            CREATE TRIGGER IF NOT EXISTS news_items_fts_au AFTER UPDATE OF summary ON news_items BEGIN
              UPDATE news_items_fts SET title = new.title, source_name = new.source_name, summary = new.summary
              WHERE rowid = new.rowid;
            END;
            """
        )
        if not conn.execute("SELECT 1 FROM news_items_fts LIMIT 1").fetchone():
            conn.execute(
                "INSERT INTO news_items_fts(rowid, title, source_name, summary, url)"
                " SELECT rowid, title, source_name, summary, url FROM news_items"
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
    """批量入库；按 URL 去重（已存在则跳过，但会回填缺失的 RSS 摘要）。返回 (新增数, 跳过数)。"""
    global _data_version
    _data_version += 1
    added, skipped = 0, 0
    with _connect() as conn:
        for r in rows:
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO news_items (url, title, source_name, published_at, fetched_at, score, summary)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        r["url"],
                        r["title"],
                        r["source_name"],
                        _iso(r.get("published_at")),
                        _iso(r.get("fetched_at")),
                        r["score"],
                        r.get("summary"),
                    ),
                )
                if cur.rowcount:
                    added += 1
                else:
                    skipped += 1
                    # 回填：旧数据没存 RSS 摘要，重抓到同 URL 时补上（摘要兜底用）
                    if r.get("summary"):
                        conn.execute(
                            "UPDATE news_items SET summary = ? WHERE url = ? AND (summary IS NULL OR summary = '')",
                            (r["summary"], r["url"]),
                        )
            except Exception as e:  # noqa: BLE001 - 单行坏数据不中断整批入库
                skipped += 1
                # 静默跳过曾让排错困难：至少留下 url 与异常原因可追查
                logger.warning("入库失败跳过 url=%s: %s", r.get("url"), e)
    return added, skipped


def cleanup() -> int:
    """删除 14 天前入库的数据。返回删除行数。"""
    global _data_version
    _data_version += 1
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM news_items WHERE fetched_at < ?", (cutoff,))
        return cur.rowcount


def _row_to_dict(row: sqlite3.Row) -> dict:
    published = _parse(row["published_at"])
    fetched = _parse(row["fetched_at"]) or datetime.now(timezone.utc)
    score = float(row["score"])
    keys = row.keys()
    title_cn = row["title_cn"] if "title_cn" in keys else None
    out = {
        "url": row["url"],
        "title": row["title"],
        "title_cn": title_cn,
        "description_cn": row["description_cn"] if "description_cn" in keys else None,
        "source_name": row["source_name"],
        "published_at": published,
        "fetched_at": fetched,
        "score": score,
        "summary": row["summary"] if "summary" in keys else None,
        "hot_score": round(hot_score(score, published, fetched), 2),
    }
    # B1：待中文整理（英文未翻译）→ 响应层实时计算（落点①），翻译完成自动消失
    if not title_cn and _needs_cn_translation(row["title"]):
        out["processing_status"] = "pending"
    return out


def get_hot(page: int = 1, per_page: int = 20, max_per_source: int = 4) -> tuple[list[dict], int]:
    """热榜：全部条目按衰减热度倒序，每源最多 max_per_source 条（多样性配额），分页返回。

    配额只影响榜单展示：高分源（HuggingFace/GitHub 等）最多占 max_per_source 席，
    让新闻源（AIHOT/量子位等）也能进榜；原始分不动，时间线/日报/分类不受影响。
    返回 (本页条目, 配额后总条数)。
    """
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM news_items").fetchall()
    items = [_row_to_dict(r) for r in rows]
    items.sort(key=lambda x: x["hot_score"], reverse=True)
    ranked: list[dict] = []
    per_source: dict[str, int] = {}
    for it in items:
        src = it["source_name"]
        if per_source.get(src, 0) >= max_per_source:
            continue
        per_source[src] = per_source.get(src, 0) + 1
        ranked.append(it)
    total = len(ranked)
    start = (max(1, page) - 1) * per_page
    return ranked[start:start + per_page], total


def get_hot_stories(page: int = 1, per_page: int = 20, max_per_source: int = 4, profile: dict | None = None) -> tuple[list[dict], int]:
    """故事级热榜（带进程内缓存：入库/清理/屏蔽/画像变化自动失效）。"""
    pkey = json.dumps(profile, sort_keys=True, ensure_ascii=False) if profile else ""
    bsig = ";".join(sorted(f"{b['kind']}:{b['value']}" for b in list_blocks()))
    key = (pkey, bsig, _data_version, max_per_source)
    if _hot_cache["key"] != key:
        _hot_cache["ranked"] = _compute_ranked_stories(profile, max_per_source)
        _hot_cache["key"] = key
    ranked = _hot_cache["ranked"]
    total = len(ranked)
    start = (max(1, page) - 1) * per_page
    return ranked[start:start + per_page], total


def _compute_ranked_stories(profile: dict | None, max_per_source: int = 4) -> list[dict]:
    """全量计算配额后的故事排行（聚类/画像/过滤/配额），供缓存层调用。"""
    from .profile import apply_profile_to_stories
    from .stories import group_stories, story_score

    with _connect() as conn:
        rows = conn.execute("SELECT * FROM news_items").fetchall()
    items = _filter_blocked([_row_to_dict(r) for r in rows])
    stories = group_stories(items)
    for st in stories:
        st["_score"] = story_score(st)
    stories = apply_profile_to_stories(stories, profile)
    stories.sort(key=lambda s: s["_score"], reverse=True)
    # 故事级分类屏蔽：代表条目的话题被屏蔽则整故事不出现
    _, _, cats = _blocked_sets()
    if cats:
        stories = [s for s in stories if classify(s["representative"]["title"]) not in cats]
    ranked: list[dict] = []
    per_source: dict[str, int] = {}
    for st in stories:
        rep = dict(st["representative"])
        src = rep["source_name"]
        if per_source.get(src, 0) >= max_per_source:
            continue
        per_source[src] = per_source.get(src, 0) + 1
        rep["hot_score"] = round(st["_score"], 2)
        rep["_story"] = {
            "count": len(st["members"]),
            "sources": st["sources"],
            "members": [
                {"title": m["title"], "url": m["url"], "source_name": m["source_name"]}
                for m in st["members"]
            ],
        }
        ranked.append(rep)
    return ranked


_CJK_QUERY_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def _needs_cn_translation(title: str | None) -> bool:
    """标题是否待中文整理（英文未翻译）。与 translator._needs_translation 同义——
    db 不反向依赖 translator（循环导入），逻辑内联于此。"""
    if not title or _CJK_QUERY_RE.search(title):
        return False
    return bool(_LATIN_WORD_RE.search(title))


def pending_translation_counts() -> dict[str, int]:
    """各源"待中文整理"条数——/api/sources/health 的 processing 状态依据。

    arXiv 论文按接入决策保持英文（不占翻译配额），不构成"整理中"。
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT source_name, title FROM news_items"
            " WHERE (title_cn IS NULL OR title_cn = '') AND source_name NOT LIKE 'arXiv%'"
        ).fetchall()
    counts: dict[str, int] = {}
    for r in rows:
        if _needs_cn_translation(r["title"]):
            counts[r["source_name"]] = counts.get(r["source_name"], 0) + 1
    return counts


def _search_cjk(q: str, limit: int) -> list[dict]:
    """中文（含 CJK 的混合）查询：LIKE 子串路径。

    为什么不走 FTS：FTS5 默认 unicode61 分词器把整段连续中文当作一个
    token，子串查询（"翻译"匹配"…翻译功能…"）基本搜不到——不止 title_cn
    缺索引，中文查询在 FTS 路径上本就失效。LIKE 覆盖 title/title_cn/
    summary 三列（ASCII 大小写不敏感），当前量级（万级行）性能足够。
    """
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{esc}%"
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM news_items"
            " WHERE title LIKE ? ESCAPE '\\' OR title_cn LIKE ? ESCAPE '\\'"
            " OR summary LIKE ? ESCAPE '\\' LIMIT ?",
            (like, like, like, limit),
        ).fetchall()
    items = [_row_to_dict(r) for r in rows]
    items.sort(key=lambda x: x["hot_score"], reverse=True)
    return items


def search_items(q: str, limit: int = 50) -> list[dict]:
    """搜索：含 CJK 走 LIKE 子串（中文分词限制，见 _search_cjk）；纯英文走
    FTS5 短语+前缀匹配（输入做转义，FTS 语法字符不炸）。均按热度排序。"""
    q = (q or "").strip()
    if not q:
        return []
    if _CJK_QUERY_RE.search(q):
        return _search_cjk(q, limit)
    safe = '"' + q.replace('"', '""') + '"*'
    try:
        with _connect() as conn:
            rids = [r[0] for r in conn.execute(
                "SELECT n.rowid FROM news_items n JOIN news_items_fts f ON n.rowid = f.rowid"
                " WHERE news_items_fts MATCH ? LIMIT ?",
                (safe, limit),
            ).fetchall()]
    except sqlite3.OperationalError:
        return []
    if not rids:
        return []
    marks = ",".join("?" * len(rids))
    with _connect() as conn:
        rows = conn.execute(f"SELECT * FROM news_items WHERE rowid IN ({marks})", rids).fetchall()
    items = [_row_to_dict(r) for r in rows]
    items.sort(key=lambda x: x["hot_score"], reverse=True)
    return items


def get_timeline(page: int = 1, per_page: int = 20) -> tuple[list[dict], int]:
    """时间线：按发布时间倒序分页（无发布时间的按入库时间），应用屏蔽过滤。返回 (条目, 总数)。"""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM news_items").fetchall()
    items = _filter_blocked([_row_to_dict(r) for r in rows])
    items.sort(key=lambda x: x["published_at"] or x["fetched_at"], reverse=True)
    total = len(items)
    start = (page - 1) * per_page
    return items[start:start + per_page], total


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

def is_known_url(url: str) -> bool:
    """URL 是否属于站内已知条目（资讯库或收藏）。

    /api/summary 的允许列表：只对站内条目生成摘要，封掉任意 URL 的
    服务端抓取（SSRF）。注意不含 summary_cache——升级前可能已缓存的
    内网读取内容不能经旧缓存重新外泄。
    """
    with _connect() as conn:
        in_news = conn.execute("SELECT 1 FROM news_items WHERE url = ?", (url,)).fetchone()
        in_marks = conn.execute("SELECT 1 FROM bookmarks WHERE url = ?", (url,)).fetchone()
    return bool(in_news or in_marks)


def toggle_bookmark(url: str) -> bool:
    """收藏/取消收藏。收藏时抓正文快照（原文失效后仍可读）。返回 True=已收藏。"""
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM bookmarks WHERE url = ?", (url,)).fetchone()
        if exists:
            conn.execute("DELETE FROM bookmarks WHERE url = ?", (url,))
            return False
        item = conn.execute(
            "SELECT title, source_name, summary FROM news_items WHERE url = ?", (url,)
        ).fetchone()
        if not item:
            raise KeyError("新闻不存在")
        snapshot = None
        try:
            from . import summarizer
            snapshot = summarizer.fetch_article_text(url, rss_summary=(item["summary"] or ""))
        except Exception:
            snapshot = None
        if not snapshot:
            snapshot = (item["summary"] or "") or None
        conn.execute(
            "INSERT INTO bookmarks (url, title, source_name, bookmarked_at, snapshot) VALUES (?, ?, ?, ?, ?)",
            (url, item["title"], item["source_name"], _iso(datetime.now(timezone.utc)), snapshot),
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
            "snapshot": r["snapshot"] if "snapshot" in r.keys() else None,
        }
        for r in rows
    ]


# ---------------- v0.3.8：自定义 RSS 源 / 屏蔽 / 行为日志 ----------------

def list_custom_sources() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM custom_sources ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def add_custom_source(name: str, url: str) -> None:
    from urllib.parse import urlparse

    from .urlguard import check_url

    name = (name or "").strip()
    url = (url or "").strip()
    if not name:
        raise ValueError("名称不能为空")
    if not url.startswith(("http://", "https://")) or not urlparse(url).hostname:
        raise ValueError("RSS 地址必须是合法的 http(s) URL")
    # SSRF 防护：源地址不得解析到内网/保留网段（服务端会周期性抓取它）。
    # 域名解析失败同样拒绝——反正永远抓不到，提前报错优于入列表后每轮失败。
    ok, reason = check_url(url)
    if not ok:
        raise ValueError(f"RSS 地址不允许（{reason}）；确需内网源请设置 ALLOW_PRIVATE_FETCH=1")
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO custom_sources (name, url, added_at) VALUES (?, ?, ?)",
                (name[:50], url, _iso(datetime.now(timezone.utc))),
            )
    except sqlite3.IntegrityError as e:
        raise ValueError("该 RSS 地址已添加过") from e


def delete_custom_source(sid: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM custom_sources WHERE id = ?", (sid,))


_BLOCK_KINDS = ("url", "source", "category")


def add_block(kind: str, value: str) -> None:
    if kind not in _BLOCK_KINDS:
        raise ValueError("kind 必须是 url / source / category")
    value = (value or "").strip()
    if not value:
        raise ValueError("value 不能为空")
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO blocks (kind, value, created_at) VALUES (?, ?, ?)",
            (kind, value, _iso(datetime.now(timezone.utc))),
        )


def delete_block(kind: str, value: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM blocks WHERE kind = ? AND value = ?", (kind, value))


def list_blocks() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT kind, value FROM blocks ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def _blocked_sets() -> tuple[set[str], set[str], set[str]]:
    """返回 (屏蔽URL集, 屏蔽来源集, 屏蔽分类集)。"""
    urls, srcs, cats = set(), set(), set()
    for b in list_blocks():
        {"url": urls, "source": srcs, "category": cats}.get(b["kind"], set()).add(b["value"])
    return urls, srcs, cats


def _filter_blocked(items: list[dict]) -> list[dict]:
    """条目级过滤：屏蔽的 URL / 来源 / 分类（分类按标题关键词规则）。"""
    urls, srcs, cats = _blocked_sets()
    if not (urls or srcs or cats):
        return items
    return [
        it for it in items
        if it["url"] not in urls
        and it["source_name"] not in srcs
        and classify(it["title"]) not in cats
    ]


def log_interaction(action: str, url: str = "", title: str = "", source_name: str = "") -> None:
    """记录行为（summary/bookmark/block），兴趣画像蒸馏的原料。"""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO interactions (ts, action, url, title, source_name) VALUES (?, ?, ?, ?, ?)",
            (_iso(datetime.now(timezone.utc)), action, url, title[:200], source_name[:60]),
        )


def recent_interactions(limit: int = 500) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM interactions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

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


def clear_stale_summaries(days: int = 30) -> int:
    """删除 N 天前的摘要缓存（孤儿缓存随时间清理；30 天而非 14 天——书签页的过期条目仍可能命中旧缓存）。"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM summary_cache WHERE created_at < ?", (cutoff,))
        return cur.rowcount
