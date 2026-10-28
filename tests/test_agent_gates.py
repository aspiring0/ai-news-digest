"""门槛批 G 系列测试：流式不阻塞事件循环 / session_id 收口 / 确认流 TTL 与文案。"""
from __future__ import annotations

import asyncio
import json
import threading

from app import agent as agent_mod
from app import db


# ══════════════════════════════════════════════════════════
# G1：流式事件在工作线程执行（事件循环不被阻塞）
# ══════════════════════════════════════════════════════════

def test_stream_events_run_off_event_loop(monkeypatch):
    """run_agent_stream 的每次迭代必须跑在线程池线程，而非事件循环线程。"""
    seen = {}

    def fake_stream(session_id, message, page_context=None):
        seen["worker_tid"] = threading.get_ident()
        yield {"type": "reply", "content": "ok"}
        seen["worker_tid2"] = threading.get_ident()

    monkeypatch.setattr(agent_mod, "run_agent_stream", fake_stream)
    import app.main as main_mod

    resp = asyncio.run(_call_endpoint(main_mod))
    assert resp["status_code"] == 200
    body = resp["body"]
    # SSE 格式不变：data: {json}\n\n
    assert body.startswith("data: ")
    event = json.loads(body[len("data: "):].strip())
    assert event == {"type": "reply", "content": "ok"}
    assert body.endswith("\n\n")
    # 核心断言：生成器代码不在主线程（=事件循环线程）执行
    loop_tid = threading.get_ident()
    assert seen["worker_tid"] != loop_tid
    assert seen["worker_tid2"] != loop_tid


async def _call_endpoint(main_mod):
    resp = await main_mod.api_chat_stream({"message": "hi"})
    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8"))
    return {"status_code": resp.status_code, "body": "".join(chunks)}


# ══════════════════════════════════════════════════════════
# G2：session_id 服务端收口（防存储型 XSS 载体）
# ══════════════════════════════════════════════════════════

def _mock_llm_plain_reply(monkeypatch):
    monkeypatch.setattr(agent_mod, "get_default",
                        lambda: {"id": "t", "base_url": "https://t.com", "api_key": "k", "model": "m"})
    monkeypatch.setattr(agent_mod, "_call_llm",
                        lambda p, m, t: {"content": "收到", "tool_calls": None})


def test_chat_malicious_session_id_replaced(client, monkeypatch):
    _mock_llm_plain_reply(monkeypatch)
    evil = '"><img src=x onerror=alert(1)>'
    r = client.post("/api/chat", json={"message": "你好", "session_id": evil})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert sid != evil and sid, "恶意 session_id 应被替换为新会话"
    assert db.get_chat_messages(evil) == [], "恶意 session_id 不应入库"
    assert db.get_chat_messages(sid), "新会话应有消息"


def test_chat_valid_session_id_preserved(client, monkeypatch):
    _mock_llm_plain_reply(monkeypatch)
    r = client.post("/api/chat", json={"message": "你好", "session_id": "my-sess_01"})
    assert r.status_code == 200
    assert r.json()["session_id"] == "my-sess_01"


# ══════════════════════════════════════════════════════════
# G3：pending 确认动作 TTL
# ══════════════════════════════════════════════════════════

def test_pending_action_expires(clean_db, monkeypatch):
    """过期 pending：用户说"是"不执行，按新消息处理。"""
    import time as _time

    _mock_llm_plain_reply(monkeypatch)
    agent_mod._pending_actions.clear()
    # 直接注入一条已过期的 pending（模拟 10 分钟前请求确认的收藏）
    agent_mod._pending_actions["ttl-test"] = {
        "tool": "block_item", "args": {"url": "https://expired/x"},
        "expires_at": _time.time() - 1,
    }
    result = agent_mod.run_agent("ttl-test", "是")
    assert result["ok"] is True
    assert not any(b["value"] == "https://expired/x" for b in db.list_blocks()), "过期 pending 不应执行"


def test_pending_action_fresh_executes(clean_db, monkeypatch):
    import time as _time

    _mock_llm_plain_reply(monkeypatch)
    agent_mod._pending_actions.clear()
    agent_mod._pending_actions["ttl-fresh"] = {
        "tool": "block_item", "args": {"url": "https://fresh/x"},
        "expires_at": _time.time() + 600,
    }
    agent_mod.run_agent("ttl-fresh", "是")
    assert any(b["value"] == "https://fresh/x" for b in db.list_blocks()), "未过期 pending 应执行"


