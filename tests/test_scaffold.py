"""Case-repo scaffold generates a neutral skeleton."""

from __future__ import annotations

from pathlib import Path

import pytest

from zframe.cli import main
from zframe.scaffold import ScaffoldError, derive_package_name, scaffold_case_repo


def test_derive_package_name():
    assert derive_package_name("acme-api-auto") == "acme"
    assert derive_package_name("acme") == "acme"
    assert derive_package_name("123-bad") == "p_123_bad"


def test_scaffold_writes_neutral_tree(tmp_path: Path):
    dest = tmp_path / "acme-api-auto"
    result = scaffold_case_repo(dest=dest)

    assert result.dest == dest.resolve()
    assert result.package == "acme"
    assert (dest / "auth.py").is_file()
    assert (dest / "conftest.py").is_file()
    assert (dest / "helpers" / "logging.py").is_file()
    assert (dest / "config" / "env" / "dev.yaml").is_file()
    assert (
        dest / "acme" / "WEB" / "API" / "Sample" / "testcases" / "test_sample.py"
    ).is_file()
    assert (
        dest / "acme" / "WEB" / "E2E" / "Sample" / "testcases" / "test_sample_flow.py"
    ).is_file()
    assert (dest / "acme" / "WEB" / "services" / "sample_api.py").is_file()

    auth_text = (dest / "auth.py").read_text(encoding="utf-8")
    assert "AuthProvider" in auth_text
    assert "ProductAuth" in auth_text
    conf = (dest / "conftest.py").read_text(encoding="utf-8")
    assert "register_auth" in conf
    assert 'register_auth("acme"' in conf
    env = (dest / "config" / "env" / "dev.yaml").read_text(encoding="utf-8")
    assert "type: none" in env
    assert "httpbin.org" in env
    api_test = (
        dest / "acme" / "WEB" / "API" / "Sample" / "testcases" / "test_sample.py"
    ).read_text(encoding="utf-8")
    assert "parametrize_from" in api_test
    assert "mark.skip" not in api_test
    sample_api = (dest / "acme" / "WEB" / "services" / "sample_api.py").read_text(
        encoding="utf-8"
    )
    assert "get_echo" in sample_api
    assert "post_echo" in sample_api

def test_scaffold_refuses_existing(tmp_path: Path):
    dest = tmp_path / "exists"
    dest.mkdir()
    (dest / "marker.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ScaffoldError, match="already exists"):
        scaffold_case_repo(dest=dest)

    result = scaffold_case_repo(dest=dest, force=True)
    assert (result.dest / "auth.py").is_file()
    assert not (result.dest / "marker.txt").exists()


def test_cli_help_exits_zero():
    assert main([]) == 0
    with pytest.raises(SystemExit) as exc:
        main(["-h"])
    assert exc.value.code == 0


def test_cli_init_requires_name():
    with pytest.raises(SystemExit) as exc:
        main(["--init"])
    assert exc.value.code == 2


def test_cli_init_no_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    assert main(["--init", "--name", "acme-api-auto"]) == 0
    assert (tmp_path / "acme-api-auto" / "auth.py").is_file()
    with pytest.raises(SystemExit) as exc:
        main(["--init", "--line", "demo", "--name", "x"])
    assert exc.value.code == 2
