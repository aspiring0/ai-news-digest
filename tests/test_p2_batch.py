"""P2 批测试：push 配置损坏回退 + SQLite 三件套（busy_timeout/close/WAL）。"""
from __future__ import annotations

import sqlite3

import pytest

from app import db, push


# ---------------- P2-1：推送配置损坏回退默认 ----------------

def test_corrupted_push_config_falls_back(clean_db):
    db.set_meta(push.CONFIG_KEY, "{not-valid-json")
    cfg = push.get_config()
    assert isinstance(cfg, dict) and cfg["channel"] == "off" and cfg["enabled"] is False
    # 默认 dict 是副本，改它不污染模块常量
    cfg["channel"] = "telegram"
    assert push.DEFAULT_CONFIG["channel"] == "off"


def test_corrupted_push_config_endpoint_ok(client):
    db.set_meta(push.CONFIG_KEY, "{not-valid-json")
    r = client.get("/api/push")
    assert r.status_code == 200
    assert r.json()["config"]["channel"] == "off"


def test_corrupted_push_config_notify_round_safe(clean_db, monkeypatch):
    db.set_meta(push.CONFIG_KEY, "{not-valid-json")
    monkeypatch.setattr(push, "send", lambda text, cfg=None: {"ok": True, "skip": True})
    monkeypatch.setattr(push, "build_digest", lambda cfg=None: "x")
    push.notify_round()  # 不应抛 AttributeError（旧行为：None.get）


# ---------------- P2-2：SQLite 三件套 ----------------

def test_connection_busy_timeout_set(clean_db):
    with db._connect() as conn:
        v = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert v == 5000


def test_connection_closed_after_with(clean_db):
    with db._connect() as conn:
        conn.execute("SELECT 1").fetchone()
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")  # with 退出后连接已关闭


def test_wal_mode_persisted(clean_db):
    with db._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_rollback_on_error_keeps_consistency(clean_db):
    db.set_meta("k1", "v1")
    with pytest.raises(RuntimeError):
        with db._connect() as conn:
            conn.execute("INSERT INTO meta (key, value) VALUES ('k2', 'v2')")
            raise RuntimeError("boom")
    assert db.get_meta("k1") == "v1"
    assert db.get_meta("k2") is None  # 异常回滚