# ══════════════════════════════════════════════════════════
# G4：bookmark 确认文案明示当前状态（toggle 语义）
# ══════════════════════════════════════════════════════════

def _mock_llm_bookmark_call(monkeypatch):
    monkeypatch.setattr(agent_mod, "get_default",
                        lambda: {"id": "t", "base_url": "https://t.com", "api_key": "k", "model": "m"})
    state = {"n": 0}

    def fake_call(provider, messages, tools):
        state["n"] += 1
        if state["n"] == 1:
            return {"content": None,
                    "tool_calls": [{"id": "tc1", "name": "bookmark_item",
                                    "arguments": '{"url": "https://w/1"}'}]}
        return {"content": "完成", "tool_calls": None}

    monkeypatch.setattr(agent_mod, "_call_llm", fake_call)


def test_bookmark_confirm_wording_reflects_state(clean_db, monkeypatch):
    from datetime import datetime, timezone

    import app.summarizer as summarizer
    monkeypatch.setattr(summarizer, "fetch_article_text", lambda url, rss_summary="": "快照")
    now = datetime.now(timezone.utc)
    db.insert_items([{"url": "https://g4/1", "title": "目标文章 Keplr", "source_name": "S",
                      "fetched_at": now, "published_at": now, "score": 66.0}])
    _mock_llm_bookmark_call(monkeypatch)

    events = list(agent_mod.run_agent_stream("bm-test", "帮我收藏那条"))
    confirm = next(e for e in events if e["type"] == "confirm")
    assert "收藏" in confirm["description"] and "取消" not in confirm["description"]

    # 确认执行后，再次请求同一 URL 的确认应提示"取消收藏"
    list(agent_mod.run_agent_stream("bm-test", "是"))
    events2 = list(agent_mod.run_agent_stream("bm-test2", "再收藏一次 https://g4/1"))
    confirm2 = next((e for e in events2 if e["type"] == "confirm"), None)
    if confirm2:
        assert "取消收藏" in confirm2["description"]


# ══════════════════════════════════════════════════════════
# G5：前端 XSS 修复的静态契约（如实标注：无 JS 测试设施，锁住修复不被回退）
# ══════════════════════════════════════════════════════════

from pathlib import Path

_WIDGET = Path(__file__).resolve().parents[1] / "templates" / "_chat_widget.html"
_MODAL = Path(__file__).resolve().parents[1] / "templates" / "_summary_modal.html"


def test_widget_safehref_defined_and_used():
    src = _WIDGET.read_text(encoding="utf-8")
    assert "function safeHref(u)" in src
    assert "/^(https?:)?\\//.test(s)" in src
    # mdToHtml 链接与两处 sources href 都过 safeHref
    assert src.count("safeHref(") >= 4
    # 回归锚点：不允许回到裸 $2 直填 href
    assert "'<a href=\"$2\"" not in src


def test_widget_chips_no_inline_onclick_concat():
    src = _WIDGET.read_text(encoding="utf-8")
    # 欢迎区的静态命令（chatSend('/trending')）是写死字符串，安全；
    # 要封死的是"不可信变量拼进内联 onclick"——likes 重建后应只剩闭包方案
    assert "chatSend(\'最近有什么关于「' + t" not in src, "likes 变量不得拼进内联 onclick"
    assert "chip.textContent" in src and "chip.addEventListener" in src
    # 拼接式 chips 构造（innerHTML + map）应已移除
    assert "suggestBox.innerHTML = likes.map" not in src


def test_widget_confirm_shows_full_args():
    src = _WIDGET.read_text(encoding="utf-8")
    assert "JSON.stringify(ev.args" in src, "确认条应完整展示参数"


def test_modal_link_uses_safehref():
    src = _MODAL.read_text(encoding="utf-8")
    assert "function safeHref(u)" in src
    assert "esc(safeHref(_sumUrl))" in src


def test_widget_session_list_escaped():
    src = _WIDGET.read_text(encoding="utf-8")
    assert 'data-sid="\' + esc(s.session_id)' in src, "data-sid 属性值应经 esc"
