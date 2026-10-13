"""D 批次：兴趣画像（蒸馏/存取/应用）+ 为我精选。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app import db
from app.profile import apply_profile_to_stories, load_profile, save_profile


def _row(url, title, source, score, hours=1.0):
    now = datetime.now(timezone.utc)
    return {"url": url, "title": title, "source_name": source,
            "published_at": now - timedelta(hours=hours), "fetched_at": now, "score": score}


# ---------------- 画像存取 ----------------

def test_profile_save_load_clear(clean_db):
    assert load_profile() is None
    save_profile({"likes": ["具身智能", "模型评测"], "dislikes": ["融资八卦"], "notes": "测试"})
    p = load_profile()
    assert p["likes"] == ["具身智能", "模型评测"] and p["dislikes"] == ["融资八卦"]
    assert p["updated_at"]  # 自动带更新时间
    db.set_meta("interest_profile", "")  # 重置
    assert load_profile() is None


# ---------------- 画像应用：加分 + 过滤 ----------------

def _story(title, score):
    item = _row("https://s/" + title[:6], title, "AIHOT", score)
    item["hot_score"] = score
    return {"representative": item, "members": [item], "sources": ["AIHOT"],
            "entities": set(), "last_time": datetime.now(timezone.utc), "_score": score}


def test_apply_profile_boosts_likes_filters_dislikes():
    stories = [
        _story("普通事件 Zenith Pole", 80.0),
        _story("具身智能机器人新进展 Embodied", 75.0),   # 命中喜欢 +15% → 86.25 反超
        _story("某公司完成 2 亿美元融资八卦", 90.0),       # 命中不喜欢 → 应消失
    ]
    profile = {"likes": ["具身智能"], "dislikes": ["融资"], "notes": ""}
    out = apply_profile_to_stories(stories, profile)
    titles = [s["representative"]["title"] for s in out]
    assert not any("融资" in t for t in titles), "不感兴趣的故事应被过滤"
    assert titles[0].startswith("具身智能"), f"命中的故事应排第一: {titles}"
    assert out[0]["_score"] > 75.0, "命中故事应有加成"


def test_apply_profile_noop_when_empty():
    stories = [_story("随便什么 Aaa", 70.0)]
    out = apply_profile_to_stories(stories, {"likes": [], "dislikes": [], "notes": ""})
    assert len(out) == 1 and out[0]["_score"] == 70.0


# ---------------- get_hot_stories 集成 ----------------

def test_get_hot_stories_with_profile(clean_db):
    db.insert_items([
        _row("https://x/1", "普通大事件 Zenith Pole Release", "AIHOT", 80),
        _row("https://x/2", "具身智能机器人重磅发布 Embodied Bot", "量子位", 75),
    ])
    profile = {"likes": ["具身智能"], "dislikes": [], "notes": ""}
    items, total = db.get_hot_stories(profile=profile)
    assert total == 2
    assert items[0]["title"].startswith("具身智能"), "画像加成应改变热榜排序"


# ---------------- API ----------------

def test_profile_api_roundtrip(client):
    r = client.get("/api/profile")
    assert r.status_code == 200 and r.json()["profile"] is None
    r2 = client.post("/api/profile", json={"likes": ["模型评测"], "dislikes": ["八卦"], "notes": "手动"})
    assert r2.status_code == 200
    assert client.get("/api/profile").json()["profile"]["likes"] == ["模型评测"]
    r3 = client.post("/api/profile", json={"likes": "不是列表"})
    assert r3.status_code == 400
    client.delete("/api/profile")
    assert client.get("/api/profile").json()["profile"] is None


def test_distill_insufficient_interactions(client):
    r = client.post("/api/profile/distill")
    assert r.status_code == 400
    assert "行为数据不足" in r.json()["message"]


def test_distill_writes_profile(client, monkeypatch):
    for i in range(8):
        db.log_interaction("summary", f"https://d/{i}", f"具身智能进展 {i}", "AIHOT")
    db.log_interaction("block", "", "融资八卦标题", "AIHOT")

    import app.profile as profile_mod
    monkeypatch.setattr(profile_mod, "get_default", lambda: {
        "id": "deepseek", "base_url": "https://api.deepseek.com", "api_key": "k", "model": "deepseek-chat",
    })

    class FakeResp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "```json\n" + json.dumps(
                {"likes": ["具身智能", "模型评测"], "dislikes": ["融资八卦"], "notes": "用户偏好具身智能"}
            ) + "\n```"}}]}
        def raise_for_status(self):
            pass

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return FakeResp()

    monkeypatch.setattr(profile_mod.requests, "post", fake_post)
    r = client.post("/api/profile/distill")
    assert r.status_code == 200, r.text
    p = client.get("/api/profile").json()["profile"]
    assert "具身智能" in p["likes"] and "融资八卦" in p["dislikes"]
    assert "chat/completions" in captured["url"]  # 走默认引擎的 OpenAI 兼容接口
    assert "具身智能进展" in json.dumps(captured["body"], ensure_ascii=False)  # 行为日志进了提示词
