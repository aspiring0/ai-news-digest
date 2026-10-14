"""推送通知：配置存取 / 摘要组装 / 四渠道发送 / 抓取轮触发。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db, push


def _now():
    return datetime.now(timezone.utc)


def _row(url, title, source, score):
    return {"url": url, "title": title, "source_name": source,
            "published_at": _now() - timedelta(hours=1), "fetched_at": _now(), "score": score}


def test_config_roundtrip(clean_db):
    assert push.get_config()["channel"] == "off"
    cfg = push.save_config({"enabled": True, "channel": "telegram",
                            "telegram_token": "123:abc", "telegram_chat": "@me", "top_n": 3})
    assert cfg["enabled"] is True and cfg["top_n"] == 3
    got = push.get_config()
    assert got["channel"] == "telegram" and got["telegram_token"] == "123:abc"
    try:
        push.save_config({"channel": "nope"})
        assert False
    except ValueError:
        pass


def test_build_digest(clean_db):
    db.insert_items([
        _row("https://d/1", "Kepler Nova 头条事件", "AIHOT", 90),
        _row("https://d/2", "Zephyr 次条", "量子位", 80),
    ])
    text = push.build_digest(push.get_config())
    assert "热榜 Top" in text and "Kepler Nova 头条事件" in text
    assert "详情：" in text


def test_send_telegram_format(clean_db, monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        text = '{"ok":true}'

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        return FakeResp()

    monkeypatch.setattr(push.requests, "post", fake_post)
    cfg = push.save_config({"channel": "telegram", "telegram_token": "T", "telegram_chat": "C"})
    out = push.send("hi", cfg)
    assert out["ok"] is True
    assert captured["url"] == "https://api.telegram.org/botT/sendMessage"
    assert captured["payload"] == {"chat_id": "C", "text": "hi"}


def test_send_wecom_and_feishu_format(clean_db, monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        text = ""

    monkeypatch.setattr(push.requests, "post", lambda url, json=None, timeout=None: (captured.update(url=url, payload=json), FakeResp())[1])
    push.send("x", push.save_config({"channel": "wecom", "wecom_key": "K"}))
    assert "qyapi.weixin.qq.com" in captured["url"] and "K" in captured["url"]
    assert captured["payload"]["msgtype"] == "text"
    push.send("y", push.save_config({"channel": "feishu", "feishu_url": "https://open.feishu.cn/hook/x"}))
    assert captured["payload"] == {"msg_type": "text", "content": {"text": "y"}}


def test_notify_round_respects_disabled(clean_db, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(push, "send", lambda *a, **k: (called.__setitem__("n", called["n"] + 1), {"ok": True})[1])
    push.notify_round()  # 默认关闭
    assert called["n"] == 0
    push.save_config({"enabled": True, "channel": "webhook", "webhook_url": "https://h"})
    push.notify_round()
    assert called["n"] == 1


def test_run_once_triggers_notify(clean_db, monkeypatch):
    import types

    import app.fetch_all as fa
    from app.fetchers.base import NewsItem

    ok_src = types.ModuleType("fake_src")
    ok_src.SOURCE_NAME = "S"
    ok_src.SCORE_CLASS = "rss"
    ok_src.fetch = lambda: [NewsItem(title="a b", url="https://n/1", source_name="S")]
    monkeypatch.setattr(fa, "FETCHERS", [ok_src])
    monkeypatch.setattr(fa, "_notify_push", lambda: called.__setitem__("n", called["n"] + 1))
    called = {"n": 0}
    fa.run_once()
    assert called["n"] == 1
