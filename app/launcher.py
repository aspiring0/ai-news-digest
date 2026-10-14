"""桌面启动入口：启动服务并自动打开浏览器（pip 安装 / 打包 exe 共用）。

PyInstaller 打包环境下先修正 DB_PATH（默认会落到临时解包目录，需指到 exe 旁边），
再导入应用——顺序不能反（db.py 在 import 时读取 DB_PATH）。
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

import uvicorn  # noqa: E402
import webbrowser  # noqa: E402

from .main import app  # noqa: E402


def run() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError:
        port = 8000
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
