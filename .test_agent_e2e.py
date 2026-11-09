# Agent 端到端实测：真实 LLM 调用，验证对话质量
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"


def chat(session_id, message):
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=json.dumps({"session_id": session_id, "message": message}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


sid = "e2e-test"
print("=" * 60)
print("回合 1：搜索")
print("=" * 60)
r1 = chat(sid, "最近有什么关于 Claude 或 Anthropic 的新闻？")
print(f"ok={r1['ok']}")
print(f"reply: {r1.get('reply', '')[:200]}")
print(f"tools: {[tc['tool'] for tc in r1.get('tool_calls', [])]}")
print(f"sources: {len(r1.get('sources', []))} 条")

print()
print("=" * 60)
print("回合 2：看热榜")
print("=" * 60)
r2 = chat(sid, "现在热榜前 3 是什么？")
print(f"ok={r2['ok']}")
print(f"reply: {r2.get('reply', '')[:200]}")
print(f"tools: {[tc['tool'] for tc in r2.get('tool_calls', [])]}")

print()
print("=" * 60)
print("回合 3：操控（收藏）")
print("=" * 60)
# 找一条 URL 来收藏
r3 = chat(sid, "帮我收藏热榜第 1 条")
print(f"ok={r3['ok']}")
print(f"reply: {r3.get('reply', '')[:200]}")
print(f"tools: {[tc['tool'] for tc in r3.get('tool_calls', [])]}")

print()
print("=" * 60)
print("回合 4：查看源状态")
print("=" * 60)
r4 = chat(sid, "现在有多少个源在正常工作？")
print(f"ok={r4['ok']}")
print(f"reply: {r4.get('reply', '')[:200]}")
print(f"tools: {[tc['tool'] for tc in r4.get('tool_calls', [])]}")

print()
print("=" * 60)
print(f"完整会话历史长度: {len(chat(sid, '')['tool_calls']) if r4['ok'] else '?'}")
print("实测完成 ✅" if all(r.get("ok") for r in [r1, r2, r3, r4]) else "有失败 ❌")
