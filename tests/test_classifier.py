"""classifier 单元测试：关键词规则分类。"""
from __future__ import annotations

from app.classifier import CATEGORIES, classify, group_by_category


def test_policy_beats_company_when_both_match():
    # 同时命中"监管"与"收购"，政策与监管在规则序列中优先
    assert classify("欧盟监管机构否决某收购案") == "政策与监管"


def test_each_category_has_a_trigger():
    assert classify("新开源大模型 Llama 发布") == "AI 大模型"
    assert classify("人形机器人量产下线") == "具身智能与机器人"
    assert classify("AI 编程助手上线") == "AI 应用"
    assert classify("创业公司完成 A 轮融资") == "融资与公司动态"
    assert classify("今天天气不错") == "其他"


def test_english_keywords():
    assert classify("OpenAI raises funding") == "融资与公司动态"
    assert classify("new LLM benchmark results") == "AI 大模型"


def test_group_by_category_sets_category_key():
    items = [{"title": "无人机新规"}, {"title": "随便一句话"}]
    grouped = group_by_category(items)
    assert set(grouped.keys()) == set(CATEGORIES)
    assert items[0]["category"] == "具身智能与机器人"
    assert items[1]["category"] == "其他"
