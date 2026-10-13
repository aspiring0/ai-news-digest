"""故事合并：同一事件多源归一（标题实体重叠 + 时间窗聚类）。

跨语言匹配原理：AI 新闻的产品/公司/人名几乎都是拉丁词，中文标题里也保留原文
（"Meta 发布 Muse Wonder"），所以只提取拉丁实体即可跨中英匹配。
纯中文实体（如"固态电池"）v1 暂不支持合并（如实记录于 README）。

规则：
- 实体 = 标题中 ≥3 字符的拉丁词（去停用词/纯版本号），全小写化
- 两条并入同一故事的条件：与故事实体集重叠 ≥2 个，且时间差 ≤ 48h
  （newsletter 类源有隔夜延迟，窗口放宽到 48h）
- 故事热度 = 成员最高 hot_score × (1 + 15% × 额外来源数)，加成上限 +100%
- 展示代表 = 故事内 hot_score 最高的成员
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

# 泛词/动词/媒体套话：出现频率高、无区分度，全部不计为实体
_STOP = frozenset("""
the a an of in on at to for with and or but its is are was were be been
new first second third says said say how why what when where who
more most less least than can could would should will shall may might must
from by as not no nor so if then else about across amid after before
over under up down out into onto via per vs and you your we our us it this that
these those there here all any some each every other another
one two three four five six seven eight nine ten
day days week weeks month months year years today yesterday tomorrow now
news report reports reported update updates latest breaking exclusive
launch launchs launched launches release released releases
announce announced announces ship shipped ships introduce introduced introduces
make makes made get gets got use used uses using build builds built
top best big huge major giant giant key main core
model models app apps tool tools agent agents assistant
ai artificial intelligence open source data cloud tech technology
analysis question story piece post article video podcast
raise raises raised funding round valuation billion million
team group plan plans set sets run runs running go goes going
here how-to guide tips tricks review look deep dive inside
leader ceo founder president chief official
""".split())

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]*")
_VERSION = re.compile(r"^v?\d+([._-]\d+)*[a-z]?$")


def extract_entities(title: str) -> set[str]:
    """从标题提取实体词（小写拉丁词，≥3 字符，去停用词与纯版本号）。"""
    out: set[str] = set()
    for raw in _TOKEN.findall(title or ""):
        t = raw.strip("._-").lower()
        if len(t) < 3 or t in _STOP:
            continue
        if _VERSION.match(t):
            continue
        out.add(t)
    return out


def _time_of(it: dict) -> datetime:
    t = it.get("published_at") or it.get("fetched_at")
    if t is None:
        return datetime.now(timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def _hot_of(it: dict) -> float:
    return float(it.get("hot_score", it.get("score", 0.0)))


def _has_cjk(title: str) -> bool:
    """标题是否含 CJK 字符（用于代表条目优先中文，用户看得懂）。"""
    return any("\u4e00" <= ch <= "\u9fff" for ch in (title or ""))


def group_stories(items: list[dict], window_hours: float = 48.0) -> list[dict]:
    """把条目聚成故事。返回 [{entities, sources, members, representative, last_time}]。"""
    stories: list[dict] = []
    for it in sorted(items, key=_time_of):
        ents = extract_entities(it.get("title", ""))
        best: dict | None = None
        best_overlap = 1  # 阈值：≥2 个共享实体才合并
        for st in stories:
            dt_hours = abs((_time_of(it) - st["last_time"]).total_seconds()) / 3600.0
            if dt_hours > window_hours:
                continue
            overlap = len(ents & st["entities"])
            if overlap >= 2 and overlap > best_overlap:
                best = st
                best_overlap = overlap
        if best is None:
            stories.append({
                "entities": set(ents),
                "last_time": _time_of(it),
                "members": [it],
                "sources": [it["source_name"]],
            })
        else:
            best["members"].append(it)
            best["entities"] |= ents
            best["last_time"] = max(best["last_time"], _time_of(it))
            if it["source_name"] not in best["sources"]:
                best["sources"].append(it["source_name"])
    for st in stories:
        st["members"].sort(key=_hot_of, reverse=True)
        # 代表条目：优先中文标题（用户可读），中文内仍取最高分；全英文回到最高分
        cn_members = [m for m in st["members"] if _has_cjk(m.get("title", ""))]
        st["representative"] = (cn_members or st["members"])[0]
        # 来源顺序跟随成员热度（代表来源排第一，供前端展示）
        ordered: list[str] = []
        for m in st["members"]:
            if m["source_name"] not in ordered:
                ordered.append(m["source_name"])
        st["sources"] = ordered
    return stories


def story_score(story: dict) -> float:
    """故事热度：成员最高 hot_score × (1 + 15%/额外来源)，加成上限 +100%。"""
    top = max(_hot_of(m) for m in story["members"])
    bonus = min(0.15 * (len(story["sources"]) - 1), 1.0)
    return top * (1.0 + bonus)
