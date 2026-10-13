"""providers 单元/安全测试：白名单、id 校验（XSS）、各家 chat 端点。"""
from __future__ import annotations

import html
import re

import pytest

from app import providers


# ---------------- 回归：既有安全规则 ----------------

def test_builtin_whitelist_blocks_foreign_host(clean_db):
    with pytest.raises(ValueError, match="官方域名"):
        providers.save_provider("deepseek", "https://evil.example.com", "sk-x")


def test_unknown_builtin_id_rejected(clean_db):
    with pytest.raises(ValueError, match="未知 provider"):
        providers.check_base_url("not-a-provider", "https://api.deepseek.com")


def test_custom_provider_allows_any_host(clean_db):
    providers.save_provider("custom-mine", "https://my-proxy.example.com", "k")
    saved = providers.get_provider("custom-mine")
    assert saved["base_url"] == "https://my-proxy.example.com"


def test_api_save_requires_key(client):
    r = client.post("/api/providers", json={"id": "deepseek", "base_url": "https://api.deepseek.com", "api_key": ""})
    assert r.status_code == 400


# ---------------- TDD：XSS 修复（保存端 id/name 校验） ----------------

def test_save_rejects_quote_in_custom_id(clean_db):
    """自定义 id 带引号/括号（审查报告中的注入 payload）必须被后端拒绝。"""
    with pytest.raises(ValueError, match="id"):
        providers.save_provider("custom-x');alert(document.domain);//", "http://h.example.com", "k")


def test_api_save_rejects_malicious_custom_id(client):
    r = client.post(
        "/api/providers",
        json={
            "id": "custom-x');alert(1);//",
            "base_url": "http://h.example.com",
            "api_key": "k",
            "builtin": False,
            "name": "innocuous",
        },
    )
    assert r.status_code == 400


def test_settings_page_no_js_string_breakout(client):
    """含引号的 name 可保存，但 /settings 渲染的 onclick 经浏览器实体解码后不得出现裸单引号。"""
    r = client.post(
        "/api/providers",
        json={
            "id": "custom-safe1",
            "base_url": "http://h.example.com",
            "api_key": "k",
            "builtin": False,
            "name": "t');alert(1);//",
        },
    )
    assert r.status_code == 200
    page = client.get("/settings").text
    # 兼容单/双引号两种属性写法，找到该 provider 卡片的 onclick
    attrs = re.findall(r'onclick=(["\'])(.*?)\1', page)
    targets = [a for _, a in attrs if "custom-safe1" in a]
    assert targets, "应能找到该 provider 卡片的 onclick 属性"
    decoded = html.unescape(targets[0])
    # 安全属性：解码后（即浏览器交给 JS 引擎的内容）不含裸单引号 → 无法逃逸 JS 字符串
    assert "'" not in decoded, f"onclick 存在字符串逃逸面: {decoded}"
    assert "custom-safe1" in decoded


# ---------------- TDD：Gemini 兼容路径 + Anthropic 移除 ----------------

def test_anthropic_no_longer_builtin():
    assert "anthropic" not in providers.BUILTIN_PROVIDERS
    with pytest.raises(ValueError):
        providers.check_base_url("anthropic", "https://api.anthropic.com")


def test_chat_url_gemini_bare_domain_gets_compat_prefix():
    u = providers.chat_url("gemini", "https://generativelanguage.googleapis.com")
    assert u == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def test_chat_url_gemini_explicit_prefix_not_duplicated():
    u = providers.chat_url("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/")
    assert u == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def test_chat_url_openai_style_providers_unchanged():
    assert providers.chat_url("deepseek", "https://api.deepseek.com") == "https://api.deepseek.com/chat/completions"
    assert providers.chat_url("custom-1", "https://p.example.com/v1") == "https://p.example.com/v1/chat/completions"


def test_settings_page_lists_six_builtins(client):
    page = client.get("/settings").text
    assert "api.anthropic.com" not in page, "Anthropic 已从内置列表移除，不应再出现在设置页"
    for host in ("api.deepseek.com", "open.bigmodel.cn", "generativelanguage.googleapis.com"):
        assert host in page
