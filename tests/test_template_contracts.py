"""模板安全静态契约：源健康面板（v2 三态）动态值必须经 escH 转义。

前端无 JS 测试设施（审计已知缺口），此为 grep 式静态断言：
锁住"面板动态值转义 + 三态结构"不被回退。动态行为靠人工验收。
"""
from __future__ import annotations

from pathlib import Path

_tpl = Path(__file__).resolve().parents[1] / "templates" / "_base.html"


def test_health_panel_values_escaped():
    src = _tpl.read_text(encoding="utf-8")
    assert "function escH(" in src, "健康面板应定义 escH"
    # v2 结构：动态值（源名/错误详情/条数）全部转义
    assert "escH(s.name)" in src, "源名应转义"
    assert "escH(s.detail" in src, "错误详情应转义"
    assert "escH(s.item_count)" in src, "条数应转义"
    # 回归锚点：不允许退回未转义的裸拼接
    assert "'>✗ ' + s.detail" not in src
    assert "' + s.name + " not in src


def test_health_panel_v2_three_states():
    """v2 面板契约：failed/processing/connected 三态渲染与指示条文案。"""
    src = _tpl.read_text(encoding="utf-8")
    assert 's.state === "failed"' in src
    assert 's.state === "processing"' in src
    assert "· 整理中" in src
    assert "个失败" in src and "个整理中" in src and "个已响应" in src
    # 回归锚点：不允许退回旧字典结构（d.sources || {}）
    assert "d.sources || {}" not in src
