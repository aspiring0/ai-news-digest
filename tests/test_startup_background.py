"""启动后台化：服务就绪不等首抓完成（拆上游切片④）。"""
from __future__ import annotations

import time as _time


def test_startup_does_not_block_on_first_fetch(monkeypatch):
    """首抓慢（模拟 1.2s）时，TestClient 就绪必须远小于该时长。"""
    from fastapi.testclient import TestClient

    import app.main as main_mod

    done: list[bool] = []

    def slow_run_once():
        _time.sleep(1.2)
        done.append(True)
        return {"_total": {"added": 0, "skipped": 0, "cleaned": 0}}

    monkeypatch.setattr(main_mod, "run_once", slow_run_once)

    class _StubSched:
        scheduler = type("S", (), {"shutdown": staticmethod(lambda wait=False: None)})()

        @staticmethod
        def start():
            pass

    monkeypatch.setattr(main_mod, "scheduler", _StubSched)

    t0 = _time.monotonic()
    with TestClient(main_mod.app) as client:
        ready_s = _time.monotonic() - t0
        r = client.get("/api/health")
        assert r.status_code == 200
    assert ready_s < 0.8, f"启动不应等待首抓完成（实际 {ready_s:.2f}s）"

    for _ in range(50):
        if done:
            break
        _time.sleep(0.1)
    assert done, "后台首抓线程应已完成"
