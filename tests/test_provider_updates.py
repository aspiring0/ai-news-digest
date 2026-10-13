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
