"""URL 抓取安全门：摘要正文抓取 / 自定义源添加前的地址校验（防 SSRF）。

判定顺序（先廉价后昂贵，短路求值）：
1. 格式门：scheme 仅 http/https；hostname 非空；拒绝反斜杠/空白字符/userinfo
2. 字面量门：IP 字面量直接查阻断表（私网/环回/链路本地/保留/组播/嵌入式 IPv4 通道）
3. 解析门：localhost 快速拒绝；DNS 解析后所有地址必须全部为公网
4. 豁免：环境变量 ALLOW_PRIVATE_FETCH 真值时跳过 2/3 的地址类别判定（格式门永远生效）

设计要点：
- 阻断表显式列网段，不依赖 stdlib is_private 语义随 Python 版本漂移；
- 嵌入式 IPv4 通道（v4-mapped / NAT64 / v4-compatible）提取内层 IPv4 复跑 IPv4 表；
- 域名一律解析后按 IP 判定，天然覆盖 0177.0.0.1 之类数字混淆写法；
- 本模块只依赖标准库，且不在 import 时读环境变量（调用时读，便于测试与免重启生效）。
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

ENV_ALLOW_PRIVATE = "ALLOW_PRIVATE_FETCH"

# IPv4 阻断网段（本网络/私网/环回/链路本地/CGNAT/特殊用途/基准/文档/组播/保留）
_V4_BLOCKED = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8",        # "this network"
    "10.0.0.0/8",       # 私网 A
    "100.64.0.0/10",    # CGNAT 共享地址
    "127.0.0.0/8",      # 环回
    "169.254.0.0/16",   # 链路本地（含云元数据 169.254.169.254）
    "172.16.0.0/12",    # 私网 B
    "192.0.0.0/24",     # IETF 协议指派
    "192.0.2.0/24",     # TEST-NET-1
    "192.88.99.0/24",   # 6to4 中继（废弃）
    "192.168.0.0/16",   # 私网 C
    "198.18.0.0/15",    # 基准测试
    "198.51.100.0/24",  # TEST-NET-2
    "203.0.113.0/24",   # TEST-NET-3
    "224.0.0.0/4",      # 组播
    "240.0.0.0/4",      # 保留（含 255.255.255.255 广播）
))

# IPv6 阻断网段（不含嵌入式通道，通道单独处理）
_V6_BLOCKED = tuple(ipaddress.ip_network(n) for n in (
    "::/128",           # 未指定
    "::1/128",          # 环回
    "fe80::/10",        # 链路本地
    "fc00::/7",         # ULA 私网
    "ff00::/8",         # 组播
    "2001:db8::/32",    # 文档
    "2001::/32",        # Teredo
))

# 嵌入式 IPv4 通道：命中后提取低 32 位作为 IPv4 复跑 IPv4 表
_V4_EMBEDDED = tuple(ipaddress.ip_network(n) for n in (
    "::ffff:0:0/96",    # IPv4-mapped
    "64:ff9b::/96",     # NAT64 well-known prefix
    "::/96",            # IPv4-compatible（已废弃，仍按内层判定）
))


def _exempt_private() -> bool:
    return os.environ.get(ENV_ALLOW_PRIVATE, "").strip().lower() in ("1", "true", "yes", "on")


def _ip_blocked(addr: ipaddress._BaseAddress) -> bool:
    """地址是否落在阻断表内（IPv6 通道段先提取内层 IPv4 复跑 IPv4 表）。"""
    if isinstance(addr, ipaddress.IPv4Address):
        return any(addr in net for net in _V4_BLOCKED)
    for chan in _V4_EMBEDDED:
        if addr in chan:
            inner = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
            return _ip_blocked(inner)
    return any(addr in net for net in _V6_BLOCKED)


def _parse_literal(host: str) -> ipaddress._BaseAddress | None:
    """host 是否是 IP 字面量（容忍 IPv6 zone 后缀 fe80::1%eth0）。"""
    for candidate in (host, host.split("%", 1)[0]):
        try:
            return ipaddress.ip_address(candidate)
        except ValueError:
            continue
    return None


def check_url(url: str) -> tuple[bool, str]:
    """判定服务端是否允许抓取该 URL。返回 (允许, 原因)；原因用于日志与测试断言。"""
    url = (url or "").strip()
    if not url:
        return False, "URL 为空"
    if "\\" in url:
        return False, "URL 含反斜杠"
    if any(ch in url for ch in " \t\r\n"):
        return False, "URL 含空白字符"

    parts = urlparse(url)
    if parts.scheme.lower() not in ("http", "https"):
        return False, f"协议不支持: {parts.scheme or '(空)'}"
    host = (parts.hostname or "").lower()
    if not host:
        return False, "缺少主机名"
    if parts.username is not None or parts.password is not None:
        return False, "URL 携带 userinfo"

    if _exempt_private():
        return True, "豁免模式（ALLOW_PRIVATE_FETCH）"

    literal = _parse_literal(host)
    if literal is not None:
        if _ip_blocked(literal):
            return False, f"IP 字面量在阻断网段: {host}"
        return True, "公网 IP 字面量"

    if host == "localhost" or host.endswith(".localhost"):
        return False, "localhost 主机"

    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, OSError) as e:
        return False, f"域名解析失败: {host} ({e})"
    for info in infos:
        raw = info[4][0].split("%", 1)[0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            return False, f"解析返回非 IP 地址: {raw}"
        if _ip_blocked(addr):
            return False, f"域名解析到受限地址: {host} -> {raw}"
    return True, "公网域名"
