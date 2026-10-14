"""推送通知：每轮抓取后把热榜 top N 推到所选渠道（默认关闭）。

渠道：Telegram Bot / 企业微信群机器人 / 飞书自定义机器人 / 通用 Webhook（POST JSON）。
凭据只存本机 SQLite（meta 表 push_config 键），与模型 key 同等保密级别。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import requests

from . import db

logger = logging.getLogger("ai-news-oss")

CONFIG_KEY = "push_config"
CHANNELS = ("off", "telegram", "wecom", "feishu", "webhook")
TIMEOUT = 15


def get_config() -> dict:
    raw = db.get_meta(CONFIG_KEY)
    if not raw:
        return {"enabled": False, "channel": "off", "telegram_token": "", "telegram_chat": "",
                "wecom_key": "", "feishu_url": "", "webhook_url": "", "base_url": "http://localhost:8000/hot",
                "top_n": 5}
    try:
        cfg = json.loads(raw)
    except ValueError:
        return get_config.__defaults__  # 不会走到；防御
    cfg.setdefault("enabled", False)
    cfg.setdefault("channel", "off")
    return cfg


def save_config(cfg: dict) -> dict:
    if cfg.get("channel") not in CHANNELS:
        raise ValueError("channel 必须是 off/telegram/wecom/feishu/webhook")
    clean = {
        "enabled": bool(cfg.get("enabled")),
        "channel": cfg["channel"],
        "telegram_token": str(cfg.get("telegram_token", ""))[:200],
        "telegram_chat": str(cfg.get("telegram_chat", ""))[:100],
        "wecom_key": str(cfg.get("wecom_key", ""))[:200],
        "feishu_url": str(cfg.get("feishu_url", ""))[:500],
        "webhook_url": str(cfg.get("webhook_url", ""))[:500],
        "base_url": str(cfg.get("base_url", "http://localhost:8000/hot"))[:300],
        "top_n": max(1, min(10, int(cfg.get("top_n", 5) or 5))),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    db.set_meta(CONFIG_KEY, json.dumps(clean, ensure_ascii=False))
    return clean


def build_digest(cfg: dict | None = None) -> str:
    """组装推送文本：今日热榜 top N（故事级，含多源徽标）。"""
    cfg = cfg or get_config()
    items, _ = db.get_hot_stories(page=1, per_page=cfg.get("top_n", 5))
    now = datetime.now(timezone.utc).strftime("%m-%d %H:%M")
    lines = [f"AI 资讯聚合 · 热榜 Top{len(items)}（{now} UTC）"]
    for i, it in enumerate(items, 1):
        story = it.get("_story") or {}
        extra = f"（{story['count']} 源）" if story.get("count", 1) > 1 else ""
        lines.append(f"{i}. {it['title'][:50]}{extra}")
    lines.append(f"详情：{cfg.get('base_url', '')}")
    return "\n".join(lines)


def send(text: str, cfg: dict | None = None) -> dict:
    """按配置渠道发送。返回 {ok} 或 {ok, message}。"""
    cfg = cfg or get_config()
    channel = cfg.get("channel", "off")
    try:
        if channel == "telegram":
            token, chat = cfg.get("telegram_token", ""), cfg.get("telegram_chat", "")
            if not token or not chat:
                return {"ok": False, "message": "请填 Telegram Bot Token 和 Chat ID"}
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text}, timeout=TIMEOUT,
            )
        elif channel == "wecom":
            key = cfg.get("wecom_key", "")
            if not key:
                return {"ok": False, "message": "请填企业微信群机器人 Key"}
            resp = requests.post(
                f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}",
                json={"msgtype": "text", "text": {"content": text}}, timeout=TIMEOUT,
            )
        elif channel == "feishu":
            url = cfg.get("feishu_url", "")
            if not url:
                return {"ok": False, "message": "请填飞书自定义机器人 Webhook 地址"}
            resp = requests.post(
                url, json={"msg_type": "text", "content": {"text": text}}, timeout=TIMEOUT,
            )
        elif channel == "webhook":
            url = cfg.get("webhook_url", "")
            if not url:
                return {"ok": False, "message": "请填 Webhook 地址"}
            resp = requests.post(
                url, json={"source": "ai-news", "text": text}, timeout=TIMEOUT,
            )
        else:
            return {"ok": False, "message": "推送未启用（channel=off）"}
        if resp.status_code == 200:
            return {"ok": True}
        return {"ok": False, "message": f"渠道返回 {resp.status_code}: {resp.text[:120]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"发送失败: {e}"}


def notify_round() -> None:
    """每轮抓取后调用：启用且配置了渠道才发。失败只记日志，不影响抓取。"""
    cfg = get_config()
    if not cfg.get("enabled") or cfg.get("channel") == "off":
        return
    result = send(build_digest(cfg), cfg)
    if result.get("ok"):
        logger.info("推送已发送（%s）", cfg["channel"])
    else:
        logger.warning("推送失败（%s）: %s", cfg["channel"], result.get("message"))
