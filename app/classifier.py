"""主题分类：关键词规则（全部规则集中在此文件，方便改）。

分类：AI 大模型 / 具身智能与机器人 / AI 应用 / 政策与监管 / 融资与公司动态 / 其他
匹配顺序即优先级：一条新闻命中多个类别时，取排在前面的。
"""
from __future__ import annotations

CATEGORIES = [
    "AI 大模型",
    "具身智能与机器人",
    "AI 应用",
    "政策与监管",
    "融资与公司动态",
    "其他",
]

# 每类关键词（中英文都覆盖一部分）。改规则只改这里。
RULES: list[tuple[str, list[str]]] = [
    (
        "政策与监管",
        [
            "监管", "立法", "法案", "合规", "审查", "禁令", "白宫", "行政令", "FTC",
            "欧盟", "AI Act", "regulation", "compliance", "lawsuit", "court ruling",
            "ban", "executive order", "antitrust",
        ],
    ),
    (
        "融资与公司动态",
        [
            "融资", "估值", "IPO", "收购", "并购", "亿美元", "轮融资", "上市",
            "raises", "funding", "valuation", "acquisition", "acquires", "IPO",
            "billion", "million round",
        ],
    ),
    (
        "具身智能与机器人",
        [
            "机器人", "人形", "具身", "机械臂", "四足", "无人机", "自动驾驶",
            "robot", "humanoid", "embodied", "drone", "self-driving", "autonomous vehicle",
        ],
    ),
    (
        "AI 大模型",
        [
            "大模型", "LLM", "GPT", "Claude", "Gemini", "Llama", "Qwen", "DeepSeek",
            "Kimi", "GLM", "文心", "混元", "foundation model", "frontier model",
            "推理模型", "多模态", "开源模型", "open weights", "benchmark",
        ],
    ),
    (
        "AI 应用",
        [
            "应用", "App", "Copilot", "助手", "智能体", "Agent", "搜索", "办公",
            "编程", "代码", "绘画", "视频生成", "音乐", "教育", "医疗",
            "agent", "copilot", "assistant", "coding", "productivity",
        ],
    ),
]


def classify(title: str, summary_hint: str = "") -> str:
    """按标题（+可选摘要提示）返回类别名。"""
    text = f"{title} {summary_hint}".lower()
    for category, keywords in RULES:
        for kw in keywords:
            if kw.lower() in text:
                return category
    return "其他"


def group_by_category(items: list[dict]) -> dict[str, list[dict]]:
    """把条目按类别分组（保持原顺序），返回 {类别: [条目]}。"""
    grouped: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for it in items:
        cat = classify(it.get("title", ""))
        it["category"] = cat
        grouped[cat].append(it)
    return grouped
