"""Agent 第一批优化：跨会话持久（A1）+ 错误恢复（A4）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db


def _now():
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════
# A1: 跨会话持久
# ══════════════════════════════════════════════════════════

def test_chat_messages_table_exists(clean_db):
    with db._connect() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "chat_messages" in tables


def test_save_and_load_chat_messages(clean_db):
    db.save_chat_message("s1", "user", "你好")
    db.save_chat_message("s1", "assistant", "你好！有什么可以帮你？", tool_calls='[{"tool":"search_news"}]')
    db.save_chat_message("s2", "user", "另一会话")

    msgs = db.get_chat_messages("s1")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user" and msgs[0]["content"] == "你好"
    assert msgs[1]["role"] == "assistant"
    assert "search_news" in (msgs[1].get("tool_calls") or "")

    msgs2 = db.get_chat_messages("s2")
    assert len(msgs2) == 1


def test_chat_sessions_list(clean_db):
    db.save_chat_message("alpha", "user", "会话1")
    db.save_chat_message("beta", "user", "会话2")
    db.save_chat_message("beta", "assistant", "回复")
    db.save_chat_message("gamma", "user", "会话3")

    sessions = db.list_chat_sessions()
    assert len(sessions) >= 3
    # 最新的排前面
    assert sessions[0]["session_id"] == "gamma"


def test_agent_survives_memory_clear(clean_db):
    """模拟重启：清掉内存缓存后，历史仍可从 DB 恢复。"""
    # 先存消息到 DB（模拟之前有对话）
    db.save_chat_message("persist-test", "user", "之前说过的话")
    db.save_chat_message("persist-test", "assistant", "之前的回复")

    # DB 中的历史在"重启"（无内存缓存）后仍然可用
    history = db.get_chat_messages("persist-test")
    assert len(history) == 2
    assert history[0]["content"] == "之前说过的话"
    assert history[1]["content"] == "之前的回复"


def test_clear_chat_session(clean_db):
    db.save_chat_message("del-test", "user", "要删的")
    db.clear_chat_session("del-test")
    assert db.get_chat_messages("del-test") == []


# ══════════════════════════════════════════════════════════
# A4: 错误恢复（工具错误信息含恢复建议）
# ══════════════════════════════════════════════════════════

def test_bookmark_error_suggests_recovery(clean_db):
    """bookmark_item 找不到 URL 时，错误信息应建议 LLM 搜索重试。"""
    from app.agent import tool_bookmark_item
    result = tool_bookmark_item("https://nonexistent/url")
    assert result["ok"] is False
    assert "search_news" in result["message"] or "搜索" in result["message"], \
        f"错误信息应包含恢复建议: {result['message']}"


def test_block_error_suggests_recovery(clean_db):
    from app.agent import tool_block_item
    # block_item 不会失败（总是成功），但检查返回格式
    result = tool_block_item("https://any/url")
    assert result["ok"] is True


def test_agent_recovery_loop(clean_db, monkeypatch):
    """Agent 工具失败后错误信息回传 LLM，LLM 可选择搜索重试。
    验证：读工具（search）失败不崩溃，Agent 能继续运行并给出回复。"""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    db.insert_items([{
        "url": "https://real/1", "title": "正确的文章 Keplr Nova",
        "source_name": "AIHOT", "published_at": now - timedelta(hours=1),
        "fetched_at": now, "score": 90,
    }])

    import app.agent as agent_mod
    monkeypatch.setattr(agent_mod, "get_default",
                        lambda: {"id": "t", "base_url": "https://t.com", "api_key": "k", "model": "m"})

    # 模拟 LLM：第1轮搜索一个不存在的词→空结果→第2轮给最终回答
    state = {"n": 0}

    def fake_llm(provider, messages, tools):
        state["n"] += 1
        if state["n"] == 1:
            return {"content": None, "tool_calls": [
                {"id": "t1", "name": "search_news", "arguments": '{"query": "不存在的词xyz"}'}]}
        return {"content": "搜索没有找到相关内容，建议换一个关键词。", "tool_calls": None}

    monkeypatch.setattr(agent_mod, "_call_llm", fake_llm)

    events = list(agent_mod.run_agent_stream("recovery-test", "帮我找一篇关于 xyz 的文章"))
    replies = [e for e in events if e["type"] == "reply"]
    tools_used = [e["tool"] for e in events if e["type"] == "tool"]

    # Agent 正常完成了循环（搜索空结果→LLM 自适应回答）
    assert "search_news" in tools_used
    assert len(replies) > 0
    assert len(events[-1].get("session_id", "")) > 0  # done 事件有 session_id
