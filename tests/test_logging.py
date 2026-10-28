"""日志系统：文件持久化 + API 查看 + 前端面板。"""
from __future__ import annotations

import os

from app import db


def test_log_file_created(clean_db):
    """启动后日志文件应存在。"""
    from app.logutil import LOG_FILE
    assert os.path.exists(LOG_FILE), f"日志文件应存在: {LOG_FILE}"


def test_api_logs_returns_recent(client):
    """GET /api/logs 应返回最近的日志行。"""
    r = client.get("/api/logs?lines=20")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert isinstance(data["lines"], list)
    assert len(data["lines"]) > 0  # 启动时至少有初始日志


def test_api_logs_filters_by_level(client):
    """按级别过滤日志。"""
    r = client.get("/api/logs?level=WARNING&lines=10")
    assert r.status_code == 200
    data = r.json()
    assert all("WARNING" in line or "ERROR" in line for line in data["lines"])


def test_log_rotation(clean_db):
    """日志文件超过 5MB 时自动轮转。"""
    from app.logutil import LOG_FILE
    # 写入大量内容触发轮转（简化：检查轮转处理器已配置）
    import logging
    root = logging.getLogger()
    handlers = [h for h in root.handlers if hasattr(h, "maxBytes")]
    assert len(handlers) > 0, "应配置 RotatingFileHandler"
    assert handlers[0].maxBytes > 0
