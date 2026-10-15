"""抓取层 SSRF 防护：_safe_get 逐跳重定向校验 + 书签快照链路（零网络，mock requests/DNS）。"""
from __future__ import annotations

import socket

import pytest

from app import db, summarizer


class _FakeResp:
    def __init__(self, status=200, headers=None, text=""):
        self.status_code = status
        self.headers = headers or {}
        self.text = text
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise summarizer.requests.HTTPError(f"status={self.status_code}")

    def close(self):
        self.closed = True


def _mock_get(monkeypatch, chain):
    """chain: {url_prefix_or_exact: _FakeResp 或 callable(url)->resp}；记录每次调用。"""
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        for key, resp in chain.items():
            if url == key or url.startswith(key):
                return resp(url) if callable(resp) else resp
        return _FakeResp(status=404)

    monkeypatch.setattr(summarizer.requests, "get", fake_get)
    return calls


def _mock_extractors(monkeypatch, text=None):
    """提取器直通，聚焦重定向逻辑本身。"""
    monkeypatch.setattr(summarizer, "_extract_with_trafilatura",
                        lambda html, url: (text if text is not None else html))
    monkeypatch.setattr(summarizer, "_extract_with_readability", lambda html, url: None)


def _dns(monkeypatch, ips):
    def fake(host, port=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]
    monkeypatch.setattr(socket, "getaddrinfo", fake)


# ---------- B1 公网→302→公网：跟随并取最终正文 ----------

def test_follows_public_redirect_chain(monkeypatch):
    _dns(monkeypatch, ["93.184.216.34"])
    _mock_get(monkeypatch, {
        "https://pub1.com/a": _FakeResp(status=302, headers={"Location": "https://pub2.com/b"}),
        "https://pub2.com/b": _FakeResp(text="<p>最终正文</p>"),
    })
    _mock_extractors(monkeypatch)
    out = summarizer.fetch_article_text("https://pub1.com/a")
    assert out == "<p>最终正文</p>"


# ---------- B2 公网→302→内网：被拒且未对内网发起请求 ----------

def test_redirect_to_private_blocked_before_request(monkeypatch):
    _dns(monkeypatch, ["93.184.216.34"])  # pub 域名公网；127.0.0.1 是字面量不走 DNS
    calls = _mock_get(monkeypatch, {
        "https://pub1.com/a": _FakeResp(status=302, headers={"Location": "http://127.0.0.1:8000/api/health"}),
    })
    _mock_extractors(monkeypatch)
    out = summarizer.fetch_article_text("https://pub1.com/a", rss_summary="RSS 兜底")
    assert out == "RSS 兜底"  # 走 RSS 摘要兜底
    assert calls == ["https://pub1.com/a"]  # 内网 URL 从未发起 requests.get
    assert summarizer.fetch_article_text("http://127.0.0.1:8000/x") is None


def test_direct_private_url_never_fetched(monkeypatch):
    calls = _mock_get(monkeypatch, {})
    out = summarizer.fetch_article_text("http://169.254.169.254/latest/meta-data/", rss_summary="")
    assert out is None
    assert calls == []


# ---------- B3 重定向过深 ----------

def test_too_many_redirects_gives_up(monkeypatch):
    _dns(monkeypatch, ["93.184.216.34"])

    def hop(url, **kw):
        return _FakeResp(status=302, headers={"Location": "https://pub1.com/next"})

    calls = _mock_get(monkeypatch, {"https://pub1.com/": hop})
    _mock_extractors(monkeypatch)
    out = summarizer.fetch_article_text("https://pub1.com/a", rss_summary="兜底")
    assert out == "兜底"
    assert len(calls) == summarizer.MAX_REDIRECTS + 1  # 首跳 + 3 次跟随


# ---------- B4 相对 Location 解析 ----------

def test_relative_location_resolved(monkeypatch):
    _dns(monkeypatch, ["93.184.216.34"])
    _mock_get(monkeypatch, {
        "https://pub1.com/a": _FakeResp(status=301, headers={"Location": "/b/c"}),
        "https://pub1.com/b/c": _FakeResp(text="正文B"),
    })
    _mock_extractors(monkeypatch)
    assert summarizer.fetch_article_text("https://pub1.com/a") == "正文B"


# ---------- B5 被拒时 RSS 摘要兜底（同 B2 语义，独立断言日志线） ----------

def test_blocked_url_falls_back_to_rss(caplog, monkeypatch):
    _mock_get(monkeypatch, {})
    _mock_extractors(monkeypatch)
    with caplog.at_level("WARNING"):
        out = summarizer.fetch_article_text("http://10.0.0.5/x", rss_summary="RSS 文本")
    assert out == "RSS 文本"
    assert any("urlguard" in r.message for r in caplog.records)


# ---------- B6 书签快照链路：库内私网 URL 收藏时不触网 ----------

def test_bookmark_private_url_snapshot_falls_back(clean_db, monkeypatch):
    from datetime import datetime, timezone

    _dns(monkeypatch, ["10.0.0.5"])  # 域名解析到私网
    calls = _mock_get(monkeypatch, {})
    now = datetime.now(timezone.utc)
    db.insert_items([{
        "url": "http://intranet-host/x", "title": "内网文章", "source_name": "内网源",
        "fetched_at": now, "published_at": now, "score": 60.0, "summary": "RSS 快照兜底文本",
    }])
    state = db.toggle_bookmark("http://intranet-host/x")
    assert state is True
    bm = db.get_bookmarks()[0]
    assert bm["snapshot"] == "RSS 快照兜底文本"
    assert calls == []  # 未对私网发起任何请求
