"""平台操控 Agent v2：流式输出 + 写操作确认 + 页面上下文 + URL 编号。

架构：OpenAI function calling 原生循环（无框架依赖）。
增强：
- SSE 流式：工具调用过程实时推送，不等全部完成
- 确认流：写操作（收藏/屏蔽/加源）先推 confirm 事件给用户，
  用户说"是"后才执行
- 页面上下文：前端传入当前页可见条目，Agent 能理解"这条""第 3 条"
- URL 编号：工具返回编号列表，提示词强制 LLM 用原文 URL
"""
from __future__ import annotations

import json
import logging
import re
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

# 写操作工具（需要用户确认）
WRITE_TOOLS = {"bookmark_item", "block_item", "block_source", "block_category", "add_rss_source"}

# 会话存储：pending_action 保留在内存（确认流不需要跨重启），
# 消息历史持久化到 DB（chat_messages 表）
_pending_actions: dict[str, dict] = {}

AGENT_SYSTEM_PROMPT = (
    "你是「AI 资讯助手」，帮用户操控他们的 AI 资讯聚合站。\n\n"
    "## 规则\n"
    "1. 用简体中文回答\n"
    "2. **写操作（收藏/屏蔽/加源）**：直接调用工具即可，系统会自动处理确认流程\n"
    "3. 回答时引用来源（标题+来源名），格式：[标题](来源名)\n"
    "4. 如果搜索无结果，建议换关键词或等下一轮抓取\n"
    "5. 库内数据只保留 14 天\n\n"
    "## 重要：URL 精确性\n"
    "搜索/热榜工具返回的每条都有编号和完整 URL。当你需要用 URL 调用其他工具时，"
    "必须使用工具返回的完整 URL 原文，不要猜测或截断。\n\n"
    "## 页面上下文\n"
    "用户消息前可能有 [当前页面] 标注，列出了用户正在看的条目。"
    '当用户说「这条」「第 N 条」时，参照该列表确定具体是哪条。'
)


# ══════════════════════════════════════════════════════════
# 工具层
# ══════════════════════════════════════════════════════════

def tool_search_news(query: str) -> list[dict]:
    items = db.search_items(query, limit=10)
    return [{"n": i + 1, "title": it.get("title_cn") or it["title"],
             "url": it["url"], "source": it["source_name"],
             "hot_score": it["hot_score"]} for i, it in enumerate(items)]


def tool_get_trending(limit: int = 5) -> list[dict]:
    items, _ = db.get_hot_stories(per_page=max(1, min(10, limit)))
    return [{"n": i + 1, "title": it.get("title_cn") or it["title"],
             "url": it["url"], "source": it["source_name"],
             "hot_score": it["hot_score"],
             "story_count": (it.get("_story") or {}).get("count", 1)}
            for i, it in enumerate(items)]


def tool_bookmark_item(url: str) -> dict:
    try:
        state = db.toggle_bookmark(url)
        return {"ok": True, "bookmarked": state, "message": "已收藏" if state else "已取消收藏"}
    except KeyError:
        return {"ok": False,
                "message": "找不到这条新闻（URL 可能不准确或已被 14 天清理）。"
                           "建议：用 search_news 搜索标题关键词找到正确 URL 后重试。"}


def tool_block_item(url: str) -> dict:
    db.add_block("url", url)
    return {"ok": True, "message": "已屏蔽"}


def tool_block_source(source_name: str) -> dict:
    db.add_block("source", source_name)
    return {"ok": True, "message": f"已屏蔽来源「{source_name}」"}


def tool_block_category(category: str) -> dict:
    db.add_block("category", category)
    return {"ok": True, "message": f"已屏蔽分类「{category}」"}


def tool_add_rss_source(name: str, url: str) -> dict:
    try:
        db.add_custom_source(name, url)
        return {"ok": True, "message": f"已添加「{name}」，下一轮抓取生效"}
    except ValueError as e:
        return {"ok": False, "message": str(e)}


def tool_get_source_health() -> dict:
    raw = db.get_meta("source_health")
    return json.loads(raw) if raw else {}


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_news", "description": "搜索新闻（标题+中文标题+描述+RSS摘要），返回带编号的结果列表",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索关键词"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_trending", "description": "获取当前热榜 top N，返回带编号的结果列表",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "返回条数（1-10）", "default": 5}}}}},
    {"type": "function", "function": {
        "name": "bookmark_item", "description": "收藏或取消收藏一条新闻（用工具返回的完整 URL）",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "新闻的完整 URL（必须与工具返回的完全一致）"}},
            "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "block_item", "description": "屏蔽某条新闻（用工具返回的完整 URL）",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "要屏蔽的新闻 URL"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "block_source", "description": "屏蔽某个来源的所有新闻",
        "parameters": {"type": "object", "properties": {
            "source_name": {"type": "string", "description": "来源名称"}}, "required": ["source_name"]}}},
    {"type": "function", "function": {
        "name": "block_category", "description": "屏蔽某个分类的所有新闻",
        "parameters": {"type": "object", "properties": {
            "category": {"type": "string", "description": "分类名称"}}, "required": ["category"]}}},
    {"type": "function", "function": {
        "name": "add_rss_source", "description": "添加自定义 RSS 源",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "源名称"},
            "url": {"type": "string", "description": "RSS 地址"}}, "required": ["name", "url"]}}},
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

