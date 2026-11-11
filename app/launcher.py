"""桌面启动入口：启动服务并自动打开浏览器（pip 安装 / 打包 exe 共用）。

PyInstaller 打包环境下先修正 DB_PATH（默认会落到临时解包目录，需指到 exe 旁边），
再导入应用——顺序不能反（db.py 在 import 时读取 DB_PATH）。

端口策略（v0.4.7）：未显式设 PORT 时，默认 8000 被占用则自动顺延
（8000-8020 内找空闲）——双击 exe 绝不因端口冲突静默退出；显式设置
PORT 的行为不变（占用即报错，尊重用户选择）。
"""
from __future__ import annotations

import os
import sys
import threading
import time


def _prepare_env() -> None:
    if getattr(sys, "frozen", False):  # PyInstaller 打包运行
        base = os.path.dirname(sys.executable)
        os.environ.setdefault("DB_PATH", os.path.join(base, "data", "news.db"))


_prepare_env()

import socket  # noqa: E402

import uvicorn  # noqa: E402
import webbrowser  # noqa: E402

from .main import app  # noqa: E402

PORT_SCAN_RANGE = 20  # 8000 被占时最多顺延尝试 20 个端口


def _port_is_free(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((probe_host, port))
            return True
        except OSError:
            return False


def _pick_port(host: str, desired: int) -> int:
    for p in range(desired, desired + PORT_SCAN_RANGE):
        if _port_is_free(host, p):
            return p
    return desired  # 全忙：返回原值，让 uvicorn 报错（与旧行为一致）


def _resolve_port(host: str, env_value: str | None) -> tuple[int, bool]:
    """(端口, 是否显式指定)。未指定 → (8000, False)；非法值 → (8000, True)。"""
    if env_value is None:
        return 8000, False
    try:
        return int(env_value), True
    except ValueError:
        return 8000, True


def run() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port, explicit = _resolve_port(host, os.environ.get("PORT"))
    if not explicit:
        picked = _pick_port(host, port)
        if picked != port:
            print(f"端口 {port} 被占用，自动改用 {picked}（如需固定端口请设 PORT 环境变量）")
            port = picked
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}/hot"

    def _open() -> None:
        time.sleep(1.5)
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_open, daemon=True).start()
    print(f"AI 资讯聚合启动中：{url}")
    print("数据保存在运行目录 data/news.db；关闭本窗口或 Ctrl+C 退出。")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run()
