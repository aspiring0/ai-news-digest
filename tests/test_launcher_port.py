"""launcher 端口策略：默认自动顺延、显式 PORT 不变、全忙回退报错。"""
from __future__ import annotations

import socket

from app import launcher


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_port_is_free_detects_occupied():
    p = _free_port()
    srv = socket.socket()
    srv.bind(("127.0.0.1", p))
    srv.listen(1)
    assert launcher._port_is_free("127.0.0.1", p) is False
    assert launcher._port_is_free("127.0.0.1", _free_port()) is True
    srv.close()


def test_pick_port_skips_occupied():
    p = _free_port()
    srv = socket.socket()
    srv.bind(("127.0.0.1", p))
    srv.listen(1)
    try:
        assert launcher._pick_port("127.0.0.1", p) == p + 1, "被占端口应顺延到下一个"
    finally:
        srv.close()
    assert launcher._pick_port("127.0.0.1", p) == p, "空闲端口应原样返回"


def test_pick_port_all_busy_falls_back():
    """全忙时返回原值（交给 uvicorn 报错，与旧行为一致）。"""
    ports = []
    try:
        base = _free_port()
        for i in range(launcher.PORT_SCAN_RANGE):
            s = socket.socket()
            s.bind(("127.0.0.1", base + i))
            s.listen(1)
            ports.append(s)
        assert launcher._pick_port("127.0.0.1", base) == base
    finally:
        for s in ports:
            s.close()


def test_resolve_port_semantics():
    assert launcher._resolve_port("127.0.0.1", None) == (8000, False), "未设 → 默认+自动"
    assert launcher._resolve_port("127.0.0.1", "8123") == (8123, True), "显式 → 不顺延"
    assert launcher._resolve_port("127.0.0.1", "abc") == (8000, True), "非法 → 默认但保持显式"
