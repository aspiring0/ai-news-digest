"""模型 provider 管理：内置官方域名白名单 + 自定义 provider。

安全规则（防 key 外发）：
1. 内置 provider 的 base_url 只能是官方域名（白名单校验）；
2. 只有"自定义" provider 允许填任意域名；
3. 修改已保存 provider 的 base_url 时，必须重新输入 key（前端+后端双校验）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from . import db

logger = logging.getLogger("ai-news-oss")

# 内置 provider：官方域名白名单（精确匹配 host）
BUILTIN_PROVIDERS = {
    "deepseek": {"name": "DeepSeek", "hosts": ["api.deepseek.com"], "default_model": "deepseek-chat"},
    "glm": {"name": "智谱 GLM", "hosts": ["open.bigmodel.cn"], "default_model": "glm-4-flash"},
    "qwen": {"name": "通义 Qwen", "hosts": ["dashscope.aliyuncs.com"], "default_model": "qwen-flash"},
    "kimi": {"name": "Kimi", "hosts": ["api.moonshot.cn"], "default_model": "kimi-k2"},
    "openai": {"name": "OpenAI", "hosts": ["api.openai.com"], "default_model": "gpt-4o-mini"},
    "anthropic": {"name": "Anthropic", "hosts": ["api.anthropic.com"], "default_model": "claude-haiku-4-5"},
    "gemini": {"name": "Gemini", "hosts": ["generativelanguage.googleapis.com"], "default_model": "gemini-2.0-flash"},
}

# 各家 chat 接口路径（都是 OpenAI-compatible 的 /chat/completions；Anthropic/Gemini 官方接口格式不同，
# 建议用它们兼容 OpenAI 格式的中转地址，或走"自定义" provider 填兼容端点）
CHAT_PATH = "/chat/completions"


def _host_of(base_url: str) -> str:
    return (urlparse(base_url).hostname or "").lower()


def _is_custom(provider_id: str) -> bool:
    """自定义 provider：id 为 custom 或 custom- 开头。"""
    return provider_id == "custom" or provider_id.startswith("custom-")


def check_base_url(provider_id: str, base_url: str) -> None:
    """校验 base_url 合法性。不合法抛 ValueError。"""
    host = _host_of(base_url)
    if not host:
        raise ValueError("base_url 不是合法的 URL")
    if _is_custom(provider_id):
        return  # 自定义 provider 允许任意域名
    meta = BUILTIN_PROVIDERS.get(provider_id)
    if meta is None:
        raise ValueError(f"未知 provider: {provider_id}")
    if host not in meta["hosts"]:
        raise ValueError(
            f"{meta['name']} 只允许官方域名（{', '.join(meta['hosts'])}），"
            "其他域名请用「自定义」provider"
        )


def chat_url(provider_id: str, base_url: str) -> str:
    """拼出 chat 接口完整 URL。"""
    return base_url.rstrip("/") + CHAT_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_provider(
    provider_id: str,
    base_url: str,
    api_key: str,
    model: str | None = None,
    builtin: bool = True,
    name: str | None = None,
) -> None:
    """新增或更新 provider。base_url 变更时调用方必须已确认 key 被重新输入。"""
    check_base_url(provider_id, base_url)
    if not api_key:
        raise ValueError("api_key 不能为空")
    meta = BUILTIN_PROVIDERS.get(provider_id, {})
    with db._connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO provider_settings (id, name, builtin, base_url, api_key, model, is_default, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT is_default FROM provider_settings WHERE id = ?), 0), ?)",
            (
                provider_id,
                name or meta.get("name", provider_id),
                1 if builtin else 0,
                base_url.rstrip("/"),
                api_key,
                model or meta.get("default_model"),
                provider_id,
                _now_iso(),
            ),
        )


def get_provider(provider_id: str) -> dict | None:
    with db._connect() as conn:
        row = conn.execute("SELECT * FROM provider_settings WHERE id = ?", (provider_id,)).fetchone()
    return dict(row) if row else None


def list_providers() -> list[dict]:
    """全部 provider（key 打码返回，前 4 位 + ****）。"""
    with db._connect() as conn:
        rows = conn.execute("SELECT * FROM provider_settings ORDER BY is_default DESC, id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        key = d.get("api_key") or ""
        d["api_key_masked"] = (key[:4] + "****") if len(key) > 4 else "****"
        del d["api_key"]
        out.append(d)
    return out


def delete_provider(provider_id: str) -> None:
    with db._connect() as conn:
        conn.execute("DELETE FROM provider_settings WHERE id = ?", (provider_id,))


def set_default(provider_id: str) -> None:
    with db._connect() as conn:
        conn.execute("UPDATE provider_settings SET is_default = 0")
        cur = conn.execute("UPDATE provider_settings SET is_default = 1 WHERE id = ?", (provider_id,))
        if cur.rowcount == 0:
            raise KeyError("provider 不存在")


def get_default() -> dict | None:
    with db._connect() as conn:
        row = conn.execute("SELECT * FROM provider_settings WHERE is_default = 1").fetchone()
    return dict(row) if row else None


def test_connection(base_url: str, api_key: str, model: str | None, provider_id: str = "custom") -> dict:
    """一键测试连接：调 /chat/completions 发一条最小请求。返回 {ok, message}。"""
    try:
        check_base_url(provider_id, base_url)
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    try:
        resp = requests.post(
            chat_url(provider_id, base_url),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model or "test",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 8,
            },
            timeout=20,
        )
        if resp.status_code == 200:
            return {"ok": True, "message": "连接成功"}
        # 401/403 多半是 key 无效；400 可能是模型名不对，但都说明"通了"
        if resp.status_code in (400, 401, 403, 404):
            return {"ok": False, "message": f"接口可达，但返回 {resp.status_code}（检查 key / 模型名）"}
        return {"ok": False, "message": f"返回 {resp.status_code}: {resp.text[:120]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"连接失败: {e}"}
