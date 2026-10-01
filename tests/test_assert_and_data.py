import httpx
import pytest
import respx

from zframe import ANY, Approx, Regex, SoftAssertions, check, extract, render
from zframe.assertx.checkers import AssertionErrorX
from zframe.assertx.compare import compare_values, merge_excludes
from zframe.assertx.defaults import bind_assert_settings, reset_assert_settings
from zframe.client.http import HttpClient
from zframe.config.models import AssertSettings


def test_render_placeholder():
    data = render(
        {"url": "${base}/v1", "id": "${user.id}"},
        {"base": "https://x", "user": {"id": 7}},
    )
    assert data == {"url": "https://x/v1", "id": 7}


def test_extract_jsonpath():
    assert extract({"a": {"b": [1, 2]}}, "$.a.b[1]") == 2


def test_soft_assertions():
    soft = SoftAssertions()
    soft.check(1 == 1, "ok")
    soft.check(1 == 2, "one != two")
    soft.run(lambda: (_ for _ in ()).throw(AssertionError("boom")))
    with pytest.raises(AssertionErrorX):
        soft.assert_all()


def test_compare_loose_ignores_list_order():
    actual = {"items": [{"id": 2}, {"id": 1}], "code": 0}
    expected = {"items": [{"id": 1}, {"id": 2}], "code": 0}
    assert compare_values(actual, expected, mode="loose") == []


def test_compare_strict_requires_list_order():
    actual = {"items": [{"id": 2}, {"id": 1}]}
    expected = {"items": [{"id": 1}, {"id": 2}]}
    diffs = compare_values(actual, expected, mode="strict")
    assert diffs
    assert any("expected" in item for item in diffs)


def test_compare_exclude_bare_key_and_path():
    actual = {
        "code": 0,
        "requestId": "abc",
        "data": {"name": "a", "ts": 1, "nested": {"ts": 2}},
    }
    expected = {"code": 0, "data": {"name": "a", "nested": {}}}
    assert (
        compare_values(
            actual,
            expected,
            exclude=["requestId", "data.ts", "$.data.nested.ts"],
        )
        == []
    )


def test_compare_allow_extra_default_true():
    actual = {"code": 0, "data": {"a": 1, "b": 2}, "extra": True}
    expected = {"code": 0, "data": {"a": 1}}
    assert compare_values(actual, expected) == []
    assert compare_values(actual, expected, allow_extra=False)


def test_compare_matchers_python_and_json_markers():
    actual = {"id": "x", "token": "eyJhbGciOi", "score": 1.001, "roles": ["b", "a"]}
    expected = {
        "id": ANY,
        "token": Regex(r"^eyJ"),
        "score": Approx(1.0, abs=0.01),
        "roles": ["a", "b"],
    }
    assert compare_values(actual, expected) == []

    markers = {
        "id": {"$any": True},
        "token": {"$regex": "^eyJ"},
        "score": {"$approx": 1.0, "abs": 0.01},
        "roles": ["a", "b"],
    }
    assert compare_values(actual, markers) == []


def test_compare_loose_hashable_multiset():
    actual = {"nums": [1, 2, 2, 3]}
    expected = {"nums": [3, 2, 1, 2]}
    assert compare_values(actual, expected, mode="loose") == []
    assert compare_values(actual, {"nums": [1, 2, 3]}, mode="loose", allow_extra=False)


def test_merge_excludes_order():
    assert merge_excludes(["a", "b"], ["b", "c"], ["d"]) == ["a", "b", "c", "d"]


@respx.mock
def test_check_jsonpath_matchers():
    respx.get("https://api.example.com/user").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "token": "eyJhbGciOi",
                    "score": 1.001,
                    "sessionId": "abc",
                    "roles": ["b", "a"],
                },
            },
        )
    )
    with HttpClient(base_url="https://api.example.com") as client:
        resp = client.get("/user")
    check(resp).jsonpath("$.code", 0).jsonpath("$.data.token", Regex(r"^eyJ")).jsonpath(
        "$.data.score", Approx(1.0, abs=0.01)
    ).jsonpath("$.data.sessionId", ANY).jsonpath(
        "$.data.roles", ["a", "b"]
    ).jsonpath("$.data.token", {"$regex": "^eyJ"}).jsonpath(
        "$.data.score", {"$approx": 1.0, "abs": 0.01}
    )


@respx.mock
def test_check_jsonpath_matcher_failure():
    respx.get("https://api.example.com/user").mock(
        return_value=httpx.Response(200, json={"data": {"token": "plain"}})
    )
    with HttpClient(base_url="https://api.example.com") as client:
        resp = client.get("/user")
    with pytest.raises(AssertionErrorX, match="JSONPath \\$\\.data\\.token assertion failed"):
        check(resp).jsonpath("$.data.token", Regex(r"^eyJ"))


@respx.mock
def test_check_body_full_assert():
    respx.get("https://api.example.com/user").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "message": "ok",
                "data": {"account": "admin", "roles": ["b", "a"], "extra": 1},
                "requestId": "rid-1",
            },
        )
    )
    expect = {
        "code": 0,
        "message": "ok",
        "data": {"account": "admin", "roles": ["a", "b"]},
    }
    with HttpClient(base_url="https://api.example.com") as client:
        resp = client.get("/user")
    check(resp).status(200).body(expect, exclude=["requestId"])


@respx.mock
def test_check_body_meta_and_global_exclude():
    respx.get("https://api.example.com/user").mock(
        return_value=httpx.Response(
            200,
            json={"code": 0, "requestId": "r1", "timestamp": 9, "traceId": "t", "ok": True},
        )
    )
    token = bind_assert_settings(AssertSettings(exclude=["traceId"]))
    try:
        with HttpClient(base_url="https://api.example.com") as client:
            resp = client.get("/user")
        check(resp).body(
            {"code": 0, "ok": True},
            meta={"exclude": ["requestId", "timestamp"]},
        )
    finally:
        reset_assert_settings(token)


@respx.mock
def test_check_body_reports_diffs():
    respx.get("https://api.example.com/user").mock(
        return_value=httpx.Response(200, json={"code": 1, "data": {"account": "x"}})
    )
    with HttpClient(base_url="https://api.example.com") as client:
        resp = client.get("/user")
    with pytest.raises(AssertionErrorX, match="Body assertion failed"):
        check(resp).body({"code": 0, "data": {"account": "admin"}})
