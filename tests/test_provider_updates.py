"""Key 留空不修改 / 模型列表代理 / 手动重抓 接口测试。"""
from __future__ import annotations

import json

import pytest

from app import providers


# ---------------- Key 留空 = 不修改 ----------------

def test_save_empty_key_keeps_old_key(clean_db):
    providers.save_provider("deepseek", "https://api.deepseek.com", "sk-real-key", model="deepseek-chat")
    # 留空保存：沿用旧 key，其余字段可更新
    providers.save_provider("deepseek", "https://api.deepseek.com", "", model="deepseek-reasoner")
    saved = providers.get_provider("deepseek")
    assert saved["api_key"] == "sk-real-key"
    assert saved["model"] == "deepseek-reasoner"


def test_save_empty_key_rejected_for_new_provider(clean_db):
    with pytest.raises(ValueError, match="必须输入 key"):
        providers.save_provider("glm", "https://open.bigmodel.cn", "")


def test_save_empty_key_rejected_when_base_url_changed(clean_db):
    """安全规则保留：改接口地址仍必须重输 key（防 key 被发往新域名）。"""
    providers.save_provider("custom-proxy", "https://old.example.com", "sk-x", builtin=False, name="P")
    with pytest.raises(ValueError, match="重新输入"):
        providers.save_provider("custom-proxy", "https://new.example.com", "", builtin=False, name="P")
    # 带新 key 则允许换地址
    providers.save_provider("custom-proxy", "https://new.example.com", "sk-y", builtin=False, name="P")
    assert providers.get_provider("custom-proxy")["base_url"] == "https://new.example.com"


def test_api_empty_key_flow(client):
    r1 = client.post("/api/providers", json={"id": "kimi", "base_url": "https://api.moonshot.cn", "api_key": "sk-1", "model": "kimi-k2"})
    assert r1.status_code == 200
    # 留空只改模型名 → 200，key 沿用
    r2 = client.post("/api/providers", json={"id": "kimi", "base_url": "https://api.moonshot.cn", "api_key": "", "model": "kimi-latest"})
    assert r2.status_code == 200, r2.text
    from app import db as dbmod
    with dbmod._connect() as conn:
        row = conn.execute("SELECT api_key, model FROM provider_settings WHERE id='kimi'").fetchone()
    assert row["api_key"] == "sk-1" and row["model"] == "kimi-latest"


# ---------------- 模型列表代理 ----------------

def test_list_models_parses_ids(clean_db, monkeypatch):
    class FakeResp:
        status_code = 200
        def json(self):
            return {"data": [{"id": "m-a"}, {"id": "m-b"}, {"other": 1}]}

    monkeypatch.setattr(providers.requests, "get", lambda url, headers=None, timeout=None: FakeResp())
    out = providers.list_models("https://api.deepseek.com", "sk-x", provider_id="deepseek")
    assert out["ok"] is True and out["models"] == ["m-a", "m-b"]


def test_list_models_url_and_auth(clean_db, monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"data": []}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["auth"] = headers.get("Authorization")
        return FakeResp()

    monkeypatch.setattr(providers.requests, "get", fake_get)
    providers.list_models("https://api.deepseek.com", "sk-x", provider_id="deepseek")
    assert captured["url"] == "https://api.deepseek.com/models"
    assert captured["auth"] == "Bearer sk-x"


def test_list_models_uses_saved_key_when_blank(clean_db, monkeypatch):
    providers.save_provider("deepseek", "https://api.deepseek.com", "sk-saved")
    captured = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"data": [{"id": "deepseek-chat"}]}

    monkeypatch.setattr(providers.requests, "get", lambda url, headers=None, timeout=None: (captured.update(auth=headers.get("Authorization")), FakeResp())[1])
    out = providers.list_models("https://api.deepseek.com", "", provider_id="deepseek")
    assert out["ok"] is True and captured["auth"] == "Bearer sk-saved"


def test_list_models_whitelist_enforced(clean_db):
    out = providers.list_models("https://evil.example.com", "sk-x", provider_id="deepseek")
    assert out["ok"] is False and "官方域名" in out["message"]


# ---------------- P1-1：存量 key 外发防护 ----------------

class _FakeResp:
    status_code = 200

    def json(self):
        return {"data": [{"id": "m-1"}]}


def test_list_models_mismatched_base_never_sends_saved_key(clean_db, monkeypatch):
    """异址 + 空 key：拒绝回退，且不发起任何 HTTP 请求（防存量 key 外发）。"""
    providers.save_provider("custom-1", "https://a.example", "SECRET-KEY", builtin=False, name="t")
    called = []
    monkeypatch.setattr(providers.requests, "get",
                        lambda url, headers=None, timeout=None: called.append(url) or _FakeResp())
    out = providers.list_models("https://evil.example", "", provider_id="custom-1")
    assert out["ok"] is False
    assert "不一致" in out["message"]
    assert called == []  # 未把存量 key 发往任何地址


def test_list_models_same_base_falls_back_for_custom(clean_db, monkeypatch):
    """同址 + 空 key：custom provider 也安全回退（既有 UX 保留）。"""
    providers.save_provider("custom-1", "https://a.example/", "SECRET-KEY", builtin=False, name="t")
    captured = {}
    monkeypatch.setattr(providers.requests, "get",
                        lambda url, headers=None, timeout=None:
                        (captured.update(auth=headers.get("Authorization")), _FakeResp())[1])
    out = providers.list_models("https://a.example", "", provider_id="custom-1")
    assert out["ok"] is True
    assert captured["auth"] == "Bearer SECRET-KEY"


def test_list_models_explicit_key_to_any_custom_base(clean_db, monkeypatch):
    """异址 + 自带 key：放行（调用方自己的 key 发自己的地址，保存前测试的 UX）。"""
    captured = {}
    monkeypatch.setattr(providers.requests, "get",
                        lambda url, headers=None, timeout=None:
                        (captured.update(auth=headers.get("Authorization"), url=url), _FakeResp())[1])
    out = providers.list_models("https://evil.example", "own-key", provider_id="custom-1")
    assert out["ok"] is True
    assert captured["auth"] == "Bearer own-key"


def test_connection_never_reads_saved_key(clean_db, monkeypatch):
    """防漂移回归：test_connection 不回退存量 key（当前实现如此，锁住该语义）。"""
    def _boom(pid):
        raise AssertionError("test_connection 不应读取存量 provider")
    monkeypatch.setattr(providers, "get_provider", _boom)

    class _PostResp:
        status_code = 401
        text = "unauthorized"

    monkeypatch.setattr(providers.requests, "post", lambda url, **kw: _PostResp())
    out = providers.test_connection("https://api.deepseek.com", "", None, provider_id="deepseek")
    assert out["ok"] is False  # 走完逻辑但从未触存储


# ---------------- 手动重抓 ----------------

def test_api_refetch(client, monkeypatch):
    called = {}

    def fake_run_once():
        called["n"] = True
        return {"_total": {"added": 3, "skipped": 5, "cleaned": 0}}

    import app.main as main_mod
    monkeypatch.setattr(main_mod, "run_once", fake_run_once)
    r = client.post("/api/refetch")
    assert r.status_code == 200
    assert r.json()["ok"] is True and called.get("n") is True
