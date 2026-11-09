# Agent v2 端到端实测：流式 + 确认流 + 页面上下文
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"


def chat_stream(session_id, message, page_context=None):
    """调用流式接口，收集所有事件。"""
    req = urllib.request.Request(
        BASE + "/api/chat/stream",
        data=json.dumps({"session_id": session_id, "message": message,
                          "page_context": page_context or []}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    events = []
    with urllib.request.urlopen(req, timeout=120) as r:
        for line in r:
            line = line.decode("utf-8").strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def print_events(events, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    for ev in events:
        t = ev["type"]
        if t == "tool":
            print(f"  🔧 {ev['tool']}({json.dumps(ev.get('args', {}), ensure_ascii=False)[:60]})")
        elif t == "tool_result":
            print(f"     → {ev.get('count', '✓')} 结果")
        elif t == "confirm":
            print(f"  ⚠️ 确认请求: {ev['description']}")
        elif t == "reply":
            print(f"  💬 {ev['content'][:150]}")
        elif t == "sources":
            print(f"  📎 来源 {len(ev['items'])} 条")
        elif t == "done":
            print(f"  ✓ 会话 {ev['session_id']}")
        elif t == "error":
            print(f"  ❌ {ev['message']}")


# ─── 测试 1：搜索（流式工具调用可见）───
sid = "v2-test"
evts = chat_stream(sid, "最近有什么关于机器人的新闻？")
print_events(evts, "回合 1：搜索（应看到实时工具调用）")

# ─── 测试 2：页面上下文 + 收藏（确认流）───
page_ctx = [
    {"n": 1, "title": "测试文章：机器人新突破", "url": "https://ctx/1"},
    {"n": 2, "title": "另一篇 AI 新闻", "url": "https://ctx/2"},
]
evts2 = chat_stream(sid, "帮我收藏第 1 条", page_context=page_ctx)
print_events(evts2, "回合 2：页面上下文 + 收藏（应看到确认请求）")

# ─── 测试 3：确认收藏 ───
evts3 = chat_stream(sid, "是")
print_events(evts3, "回合 3：确认执行（应看到 bookmark_item 执行）")

print("\n" + "=" * 60)
all_ok = all(any(e["type"] == "reply" for e in evts) for evts in [evts, evts2, evts3])
print("实测完成 ✅" if all_ok else "有失败 ❌")
