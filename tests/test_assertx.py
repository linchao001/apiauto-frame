"""Coverage for zframe.assertx: accuracy, reliability, and edge cases."""

from __future__ import annotations

import re

import httpx
import pytest

from zframe import ANY, Approx, Regex, SoftAssertions, check, extract
from zframe.assertx.checkers import AssertionErrorX
from zframe.assertx.compare import apply_excludes, compare_values, merge_excludes
from zframe.assertx.defaults import (
    bind_assert_settings,
    get_assert_settings,
    reset_assert_settings,
)
from zframe.assertx.matchers import coerce_expected
from zframe.client.response import Response
from zframe.config.models import AssertSettings, Settings


def _resp(
    *,
    status: int = 200,
    json: object | None = None,
    text: str | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    kwargs: dict = {}
    if json is not None:
        kwargs["json"] = json
    elif text is not None:
        kwargs["text"] = text
    if headers is not None:
        kwargs["headers"] = headers
    # Synthetic responses have no stream timing; avoid httpx `.elapsed` access.
    return Response(httpx.Response(status, **kwargs), elapsed_ms=0.0)


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


def test_extract_single_and_default():
    data = {"a": {"b": [1, 2]}}
    assert extract(data, "$.a.b[1]") == 2
    assert extract(data, "$.missing", default="x") == "x"
    assert extract(data, "$.missing") is None


def test_extract_multiple_matches_returns_list():
    data = {"items": [{"id": 1}, {"id": 2}]}
    assert extract(data, "$.items[*].id") == [1, 2]


# ---------------------------------------------------------------------------
# matchers + coerce_expected
# ---------------------------------------------------------------------------


def test_any_matcher_always_matches():
    assert ANY.matches(None)
    assert ANY.matches(0)
    assert ANY.matches({"a": 1})
    assert repr(ANY) == "ANY"


def test_regex_matcher_flags_and_non_string():
    assert Regex(r"^admin").matches("admin")
    assert not Regex(r"^admin").matches("xadmin")
    assert not Regex(r"ADMIN").matches("admin")
    assert Regex(r"ADMIN", flags=re.IGNORECASE).matches("admin")
    assert not Regex(r"\d+").matches(123)
    assert not Regex(r"\d+").matches(None)


def test_approx_abs_rel_nan_and_bool_rejected():
    assert Approx(1.0, abs=0.01).matches(1.005)
    assert not Approx(1.0, abs=0.001).matches(1.01)
    assert Approx(100.0, rel=0.01).matches(100.5)
    assert not Approx(100.0, rel=0.001).matches(100.5)
    # default rel=1e-6 when neither abs nor rel set
    assert Approx(1.0).matches(1.0 + 1e-7)
    assert not Approx(1.0).matches(1.0 + 1e-5)
    assert Approx(float("nan")).matches(float("nan"))
    assert not Approx(1.0).matches(float("nan"))
    assert not Approx(float("nan")).matches(1.0)
    assert not Approx(1.0).matches(True)  # bool must not count as number
    assert not Approx(1.0).matches("1.0")
    assert "abs=" in repr(Approx(1.0, abs=0.01))
    assert "rel=" in repr(Approx(1.0, rel=1e-3))


def test_coerce_expected_nested_markers():
    coerced = coerce_expected(
        {
            "id": {"$any": True},
            "token": {"$regex": "^eyJ", "flags": re.IGNORECASE},
            "score": {"$approx": 1.0, "abs": 0.01},
            "nested": [{"x": {"$any": True}}],
        }
    )
    assert coerced["id"] is ANY
    assert isinstance(coerced["token"], Regex)
    assert coerced["token"].matches("EyJabc")
    assert isinstance(coerced["score"], Approx)
    assert coerced["nested"][0]["x"] is ANY
    assert coerce_expected(ANY) is ANY
    assert coerce_expected([1, 2]) == [1, 2]


# ---------------------------------------------------------------------------
# compare_values / apply_excludes / merge_excludes
# ---------------------------------------------------------------------------


def test_merge_excludes_skips_empty_and_duplicates():
    assert merge_excludes(None, [], ["  a ", "a", "", "b"], None) == ["a", "b"]


def test_compare_bool_not_equal_to_int():
    assert compare_values(True, 1)  # diffs non-empty
    assert compare_values(1, True)
    assert compare_values(True, True) == []
    assert compare_values(False, False) == []


def test_compare_int_float_numbers():
    assert compare_values(1, 1.0) == []
    assert compare_values({"n": 1}, {"n": 1.0}) == []
    assert compare_values(1, 2)


def test_compare_type_mismatch_and_string():
    diffs = compare_values("a", 1)
    assert any("type mismatch" in d for d in diffs)
    assert compare_values("a", "a") == []
    assert compare_values("a", "b")


def test_compare_dict_missing_and_unexpected_keys():
    diffs = compare_values({"a": 1}, {"a": 1, "b": 2})
    assert any("missing" in d for d in diffs)
    diffs = compare_values({"a": 1, "b": 2}, {"a": 1}, allow_extra=False)
    assert any("unexpected keys" in d for d in diffs)
    assert compare_values({"a": 1, "b": 2}, {"a": 1}, allow_extra=True) == []


def test_compare_actual_not_dict_or_list():
    assert any("expected object" in d for d in compare_values([1], {"a": 1}))
    assert any("expected array" in d for d in compare_values({"a": 1}, [1]))


def test_compare_strict_list_length():
    assert compare_values([1, 2], [1], mode="strict", allow_extra=True) == []
    diffs = compare_values([1], [1, 2], mode="strict", allow_extra=True)
    assert any("list too short" in d for d in diffs)
    diffs = compare_values([1, 2], [1], mode="strict", allow_extra=False)
    assert any("list length mismatch" in d for d in diffs)


def test_compare_loose_list_extra_and_missing():
    assert compare_values([1, 2, 3], [1, 2], mode="loose", allow_extra=True) == []
    diffs = compare_values([1, 2], [1, 2, 3], mode="loose")
    assert any("no matching item" in d or "missing item" in d for d in diffs)
    diffs = compare_values([1, 2, 3], [1, 2], mode="loose", allow_extra=False)
    assert any("unexpected extra" in d for d in diffs)


def test_compare_loose_nested_bag_match():
    actual = [{"id": 2, "extra": True}, {"id": 1}]
    expected = [{"id": 1}, {"id": 2}]
    assert compare_values(actual, expected, mode="loose") == []
    diffs = compare_values(actual, [{"id": 1}, {"id": 3}], mode="loose")
    assert diffs


def test_compare_matcher_failure_message():
    diffs = compare_values({"t": "plain"}, {"t": Regex(r"^eyJ")})
    assert len(diffs) == 1
    assert "expected Regex" in diffs[0]
    diffs = compare_values({"n": 2.0}, {"n": Approx(1.0, abs=0.01)})
    assert "Approx" in diffs[0]


def test_exclude_wildcard_and_index():
    actual = {
        "items": [{"id": 1, "ts": 9}, {"id": 2, "ts": 8}],
        "tags": ["a", "b"],
    }
    expected = {"items": [{"id": 1}, {"id": 2}], "tags": ["a"]}
    assert (
        compare_values(
            actual,
            expected,
            exclude=["items[*].ts", "tags[1]"],
        )
        == []
    )


def test_exclude_clear_star_list_and_invalid_path():
    data = {"items": [1, 2, 3]}
    assert apply_excludes(data, ["items[*]"]) == {"items": []}
    with pytest.raises(ValueError, match="Invalid exclude path"):
        apply_excludes({"a": 1}, ["items[x]"])


def test_exclude_bare_key_digit_prefix_not_bare():
    # leading digit → path parse, not strip-anywhere
    actual = {"0x": 1, "data": {"0x": 2}}
    # "0x" is not a bare key (_is_bare_key rejects digit start); invalid path tokens
    with pytest.raises(ValueError, match="Invalid exclude path"):
        compare_values(actual, {}, exclude=["0x"])


def test_compare_does_not_mutate_inputs():
    actual = {"requestId": "r", "code": 0}
    expected = {"code": 0, "requestId": "ignored"}
    assert compare_values(actual, expected, exclude=["requestId"]) == []
    assert "requestId" in actual
    assert "requestId" in expected


# ---------------------------------------------------------------------------
# defaults (ContextVar)
# ---------------------------------------------------------------------------


def test_get_assert_settings_default_and_bind():
    assert get_assert_settings().mode == "loose"
    token = bind_assert_settings(AssertSettings(mode="strict", allow_extra=False, exclude=["ts"]))
    try:
        cfg = get_assert_settings()
        assert cfg.mode == "strict"
        assert cfg.allow_extra is False
        assert cfg.exclude == ["ts"]
    finally:
        reset_assert_settings(token)
    assert get_assert_settings().mode == "loose"


# ---------------------------------------------------------------------------
# SoftAssertions
# ---------------------------------------------------------------------------


def test_soft_assertions_pass_and_failures_property():
    soft = SoftAssertions()
    soft.check(True, "should not record").run(lambda: None)
    assert soft.failures == []
    soft.assert_all()  # no raise

    soft2 = SoftAssertions()
    soft2.check(False, "a").check(False, "b")
    assert soft2.failures == ["a", "b"]
    with pytest.raises(AssertionErrorX, match="Soft assertion \\(2 differences\\)"):
        soft2.assert_all()


def test_soft_assertions_run_only_catches_assertion_error():
    soft = SoftAssertions()
    soft.run(lambda: (_ for _ in ()).throw(AssertionError("assert-fail")))
    assert soft.failures == ["assert-fail"]
    with pytest.raises(ValueError, match="other"):
        soft.run(lambda: (_ for _ in ()).throw(ValueError("other")))


# ---------------------------------------------------------------------------
# check() fluent API
# ---------------------------------------------------------------------------


def test_check_status_and_status_in():
    resp = _resp(status=201, json={})
    check(resp).status(201).status_in(200, 201)
    with pytest.raises(AssertionErrorX, match="HTTP status"):
        check(resp).status(200)
    with pytest.raises(AssertionErrorX, match="HTTP status"):
        check(resp).status_in(400, 404)
    try:
        check(resp).status(200)
    except AssertionErrorX as exc:
        assert exc.response is resp


def test_check_contains():
    resp = _resp(text="hello world")
    check(resp).contains("world")
    with pytest.raises(AssertionErrorX, match="does not contain"):
        check(resp).contains("missing")


def test_check_header():
    resp = _resp(json={}, headers={"X-Trace": "abc", "Content-Type": "application/json"})
    check(resp).header("X-Trace").header("X-Trace", "abc")
    with pytest.raises(AssertionErrorX, match="Header missing"):
        check(resp).header("X-Missing")
    with pytest.raises(AssertionErrorX, match="Header X-Trace"):
        check(resp).header("X-Trace", "xyz")


def test_check_schema_ok_and_fail():
    resp = _resp(json={"code": 0, "name": "a"})
    check(resp).schema(
        {
            "type": "object",
            "required": ["code", "name"],
            "properties": {
                "code": {"type": "integer"},
                "name": {"type": "string"},
            },
        }
    )
    with pytest.raises(AssertionErrorX, match="Schema validation failed"):
        check(resp).schema({"type": "object", "required": ["missing"]})


def test_check_schema_non_json():
    resp = _resp(text="not-json")
    with pytest.raises(AssertionErrorX, match="Response is not JSON"):
        check(resp).schema({"type": "object"})


def test_check_jsonpath_exists_and_only():
    resp = _resp(json={"code": 0, "data": None})
    check(resp).jsonpath("$.code")  # exists only
    check(resp).jsonpath("$.missing", exists=False)
    with pytest.raises(AssertionErrorX, match="JSONPath not found"):
        check(resp).jsonpath("$.missing")
    # None value with exists=True is treated as not found
    with pytest.raises(AssertionErrorX, match="JSONPath not found"):
        check(resp).jsonpath("$.data")


def test_check_jsonpath_nested_expect():
    resp = _resp(json={"data": {"roles": ["b", "a"], "score": 1.001}})
    check(resp).jsonpath(
        "$.data",
        {"roles": ["a", "b"], "score": {"$approx": 1.0, "abs": 0.01}},
    )


def test_check_body_path_subset():
    resp = _resp(json={"code": 0, "data": {"account": "admin", "extra": 1}})
    check(resp).body({"account": "admin"}, path="$.data")
    with pytest.raises(AssertionErrorX, match="JSONPath not found"):
        check(resp).body({"a": 1}, path="$.missing")


def test_check_body_strict_and_allow_extra_false():
    resp = _resp(json={"items": [{"id": 2}, {"id": 1}], "extra": True})
    check(resp).body({"items": [{"id": 1}, {"id": 2}]}, mode="loose")
    with pytest.raises(AssertionErrorX, match="Body assertion failed"):
        check(resp).body({"items": [{"id": 1}, {"id": 2}]}, mode="strict")
    with pytest.raises(AssertionErrorX, match="Body assertion failed"):
        check(resp).body({"items": [{"id": 1}, {"id": 2}]}, allow_extra=False)


def test_check_body_invalid_mode_and_meta_exclude_type():
    resp = _resp(json={"code": 0})
    with pytest.raises(ValueError, match="Unsupported compare mode"):
        check(resp).body({"code": 0}, mode="weird")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="meta\\['exclude'\\]"):
        check(resp).body({"code": 0}, meta={"exclude": "requestId"})


