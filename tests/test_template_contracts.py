"""模板安全静态契约：健康面板动态值必须经 escH 转义（H1）。

前端无 JS 测试设施（审计已知缺口），此为 grep 式静态断言：
锁住"health-row 构造使用 escH"不被回退。动态 XSS 行为靠人工验收。
"""
from __future__ import annotations

from pathlib import Path

_tpl = Path(__file__).resolve().parents[1] / "templates" / "_base.html"


def test_health_panel_values_escaped():
    src = _tpl.read_text(encoding="utf-8")
    assert "function escH(" in src, "健康面板应定义 escH"
    assert "escH(s.fetched)" in src, "条数应转义"
    assert 'escH(String(s.error || "失败").slice(0, 60))' in src, "错误文本应转义"
    assert "escH(n)" in src, "源名应转义"
    # 回归锚点：不允许退回未转义的裸拼接
    assert "'<div class=\"health-row\"><span>' + n +" not in src


def test_health_panel_zero_fetch_shows_warning():
    """P3：ok 但 0 条不再显示绿色——失败被源内部捕获后返回空列表，
    绿色 ✓ 0 条会掩盖问题，应有黄色 ⚠ 分支（用现有 --amber-text 变量）。"""
    src = _tpl.read_text(encoding="utf-8")
    assert 'style="color:var(--amber-text)">⚠ 0 条</span>' in src, "ok 且 0 条应有黄色 ⚠ 0 条分支"
    assert "Number(s.fetched) > 0" in src, "绿色 ✓ 分支应以 fetched>0 为条件"
