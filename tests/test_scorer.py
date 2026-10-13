"""scorer 单元测试：静态分规则 + 48 小时半衰公式。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.scorer import hot_score, static_score


def test_static_score_rss_decay_with_floor():
    assert static_score("rss", 0) == 66.0
    assert static_score("rss", 1) == 64.0
    # 下限 48：66 - 2*9 = 48，第 10 位以后不再下降
    assert static_score("rss", 9) == 48.0
    assert static_score("rss", 50) == 48.0


def test_static_score_other_classes():
    assert static_score("hf", 0) == 72.0
    assert static_score("ph", 0) == 70.0
    # 未知类别回落到 rss 规则
    assert static_score("unknown", 0) == 66.0


def test_static_score_aihot_uses_upstream():
    assert static_score("aihot", 0, upstream_score=88.0) == 88.0
    assert static_score("aihot", 0, upstream_score=None) == 50.0


def test_hot_score_halves_after_48h():
    now = datetime.now(timezone.utc)
    published_48h_ago = now - timedelta(hours=48)
    assert abs(hot_score(80.0, published_48h_ago, now) - 40.0) < 0.01


def test_hot_score_falls_back_to_fetched_at():
    now = datetime.now(timezone.utc)
    fetched_24h_ago = now - timedelta(hours=24)
    # published_at 缺失 → 按 fetched_at 计龄：24h = 一个半衰期的一半
    assert abs(hot_score(60.0, None, fetched_24h_ago) - 60.0 * 0.5**0.5) < 0.01


def test_hot_score_future_proof():
    now = datetime.now(timezone.utc)
    future = now + timedelta(hours=10)
    assert hot_score(50.0, future, now) == 50.0  # 负龄按 0 处理
