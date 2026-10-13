"""测试公共设施：零网络、临时数据库。

关键点：db.py 在 import 时读取 DB_PATH，所以必须在导入 app 之前设置环境变量。
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 仓库根目录入 sys.path，保证 `import app` 可用（pytest 从任意目录运行）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_TMP_DIR = tempfile.mkdtemp(prefix="ai-news-test-")
os.environ["DB_PATH"] = os.path.join(_TMP_DIR, "test.db")

import pytest  # noqa: E402

from app import db  # noqa: E402


class _Inner:
    """替代 BackgroundScheduler 实例：shutdown 不抛错。"""

    def shutdown(self, wait: bool = False) -> None:  # noqa: D102
        pass


class _SchedulerModuleStub:
    """替代 app.main.scheduler 模块：不真正调度。"""

    scheduler = _Inner()

    @staticmethod
    def start() -> None:
        pass


_SEED_ROWS = [
    {
        "url": "https://example.com/news/1",
        "title": "OpenAI 发布 GPT-5 对齐研究报告",
        "source_name": "Test RSS",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=1),
        "fetched_at": datetime.now(timezone.utc),
        "score": 66.0,
    },
    {
        "url": "https://example.com/news/2",
        "title": "某机器人公司完成 2 亿美元融资",
        "source_name": "Test RSS",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=5),
        "fetched_at": datetime.now(timezone.utc),
        "score": 64.0,
    },
    {
        "url": "https://example.com/news/3",
        "title": "欧盟通过新 AI 监管法案",
        "source_name": "Test RSS",
        "published_at": None,
        "fetched_at": datetime.now(timezone.utc) - timedelta(hours=10),
        "score": 62.0,
    },
]


@pytest.fixture()
def client(monkeypatch):
    """FastAPI TestClient：不打网络（首次抓取与调度都被替换），DB 指向临时文件。"""
    db.init_db()
    db.insert_items(_SEED_ROWS)

    from fastapi.testclient import TestClient

    import app.main as main_mod

    monkeypatch.setattr(main_mod, "run_once", lambda: {"_total": {"added": 0, "skipped": 0, "cleaned": 0}})
    monkeypatch.setattr(main_mod, "scheduler", _SchedulerModuleStub)

    with TestClient(main_mod.app) as c:
        yield c


@pytest.fixture()
def clean_db():
    """给不经过 TestClient 的单元测试：初始化并清空临时库。"""
    db.init_db()
    with db._connect() as conn:
        conn.execute("DELETE FROM news_items")
        conn.execute("DELETE FROM provider_settings")
    return db
