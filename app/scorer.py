"""打分 + 热榜时间衰减。

静态分（抓取时按源内位置一次写入）：
- rss 类：66 起，每位 -2，不低于 48
- hf 类（HuggingFace）：72 起，每位 -2，不低于 50
- ph 类（ProductHunt/GitHub）：70 起，每位 -2，不低于 54
- search 类（站点检索）：64 起，每位 -3，不低于 48
- aihot：采用上游分，无则 50

热榜分（读取时实时计算，原始分不动）：
    hot_score = score × 0.5^(age_hours / 48)
age 按 published_at 计算；缺失则按入库时间（fetched_at）。
48 小时半衰：两天前的条目热度减半，旧"钉子户"自然下沉。
"""
from __future__ import annotations

from datetime import datetime, timezone

# 类别 -> (起始分, 步长, 下限)
SCORE_RULES: dict[str, tuple[float, float, float]] = {
    "rss": (66, 2, 48),
    "hf": (72, 2, 50),
    "ph": (70, 2, 54),
    "search": (64, 3, 48),
}

AIHOT_DEFAULT_SCORE = 50.0
HALF_LIFE_HOURS = 48.0


def static_score(score_class: str, position: int, upstream_score: float | None = None) -> float:
    """按源内位置（0 起）算静态分。"""
    if score_class == "aihot":
        return float(upstream_score) if upstream_score else AIHOT_DEFAULT_SCORE
    start, step, floor = SCORE_RULES.get(score_class, SCORE_RULES["rss"])
    return max(floor, start - step * position)


def hot_score(score: float, published_at: datetime | None, fetched_at: datetime) -> float:
    """时间衰减热度分：hot_score = score × 0.5^(age_hours/48)。"""
    base = published_at or fetched_at
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_hours = max(0.0, (now - base).total_seconds() / 3600.0)
    return score * (0.5 ** (age_hours / HALF_LIFE_HOURS))
