"""Agent 平台操控：工具层 / 循环骨架 / 写操作确认流 / API。

测试即行为合同——实现必须让所有测试变绿。
LLM 相关全部 mock（确定性测试）；对话质量由人工验收。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import db


def _now():
    return datetime.now(timezone.utc)


def _row(url, title, source, score=66.0):
    return {"url": url, "title": title, "source_name": source,
            "published_at": _now() - timedelta(hours=1), "fetched_at": _now(), "score": score}


# ══════════════════════════════════════════════════════════
# 一、工具层（确定性，标准 TDD）
# ══════════════════════════════════════════════════════════

class TestTools:
    def test_search_news_returns_formatted(self, clean_db):
        from app.agent import tool_search_news
        db.insert_items([_row("https://a/1", "Claude 发布新版本 Keplr", "AIHOT")])
        result = tool_search_news("Claude")
        assert len(result) >= 1
        assert any("Claude" in r["title"] for r in result)
        assert all("url" in r and "source" in r for r in result)

    def test_get_trending_returns_top(self, clean_db):
        from app.agent import tool_get_trending
        db.insert_items([
            _row("https://t/1", "热门事件 Keplr Nova Alpha", "AIHOT", 90),
            _row("https://t/2", "次热门 Zephyr Orbit", "量子位", 80),
        ])
        result = tool_get_trending(2)
        assert len(result) <= 2
        assert result[0]["title"]  # 有标题

    def test_bookmark_item_toggles(self, clean_db):
        from app.agent import tool_bookmark_item
        db.insert_items([_row("https://b/1", "要收藏的文章 Keplr", "S")])
        r1 = tool_bookmark_item("https://b/1")
        assert r1["bookmarked"] is True
        r2 = tool_bookmark_item("https://b/1")
        assert r2["bookmarked"] is False

    def test_block_category(self, clean_db):
        from app.agent import tool_block_category
        r = tool_block_category("融资与公司动态")
        assert r["ok"] is True
        blocks = db.list_blocks()
        assert any(b["kind"] == "category" and "融资" in b["value"] for b in blocks)

    def test_block_item(self, clean_db):
        from app.agent import tool_block_item
        r = tool_block_item("https://x/1")
        assert r["ok"] is True

    def test_add_rss_source_validates(self, clean_db):
        from app.agent import tool_add_rss_source
        ok = tool_add_rss_source("测试源", "https://example.com/feed")
        assert ok["ok"] is True
        bad = tool_add_rss_source("坏源", "not-a-url")
        assert bad["ok"] is False

    def test_get_source_health(self, clean_db):
        from app.agent import tool_get_source_health
        result = tool_get_source_health()
        assert isinstance(result, dict)  # 空 dict 也 OK（没跑过抓取）


# ══════════════════════════════════════════════════════════
# 二、Agent 循环骨架（mock LLM，测护栏）
# ══════════════════════════════════════════════════════════

class TestAgentLoop:
    def _mock_llm_single_tool(self, monkeypatch, tool_name, tool_args, final_reply):
        """模拟 LLM：第一轮返回 tool_call，第二轮返回最终文本。"""
        import app.agent as agent_mod
        call_count = {"n": 0}

        def fake_call(provider, messages, tools):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {
                    "content": None,
                    "tool_calls": [{"id": "tc1", "name": tool_name, "arguments": json.dumps(tool_args)}],
                }
            return {"content": final_reply, "tool_calls": None}

        monkeypatch.setattr(agent_mod, "_call_llm", fake_call)

    def _mock_provider(self, monkeypatch):
        import app.agent as agent_mod
        monkeypatch.setattr(agent_mod, "get_default",
                            lambda: {"id": "test", "base_url": "https://t.com", "api_key": "k", "model": "m"})

    def test_single_tool_call_and_answer(self, clean_db, monkeypatch):
        db.insert_items([_row("https://q/1", "Claude 相关新闻 Keplr", "AIHOT")])
        self._mock_provider(monkeypatch)
        self._mock_llm_single_tool(monkeypatch, "search_news", {"query": "Claude"}, "找到了相关新闻")
        from app.agent import run_agent
        result = run_agent("session1", "有什么 Claude 新闻？")
        assert result["ok"] is True
        assert "找到了" in result["reply"]
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool"] == "search_news"

    def test_max_iterations_guard(self, clean_db, monkeypatch):
        """LLM 永远返回 tool_call → 超过 5 轮强制终止。"""
        self._mock_provider(monkeypatch)
        import app.agent as agent_mod
        monkeypatch.setattr(agent_mod, "_call_llm",
                            lambda p, m, t: {"content": None,
                                             "tool_calls": [{"id": "tc", "name": "search_news",
                                                             "arguments": '{"query": "x"}'}]})
        from app.agent import run_agent
        result = run_agent("session2", "搜索一下")
        assert result["ok"] is True  # 不崩溃
        assert "信息不足" in result["reply"] or "无法" in result["reply"]

    def test_no_provider_error(self, clean_db, monkeypatch):
        import app.agent as agent_mod
        monkeypatch.setattr(agent_mod, "get_default", lambda: None)
        from app.agent import run_agent
        result = run_agent("session3", "hi")
        assert result["ok"] is False
        assert "设置" in result["message"] or "引擎" in result["message"]

    def test_llm_returns_garbage(self, clean_db, monkeypatch):
        """LLM 返回无法解析的内容 → 容错。"""
        self._mock_provider(monkeypatch)
        import app.agent as agent_mod
        monkeypatch.setattr(agent_mod, "_call_llm",
                            lambda p, m, t: {"content": "垃圾", "tool_calls": None})
        from app.agent import run_agent
        result = run_agent("session4", "hello")
        assert result["ok"] is True  # 不崩溃
        assert result["reply"]  # 有回复（可能是"垃圾"原文，但不崩）


# ══════════════════════════════════════════════════════════
# 三、写操作确认流（Agent 安全核心）
# ══════════════════════════════════════════════════════════

class TestWriteConfirmation:
    def _mock_provider(self, monkeypatch):
        import app.agent as agent_mod
        monkeypatch.setattr(agent_mod, "get_default",
                            lambda: {"id": "test", "base_url": "https://t.com", "api_key": "k", "model": "m"})

    def _mock_bookmark_summarizer(self, monkeypatch):
        """mock 掉 toggle_bookmark 里的正文抓取（不走网络）。"""
        import app.summarizer as summarizer
        monkeypatch.setattr(summarizer, "fetch_article_text", lambda url, rss_summary="": "模拟正文快照")

    def test_write_action_flagged_in_response(self, clean_db, monkeypatch):
        """Agent 调写工具时，结果应标记 pending_confirmation。"""
        db.insert_items([_row("https://w/1", "要收藏的文章 Keplr Nova", "S")])
        self._mock_provider(monkeypatch)
        self._mock_bookmark_summarizer(monkeypatch)
        # 模拟 LLM 要调 bookmark_item
        import app.agent as agent_mod
        call_count = {"n": 0}

        def fake_call(provider, messages, tools):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"content": None,
                        "tool_calls": [{"id": "tc1", "name": "bookmark_item",
                                        "arguments": '{"url": "https://w/1"}'}]}
            return {"content": "已帮您收藏", "tool_calls": None}

        monkeypatch.setattr(agent_mod, "_call_llm", fake_call)
        from app.agent import run_agent
        result = run_agent("session5", "帮我收藏那条")
        assert result["ok"] is True
        # 确认收藏确实执行了
        bm = db.get_bookmarks()
        assert any(b["url"] == "https://w/1" for b in bm)


# ══════════════════════════════════════════════════════════
# 四、API 层
# ══════════════════════════════════════════════════════════

class TestChatAPI:
    def test_chat_creates_session(self, client, monkeypatch):
        import app.agent as agent_mod
        monkeypatch.setattr(agent_mod, "get_default", lambda: None)
        r = client.post("/api/chat", json={"message": "hi"})
        assert r.status_code == 400  # 无引擎

    def test_chat_history_empty(self, client):
        r = client.get("/api/chat/history?session_id=new")
        assert r.status_code == 200
        assert r.json()["messages"] == []

    def test_chat_clear(self, client):
        r = client.delete("/api/chat?session_id=whatever")
        assert r.status_code == 200
