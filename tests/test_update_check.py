"""半自动更新检查：版本比对 / 资产挑选 / 缓存 / 失败静默 / 端点。"""
from __future__ import annotations

import pytest

from app import updatecheck


def _mock_gh(monkeypatch, payload, status=200):
    class _Resp:
        status_code = status

        def raise_for_status(self):
            if status >= 400:
                raise updatecheck.requests.HTTPError(f"{status}")

        def json(self):
            return payload

    monkeypatch.setattr(updatecheck.requests, "get", lambda url, **kw: _Resp())
    updatecheck._cache["result"] = None  # 绕过缓存


def test_version_tuple_compare():
    assert updatecheck._version_tuple("v0.4.10") > updatecheck._version_tuple("0.4.9")
    assert updatecheck._version_tuple("0.5") > updatecheck._version_tuple("0.4.99")
    assert updatecheck._version_tuple("0.4.5") == updatecheck._version_tuple("v0.4.5")
    assert updatecheck._version_tuple("1.0.0a") < updatecheck._version_tuple("1.0.1")  # 非数字段按 0


def test_newer_release_flags_update(monkeypatch):
    from app import __version__
    newer = ".".join(str(int(x) + 1) for x in __version__.split("."))
    _mock_gh(monkeypatch, {
        "tag_name": f"v{newer}", "html_url": "https://github.com/r/releases/vX",
        "assets": [{"name": "ai-news-win.exe", "browser_download_url": "https://dl/win.exe"},
                   {"name": "Source.zip", "browser_download_url": "https://dl/z"}],
    })
    d = updatecheck.check(force=True)
    assert d["ok"] and d["has_update"] is True
    assert d["current"] == __version__ and d["latest"] == newer
    assert d["download_url"] == "https://dl/win.exe", "应优先 Windows exe 资产"


def test_same_version_no_update(monkeypatch):
    from app import __version__
    _mock_gh(monkeypatch, {"tag_name": f"v{__version__}", "html_url": "u", "assets": []})
    d = updatecheck.check(force=True)
    assert d["ok"] and d["has_update"] is False
    assert d["download_url"] == "u", "无资产时回 Release 页"


def test_no_release_404_silent(monkeypatch):
    _mock_gh(monkeypatch, {"message": "Not Found"}, status=404)
    d = updatecheck.check(force=True)
    assert d["ok"] is False


def test_network_error_silent(monkeypatch):
    def boom(url, **kw):
        raise ConnectionError("offline")
    monkeypatch.setattr(updatecheck.requests, "get", boom)
    d = updatecheck.check(force=True)
    assert d["ok"] is False and "不可用" in d.get("message", "")


def test_cache_within_ttl(monkeypatch):
    calls = {"n": 0}

    def counter(url, **kw):
        calls["n"] += 1

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"tag_name": "v0.0.1", "html_url": "u", "assets": []}

        return _Resp()

    monkeypatch.setattr(updatecheck.requests, "get", counter)
    updatecheck._cache["result"] = None
    updatecheck.check(force=True)
    updatecheck.check()  # 命中缓存
    updatecheck.check()  # 命中缓存
    assert calls["n"] == 1


def test_endpoint(client, monkeypatch):
    import app.main as main_mod
    monkeypatch.setattr(main_mod.updatecheck, "check",
                        lambda: {"ok": True, "has_update": False, "current": "x", "latest": "x"})
    r = client.get("/api/update-check")
    assert r.status_code == 200 and r.json()["ok"] is True
