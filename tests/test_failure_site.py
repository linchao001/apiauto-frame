"""Case-side failure location and compact call-phase failure repr."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import httpx
import pytest

from zframe.assertx.checkers import AssertionErrorX, check
from zframe.assertx.site import (
    apply_case_failure_location,
    format_call_failure,
    format_failure_at,
    resolve_case_failure_site,
    should_compact_call_failures,
)
from zframe.client.response import Response


def _resp(*, status: int = 200, json: object | None = None) -> Response:
    return Response(httpx.Response(status, json=json or {}), elapsed_ms=1.0)


def test_resolve_case_failure_site_points_at_check_call():
    line_holder: list[int] = []

    def _fail():
        line_holder.append(inspect.currentframe().f_lineno + 1)  # type: ignore[union-attr]
        check(_resp(status=400, json={"code": -1})).status(200)

    with pytest.raises(AssertionErrorX) as excinfo:
        _fail()

    site = resolve_case_failure_site(excinfo.value)
    assert site is not None
    path, lineno, func = site
    assert path.endswith("test_failure_site.py")
    assert lineno == line_holder[0]
    assert func == "_fail"
    assert "checkers.py" not in path


def test_format_failure_at_includes_file_line():
    text = format_failure_at(
        str(AssertionErrorX("Expected value to be not None, got None")),
        ("acme/WEB/E2E/Sample/testcases/test_sample_flow.py", 85, "test_flow"),
    )
    assert "at test_sample_flow.py:85 in test_flow" in text
    assert "Expected value to be not None" in text
    assert "def test_flow" not in text


def test_apply_case_failure_location_uses_pytest_zero_based_lineno():
    line_holder: list[int] = []

    def _fail():
        line_holder.append(inspect.currentframe().f_lineno + 1)  # type: ignore[union-attr]
        check(None).is_not_none()

    report = SimpleNamespace(location=("cases/test_x.py", 10, "TestX.test_y"))
    try:
        _fail()
    except AssertionErrorX as exc:
        site = apply_case_failure_location(report, exc)
        longrepr = format_failure_at(str(exc), site)

    assert site is not None
    assert report.location == ("cases/test_x.py", line_holder[0] - 1, "TestX.test_y")
    assert f"at test_failure_site.py:{line_holder[0]} in _fail" in longrepr
    assert "Expected value to be not None" in longrepr
    assert "Traceback" not in longrepr


def test_format_call_failure_plain_assert_no_source():
    line_holder: list[int] = []

    def _fail_plain():
        line_holder.append(inspect.currentframe().f_lineno + 1)  # type: ignore[union-attr]
        assert 1 == 2

    try:
        _fail_plain()
    except AssertionError as exc:
        site = resolve_case_failure_site(exc)
        text = format_call_failure(exc, site)

    assert site is not None
    assert f"at test_failure_site.py:{line_holder[0]} in _fail_plain" in text
    assert "AssertionError" in text
    assert "def _fail_plain" not in text
    assert "Traceback" not in text


def test_format_call_failure_keeps_assertion_error_x_diff():
    try:
        check(_resp(status=400, json={"code": -1})).status(200)
    except AssertionErrorX as exc:
        text = format_call_failure(exc, ("cases/test_x.py", 10, "test_x"))

    assert "at test_x.py:10 in test_x" in text
    assert "Assertion failed: HTTP status" in text
    assert "200" in text and "400" in text


def test_should_compact_call_failures_default_yes():
    assert should_compact_call_failures(("-q", "--env", "test")) is True


def test_should_compact_call_failures_explicit_tb_no():
    assert should_compact_call_failures(("--tb=long",)) is False
    assert should_compact_call_failures(("--tb", "short")) is False
    assert should_compact_call_failures(("--tb=auto",)) is False