_TOOL_DESCRIPTIONS = {
    "bookmark_item": "收藏", "block_item": "屏蔽", "block_source": "屏蔽来源",
    "block_category": "屏蔽分类", "add_rss_source": "添加 RSS 源",
}


# ══════════════════════════════════════════════════════════
# 确认流辅助
# ══════════════════════════════════════════════════════════

_YES_RE = re.compile(r"^(是|是的|确认|好|好的|嗯|OK|ok|Yes|yes|可以|没错|对)\b")
_NO_RE = re.compile(r"^(不|不要|算了|取消|No|no|别)\b")


def _is_affirmative(message: str) -> bool:
    return bool(_YES_RE.match(message.strip()))


def _is_negative(message: str) -> bool:
    return bool(_NO_RE.match(message.strip()))


def _execute_pending(pending: dict) -> dict:
    """执行待确认的写操作。"""
    tool_name = pending["tool"]
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if not tool_fn:
        return {"ok": False, "message": f"未知操作: {tool_name}"}
    try:
        return tool_fn(**pending["args"])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"执行失败: {e}"}


# ══════════════════════════════════════════════════════════
# Agent 主循环（流式生成器）
# ══════════════════════════════════════════════════════════

def run_agent_stream(session_id: str, user_message: str, page_context: list[dict] | None = None):
    """流式 Agent：yield SSE 事件字典。

    事件类型：
    - {"type": "tool", "tool": "...", "args": {...}}          工具调用开始
    - {"type": "tool_result", "tool": "...", "count": N}       工具返回（条数）
    - {"type": "confirm", "action": "...", "description": "...", "args": {...}}  请求确认
    - {"type": "reply", "content": "..."}                      最终回复（一段）
    - {"type": "sources", "items": [...]}                       引用来源
    - {"type": "done", "session_id": "..."}                     流结束
    - {"type": "error", "message": "..."}                       错误
    """
    provider = get_default()
    if not provider:
        logger.warning("[agent] 无默认引擎，拒绝请求 session=%s", session_id)
        yield {"type": "error", "message": "请先在设置页配置默认解读引擎"}
        return

    session_id = session_id or str(uuid.uuid4())[:8]
    agent_start = time.time()

    # 确认流：有 pending_action 且用户说"是" → 执行
    pending = _pending_actions.pop(session_id, None)
    if pending:
        if _is_affirmative(user_message):
            logger.info("[agent] 确认执行 session=%s tool=%s args=%s", session_id, pending["tool"],
                        json.dumps(pending["args"], ensure_ascii=False)[:100])
            yield {"type": "tool", "tool": pending["tool"], "args": pending["args"]}
            result = _execute_pending(pending)
            desc = _TOOL_DESCRIPTIONS.get(pending["tool"], pending["tool"])
            reply = result.get("message", "操作完成") if result.get("ok") else f"❌ {result.get('message', '失败')}"
            logger.info("[agent] 确认结果 session=%s ok=%s reply=%s", session_id, result.get("ok"), reply[:50])
            db.save_chat_message(session_id, "user", user_message)
            db.save_chat_message(session_id, "assistant", reply)
            yield {"type": "reply", "content": reply}
            yield {"type": "done", "session_id": session_id}
            return
        elif _is_negative(user_message):
            logger.info("[agent] 用户取消 session=%s pending_tool=%s", session_id, pending["tool"])
            db.save_chat_message(session_id, "user", user_message)
            reply = "好的，已取消。"
            db.save_chat_message(session_id, "assistant", reply)
            yield {"type": "reply", "content": reply}
            yield {"type": "done", "session_id": session_id}
            return
        # 既不是确认也不是拒绝 → 当作新消息继续处理

    # 构建用户消息（含页面上下文）
    user_content = user_message
    if page_context:
        ctx_lines = [f"[当前页面] 用户正在看以下条目："]
        for item in page_context[:10]:
            ctx_lines.append(f"  {item.get('n', '?')}. {item.get('title', '')} | URL: {item.get('url', '')}")
        user_content = "\n".join(ctx_lines) + f"\n\n用户说：{user_message}"

    db.save_chat_message(session_id, "user", user_content)
    logger.info("[agent] 开始 session=%s msg=%s ctx=%d条 迭代上限=%d", session_id, user_message[:50],
                len(page_context or []), MAX_ITERATIONS)

    # 从 DB 加载历史（跨重启持久）
    db_history = db.get_chat_messages(session_id, limit=HISTORY_MAX_ROUNDS * 2)
    all_messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    all_messages.extend({"role": m["role"], "content": m["content"]} for m in db_history)

    tool_calls_log: list[dict] = []
    sources_used: list[dict] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    start = time.time()

    try:
        for iteration in range(MAX_ITERATIONS):
            if time.time() - start > TIMEOUT_SECONDS:
                logger.warning("[agent] 超时 session=%s elapsed=%.1fs", session_id, time.time() - start)
                break

            llm_start = time.time()
            llm_result = _call_llm(provider, all_messages, TOOL_SCHEMAS)
            llm_ms = int((time.time() - llm_start) * 1000)
            u = llm_result.get("usage") or {}
            total_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += u.get("completion_tokens", 0)
            total_usage["total_tokens"] += u.get("total_tokens", 0)
            logger.info("[agent] LLM调用 session=%s iter=%d 耗时=%dms tool_calls=%s",
                        session_id, iteration + 1, llm_ms,
                        [tc["name"] for tc in llm_result["tool_calls"]] if llm_result["tool_calls"] else "无(最终回答)")

            if not llm_result["tool_calls"]:
                reply = llm_result["content"] or "抱歉，我没有得到有效回复。"
                db.save_chat_message(session_id, "assistant", reply,
                                      tool_calls=json.dumps(tool_calls_log, ensure_ascii=False) if tool_calls_log else None)
                logger.info("[agent] 完成 session=%s 总耗时=%.1fs 迭代=%d 工具调用=%d 回复长度=%d",
                            session_id, time.time() - agent_start, iteration + 1,
                            len(tool_calls_log), len(reply))
                yield {"type": "reply", "content": reply}
                if sources_used:
                    yield {"type": "sources", "items": sources_used[:10]}
                if total_usage["total_tokens"] > 0:
                    yield {"type": "tokens", "usage": total_usage}
                yield {"type": "done", "session_id": session_id}
                return

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
                    if "query" in tool_args:
                        tool_args["query"] = str(tool_args["query"])[:200]
                except (ValueError, TypeError):
                    tool_args = {}

                if not tool_fn:
                    all_messages.append({"role": "tool", "tool_call_id": tc["id"],
                                         "content": json.dumps({"error": f"未知工具: {tool_name}"})})
                    continue

                # ── 写操作确认流 ──
                if tool_name in WRITE_TOOLS:
                    desc = _TOOL_DESCRIPTIONS.get(tool_name, tool_name)
                    arg_desc = ", ".join(f"{k}={str(v)[:50]}" for k, v in tool_args.items())
                    logger.info("[agent] 请求确认 session=%s tool=%s args=%s", session_id, tool_name, arg_desc[:80])
                    yield {"type": "confirm", "action": tool_name,
                           "description": f"{desc}（{arg_desc}）",
                           "args": tool_args}
                    # 存 pending，本轮不执行，等下一轮用户确认
                    _pending_actions[session_id] = {"tool": tool_name, "args": tool_args}
                    # 告诉 LLM 已请求确认
                    all_messages.append({"role": "tool", "tool_call_id": tc["id"],
                                         "content": json.dumps({"status": "confirming",
                                                                 "message": f"已向用户发送确认请求：{desc} {arg_desc}"},
                                                                ensure_ascii=False)})
                    db.save_chat_message(session_id, "assistant", f"确认要{desc}吗？（{arg_desc}）")
                    yield {"type": "reply", "content": f"确认要{desc}吗？（{arg_desc}）"}
                    yield {"type": "done", "session_id": session_id}
                    return

                # ── 读操作直接执行 ──
                tool_start = time.time()
                yield {"type": "tool", "tool": tool_name, "args": tool_args}
                try:
                    result = tool_fn(**tool_args)
                except Exception as e:  # noqa: BLE001
                    result = {"error": f"工具执行失败: {e}"}
                tool_ms = int((time.time() - tool_start) * 1000)

                result_str = json.dumps(result, ensure_ascii=False, default=str)[:TOOL_RESULT_MAX_CHARS]
                all_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})
                logger.info("[agent] 工具 session=%s tool=%s 耗时=%dms 结果=%s",
                            session_id, tool_name, tool_ms,
                            f"{len(result)}条" if isinstance(result, list) else str(result)[:80])

                if isinstance(result, list):
                    yield {"type": "tool_result", "tool": tool_name, "count": len(result)}
                    tool_calls_log.append({"tool": tool_name, "args": tool_args, "result_count": len(result)})
                    for r in result:
                        if isinstance(r, dict) and "url" in r:
                            if not any(s["url"] == r["url"] for s in sources_used):
                                sources_used.append({"title": r.get("title", ""), "url": r["url"],
                                                     "source": r.get("source", "")})
                else:
                    yield {"type": "tool_result", "tool": tool_name}
                    tool_calls_log.append({"tool": tool_name, "args": tool_args})

        logger.warning("[agent] 达到最大迭代 session=%s iterations=%d tools=%d", session_id, MAX_ITERATIONS, len(tool_calls_log))
        reply = "基于已有信息，我暂时无法得到更完整的答案。请尝试换一个问法。"
        db.save_chat_message(session_id, "assistant", reply)
        yield {"type": "reply", "content": reply}
        yield {"type": "done", "session_id": session_id}

    except requests.Timeout:
        logger.warning("[agent] LLM超时 session=%s elapsed=%.1fs", session_id, time.time() - start)
        yield {"type": "error", "message": "模型响应超时。可能是网络波动或模型负载高，请稍后重试。"}
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        logger.error("[agent] LLM HTTP错误 session=%s status=%s", session_id, status)
        if status == "401":
            yield {"type": "error", "message": "API key 无效或已过期，请到设置页检查。"}
        elif status in ("429", "503"):
            yield {"type": "error", "message": f"模型服务暂时不可用（{status}），已重试仍失败。请稍后再试。"}
        else:
            yield {"type": "error", "message": f"模型接口返回错误 {status}，请稍后重试。"}
    except Exception as e:  # noqa: BLE001
        logger.error("[agent] 异常 session=%s error=%s", session_id, e, exc_info=True)
        yield {"type": "error", "message": f"Agent 出错: {e}"}


