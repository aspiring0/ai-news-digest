"""半自动更新检查：查询 GitHub Releases 最新版并与本地版本比对。

设计（v0.4.6）：
- 只查不替：发现新版在页面顶部出横幅（下载 exe / 更新日志 / 本次忽略），
  不做自动下载自替换——那需要引导器+校验+回滚的完整设计，等 CI 通道恢复再议；
- 进程内缓存 1 小时：页面每刷都查会白白打 GitHub；
- 失败静默（离线/无 Release/限流）：返回 ok=False，前端不显示任何东西；
  源码方式部署的用户没有"版本"概念负担，横幅同样适用（更新日志可看）。
"""
from __future__ import annotations

import logging
import time

import requests

from . import __version__

logger = logging.getLogger("ai-news-oss")

REPO = "aspiring0/ai-news-digest"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
CACHE_TTL_SECONDS = 3600

_cache: dict = {"at": 0.0, "result": None}


def _version_tuple(v: str) -> tuple[int, ...]:
    """'v0.4.10' → (0, 4, 10)；非数字段按 0 处理，短版本补齐比较。"""
    parts = v.strip().lstrip("vV").split(".")
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def _pick_download_url(release: dict) -> str:
    """优先 Windows exe 资产，否则回 Release 页。"""
    assets = release.get("assets") or []
    exes = [a for a in assets if (a.get("name") or "").lower().endswith(".exe")]
    wins = [a for a in exes if "win" in (a.get("name") or "").lower()]
    for pool in (wins, exes):
        if pool:
            return pool[0].get("browser_download_url") or release.get("html_url", "")
    return release.get("html_url", "")


def check(force: bool = False) -> dict:
    """查询最新 Release 并与 __version__ 比对。任何失败都返回 ok=False（不抛）。"""
    now = time.time()
    if not force and _cache["result"] and now - _cache["at"] < CACHE_TTL_SECONDS:
        return _cache["result"]
    try:
        resp = requests.get(RELEASES_LATEST_URL, timeout=5,
                            headers={"Accept": "application/vnd.github+json"})
        if resp.status_code == 404:
            result = {"ok": False, "message": "尚无发布版本"}
        else:
            resp.raise_for_status()
            release = resp.json()
            latest = (release.get("tag_name") or "").lstrip("vV")
            has_update = bool(latest) and _version_tuple(latest) > _version_tuple(__version__)
            result = {
                "ok": True,
                "current": __version__,
                "latest": latest,
                "has_update": has_update,
                "download_url": _pick_download_url(release),
                "release_url": release.get("html_url", ""),
                "notes": (release.get("body") or "")[:300],
            }
    except Exception as e:  # noqa: BLE001 - 离线/限流/改版都静默
        logger.debug("更新检查失败（忽略）: %s", e)
        result = {"ok": False, "message": "更新检查不可用"}
    _cache["at"], _cache["result"] = now, result
    return result
