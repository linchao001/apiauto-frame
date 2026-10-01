"""Tests for @pytest.mark.device filtering and parallel runner helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from zframe.parallel import (
    build_pytest_command,
    resolve_target_envs,
)
from zframe.plugin.device_filter import deselect_for_env, should_run_on_env


class _FakeItem:
    def __init__(self, *devices: str):
        self._devices = devices

    def get_closest_marker(self, name: str):
        if name != "device" or not self._devices:
            return None

        class _M:
            args = self._devices
            kwargs: dict = {}

        return _M()


def test_should_run_on_env_unmarked():
    assert should_run_on_env(_FakeItem(), "dev") is True


def test_should_run_on_env_marked():
    item = _FakeItem("dev", "env-c")
    assert should_run_on_env(item, "dev") is True
    assert should_run_on_env(item, "env-c") is True
    assert should_run_on_env(item, "env-b") is False


def test_deselect_for_env():
    a = _FakeItem()
    b = _FakeItem("dev")
    c = _FakeItem("env-b")
    kept, deselected = deselect_for_env([a, b, c], "dev")  # type: ignore[arg-type]
    assert kept == [a, b]
    assert deselected == [c]


def test_resolve_target_envs_explicit():
    assert resolve_target_envs(envs=["dev", "dev", "env-c"]) == [
        "dev",
        "env-c",
    ]


def test_resolve_target_envs_all(tmp_path: Path):
    config = tmp_path / "config"
    env_dir = config / "env"
    env_dir.mkdir(parents=True)
    (env_dir / "dev.yaml").write_text("vars: {}\n", encoding="utf-8")
    (env_dir / "env-b.yaml").write_text("vars: {}\n", encoding="utf-8")
    assert resolve_target_envs(all_envs=True, config_dir=config) == ["dev", "env-b"]


def test_resolve_target_envs_requires_choice():
    with pytest.raises(ValueError, match="--envs"):
        resolve_target_envs()


def test_build_pytest_command_injects_env(tmp_path: Path):
    cmd = build_pytest_command(
        "dev",
        ["-q", "tests"],
        config_dir=tmp_path,
        python="python",
    )
    assert cmd[:3] == ["python", "-m", "pytest"]
    assert "--env" in cmd and cmd[cmd.index("--env") + 1] == "dev"
    assert "--config-dir" in cmd and cmd[cmd.index("--config-dir") + 1] == str(tmp_path)