# ══════════════════════════════════════════════════════════
# LLM 调用
# ══════════════════════════════════════════════════════════

def _call_llm(provider: dict, messages: list[dict], tools: list[dict]) -> dict:
    """调 LLM 的 /chat/completions（带重试：503/429 等瞬态错误最多重试 2 次）。"""
    import time as _time

    last_err = None
    for attempt in range(3):  # 最多 3 次（1 原始 + 2 重试）
        try:
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
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                logger.warning("[agent] LLM 瞬态错误 %d（第 %d 次，%.1fs 后重试）",
                               resp.status_code, attempt + 1, 1.5 * (attempt + 1))
                _time.sleep(1.5 * (attempt + 1))  # 指数退避
                continue
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            usage = resp.json().get("usage", {})
            tool_calls = None
            if msg.get("tool_calls"):
                tool_calls = [
                    {"id": tc["id"], "name": tc["function"]["name"],
                     "arguments": tc["function"]["arguments"]}
                    for tc in msg["tool_calls"]
                ]
            return {"content": msg.get("content"), "tool_calls": tool_calls, "usage": usage}
        except requests.Timeout:
            raise  # 超时不重试（已有 60s 总护栏）
        except requests.ConnectionError as e:
            last_err = e
            if attempt < 2:
                logger.warning("[agent] LLM 连接错误（第 %d 次重试）", attempt + 1)
                _time.sleep(2)
                continue
            raise
    raise last_err or RuntimeError("LLM 调用失败")


