"""兴趣画像（自我进化闭环）：行为日志 → LLM 蒸馏画像 → 热榜个性化。

画像存在本地 meta 表（key=interest_profile），随时可看/可改/可重置——透明可控，
不做黑箱。应用规则：命中"喜欢"关键词的故事 +15%/词加成（上限 +60%），
命中"不感兴趣"的故事直接不出现（与屏蔽语义一致）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import requests

from . import db
from .providers import chat_url, get_default

logger = logging.getLogger("ai-news-oss")

PROFILE_KEY = "interest_profile"
MIN_INTERACTIONS = 6  # 蒸馏前至少要有这么多条行为
BOOST_PER_LIKE = 0.15
BOOST_CAP = 0.60

DISTILL_PROMPT = (
    "你是用户兴趣分析器。根据下面的用户行为日志（看了摘要/收藏/屏蔽了哪些新闻标题），"
    "输出严格的 JSON（只输出 JSON）：\n"
    '{"likes": ["感兴趣的主题关键词，3-10 个，中英文均可"], '
    '"dislikes": ["明确不感兴趣的主题关键词，0-8 个"], '
    '"notes": "一句话总结该用户的阅读偏好"}\n'
    "关键词要具体（如「具身智能」「模型评测」「Claude」），不要泛词（如「AI」「科技」）。"
)


def load_profile() -> dict | None:
    raw = db.get_meta(PROFILE_KEY)
    if not raw:
        return None
    try:
        p = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(p, dict):
        return None
    p.setdefault("likes", [])
    p.setdefault("dislikes", [])
    p.setdefault("notes", "")
    return p


def save_profile(profile: dict) -> dict:
    likes = profile.get("likes")
    dislikes = profile.get("dislikes")
    if not isinstance(likes, list) or not isinstance(dislikes, list):
        raise ValueError("likes / dislikes 必须是字符串列表")
    clean = {
        "likes": [str(x)[:40] for x in likes if str(x).strip()][:15],
        "dislikes": [str(x)[:40] for x in dislikes if str(x).strip()][:15],
        "notes": str(profile.get("notes", ""))[:200],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    db.set_meta(PROFILE_KEY, json.dumps(clean, ensure_ascii=False))
    return clean


def clear_profile() -> None:
    db.set_meta(PROFILE_KEY, "")


def distill() -> dict:
    """把行为日志蒸溜成画像（调默认引擎，一次几分钱级）。返回 {ok} 或 {ok, message}。"""
    rows = db.recent_interactions(500)
    if len(rows) < MIN_INTERACTIONS:
        return {"ok": False, "message": f"行为数据不足（至少 {MIN_INTERACTIONS} 条，先多点几篇摘要/收藏/屏蔽）"}
    provider = get_default()
    if not provider:
        return {"ok": False, "message": "未配置默认解读引擎（先在模型平台设置）"}

    lines = []
    for r in rows[:200]:
        act = {"summary": "看了摘要", "bookmark": "收藏", "block": "屏蔽"}.get(r["action"], r["action"])
        title = (r.get("title") or r.get("url") or "")[:60]
        lines.append(f"- [{act}] {title}")
    user_prompt = "用户行为日志（新到旧）：\n" + "\n".join(lines)

    try:
        resp = requests.post(
            chat_url(provider["id"], provider["base_url"]),
            headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
            json={
                "model": provider.get("model") or "default",
                "messages": [
                    {"role": "system", "content": DISTILL_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 600,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("画像蒸馏模型调用失败: %s", e)
        return {"ok": False, "message": f"模型调用失败: {e}"}

    if content.startswith("```"):
        content = content.strip("`").strip()
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        parsed = json.loads(content)
    except ValueError:
        return {"ok": False, "message": "模型返回的画像无法解析，请重试"}

    saved = save_profile(parsed)
    db.log_interaction("distill", "", f"画像更新 likes={saved['likes'][:3]}", "")
    return {"ok": True, "profile": saved}


def _hit_count(title: str, keywords: list[str]) -> int:
    t = (title or "").lower()
    return sum(1 for k in keywords if k and k.lower() in t)


def apply_profile_to_stories(stories: list[dict], profile: dict | None) -> list[dict]:
    """按画像调整故事列表：过滤不感兴趣、给命中的加成，然后重排（原序为热度序）。"""
    if not profile:
        return stories
    dislikes = [k for k in profile.get("dislikes", []) if k]
    likes = [k for k in profile.get("likes", []) if k]
    if not dislikes and not likes:
        return stories
    out = []
    for st in stories:
        title = st["representative"].get("title", "")
        if dislikes and _hit_count(title, dislikes) > 0:
            continue  # 不感兴趣：直接不出现
        n = _hit_count(title, likes)
        if n:
            st = dict(st)
            st["_score"] = st["_score"] * (1.0 + min(BOOST_PER_LIKE * n, BOOST_CAP))
        out.append(st)
    out.sort(key=lambda s: s["_score"], reverse=True)
    return out
