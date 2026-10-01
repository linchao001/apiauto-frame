import json
import importlib.util
import sys
from pathlib import Path
from typing import Any

from zframe import Parametrize, load_cases, parametrize_from
from zframe.data.loader import resolve_data_path, select_cases


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_load_cases_json(tmp_path: Path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps([{"id": "c1", "expect": 1}, {"id": "c2", "expect": 2}]),
        encoding="utf-8",
    )
    cases = load_cases(path)
    assert len(cases) == 2
    assert cases[0]["id"] == "c1"


def test_parametrize_from_ids(tmp_path: Path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "meta_data": {"id": "alpha"},
                    "req": {"n": 1},
                    "expect": {"ok": True},
                }
            ]
        ),
        encoding="utf-8",
    )

    @parametrize_from(path)
    def _sample(meta_data, req, expect, test_data):
        return req["n"]

    mark = _sample.pytestmark[0]
    assert mark.name == "parametrize"
    assert mark.args[0] == "meta_data,req,expect,test_data"
    assert mark.kwargs["ids"] == ["alpha"]
    assert mark.args[1][0] == ({"id": "alpha"}, {"n": 1}, {"ok": True}, {})


def test_parametrize_from_normalizes_legacy_flat_case(tmp_path: Path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps([{"id": "legacy", "title": "t", "request": {"a": 1}, "response": {"b": 2}}]),
        encoding="utf-8",
    )

    @parametrize_from(path)
    def _sample(meta_data, req, expect, test_data):
        return meta_data, req, expect, test_data

    row = _sample.pytestmark[0].args[1][0]
    assert row == ({"id": "legacy", "title": "t"}, {"a": 1}, {"b": 2}, {})


def test_resolve_data_path_sibling_testdata(tmp_path: Path):
    """Prefer sibling testdata/ of enclosing testcases/ (product module layout)."""
    module_root = tmp_path / "acme" / "WEB"
    testcases = module_root / "testcases"
    testdata = module_root / "testdata"
    testcases.mkdir(parents=True)
    testdata.mkdir(parents=True)
    module = testcases / "test_echo.py"
    module.write_text("# placeholder\n", encoding="utf-8")
    data_file = testdata / "test_echo.json"
    data_file.write_text(json.dumps({"test_echo": []}), encoding="utf-8")

    assert resolve_data_path(module) == data_file.resolve()


def test_resolve_data_path_prefers_json_over_yaml(tmp_path: Path):
    testcases = tmp_path / "testcases"
    testdata = tmp_path / "testdata"
    testcases.mkdir()
    testdata.mkdir()
    module = testcases / "test_echo.py"
    module.write_text("# placeholder\n", encoding="utf-8")
    json_file = testdata / "test_echo.json"
    yaml_file = testdata / "test_echo.yaml"
    json_file.write_text(json.dumps({"test_echo": [{"id": "from_json"}]}), encoding="utf-8")
    yaml_file.write_text("test_echo:\n  - id: from_yaml\n", encoding="utf-8")

    assert resolve_data_path(module) == json_file.resolve()


def test_resolve_data_path_legacy_data_dir(tmp_path: Path):
    testcases = tmp_path / "testcases"
    data = tmp_path / "data"
    testcases.mkdir()
    data.mkdir()
    module = testcases / "test_echo.py"
    module.write_text("# placeholder\n", encoding="utf-8")
    data_file = data / "test_echo.json"
    data_file.write_text(json.dumps({"test_echo": []}), encoding="utf-8")

    assert resolve_data_path(module) == data_file.resolve()


def test_load_cases_by_method_name(tmp_path: Path):
    path = tmp_path / "test_echo.json"
    path.write_text(
        json.dumps(
            {
                "test_echo": [{"id": "a", "n": 1}],
                "test_other": [{"id": "b", "n": 2}],
            }
        ),
        encoding="utf-8",
    )
    cases = load_cases(path, method="test_echo")
    assert len(cases) == 1
    assert cases[0]["id"] == "a"


def test_load_cases_by_class_nesting(tmp_path: Path):
    path = tmp_path / "test_echo.json"
    path.write_text(
        json.dumps({"TestEcho": {"test_echo": [{"id": "nested", "n": 3}]}}),
        encoding="utf-8",
    )
    cases = load_cases(path, method="test_echo", qualname="TestEcho.test_echo")
    assert cases[0]["id"] == "nested"