# ══════════════════════════════════════════════════════════
# 兼容旧接口（非流式）
# ══════════════════════════════════════════════════════════

def run_agent(session_id: str, user_message: str) -> dict:
    """非流式版本（测试兼容）：收集所有事件后组装结果。"""
    events = list(run_agent_stream(session_id, user_message))
    reply = ""
    sources = []
    tool_calls = []
    sid = session_id
    for ev in events:
        if ev["type"] == "reply":
            reply = ev["content"]
        elif ev["type"] == "sources":
            sources = [json.dumps(s, ensure_ascii=False) for s in ev["items"]]
        elif ev["type"] == "tool":
            tool_calls.append({"tool": ev["tool"], "args": ev["args"]})
        elif ev["type"] == "tool_result":
            if tool_calls:
                tool_calls[-1]["result_count"] = ev.get("count", 0)
        elif ev["type"] == "done":
            sid = ev["session_id"]
        elif ev["type"] == "error":
            return {"ok": False, "message": ev["message"]}
    return {"ok": True, "session_id": sid, "reply": reply,
            "tool_calls": tool_calls, "sources": sources}


def get_history(session_id: str) -> list[dict]:
    return db.get_chat_messages(session_id)


def clear_session(session_id: str) -> None:
    db.clear_chat_session(session_id)
    _pending_actions.pop(session_id, None)
