# Agent 日志实测：一轮对话后查看结构化日志
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://localhost:8000"

# 1. 发一轮对话
print("发送 Agent 对话…")
req = urllib.request.Request(
    BASE + "/api/chat/stream",
    data=json.dumps({"session_id": "log-test", "message": "热榜前 3 给我看看"}).encode(),
    headers={"Content-Type": "application/json"}, method="POST",
)
with urllib.request.urlopen(req, timeout=120) as r:
    for line in r:
        pass  # 消费完整流
print("对话完成")

# 2. 查 Agent 日志
print("\n=== Agent 日志（module=agent）===")
req2 = urllib.request.Request(BASE + "/api/logs?lines=20&module=agent")
with urllib.request.urlopen(req2) as r:
    data = json.loads(r.read().decode())
for line in data["lines"]:
    print(f"  {line}")

# 3. 查全部 WARNING
print("\n=== 全部 WARNING ===")
req3 = urllib.request.Request(BASE + "/api/logs?lines=10&level=WARNING")
with urllib.request.urlopen(req3) as r:
    data3 = json.loads(r.read().decode())
for line in data3["lines"]:
    print(f"  {line}")