def test_parametrize_from_auto_resolve(tmp_path: Path):
    testcases = tmp_path / "testcases"
    testdata = tmp_path / "testdata"
    testcases.mkdir()
    testdata.mkdir()
    module = testcases / "test_auto.py"
    module.write_text(
        "from zframe import parametrize_from\n"
        "\n"
        "class TestAuto:\n"
        "    @parametrize_from\n"
        "    def test_sample(self, meta_data, req, expect, test_data):\n"
        "        return req['n']\n",
        encoding="utf-8",
    )
    (testdata / "test_auto.json").write_text(
        json.dumps(
            {
                "test_sample": [
                    {
                        "meta_data": {"id": "auto"},
                        "req": {"n": 9},
                        "expect": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    mod = _load_module(module, "test_auto_mod")
    mark = mod.TestAuto.test_sample.pytestmark[0]
    assert mark.name == "parametrize"
    assert mark.kwargs["ids"] == ["auto"]
    assert mark.args[1][0][1]["n"] == 9


def test_select_cases_qualname_key(tmp_path: Path):
    data = {
        "TestEcho.test_echo": [{"id": "q"}],
        "test_echo": [{"id": "m"}],
    }
    cases = select_cases(
        data,
        path=tmp_path / "x.json",
        method="test_echo",
        qualname="TestEcho.test_echo",
    )
    assert cases[0]["id"] == "q"


def test_load_cases_legacy_yaml(tmp_path: Path):
    path = tmp_path / "cases.yaml"
    path.write_text(
        "- id: c1\n  expect: 1\n- id: c2\n  expect: 2\n",
        encoding="utf-8",
    )
    cases = load_cases(path)
    assert len(cases) == 2
    assert cases[0]["id"] == "c1"


def test_passthrough_custom_structure(tmp_path: Path):
    """Non-default JSON keys inject as test params via passthrough."""
    path = tmp_path / "login.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "L1",
                    "username": "admin",
                    "password": "secret",
                    "expect_code": 0,
                }
            ]
        ),
        encoding="utf-8",
    )

    @parametrize_from(path, argname="username,password,expect_code", passthrough=True)
    def test_login(username, password, expect_code):
        return username, password, expect_code

    mark = test_login.pytestmark[0]
    assert mark.args[0] == "username,password,expect_code"
    assert mark.kwargs["ids"] == ["L1"]
    assert mark.args[1][0] == ("admin", "secret", 0)


def test_custom_parametrize_subclass(tmp_path: Path):
    """Reusable engine: custom args, passthrough, filter_cases, arg_fields."""
    path = tmp_path / "table.json"
    path.write_text(
        json.dumps(
            {
                "test_add": [
                    {"id": "A1", "left": 1, "right": 2, "sum": 3, "enabled": True},
                    {"id": "A-skip", "left": 0, "right": 0, "sum": 1, "enabled": False},
                    {"id": "A2", "left": 4, "right": 5, "sum": 9, "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )

    class TableParametrize(Parametrize):
        default_argnames = ("left", "right", "sum")
        passthrough = True

        def filter_cases(self, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [c for c in cases if c.get("enabled", True)]

    engine = TableParametrize()

    @engine(path)
    def test_add(left, right, sum):
        return left + right == sum

    mark = test_add.pytestmark[0]
    assert mark.args[0] == "left,right,sum"
    assert mark.kwargs["ids"] == ["A1", "A2"]
    assert mark.args[1] == [(1, 2, 3), (4, 5, 9)]


def test_custom_normalize_with_arg_fields(tmp_path: Path):
    """Reshape nested JSON then map params via arg_fields."""
    path = tmp_path / "nested.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "N1",
                    "payload": {"a": 1},
                    "checks": {"ok": True},
                }
            ]
        ),
        encoding="utf-8",
    )

    class NestedParametrize(Parametrize):
        default_argnames = ("body", "assert_body")
        arg_fields = {"body": "payload", "assert_body": "checks"}

        def normalize_case(self, case: dict[str, Any]) -> dict[str, Any]:
            return {
                "id": case.get("id"),
                "payload": case["payload"],
                "checks": case["checks"],
            }

    engine = NestedParametrize()

    @engine(path)
    def test_nested(body, assert_body):
        return body, assert_body

    mark = test_nested.pytestmark[0]
    assert mark.kwargs["ids"] == ["N1"]
    assert mark.args[1][0] == ({"a": 1}, {"ok": True})
