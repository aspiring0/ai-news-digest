"""中文标题/描述：抓取后批量翻译英文条目（走默认引擎，每 4h 约 2-3 次调用）。

流程：run_once 入库完成后 → 找出 title_cn 为空且标题含英文的条目 →
按 20 条一批调 LLM 翻译 → 写入 title_cn / description_cn 列。
失败只记日志，不影响抓取；未翻译的条目下一轮自动重试。
"""
from __future__ import annotations

import json
import logging
import re

import requests

from . import db
from .providers import chat_url, get_default

logger = logging.getLogger("ai-news-oss")

BATCH_SIZE = 20

TRANSLATE_PROMPT = (
    "你是标题翻译器。把下面编号的英文（或其他非中文）新闻标题翻译成中文。\n"
    "输出严格 JSON 数组，每项：{\"n\": 编号, \"t\": \"中文短标题（≤30字）\", \"d\": \"一句话中文描述（≤50字）\"}\n"
    "要求：\n"
    "- 标题保留专有名词原文（如 GPT-5、Claude、Meta 不翻）\n"
    "- 描述说清楚这是什么产品/公司/事件\n"
    "- 只输出 JSON，不要其他文字"
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _needs_translation(title: str) -> bool:
    """标题含拉丁字母且不含 CJK 字符 → 需要翻译。"""
    if not title:
        return False
    if _CJK_RE.search(title):
        return False
    return bool(re.search(r"[A-Za-z]{3,}", title))


def _call_llm_translate(titles: list[str]) -> dict[str, tuple[str, str]]:
    """调 LLM 批量翻译。返回 {原标题: (中文标题, 中文描述)}。"""
    provider = get_default()
    if not provider:
        return {}

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    try:
        resp = requests.post(
            chat_url(provider["id"], provider["base_url"]),
            headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
            json={
                "model": provider.get("model") or "default",
                "messages": [
                    {"role": "system", "content": TRANSLATE_PROMPT},
                    {"role": "user", "content": numbered},
                ],
                "temperature": 0.1,
                "max_tokens": 2000,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("批量翻译模型调用失败: %s", e)
        raise

    if content.startswith("```"):
        content = content.strip("`").strip()
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        parsed = json.loads(content)
    except ValueError:
        logger.warning("批量翻译返回无法解析: %s", content[:100])
        return {}

    result: dict[str, tuple[str, str]] = {}
    for item in parsed:
        n = int(item.get("n", 0)) - 1
        if 0 <= n < len(titles):
            result[titles[n]] = (str(item.get("t", ""))[:60], str(item.get("d", ""))[:100])
    return result


def translate_untranslated(limit: int = 60) -> int:
    """找出未翻译的英文条目，批量翻译写入。返回翻译条数。

    回写按 url 精确定位（P3）：同标题不同 URL 的多行存在时，按标题
    UPDATE 会误伤所有同标题行；这里用 title→url 映射回写映射到的那行，
    其余行保持空、下一轮重试。LLM 协议不变（仍按 title 对键）。
    """
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT url, title FROM news_items"
            " WHERE (title_cn IS NULL OR title_cn = '')"
            " ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()

    title_url = {r["title"]: r["url"] for r in rows}
    pending = [t for t in title_url if _needs_translation(t)]
    if not pending:
        return 0

    translated = 0
    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i:i + BATCH_SIZE]
        try:
            results = _call_llm_translate(batch)
        except Exception:
            break  # 本轮放弃，下轮重试
        if not results:
            break
        with db._connect() as conn:
            for title, (t_cn, d_cn) in results.items():
                url = title_url.get(title)
                if not t_cn or not url:
                    continue  # 映射缺失则跳过（防御：LLM 返回的键不在待译集）
                conn.execute(
                    "UPDATE news_items SET title_cn = ?, description_cn = ?"
                    " WHERE url = ? AND (title_cn IS NULL OR title_cn = '')",
                    (t_cn, d_cn or None, url),
                )
                translated += 1
    if translated:
        logger.info("批量翻译：%d 条英文标题已配中文", translated)
    return translated
