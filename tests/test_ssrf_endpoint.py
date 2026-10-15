"""端点层 SSRF 防护：/api/summary 允许列表 + custom-sources 添加校验（C 系列）。"""
from __future__ import annotations

import socket

from app import db


def _dns(monkeypatch, ips):
    def fake(host, port=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]
    monkeypatch.setattr(socket, "getaddrinfo", fake)


# ---------- C1 未知 URL → 400 ----------

def test_summary_unknown_url_rejected(client):
    r = client.get("/api/summary?url=https%3A%2F%2Fattacker.example%2Fx")
    assert r.status_code == 400
    assert "站内" in r.json()["message"]


# ---------- C2 未知 URL + regenerate 不删既有缓存 ----------

def test_summary_regenerate_unknown_keeps_cache(client):
    victim = "https://not-in-lib/x"
    db.save_summary(victim, {"core": "c", "plain": "p", "details": "d", "link": victim}, "p", "m")
    r = client.get(f"/api/summary?url={victim.replace('/', '%2F').replace(':', '%3A')}&regenerate=1")
    assert r.status_code == 400
    assert db.get_summary(victim) is not None  # 缓存未被删除


# ---------- C3 站内 URL 正常路径（收藏中的 URL 也放行） ----------

def test_summary_bookmarked_url_allowed(client, monkeypatch):
    from datetime import datetime, timezone

    import app.main as main_mod

    url = "https://example.com/news/1"  # client fixture 已入库
    now = datetime.now(timezone.utc)
    db.insert_items([{
        "url": "https://gone.example/old", "title": "已过期条目", "source_name": "S",
        "fetched_at": now, "published_at": now, "score": 60.0, "summary": "旧摘要",
    }])
    # 模拟"资讯库已清理但仍在收藏中"的过期书签场景
    with db._connect() as conn:
        conn.execute("DELETE FROM news_items WHERE url = ?", ("https://gone.example/old",))
        conn.execute(
            "INSERT INTO bookmarks (url, title, source_name, bookmarked_at, snapshot)"
            " VALUES (?, ?, ?, ?, ?)",
            ("https://gone.example/old", "已过期条目", "S", now.isoformat(), None),
        )
    captured = {}

    def spy(u, title="", rss_summary="", regenerate=False):
        captured["url"] = u
        return {"core": "c", "plain": "p", "details": "d", "link": u}

    monkeypatch.setattr(main_mod.summarizer, "summarize", spy)
    r1 = client.get(f"/api/summary?url={url.replace('/', '%2F').replace(':', '%3A')}")
    assert r1.status_code == 200
    r2 = client.get("/api/summary?url=https%3A%2F%2Fgone.example%2Fold")
    assert r2.status_code == 200  # 收藏中的 URL 也属于站内条目
    assert captured["url"] == "https://gone.example/old"


# ---------- C4 添加解析到内网的自定义源 → 400 ----------

def test_add_custom_source_private_rejected(client, monkeypatch):
    _dns(monkeypatch, ["10.0.0.9"])
    r = client.post("/api/custom-sources", json={"name": "内网源", "url": "http://intranet.example/feed"})
    assert r.status_code == 400
    body = r.json()["message"]
    assert "内网" in body or "保留" in body or "受限" in body or "ALLOW_PRIVATE_FETCH" in body
    assert all(s["url"] != "http://intranet.example/feed" for s in db.list_custom_sources())


# ---------- C5 豁免开关下放行 ----------

def test_add_custom_source_private_allowed_with_env(client, monkeypatch):
    _dns(monkeypatch, ["10.0.0.9"])
    monkeypatch.setenv("ALLOW_PRIVATE_FETCH", "1")
    r = client.post("/api/custom-sources", json={"name": "内网源", "url": "http://intranet.example/feed"})
    assert r.status_code == 200
    assert any(s["url"] == "http://intranet.example/feed" for s in db.list_custom_sources())
