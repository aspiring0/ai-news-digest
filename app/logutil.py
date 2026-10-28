"""日志系统：文件持久化 + 轮转 + API 查询。

- 日志写入 data/logs/app.log（RotatingFileHandler，5MB × 3 份备份）
- 格式：时间戳 [级别] [模块] 消息
- API：GET /api/logs?lines=N&level=LEVEL → 最近 N 行
- 前端：设置抽屉「运行日志」面板
"""
from __future__ import annotations

import logging
import logging.handlers
import os

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """初始化日志：终端 + 文件双写，文件自动轮转。"""
    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    # 终端（保持原有行为）
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

    # 文件（5MB × 3 备份）
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # uvicorn 访问日志也入文件
    for name in ("uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in lg.handlers):
            lg.addHandler(file_handler)


def read_recent_logs(lines: int = 100, level: str = "") -> list[str]:
    """读取最近 N 行日志，可按级别过滤。"""
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except OSError:
        return []

    if level:
        level_upper = level.upper()
        all_lines = [l for l in all_lines if f"[{level_upper}]" in l]

    return [l.rstrip("\n") for l in all_lines[-lines:]]
