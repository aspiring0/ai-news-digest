"""urlguard 单测：A 系列判定表全分支覆盖（零网络，DNS 全 mock）。"""
from __future__ import annotations

import ipaddress
import socket

import pytest

from app import urlguard


def _dns(monkeypatch, ips):
    """把 socket.getaddrinfo mock 成返回给定 IP 列表。"""
    def fake(host, port=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]
    monkeypatch.setattr(socket, "getaddrinfo", fake)


# ---------- A1 公网放行 ----------

def test_public_ip_literal_allowed():
    ok, _ = urlguard.check_url("http://93.184.216.34/x")
    assert ok is True
    ok, _ = urlguard.check_url("https://8.8.8.8:8080/x")
    assert ok is True


def test_public_domain_allowed(monkeypatch):
    _dns(monkeypatch, ["93.184.216.34"])
    ok, _ = urlguard.check_url("https://example.com/a?b=1")
    assert ok is True


def test_trailing_dot_and_idn_pass_dns(monkeypatch):
    seen = []
    def fake(host, port=None):
        seen.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert urlguard.check_url("http://example.com./x")[0] is True
    assert urlguard.check_url("http://例え.jp/")[0] is True


# ---------- A2 协议/格式门 ----------

@pytest.mark.parametrize("url", [
    "ftp://example.com/f",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "data:text/html,<script>",
    "example.com/no-scheme",
    "",
    "http://",            # 无主机
])
def test_bad_scheme_or_shape_rejected(url):
    assert urlguard.check_url(url)[0] is False


# ---------- A3 IPv4 阻断网段 ----------

@pytest.mark.parametrize("ip", [
    "0.0.0.1", "10.1.2.3", "100.64.0.1", "100.127.255.254",
    "127.0.0.1", "127.8.8.8", "169.254.169.254", "172.16.0.1", "172.31.9.9",
    "192.0.0.9", "192.0.2.1", "192.88.99.1", "192.168.0.5",
    "198.18.0.1", "198.19.5.5", "198.51.100.7", "203.0.113.9",
    "224.0.0.9", "239.1.1.1", "240.0.0.1", "255.255.255.255",
])
def test_ipv4_blocked_literals(ip):
    ok, reason = urlguard.check_url(f"http://{ip}/x")
    assert ok is False, reason


# ---------- A4 IPv6 阻断网段 ----------

@pytest.mark.parametrize("ip", [
    "::", "::1", "fe80::1", "fc00::5", "fd12:3456::1",
    "ff02::1", "2001:db8::1", "2001:0000::1",
])
def test_ipv6_blocked_literals(ip):
    ok, reason = urlguard.check_url(f"http://[{ip}]/x")
    assert ok is False, reason


def test_ipv6_zone_suffix_blocked():
    # zone 后缀（fe80::1%25eth0 经 urlparse 还原为 %eth0）
    ok, _ = urlguard.check_url("http://[fe80::1%25eth0]/x")
    assert ok is False


# ---------- A5 嵌入式 IPv4 通道 ----------

@pytest.mark.parametrize("ip,expect", [
    ("::ffff:127.0.0.1", False),
    ("::ffff:10.0.0.1", False),
    ("::ffff:169.254.169.254", False),
    ("64:ff9b::a00:1", False),        # NAT64(10.0.0.1)
    ("::ffff:8.8.8.8", True),         # 内层公网 → 按设计放行
    ("::8.8.8.8", True),              # v4-compatible 内层公网（废弃格式，按设计按内层判定）
])
def test_embedded_ipv4_channels(ip, expect):
    ok, _ = urlguard.check_url(f"http://[{ip}]/x")
    assert ok is expect


# ---------- A6 localhost ----------

def test_localhost_rejected(monkeypatch):
    called = {"n": 0}
    def fake(host, port=None):
        called["n"] += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert urlguard.check_url("http://localhost/x")[0] is False
    assert urlguard.check_url("http://LOCALHOST/x")[0] is False
    assert urlguard.check_url("http://api.localhost/x")[0] is False
    assert called["n"] == 0  # 走快速路径，未做 DNS


# ---------- A7 混合记录 ----------

def test_mixed_dns_records_rejected(monkeypatch):
    _dns(monkeypatch, ["8.8.8.8", "10.0.0.7"])
    ok, reason = urlguard.check_url("http://example.com/x")
    assert ok is False
    assert "10.0.0.7" in reason


def test_numeric_obfuscation_caught_by_resolution(monkeypatch):
    # 0177.0000.0000.0001 之类数字写法：解析结果按 IP 表判定
    _dns(monkeypatch, ["127.0.0.1"])
    assert urlguard.check_url("http://0177.0.0.1/x")[0] is False


# ---------- A8 反斜杠 / userinfo / 空白 ----------

def test_backslash_userinfo_whitespace_rejected(monkeypatch):
    _dns(monkeypatch, ["93.184.216.34"])
    assert urlguard.check_url("http://evil.com\\@127.0.0.1/")[0] is False
    assert urlguard.check_url("http://user:pass@example.com/")[0] is False
    assert urlguard.check_url("http://example.com /x")[0] is False
    assert urlguard.check_url("http://evil.com\n@127.0.0.1/")[0] is False


# ---------- A9 豁免开关 ----------

def test_exemption_allows_private_but_not_bad_scheme(monkeypatch):
    monkeypatch.setenv(urlguard.ENV_ALLOW_PRIVATE, "1")
    assert urlguard.check_url("http://127.0.0.1:8000/api/health")[0] is True
    assert urlguard.check_url("http://10.0.0.5/x")[0] is True
    # 格式门在豁免下仍然生效
    assert urlguard.check_url("ftp://10.0.0.5/x")[0] is False
    assert urlguard.check_url("http://user:pass@10.0.0.5/")[0] is False


@pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
def test_exemption_falsy_values(monkeypatch, val):
    monkeypatch.setenv(urlguard.ENV_ALLOW_PRIVATE, val)
    assert urlguard.check_url("http://127.0.0.1/x")[0] is False


# ---------- A10 解析失败 ----------

def test_dns_failure_rejected(monkeypatch):
    def fake(host, port=None):
        raise socket.gaierror("no such host")
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    ok, reason = urlguard.check_url("http://nonexistent.invalid/x")
    assert ok is False
    assert "解析失败" in reason


# ---------- A12 豁免调用时读取 ----------

def test_exemption_read_at_call_time(monkeypatch):
    monkeypatch.delenv(urlguard.ENV_ALLOW_PRIVATE, raising=False)
    assert urlguard.check_url("http://127.0.0.1/x")[0] is False
    monkeypatch.setenv(urlguard.ENV_ALLOW_PRIVATE, "1")
    assert urlguard.check_url("http://127.0.0.1/x")[0] is True
