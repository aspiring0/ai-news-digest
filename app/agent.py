"""平台操控 Agent：用自然语言操控资讯台（搜索/收藏/屏蔽/加源）。

架构：OpenAI function calling 原生循环（无框架依赖）。
LLM 不执行工具——它返回 tool_calls，本模块执行后将结果喂回，
直到 LLM 给出最终文本回答或触发护栏。
"""
from __future__ import annotations

import json
import logging
import time
import uuid

import requests

from . import db
from .providers import chat_url, get_default

logger = logging.getLogger("ai-news-agent")

MAX_ITERATIONS = 5
TIMEOUT_SECONDS = 60
TOOL_RESULT_MAX_CHARS = 2000
HISTORY_MAX_ROUNDS = 10

# 会话存储（in-memory，重启清空）
_sessions: dict[str, list[dict]] = {}

AGENT_SYSTEM_PROMPT = (
    "你是「AI 资讯助手」，帮用户操控他们的 AI 资讯聚合站。\n"
    "你可以搜索新闻、查看热榜、收藏/屏蔽条目、添加 RSS 源。\n"
    "规则：\n"
    "1. 用简体中文回答\n"
    "2. 涉及写操作（收藏/屏蔽/加源）时，先告知用户你要做什么再执行\n"
    "3. 回答时引用来源（标题+来源名）\n"
    "4. 如果搜索无结果，建议用户换关键词或等下一轮抓取\n"
    "5. 库内数据只保留 14 天，更早的内容无法查到"
)


# ══════════════════════════════════════════════════════════
# 工具层（每个工具 = 一个函数 + 一个 JSON schema）
# ══════════════════════════════════════════════════════════

def tool_search_news(query: str) -> list[dict]:
    """FTS5 全文搜索（标题+中文标题+描述+RSS 摘要）。"""
    items = db.search_items(query, limit=10)
    return [{"title": it.get("title_cn") or it["title"],
             "url": it["url"], "source": it["source_name"],
             "hot_score": it["hot_score"]} for it in items]


def tool_get_trending(limit: int = 5) -> list[dict]:
    """当前热榜 top N（故事级）。"""
    items, _ = db.get_hot_stories(per_page=max(1, min(10, limit)))
    return [{"title": it.get("title_cn") or it["title"],
             "url": it["url"], "source": it["source_name"],
             "hot_score": it["hot_score"],
             "story_count": (it.get("_story") or {}).get("count", 1)} for it in items]


def tool_bookmark_item(url: str) -> dict:
    """收藏/取消收藏一条新闻。"""
    try:
        state = db.toggle_bookmark(url)
        return {"ok": True, "bookmarked": state,
                "message": "已收藏" if state else "已取消收藏"}
    except KeyError:
        return {"ok": False, "message": "找不到这条新闻（可能已过期被清理）"}


def tool_block_item(url: str) -> dict:
    """屏蔽某条新闻（不再出现在热榜/时间线）。"""
    db.add_block("url", url)
    return {"ok": True, "message": "已屏蔽"}


def tool_block_source(source_name: str) -> dict:
    """屏蔽某个来源的所有新闻。"""
    db.add_block("source", source_name)
    return {"ok": True, "message": f"已屏蔽来源「{source_name}」"}


def tool_block_category(category: str) -> dict:
    """屏蔽某个分类的所有新闻。"""
    db.add_block("category", category)
    return {"ok": True, "message": f"已屏蔽分类「{category}」"}


def tool_add_rss_source(name: str, url: str) -> dict:
    """添加自定义 RSS 源。"""
    try:
        db.add_custom_source(name, url)
        return {"ok": True, "message": f"已添加「{name}」，下一轮抓取生效"}
    except ValueError as e:
        return {"ok": False, "message": str(e)}


def tool_get_source_health() -> dict:
    """各源最近一轮抓取状态。"""
    raw = db.get_meta("source_health")
    return json.loads(raw) if raw else {}


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_news", "description": "搜索新闻（标题+中文标题+描述+RSS摘要）",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索关键词"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_trending", "description": "获取当前热榜 top N",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "返回条数（1-10）", "default": 5}}}}},
    {"type": "function", "function": {
        "name": "bookmark_item", "description": "收藏或取消收藏一条新闻",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "新闻的 URL"}},
            "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "block_item", "description": "屏蔽某条新闻",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "要屏蔽的新闻 URL"}},
            "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "block_source", "description": "屏蔽某个来源的所有新闻",
        "parameters": {"type": "object", "properties": {
            "source_name": {"type": "string", "description": "来源名称"}},
            "required": ["source_name"]}}},
    {"type": "function", "function": {
        "name": "block_category", "description": "屏蔽某个分类的所有新闻",
        "parameters": {"type": "object", "properties": {
            "category": {"type": "string", "description": "分类名称"}},
            "required": ["category"]}}},
    {"type": "function", "function": {
        "name": "add_rss_source", "description": "添加自定义 RSS 源",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "源名称"},
            "url": {"type": "string", "description": "RSS 地址"}},
            "required": ["name", "url"]}}},
    {"type": "function", "function": {
        "name": "get_source_health", "description": "各源最近一轮抓取状态",
        "parameters": {"type": "object", "properties": {}}}},
]

