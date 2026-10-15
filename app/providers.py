"""模型 provider 管理：内置官方域名白名单 + 自定义 provider。

安全规则（防 key 外发 / 防注入）：
1. 内置 provider 的 base_url 只能是官方域名（白名单校验）；
2. 只有"自定义" provider 允许填任意域名；
3. 修改已保存 provider 的 base_url 时，必须重新输入 key（前端+后端双校验）；
4. provider id 一律 `^[A-Za-z0-9_-]{1,64}$`（设置页模板把它拼进内联 JS，必须限字符集）；
   Anthropic 官方无 OpenAI 兼容端点，不内置，请走"自定义"填中转地址。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from . import db

logger = logging.getLogger("ai-news-oss")

# provider id 字符集（字母/数字/横线/下划线，≤64 位）
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# 内置 provider：官方域名白名单（精确匹配 host）
BUILTIN_PROVIDERS = {
    "deepseek": {"name": "DeepSeek", "hosts": ["api.deepseek.com"], "default_model": "deepseek-chat"},
    "glm": {"name": "智谱 GLM", "hosts": ["open.bigmodel.cn"], "default_model": "glm-4-flash"},
    "qwen": {"name": "通义 Qwen", "hosts": ["dashscope.aliyuncs.com"], "default_model": "qwen-flash"},
    "kimi": {"name": "Kimi", "hosts": ["api.moonshot.cn"], "default_model": "kimi-k2"},
    "openai": {"name": "OpenAI", "hosts": ["api.openai.com"], "default_model": "gpt-4o-mini"},
    # Gemini 的 OpenAI 兼容端点在 /v1beta/openai/ 下，裸域名 base_url 自动补该前缀
    "gemini": {
        "name": "Gemini",
        "hosts": ["generativelanguage.googleapis.com"],
        "default_model": "gemini-2.0-flash",
        "chat_prefix": "/v1beta/openai",
    },
}

# 各家 chat 接口路径（OpenAI-compatible 的 /chat/completions）
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
    """拼出 chat 接口完整 URL。

    内置 provider 可声明 chat_prefix（目前仅 Gemini 需要）：base_url 为裸域名
    （无路径，即旧配置或默认填法）时自动补全前缀，显式填了前缀则不会重复拼接。
    """
    meta = BUILTIN_PROVIDERS.get(provider_id, {})
    base = base_url.rstrip("/")
    prefix = meta.get("chat_prefix", "")
    if prefix and urlparse(base).path == "":
        base += prefix
    return base + CHAT_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_provider(
    provider_id: str,
    base_url: str,
    api_key: str = "",
    model: str | None = None,
    builtin: bool = True,
    name: str | None = None,
) -> None:
    """新增或更新 provider。

    Key 规则：留空 = 沿用已保存的 key（只改模型名等）；但新增 provider 必须给 key，
    且修改接口地址（base_url 变化）时必须重输 key（防已存 key 被发往新域名）。
    """
    provider_id = (provider_id or "").strip()
    if not _PROVIDER_ID_RE.fullmatch(provider_id):
        raise ValueError("id 只能包含英文字母/数字/横线/下划线，长度 1-64")
    check_base_url(provider_id, base_url)
    with db._connect() as conn:
        old = conn.execute(
            "SELECT api_key, base_url FROM provider_settings WHERE id = ?", (provider_id,)
        ).fetchone()
        if not api_key:
            if old is None:
                raise ValueError("新增 provider 必须输入 key")
            if old["base_url"] != base_url.rstrip("/"):
                raise ValueError("修改接口地址必须重新输入 key")
            api_key = old["api_key"]
    if not api_key:
        raise ValueError("api_key 不能为空")
    meta = BUILTIN_PROVIDERS.get(provider_id, {})
    name = (name or "").strip()[:64] or None
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


def list_models(base_url: str, api_key: str = "", provider_id: str = "custom") -> dict:
    """一键获取模型列表：后端代理请求 {base_url}/models（浏览器直连第三方会跨域）。

    key 优先用入参；留空时仅在「接口地址与已保存的完全一致」才回退到存量
    key——与 save_provider 的"改址必须重输 key"规则对齐，防止无鉴权下
    他人借 custom provider 把已保存 key 外发到任意域名（审计 P1-1）。
    返回 {ok, models} 或 {ok, message}。
    """
    try:
        check_base_url(provider_id, base_url)
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    key = api_key or ""
    if not key:
        saved = get_provider(provider_id)
        if saved and saved["base_url"] == base_url.rstrip("/"):
            key = saved["api_key"]  # 同址：安全回退
    if not key:
        return {"ok": False, "message": "请先填写 key（接口地址与已保存的不一致时必须重输）"}
    try:
        resp = requests.get(
            base_url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=20,
        )
        if resp.status_code != 200:
            return {"ok": False, "message": f"接口返回 {resp.status_code}（检查 key 是否有效）"}
        data = resp.json()
        ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        return {"ok": True, "models": ids[:100]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"获取失败: {e}"}


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
