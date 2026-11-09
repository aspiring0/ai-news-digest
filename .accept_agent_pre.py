# feature/agent 技术预验收：mock LLM + 真实服务进程，验证聊天链路机制（不含 LLM 质量——那属人工验收）
# 覆盖：确认流执行 / SSE 事件流 / P0-2 事件循环不阻塞 / 会话管理与历史
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP_PORT = 8901
MOCK_PORT = 18990
BASE = f"http://127.0.0.1:{APP_PORT}"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)


def http(method, url, body=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


# ---------- mock OpenAI 兼容服务 ----------
_state = {"tool_calls_done": 0}

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockLLM(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        has_tools = bool(body.get("tools"))
        slow = any("慢" in (m.get("content") or "") for m in body.get("messages", []))
        if slow:
            time.sleep(2.5)  # 模拟长 LLM 调用，验证事件循环不被阻塞
        if has_tools:
            if _state["tool_calls_done"] == 0:
                _state["tool_calls_done"] += 1
                msg = {"content": None, "tool_calls": [{"id": "tc1", "type": "function", "function": {
                    "name": "bookmark_item", "arguments": json.dumps({"url": "https://accept.test/1"})}}]}
            else:
                msg = {"content": "已处理你的请求。"}
        else:
            msg = {"content": "ok"}
        resp = {"choices": [{"message": msg, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        out = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), MockLLM).serve_forever_daemon = None
mock_srv = ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), MockLLM)
threading.Thread(target=mock_srv.serve_forever, daemon=True).start()

# ---------- 启动被测服务（feature/agent 代码，临时 DB） ----------
env = dict(os.environ, DB_PATH=os.path.join(os.environ["TEMP"], "agent-accept.db"),
           PORT=str(APP_PORT))
if os.path.exists(env["DB_PATH"]):
    os.remove(env["DB_PATH"])
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(APP_PORT)],
    env=env, cwd=os.path.dirname(os.path.abspath(__file__)),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
try:
    for _ in range(60):
        try:
            s, h = http("GET", f"{BASE}/api/health", timeout=2)
            if s == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        raise RuntimeError("服务未就绪")
    check("服务就绪（首抓后台不阻塞）", True, f"version={h.get('version')}")

    # 配 mock 为默认引擎
    s, _ = http("POST", f"{BASE}/api/providers",
                {"id": "custom-mock", "base_url": f"http://127.0.0.1:{MOCK_PORT}",
                 "api_key": "test", "model": "mock", "builtin": False, "name": "Mock"})
    s2, _ = http("POST", f"{BASE}/api/providers/custom-mock/default")
    check("配置 mock 引擎并设默认", s == 200 and s2 == 200)

    # 1) 确认流：收藏请求 → 确认 → 执行
    s, r1 = http("POST", f"{BASE}/api/chat", {"message": "帮我收藏 https://accept.test/1"})
    sid = r1.get("session_id", "")
    check("写操作先出确认", r1.get("ok") and "确认" in r1.get("reply", ""), f"reply={r1.get('reply', '')[:30]}")
    s, r2 = http("POST", f"{BASE}/api/chat", {"message": "是", "session_id": sid})
    check("确认后执行（URL 不在库 → 引导话术）", r2.get("ok") and ("找不到" in r2.get("reply", "") or "search_news" in r2.get("reply", "")),
          f"reply={r2.get('reply', '')[:40]}")

    # 2) SSE 流式事件
    req = urllib.request.Request(f"{BASE}/api/chat/stream", method="POST",
                                 data=json.dumps({"message": "热榜看看", "session_id": sid}).encode(),
                                 headers={"Content-Type": "application/json"})
    events = []
    with urllib.request.urlopen(req, timeout=30) as resp:
        buf = b""
        while True:
            chunk = resp.read(512)
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf:
                line, buf = buf.split(b"\n\n", 1)
                line = line.decode().strip()
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
    types = [e["type"] for e in events]
    check("SSE 事件流完整", "reply" in types and "done" in types, f"types={types}")

    # 3) P0-2：长 LLM 调用期间健康检查不被阻塞
    def slow_chat():
        try:
            http("POST", f"{BASE}/api/chat/stream", {"message": "慢一点回复"}, timeout=30)
        except Exception:
            pass
    threading.Thread(target=slow_chat, daemon=True).start()
    time.sleep(0.6)  # 等 SSE 进入阻塞的 LLM 调用
    t0 = time.time()
    s, _ = http("GET", f"{BASE}/api/health", timeout=5)
    dt = time.time() - t0
    check("长 LLM 调用期间 /api/health 秒回（事件循环未阻塞）", s == 200 and dt < 1.0, f"{dt:.2f}s")

    # 4) 会话管理
    s, sess = http("GET", f"{BASE}/api/chat/sessions")
    s2, hist = http("GET", f"{BASE}/api/chat/history?session_id={sid}")
    s3, _ = http("DELETE", f"{BASE}/api/chat?session_id={sid}")
    s4, hist2 = http("GET", f"{BASE}/api/chat/history?session_id={sid}")
    check("会话列表/历史/清空", s == 200 and any(x["session_id"] == sid for x in sess["sessions"])
          and len(hist["messages"]) >= 2 and s3 == 200 and hist2["messages"] == [])

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n=== 技术预验收：{passed}/{len(RESULTS)} 通过 ===")
finally:
    proc.terminate()
    mock_srv.shutdown()
