"""Unit tests for default Parametrize and subclass extension hooks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from zframe import Parametrize, parametrize_from
from zframe.data.parametrize import DEFAULT_ARGNAMES


# ---------------------------------------------------------------------------
# Default engine — normalize_case / prepare_case
# ---------------------------------------------------------------------------


class TestNormalizeCase:
    def setup_method(self) -> None:
        self.engine = Parametrize()

    def test_standard_meta_req_expect(self) -> None:
        out = self.engine.normalize_case(
            {
                "meta_data": {"id": "T1", "title": "x"},
                "req": {"a": 1},
                "expect": {"code": 0},
            }
        )
        assert out == {
            "meta_data": {"id": "T1", "title": "x"},
            "request": {"a": 1},
            "expect": {"code": 0},
            "test_data": {},
        }

    def test_folds_stray_top_level_into_meta_data(self) -> None:
        out = self.engine.normalize_case(
            {
                "meta_data": {"id": "T1"},
                "priority": "P0",
                "req": {},
                "expect": {},
            }
        )
        assert out["meta_data"] == {"id": "T1", "priority": "P0"}

    def test_body_keys_not_folded_into_meta(self) -> None:
        out = self.engine.normalize_case(
            {
                "meta_data": {"id": "T1"},
                "req": {"x": 1},
                "request": {"ignored_when_req_present": True},
                "expect": {"y": 2},
                "response": {"ignored_when_expect_present": True},
            }
        )
        assert "req" not in out["meta_data"]
        assert "request" not in out["meta_data"]
        assert "expect" not in out["meta_data"]
        assert "response" not in out["meta_data"]
        assert "test_data" not in out["meta_data"]
        assert out["request"] == {"x": 1}
        assert out["expect"] == {"y": 2}
        assert out["test_data"] == {}

    def test_prefer_req_over_request(self) -> None:
        out = self.engine.normalize_case(
            {"meta_data": {}, "req": {"from": "req"}, "request": {"from": "request"}, "expect": {}}
        )
        assert out["request"] == {"from": "req"}

    def test_prefer_expect_over_response(self) -> None:
        out = self.engine.normalize_case(
            {"meta_data": {}, "req": {}, "expect": {"e": 1}, "response": {"e": 2}}
        )
        assert out["expect"] == {"e": 1}

    def test_legacy_flat_request_response(self) -> None:
        out = self.engine.normalize_case(
            {"id": "L1", "title": "t", "request": {"a": 1}, "response": {"b": 2}}
        )
        assert out == {
            "meta_data": {"id": "L1", "title": "t"},
            "request": {"a": 1},
            "expect": {"b": 2},
            "test_data": {},
        }

    def test_empty_req_and_expect_default_to_empty_dict(self) -> None:
        out = self.engine.normalize_case({"meta_data": {"id": "E1"}})
        assert out["request"] == {}
        assert out["expect"] == {}
        assert out["test_data"] == {}

    def test_test_data_preserved(self) -> None:
        seed = {"account": "u1", "password": "p1"}
        out = self.engine.normalize_case(
            {
                "meta_data": {"id": "T1"},
                "req": {"n": 1},
                "expect": {"code": 0},
                "test_data": {"seed": seed},
            }
        )
        assert out["test_data"] == {"seed": seed}

    def test_prepare_case_passthrough_skips_normalize(self) -> None:
        raw = {"username": "u", "password": "p"}
        assert self.engine.prepare_case(raw, passthrough=True) == raw
        assert self.engine.prepare_case(raw, passthrough=False)["meta_data"]["username"] == "u"


# ---------------------------------------------------------------------------
# Default engine — case_id / parse_argnames / row_values / validate
# ---------------------------------------------------------------------------


class TestCaseIdAndArgs:
    def setup_method(self) -> None:
        self.engine = Parametrize()

    def test_case_id_from_meta_data_id(self) -> None:
        case = {"meta_data": {"id": "M1"}, "request": {}, "expect": {}}
        assert self.engine.case_id(case, 0, "id") == "M1"

    def test_case_id_custom_id_key_in_meta(self) -> None:
        case = {"meta_data": {"case_no": "CN-9", "id": "ignored"}, "request": {}, "expect": {}}
        assert self.engine.case_id(case, 0, "case_no") == "CN-9"

    def test_case_id_top_level_when_no_meta(self) -> None:
        case = {"id": "TOP", "username": "a"}
        assert self.engine.case_id(case, 0, "id") == "TOP"

    def test_case_id_fallback_title_then_name(self) -> None:
        assert self.engine.case_id({"meta_data": {"title": "hello"}, "request": {}, "expect": {}}, 0, "id") == "hello"
        assert self.engine.case_id({"name": "n1"}, 0, "id") == "n1"

    def test_case_id_fallback_case_index(self) -> None:
        assert self.engine.case_id({"meta_data": {}, "request": {}, "expect": {}}, 3, "id") == "case_3"

    def test_parse_argnames_string_sequence_and_default(self) -> None:
        assert self.engine.parse_argnames("req, expect") == ("req", "expect")
        assert self.engine.parse_argnames(("meta_data", "expect")) == ("meta_data", "expect")
        assert self.engine.parse_argnames("") == DEFAULT_ARGNAMES
        assert self.engine.parse_argnames([]) == DEFAULT_ARGNAMES

    def test_row_values_maps_req_to_request(self) -> None:
        case = {
            "meta_data": {"id": "1"},
            "request": {"n": 1},
            "expect": {"ok": True},
            "test_data": {"seed": "x"},
        }
        assert self.engine.row_values(case, ("meta_data", "req", "expect", "test_data")) == (
            {"id": "1"},
            {"n": 1},
            {"ok": True},
            {"seed": "x"},
        )

    def test_row_values_defaults_missing_test_data(self) -> None:
        case = {"meta_data": {"id": "1"}, "request": {}, "expect": {}}
        assert self.engine.row_values(case, ("meta_data", "test_data")) == ({"id": "1"}, {})

    def test_row_values_missing_field_raises(self) -> None:
        with pytest.raises(KeyError, match="missing field"):
            self.engine.row_values({"meta_data": {}}, ("meta_data", "req", "expect"))

    def test_validate_argnames_rejects_request(self) -> None:
        with pytest.raises(ValueError, match="reserved by pytest"):
            self.engine.validate_argnames(("meta_data", "request", "expect"), qualname="t")


# ---------------------------------------------------------------------------
# Default engine — decorator integration
# ---------------------------------------------------------------------------


class TestDefaultDecorator:
    def test_bare_decorator_style(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(
            json.dumps(
                [{"meta_data": {"id": "B1"}, "req": {"n": 2}, "expect": {"ok": True}}]
            ),
            encoding="utf-8",
        )

        @parametrize_from(path)
        def test_fn(meta_data, req, expect, test_data):
            return meta_data, req, expect, test_data

        mark = test_fn.pytestmark[0]
        assert mark.args[0] == "meta_data,req,expect,test_data"
        assert mark.kwargs["ids"] == ["B1"]
        assert mark.args[1][0] == ({"id": "B1"}, {"n": 2}, {"ok": True}, {})

    def test_bare_decorator_with_test_data(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "meta_data": {"id": "TD1"},
                        "req": {"n": 1},
                        "expect": {"ok": True},
                        "test_data": {"seed": {"account": "u1"}},
                    }
                ]
            ),
            encoding="utf-8",
        )

        @parametrize_from(path)
        def test_fn(meta_data, req, expect, test_data):
            return test_data

        assert test_fn.pytestmark[0].args[1][0][3] == {"seed": {"account": "u1"}}

    def test_argname_subset(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(
            json.dumps([{"meta_data": {"id": "S1"}, "req": {"x": 1}, "expect": {"y": 2}}]),
            encoding="utf-8",
        )

        @parametrize_from(path, argname="req,expect")
        def test_fn(req, expect):
            return req, expect

        mark = test_fn.pytestmark[0]
        assert mark.args[0] == "req,expect"
        assert mark.args[1][0] == ({"x": 1}, {"y": 2})

    def test_custom_id_key(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "meta_data": {"case_no": "CN-1", "id": "other"},
                        "req": {},
                        "expect": {},
                    }
                ]
            ),
            encoding="utf-8",
        )

        @parametrize_from(path, id_key="case_no")
        def test_fn(meta_data, req, expect, test_data):
            return meta_data

        assert test_fn.pytestmark[0].kwargs["ids"] == ["CN-1"]

    def test_explicit_key_selects_case_list(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(
            json.dumps(
                {
                    "suite_a": [{"meta_data": {"id": "A"}, "req": {"n": 1}, "expect": {}}],
                    "suite_b": [{"meta_data": {"id": "B"}, "req": {"n": 2}, "expect": {}}],
                }
            ),
            encoding="utf-8",
        )

        @parametrize_from(path, key="suite_b")
        def test_fn(meta_data, req, expect, test_data):
            return req["n"]

        mark = test_fn.pytestmark[0]
        assert mark.kwargs["ids"] == ["B"]
        assert mark.args[1][0][1] == {"n": 2}

    def test_root_joins_relative_path(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cases.json").write_text(
            json.dumps([{"meta_data": {"id": "R1"}, "req": {}, "expect": {}}]),
            encoding="utf-8",
        )

        @parametrize_from("cases.json", root=data_dir)
        def test_fn(meta_data, req, expect, test_data):
            return meta_data["id"]

        assert test_fn.pytestmark[0].kwargs["ids"] == ["R1"]

    def test_rejects_request_argname(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(json.dumps([{"meta_data": {}, "req": {}, "expect": {}}]), encoding="utf-8")

        with pytest.raises(ValueError, match="reserved by pytest"):

            @parametrize_from(path, argname="meta_data,request,expect")
            def test_fn(meta_data, request, expect):
                return request

    def test_empty_case_list(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(json.dumps([]), encoding="utf-8")

        @parametrize_from(path)
        def test_fn(meta_data, req, expect, test_data):
            return None

        mark = test_fn.pytestmark[0]
        assert mark.kwargs["ids"] == []
        assert mark.args[1] == []

    def test_multiple_cases_expand(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(
            json.dumps(
                [
                    {"meta_data": {"id": "1"}, "req": {"n": 1}, "expect": {}},
                    {"meta_data": {"id": "2"}, "req": {"n": 2}, "expect": {}},
                ]
            ),
            encoding="utf-8",
        )

        @parametrize_from(path)
        def test_fn(meta_data, req, expect, test_data):
            return req["n"]

        mark = test_fn.pytestmark[0]
        assert mark.kwargs["ids"] == ["1", "2"]
        assert [row[1]["n"] for row in mark.args[1]] == [1, 2]

    def test_meta_data_exclude_preserved_for_assertions(self, tmp_path: Path) -> None:
        path = tmp_path / "c.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "meta_data": {"id": "E1", "exclude": ["requestId"]},
                        "req": {},
                        "expect": {"code": 0},
                    }
                ]
            ),
            encoding="utf-8",
        )

        @parametrize_from(path)
        def test_fn(meta_data, req, expect, test_data):
            return meta_data

        meta = test_fn.pytestmark[0].args[1][0][0]
        assert meta["exclude"] == ["requestId"]


# ---------------------------------------------------------------------------
# Extension — subclass Parametrize
# ---------------------------------------------------------------------------


class TestParametrizeExtension:
    def test_subclass_default_argnames_and_passthrough(self, tmp_path: Path) -> None:
        path = tmp_path / "t.json"
        path.write_text(
            json.dumps([{"id": "C1", "left": 1, "right": 2, "expected": 3}]),
            encoding="utf-8",
        )

        class CalcParametrize(Parametrize):
            default_argnames = ("left", "right", "expected")
            passthrough = True

        @CalcParametrize()(path)
        def test_add(left, right, expected):
            return left + right == expected

        mark = test_add.pytestmark[0]
        assert mark.args[0] == "left,right,expected"
        assert mark.kwargs["ids"] == ["C1"]
        assert mark.args[1][0] == (1, 2, 3)

    def test_decorator_passthrough_overrides_class_false(self, tmp_path: Path) -> None:
        path = tmp_path / "t.json"
        path.write_text(
            json.dumps([{"id": "P1", "username": "a", "expect_code": 0}]),
            encoding="utf-8",
        )

        class DefaultShape(Parametrize):
            passthrough = False

        @DefaultShape()(path, argname="username,expect_code", passthrough=True)
        def test_login(username, expect_code):
            return username, expect_code

        assert test_login.pytestmark[0].args[1][0] == ("a", 0)

    def test_override_normalize_case(self, tmp_path: Path) -> None:
        path = tmp_path / "t.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "id": "N1",
                        "user": {"name": "admin", "pwd": "x"},
                        "assert": {"code": 0},
                    }
                ]
            ),
            encoding="utf-8",
        )

        class Nested(Parametrize):
            default_argnames = ("username", "password", "expect_code")

            def normalize_case(self, case: dict[str, Any]) -> dict[str, Any]:
                return {
                    "id": case["id"],
                    "username": case["user"]["name"],
                    "password": case["user"]["pwd"],
                    "expect_code": case["assert"]["code"],
                }

        @Nested()(path)
        def test_login(username, password, expect_code):
            return username, password, expect_code

        assert test_login.pytestmark[0].args[1][0] == ("admin", "x", 0)

    def test_override_filter_cases(self, tmp_path: Path) -> None:
        path = tmp_path / "t.json"
        path.write_text(
            json.dumps(
                [
                    {"meta_data": {"id": "on", "enabled": True}, "req": {"n": 1}, "expect": {}},
                    {"meta_data": {"id": "off", "enabled": False}, "req": {"n": 2}, "expect": {}},
                ]
            ),
            encoding="utf-8",
        )

        class OnlyEnabled(Parametrize):
            def filter_cases(self, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
                return [c for c in cases if c["meta_data"].get("enabled", True)]

        @OnlyEnabled()(path)
        def test_fn(meta_data, req, expect, test_data):
            return req["n"]

        mark = test_fn.pytestmark[0]
        assert mark.kwargs["ids"] == ["on"]
        assert len(mark.args[1]) == 1

    def test_override_arg_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "t.json"
        path.write_text(
            json.dumps([{"id": "F1", "payload": {"a": 1}, "checks": {"ok": True}}]),
            encoding="utf-8",
        )

        class Mapped(Parametrize):
            default_argnames = ("body", "assert_body")
            arg_fields = {"body": "payload", "assert_body": "checks"}
            passthrough = True

        @Mapped()(path)
        def test_fn(body, assert_body):
            return body, assert_body

        assert test_fn.pytestmark[0].args[1][0] == ({"a": 1}, {"ok": True})

    def test_override_case_id(self, tmp_path: Path) -> None:
        path = tmp_path / "t.json"
        path.write_text(
            json.dumps(
                [{"meta_data": {"id": "raw", "env": "test"}, "req": {}, "expect": {}}]
            ),
            encoding="utf-8",
        )

        class PrefixedId(Parametrize):
            def case_id(self, case: dict[str, Any], index: int, id_key: str) -> str:
                base = super().case_id(case, index, id_key)
                env = (case.get("meta_data") or {}).get("env", "")
                return f"{base}@{env}" if env else base

        @PrefixedId()(path)
        def test_fn(meta_data, req, expect, test_data):
            return meta_data

        assert test_fn.pytestmark[0].kwargs["ids"] == ["raw@test"]

    def test_override_row_values(self, tmp_path: Path) -> None:
        path = tmp_path / "t.json"
        path.write_text(
            json.dumps([{"meta_data": {"id": "R1"}, "req": {"n": 5}, "expect": {}}]),
            encoding="utf-8",
        )

        class DoubledReq(Parametrize):
            def row_values(
                self, case: dict[str, Any], argnames: tuple[str, ...]
            ) -> tuple[Any, ...]:
                values = list(super().row_values(case, argnames))
                # double req dict's n for demo
                idx = argnames.index("req")
                req = dict(values[idx])
                req["n"] = req["n"] * 2
                values[idx] = req
                return tuple(values)

        @DoubledReq()(path)
        def test_fn(meta_data, req, expect, test_data):
            return req["n"]

        assert test_fn.pytestmark[0].args[1][0][1] == {"n": 10}

    def test_override_resolve_path(self, tmp_path: Path) -> None:
        fixed = tmp_path / "fixed.json"
        fixed.write_text(
            json.dumps([{"meta_data": {"id": "FIXED"}, "req": {}, "expect": {}}]),
            encoding="utf-8",
        )

        class FixedPath(Parametrize):
            def resolve_path(self, module_file: str | Path) -> Path:
                return fixed

        # No path arg → uses resolve_path
        @FixedPath()
        def test_fn(meta_data, req, expect, test_data):
            return meta_data["id"]

        assert test_fn.pytestmark[0].kwargs["ids"] == ["FIXED"]

    def test_override_load_raw_cases(self, tmp_path: Path) -> None:
        path = tmp_path / "ignored.json"
        path.write_text(json.dumps([]), encoding="utf-8")

        class InlineCases(Parametrize):
            def load_raw_cases(self, file_path, **kwargs):  # type: ignore[no-untyped-def]
                return [
                    {"meta_data": {"id": "INLINE"}, "req": {"n": 7}, "expect": {}},
                ]

        @InlineCases()(path)
        def test_fn(meta_data, req, expect, test_data):
            return req["n"]

        mark = test_fn.pytestmark[0]
        assert mark.kwargs["ids"] == ["INLINE"]
        assert mark.args[1][0][1] == {"n": 7}

    def test_override_prepare_case(self, tmp_path: Path) -> None:
        path = tmp_path / "t.json"
        path.write_text(
            json.dumps([{"id": "P1", "value": 1}]),
            encoding="utf-8",
        )

        class AlwaysWrap(Parametrize):
            default_argnames = ("value",)
            passthrough = True  # would normally skip normalize

            def prepare_case(self, case: dict[str, Any], *, passthrough: bool) -> dict[str, Any]:
                # ignore passthrough flag; always wrap
                return {"id": case["id"], "value": case["value"] * 10}

        @AlwaysWrap()(path)
        def test_fn(value):
            return value

        assert test_fn.pytestmark[0].args[1][0] == (10,)