def test_check_body_settings_override_and_settings_object():
    resp = _resp(json={"code": 0, "ts": 1, "extra": True})
    # call-site AssertSettings
    check(resp).body(
        {"code": 0},
        settings=AssertSettings(exclude=["ts"], allow_extra=True),
    )
    # Settings wrapper
    check(resp).body(
        {"code": 0},
        settings=Settings(assertx=AssertSettings(exclude=["ts"])),
    )
    # bound defaults + call-site allow_extra=False should fail on extra
    token = bind_assert_settings(AssertSettings(exclude=["ts"]))
    try:
        with pytest.raises(AssertionErrorX):
            check(resp).body({"code": 0}, allow_extra=False)
    finally:
        reset_assert_settings(token)


def test_check_body_non_json():
    resp = _resp(text="plain")
    with pytest.raises(AssertionErrorX, match="Response is not JSON"):
        check(resp).body({"code": 0})


def test_check_body_matchers_in_expect():
    resp = _resp(
        json={
            "id": "any",
            "token": "eyJhbGciOi",
            "score": 1.001,
        }
    )
    check(resp).body(
        {
            "id": ANY,
            "token": Regex(r"^eyJ"),
            "score": Approx(1.0, abs=0.01),
        }
    )
    check(resp).body(
        {
            "id": {"$any": True},
            "token": {"$regex": "^eyJ"},
            "score": {"$approx": 1.0, "abs": 0.01},
        }
    )


