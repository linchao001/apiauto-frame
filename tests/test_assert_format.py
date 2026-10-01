"""Assertion failure formatting and pytest compact repr."""

from __future__ import annotations

import httpx
import pytest

from zframe.assertx.checkers import AssertionErrorX, check
from zframe.assertx.format import format_assertion_failure
from zframe.client.response import Response


def _resp(*, status: int = 200, json: object | None = None) -> Response:
    return Response(httpx.Response(status, json=json or {}), elapsed_ms=1.0)


def test_format_assertion_failure_table():
    text = format_assertion_failure(
        "Body assertion failed",
        ["$.code: expected 0, got -1", "$.message: expected '成功', got '失败'"],
    )
    assert "Assertion failed: Body assertion failed (2 differences)" in text
    assert "Field" in text and "Expected" in text and "Actual" in text
    assert "$.code" in text
    assert "0" in text and "-1" in text
    assert "成功" in text and "失败" in text


def test_format_status_with_body_hint():
    resp = _resp(
        status=400,
        json={"code": -1, "message": "文件中有效热词数量为0", "data": {"failCount": 1}},
    )
    text = format_assertion_failure(
        "HTTP status",
        ["status: expected 200, got 400"],
        response=resp,
        show_body_hint=True,
    )
    assert "HTTP status" in text
    assert "200" in text and "400" in text
    assert "Response body (context):" in text
    assert "code: -1" in text


def test_assertion_error_x_status_message():
    resp = _resp(status=400, json={"code": -1, "message": "err"})
    with pytest.raises(AssertionErrorX) as excinfo:
        check(resp).status(200)
    msg = str(excinfo.value)
    assert "Assertion failed: HTTP status" in msg
    assert "200" in msg and "400" in msg
    assert "Response body (context):" in msg
    assert excinfo.value.diffs == ["status: expected 200, got 400"]


def test_status_msg_replaces_failure_label():
    resp = _resp(status=400, json={"code": -1, "message": "err"})
    with pytest.raises(AssertionErrorX) as excinfo:
        check(resp).status(200, msg="登录应返回 HTTP 200")
    text = str(excinfo.value)
    assert "Assertion failed: 登录应返回 HTTP 200" in text
    assert "HTTP status" not in text
    assert "200" in text and "400" in text
    assert "Response body (context):" in text


def test_body_msg_replaces_failure_label():
    resp = _resp(json={"code": -1, "message": "bad"})
    with pytest.raises(AssertionErrorX) as excinfo:
        check(resp).body({"code": 0}, msg="sampleApi body should succeed")
    text = str(excinfo.value)
    assert "Assertion failed: sampleApi body should succeed" in text
    assert "Body assertion failed" not in text
    assert "$.code" in text


def test_equals_msg_replaces_failure_label():
    with pytest.raises(AssertionErrorX) as excinfo:
        check({"account": "x"}).equals({"account": "admin"}, msg="用户应已落库")
    text = str(excinfo.value)
    assert "Assertion failed: 用户应已落库" in text
    assert "Value assertion failed" not in text
    assert "$.account" in text


def test_plain_failure_msg_prefixes_detail():
    with pytest.raises(AssertionErrorX) as excinfo:
        check(None).is_not_none(msg="查询结果不应为空")
    text = str(excinfo.value)
    assert "查询结果不应为空" in text
    assert "Expected value to be not None" in text


def test_assertion_error_x_body_diff_table():
    resp = _resp(json={"code": -1, "message": "bad"})
    with pytest.raises(AssertionErrorX) as excinfo:
        check(resp).body({"code": 0, "message": "成功"})
    msg = str(excinfo.value)
    assert "Body assertion failed" in msg
    assert "$.code" in msg
    assert "0" in msg and "-1" in msg


def test_pytest_compact_longrepr():
    """AssertionErrorX longrepr stays compact (no source dump) but may include site."""

    def _fail_status():
        resp = _resp(status=400, json={"code": -1})
        check(resp).status(200)

    with pytest.raises(AssertionErrorX):
        _fail_status()

    # Simulate plugin hook behaviour
    try:
        _fail_status()
    except AssertionErrorX as exc:
        longrepr = str(exc)
    assert "def _fail_status" not in longrepr
    assert "HTTP status" in longrepr
