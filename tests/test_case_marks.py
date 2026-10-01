"""Tests for case_title / P0–P2 markers."""

from __future__ import annotations

from typing import Any

import pytest

from zframe.plugin.case_marks import (
    CaseMeta,
    format_case_summary,
    parse_case_title,
    resolve_case_meta,
    resolve_priority,
    user_properties_for_meta,
)
from zframe.report.html_utils import extras_for_text


class _Marker:
    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs


class _Callspec:
    def __init__(self, params: dict[str, Any]):
        self.params = params


class _FakeItem:
    def __init__(
        self,
        markers: dict[str, _Marker] | None = None,
        nodeid: str = "t",
        callspec: _Callspec | None = None,
    ):
        self._markers = markers or {}
        self.nodeid = nodeid
        self.callspec = callspec

    def get_closest_marker(self, name: str):
        return self._markers.get(name)


def test_parse_case_title_kwargs():
    case_id, title = parse_case_title(
        _Marker(case_id="E2E-01", title="用户管理完整链路")
    )
    assert case_id == "E2E-01"
    assert title == "用户管理完整链路"


def test_parse_case_title_args():
    case_id, title = parse_case_title(_Marker("E2E-02", "列表查询"))
    assert case_id == "E2E-02"
    assert title == "列表查询"


def test_parse_case_title_partial():
    case_id, title = parse_case_title(_Marker(case_id="E2E-03"))
    assert case_id == "E2E-03"
    assert title == ""


def test_resolve_priority_single():
    item = _FakeItem({"P1": _Marker()})
    assert resolve_priority(item) == "P1"


def test_resolve_priority_highest_wins(caplog: pytest.LogCaptureFixture):
    item = _FakeItem({"P0": _Marker(), "P2": _Marker()}, nodeid="sample::test_x")
    with caplog.at_level("WARNING", logger="zframe.plugin.case_marks"):
        assert resolve_priority(item) == "P0"
    assert "multiple priority marks" in caplog.text
    assert "P0" in caplog.text


def test_resolve_priority_warn_false_silent(caplog: pytest.LogCaptureFixture):
    item = _FakeItem({"P1": _Marker(), "P2": _Marker()})
    with caplog.at_level("WARNING", logger="zframe.plugin.case_marks"):
        assert resolve_priority(item, warn=False) == "P1"
    assert "multiple priority marks" not in caplog.text


def test_resolve_case_meta_combined():
    item = _FakeItem(
        {
            "case_title": _Marker(case_id="E2E-01", title="CRUD"),
            "P0": _Marker(),
        }
    )
    meta = resolve_case_meta(item)
    assert meta == CaseMeta(case_id="E2E-01", title="CRUD", priority="P0")
    assert meta.any is True
    assert format_case_summary(meta) == "E2E-01 [P0] CRUD"
    assert user_properties_for_meta(meta) == [
        ("case_id", "E2E-01"),
        ("title", "CRUD"),
        ("priority", "P0"),
    ]


def test_resolve_case_meta_empty():
    meta = resolve_case_meta(_FakeItem())
    assert meta.any is False
    assert format_case_summary(meta) == ""
    assert user_properties_for_meta(meta) == []


def test_resolve_case_meta_from_parametrize_row():
    item = _FakeItem(
        callspec=_Callspec(
            {
                "meta_data": {
                    "id": "API-01",
                    "title": "获取用户信息",
                    "priority": "P1",
                }
            }
        )
    )
    meta = resolve_case_meta(item)
    assert meta == CaseMeta(case_id="API-01", title="获取用户信息", priority="P1")


def test_resolve_case_meta_row_overrides_marks():
    item = _FakeItem(
        {
            "case_title": _Marker(case_id="E2E-OLD", title="旧标题"),
            "P2": _Marker(),
        },
        callspec=_Callspec(
            {
                "meta_data": {
                    "id": "API-02",
                    "title": "行级标题",
                    "priority": "P0",
                }
            }
        ),
    )
    meta = resolve_case_meta(item, warn=False)
    assert meta == CaseMeta(case_id="API-02", title="行级标题", priority="P0")


def test_resolve_case_meta_marks_fallback_when_row_partial():
    item = _FakeItem(
        {"case_title": _Marker(case_id="E2E-01", title="兜底标题"), "P1": _Marker()},
        callspec=_Callspec({"meta_data": {"id": "API-03"}}),
    )
    meta = resolve_case_meta(item, warn=False)
    assert meta == CaseMeta(case_id="API-03", title="兜底标题", priority="P1")


def test_resolve_case_meta_priority_conflict_highest_wins(caplog: pytest.LogCaptureFixture):
    item = _FakeItem(
        {"P2": _Marker()},
        nodeid="sample::test_x",
        callspec=_Callspec({"meta_data": {"id": "X", "title": "t", "priority": "P0"}}),
    )
    with caplog.at_level("WARNING", logger="zframe.plugin.case_marks"):
        meta = resolve_case_meta(item)
    assert meta.priority == "P0"
    assert "priority mismatch" in caplog.text


def test_resolve_case_meta_title_mismatch_warns(caplog: pytest.LogCaptureFixture):
    item = _FakeItem(
        {"case_title": _Marker(case_id="E2E-01", title="方法标题")},
        nodeid="sample::test_y",
        callspec=_Callspec({"meta_data": {"title": "行级标题"}}),
    )
    with caplog.at_level("WARNING", logger="zframe.plugin.case_marks"):
        meta = resolve_case_meta(item)
    assert meta.title == "行级标题"
    assert "case title mismatch" in caplog.text


def test_case_markers_registered(pytestconfig: pytest.Config):
    text = "\n".join(pytestconfig.getini("markers"))
    assert "case_title" in text
    assert "P0" in text and "P1" in text and "P2" in text


def test_extras_for_case_summary():
    extras = extras_for_text("E2E-01 [P0] CRUD", name="case")
    assert len(extras) == 1
    assert extras[0].get("name") == "case" or "E2E-01" in str(extras[0])


def test_render_case_detail_html_includes_title_and_steps():
    from zframe.report.html_utils import render_case_detail_html, render_title_cell_html

    html = render_case_detail_html(
        case_id="E2E-01",
        title="用户管理完整链路",
        priority="P0",
        steps=[("1. 列表", "ok"), ("2. 删除", "fail")],
    )
    assert "E2E-01" in html
    assert "[P0]" in html
    assert "用户管理完整链路" in html
    assert "1. 列表" in html
    assert "2. 删除" in html

    cell = render_title_cell_html(title="用户管理完整链路", detail_html=html)
    assert "zframe-title-trigger" in cell
    assert "zframe-title-popup" in cell
    assert "用户管理完整链路" in cell

    plain = render_title_cell_html(title="only", detail_html="")
    assert "zframe-title-popup" not in plain
    assert plain == '<td class="col-caseTitle">only</td>'