def test_check_chaining_fluent():
    resp = _resp(status=200, json={"code": 0, "msg": "ok"}, headers={"X-A": "1"})
    check(resp).status(200).status_in(200).header("X-A", "1").contains("code").jsonpath(
        "$.code", 0
    ).body({"code": 0}).schema(
        {"type": "object", "properties": {"code": {"type": "integer"}}}
    )


# ---------------------------------------------------------------------------
# check() value API (DB rows / generic)
# ---------------------------------------------------------------------------


def test_value_check_equals_row_subset():
    row = {"account": "autotest", "user_name": "接口自动化账号", "id": 9, "extra": True}
    check(row).is_not_none().equals(
        {"account": "autotest", "user_name": "接口自动化账号"}
    )
    with pytest.raises(AssertionErrorX, match="Value assertion failed"):
        check(row).equals({"account": "other"})


def test_value_check_is_none_helpers():
    check(None).is_none()
    with pytest.raises(AssertionErrorX, match="not None"):
        check(None).is_not_none()
    with pytest.raises(AssertionErrorX, match="to be None"):
        check({"a": 1}).is_none()


def test_value_check_count_variants():
    rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    check(rows).count(3).count_at_least(2).count_at_most(5)
    with pytest.raises(AssertionErrorX, match="Expected count 2, got 3"):
        check(rows).count(2)
    with pytest.raises(AssertionErrorX, match="Expected count >= 4"):
        check(rows).count_at_least(4)
    with pytest.raises(AssertionErrorX, match="Expected count <= 1"):
        check(rows).count_at_most(1)
    with pytest.raises(AssertionErrorX, match="got None"):
        check(None).count(0)
    with pytest.raises(AssertionErrorX, match="collections"):
        check("abc").count(3)