TOOL_REGISTRY = {
    "search_news": tool_search_news,
    "get_trending": tool_get_trending,
    "bookmark_item": tool_bookmark_item,
    "block_item": tool_block_item,
    "block_source": tool_block_source,
    "block_category": tool_block_category,
    "add_rss_source": tool_add_rss_source,
    "get_source_health": tool_get_source_health,
}


# ══════════════════════════════════════════════════════════
# LLM 调用（OpenAI function calling 原生格式）
# ══════════════════════════════════════════════════════════

def _call_llm(provider: dict, messages: list[dict], tools: list[dict]) -> dict:
    """调 LLM 的 /chat/completions，返回 {content, tool_calls} 或抛异常。"""
    resp = requests.post(
        chat_url(provider["id"], provider["base_url"]),
        headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
        json={
            "model": provider.get("model") or "default",
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.3,
            "max_tokens": 2000,
        },
        timeout=55,
    )
    resp.raise_for_status()
    msg = resp.json()["choices"][0]["message"]
    tool_calls = None
    if msg.get("tool_calls"):
        tool_calls = [
            {"id": tc["id"], "name": tc["function"]["name"],
             "arguments": tc["function"]["arguments"]}
            for tc in msg["tool_calls"]
        ]
    return {"content": msg.get("content"), "tool_calls": tool_calls}


# ══════════════════════════════════════════════════════════
# Agent 主循环
# ══════════════════════════════════════════════════════════

def run_agent(session_id: str, user_message: str) -> dict:
    """主入口：接收用户消息，跑 Agent 循环，返回最终回复。"""
    provider = get_default()
    if not provider:
        return {"ok": False, "message": "请先在设置页配置默认解读引擎（模型 key）"}

    session_id = session_id or str(uuid.uuid4())[:8]
    history = _sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": user_message})

    # 构建消息列表（system + 最近 N 轮历史）
    all_messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    recent = history[-HISTORY_MAX_ROUNDS * 2:]
    all_messages.extend(recent)

    tool_calls_log: list[dict] = []
    sources_used: set[dict] = set()
    start = time.time()

    try:
        for _iteration in range(MAX_ITERATIONS):
            if time.time() - start > TIMEOUT_SECONDS:
                break

            llm_result = _call_llm(provider, all_messages, TOOL_SCHEMAS)

            if not llm_result["tool_calls"]:
                # 最终回答
                reply = llm_result["content"] or "抱歉，我没有得到有效回复。"
                history.append({"role": "assistant", "content": reply})
                return {"ok": True, "session_id": session_id, "reply": reply,
                        "tool_calls": tool_calls_log, "sources": list(sources_used)}

            # 有 tool_calls → 执行工具
            assistant_msg = {"role": "assistant", "content": llm_result["content"],
                             "tool_calls": [{"id": tc["id"], "type": "function",
                                            "function": {"name": tc["name"],
                                                          "arguments": tc["arguments"]}}
                                           for tc in llm_result["tool_calls"]]}
            all_messages.append(assistant_msg)

            for tc in llm_result["tool_calls"]:
                tool_name = tc["name"]
                tool_fn = TOOL_REGISTRY.get(tool_name)
                try:
                    tool_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    # 参数安全：query 限长
                    if "query" in tool_args:
                        tool_args["query"] = str(tool_args["query"])[:200]
                except (ValueError, TypeError):
                    tool_args = {}

                if tool_fn:
                    try:
                        result = tool_fn(**tool_args)
                    except Exception as e:  # noqa: BLE001
                        result = {"error": f"工具执行失败: {e}"}
                else:
                    result = {"error": f"未知工具: {tool_name}"}

                result_str = json.dumps(result, ensure_ascii=False, default=str)[:TOOL_RESULT_MAX_CHARS]
                all_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})

                # 记录工具调用
                log_entry = {"tool": tool_name, "args": tool_args}
                if isinstance(result, list):
                    log_entry["result_count"] = len(result)
                    for r in result:
                        if isinstance(r, dict) and "url" in r:
                            sources_used.add(json.dumps({"title": r.get("title", ""),
                                                          "url": r["url"],
                                                          "source": r.get("source", "")},
                                                         ensure_ascii=False))
                elif isinstance(result, dict):
                    log_entry["result"] = {k: v for k, v in result.items() if k != "error"}
                tool_calls_log.append(log_entry)

        # 超过最大轮次
        reply = "基于已有信息，我暂时无法得到更完整的答案。请尝试换一个问法，或等下一轮数据更新后再问。"
        history.append({"role": "assistant", "content": reply})
        return {"ok": True, "session_id": session_id, "reply": reply,
                "tool_calls": tool_calls_log, "sources": list(sources_used)}

    except requests.Timeout:
        return {"ok": False, "message": "模型调用超时，请稍后重试"}
    except Exception as e:  # noqa: BLE001
        logger.warning("Agent 异常: %s", e)
        return {"ok": False, "message": f"Agent 出错: {e}"}


def get_history(session_id: str) -> list[dict]:
    return _sessions.get(session_id, [])


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
