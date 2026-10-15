"""摘要链路：抓正文（trafilatura → readability-lxml → RSS 摘要兜底）→ 调用户自配模型 → 四段式中文摘要 → 按 URL 缓存。

单篇失败只记日志，调用方收到 None 后弹窗显示"摘要暂不可用"。
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urljoin, urlparse

import requests

from . import db
from .fetchers.base import FETCH_TIMEOUT, HEADERS
from .providers import chat_url
from .urlguard import check_url

logger = logging.getLogger("ai-news-oss")

MAX_CHARS = 6000  # 正文截断长度
MAX_REDIRECTS = 3  # 手动跟随重定向的跳数上限（逐跳过 urlguard）


class _BlockedURLError(Exception):
    """URL 被 urlguard 拒绝（内网/保留网段/非法格式）。按正文抓取失败处理。"""


def _loggable(url: str) -> str:
    """日志里只记 scheme+host，避免 query 串中的 token 落盘。"""
    p = urlparse(url)
    return f"{p.scheme}://{p.hostname}"


def _safe_get(url: str, depth: int = 0) -> requests.Response:
    """安全 GET：抓取前过 urlguard；重定向手动逐跳跟随，每一跳重新校验。

    requests 默认自动跟随重定向，公网 URL 302 到内网的绕过面由此封死。
    """
    if depth > MAX_REDIRECTS:
        raise _BlockedURLError(f"重定向超过 {MAX_REDIRECTS} 跳")
    ok, reason = check_url(url)
    if not ok:
        logger.warning("[urlguard] 拒绝抓取 %s: %s", _loggable(url), reason)
        raise _BlockedURLError(reason)
    resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT, allow_redirects=False)
    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("Location")
        resp.close()  # 释放中间跳的连接
        if not location:
            raise _BlockedURLError("重定向响应缺少 Location")
        return _safe_get(urljoin(url, location), depth + 1)
    return resp

SYSTEM_PROMPT = (
    "你是中文资讯解读助手。请用简体中文输出严格的 JSON（只输出 JSON，不要其他文字），"
    "包含以下四个字段：\n"
    '{"core": "一句话核心（30字以内）", '
    '"plain": "说人话：这是什么、跟我有什么关系、要不要管（80-150字）", '
    '"details": "关键细节（2-4条，每条一句话）", '
    '"link": "原文链接（原样返回用户给的URL）"}'
)


def _extract_with_trafilatura(html: str, url: str) -> str | None:
    try:
        import trafilatura

        text = trafilatura.extract(html, include_comments=False, include_tables=False)
        return text.strip() if text and text.strip() else None
    except Exception as e:  # noqa: BLE001
        logger.debug("trafilatura 提取失败 %s: %s", url, e)
        return None


def _extract_with_readability(html: str, url: str) -> str | None:
    try:
        from readability import Document
        from lxml import html as lxml_html

        doc = Document(html)
        tree = lxml_html.fromstring(doc.summary())
        text = tree.text_content().strip()
        return text if text else None
    except Exception as e:  # noqa: BLE001
        logger.debug("readability 提取失败 %s: %s", url, e)
        return None


def fetch_article_text(url: str, rss_summary: str = "") -> str | None:
    """抓正文：trafilatura → readability → RSS 摘要兜底。返回截断后的文本或 None。"""
    try:
        resp = _safe_get(url)
        resp.raise_for_status()
        html = resp.text
    except _BlockedURLError as e:
        logger.warning("正文抓取被安全策略拒绝 %s: %s", _loggable(url), e)
        html = ""
    except Exception as e:  # noqa: BLE001
        logger.warning("正文抓取失败 %s: %s", url, e)
        html = ""

    text = None
    if html:
        text = _extract_with_trafilatura(html, url) or _extract_with_readability(html, url)
    if not text and rss_summary:
        text = rss_summary.strip() or None
    if not text:
        return None
    # 压缩空白并截断
    text = " ".join(text.split())
    return text[:MAX_CHARS]


def _call_llm(provider: dict, title: str, article_text: str, url: str) -> dict | None:
    """调 OpenAI-compatible /chat/completions，返回四段式 dict 或 None。"""
    user_prompt = f"标题：{title}\n原文链接：{url}\n正文：\n{article_text}"
    try:
        resp = requests.post(
            chat_url(provider["id"], provider["base_url"]),
            headers={
                "Authorization": f"Bearer {provider['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": provider.get("model") or "default",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1200,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("模型调用失败 [%s]: %s", provider["id"], e)
        return None
    # 解析 JSON（模型偶尔会在前后加 markdown 围栏，做一次清洗）
    try:
        if content.startswith("```"):
            content = content.strip("`").strip()
            if content.lower().startswith("json"):
                content = content[4:].strip()
        parsed = json.loads(content)
        return {
            "core": str(parsed.get("core", ""))[:200],
            "plain": str(parsed.get("plain", ""))[:800],
            "details": str(parsed.get("details", ""))[:1200],
            "link": url,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("摘要 JSON 解析失败: %s", e)
        return None


def summarize(url: str, title: str = "", rss_summary: str = "", regenerate: bool = False) -> dict | None:
    """主入口：先查缓存（regenerate=True 则跳过缓存），没有则走全链路并缓存。

    返回 {"core","plain","details","link","_cached",...} 或 None（失败）。
    """
    from .providers import get_default

    if not regenerate:
        cached = db.get_summary(url)
        if cached:
            return cached
    provider = get_default()
    if not provider:
        logger.warning("摘要请求被跳过：未配置默认解读引擎（先去设置页配置）")
        return None
    text = fetch_article_text(url, rss_summary)
    if not text:
        logger.warning("摘要请求被跳过：正文抓取失败 %s", url)
        return None
    result = _call_llm(provider, title or url, text, url)
    if not result:
        return None
    db.save_summary(url, result, provider["id"], provider.get("model"))
    result["_cached"] = False
    return result