def test_value_check_multi_row_equals_and_contains():
    rows = [
        {"account": "b", "user_name": "B", "ts": 2},
        {"account": "a", "user_name": "A", "ts": 1},
        {"account": "c", "user_name": "C", "ts": 3},
    ]
    check(rows).count(3).equals(
        [
            {"account": "a", "user_name": "A"},
            {"account": "b", "user_name": "B"},
            {"account": "c", "user_name": "C"},
        ],
        exclude=["ts"],
    )
    # subset of rows (allow_extra on list)
    check(rows).equals(
        [
            {"account": "a", "user_name": "A"},
            {"account": "b"},
        ]
    )
    check(rows).contains({"account": "a", "user_name": "A"})
    with pytest.raises(AssertionErrorX, match="No item matching"):
        check(rows).contains({"account": "missing"})
    with pytest.raises(AssertionErrorX, match="requires a list/tuple"):
        check({"account": "a"}).contains({"account": "a"})


def test_value_check_equals_respects_bound_settings():
    token = bind_assert_settings(AssertSettings(exclude=["ts"], allow_extra=True))
    try:
        check({"code": 0, "ts": 1, "extra": True}).equals({"code": 0})
        with pytest.raises(AssertionErrorX):
            check({"code": 0, "extra": True}).equals({"code": 0}, allow_extra=False)
    finally:
        reset_assert_settings(token)
