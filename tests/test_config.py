from pathlib import Path

import pytest

from zframe.config.loader import (
    DEFAULT_ENV,
    discover_config_root,
    discover_envs,
    load_settings,
    resolve_env_name,
)
from zframe.utils.dictutil import deep_merge


def test_deep_merge_nested():
    base = {"http": {"timeout": 30, "base_url": "a"}, "vars": {"x": 1}}
    override = {"http": {"base_url": "b"}, "vars": {"y": 2}}
    merged = deep_merge(base, override)
    assert merged["http"]["timeout"] == 30
    assert merged["http"]["base_url"] == "b"
    assert merged["vars"] == {"x": 1, "y": 2}


def test_load_settings_layers(tmp_path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text(
        "product: sample\nhttp:\n  timeout: 10\n  max_retries: 2\nvars:\n  a: 1\n",
        encoding="utf-8",
    )
    (config / "env" / "test.yaml").write_text(
        "http:\n  base_url: https://example.com\nvars:\n  b: 2\n",
        encoding="utf-8",
    )
    settings = load_settings(env="test", config_dir=config, overrides={"vars": {"c": 3}})
    assert settings.product == "sample"
    assert settings.env == "test"
    assert settings.http.base_url == "https://example.com"
    assert settings.http.timeout == 10
    assert settings.http.max_retries == 2
    assert settings.vars == {"a": 1, "b": 2, "c": 3}
    assert settings.assertx.allow_extra is True
    assert settings.assertx.mode == "loose"


def test_load_settings_assertx(tmp_path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text(
        "product: sample\nassertx:\n  exclude:\n    - requestId\n  mode: strict\n",
        encoding="utf-8",
    )
    (config / "env" / "test.yaml").write_text(
        "assertx:\n  exclude:\n    - timestamp\n  allow_extra: false\n",
        encoding="utf-8",
    )
    settings = load_settings(env="test", config_dir=config)
    assert settings.assertx.mode == "strict"
    assert settings.assertx.allow_extra is False
    assert settings.assertx.exclude == ["timestamp"]


def test_discover_config_root_walks_up(tmp_path: Path):
    config = tmp_path / "config"
    nested = tmp_path / "testcases"
    config.mkdir()
    nested.mkdir()
    assert discover_config_root(nested) == config.resolve()


def test_discover_envs(tmp_path: Path):
    config = tmp_path / "config"
    env_dir = config / "env"
    env_dir.mkdir(parents=True)
    (env_dir / "uat.yaml").write_text("vars:\n  x: 1\n", encoding="utf-8")
    (env_dir / "dev.yml").write_text("vars:\n  y: 2\n", encoding="utf-8")
    (env_dir / "readme.txt").write_text("ignore", encoding="utf-8")
    assert discover_envs(config) == ["dev", "uat"]


def test_resolve_env_name_priority_and_auto():
    assert resolve_env_name(explicit="uat", configured="dev", available=["dev", "uat"]) == "uat"
    assert resolve_env_name(configured="dev", available=["dev", "uat"]) == "dev"
    assert resolve_env_name(available=["staging"]) == "staging"
    assert resolve_env_name(available=[]) == DEFAULT_ENV
    with pytest.raises(FileNotFoundError, match="available: dev, uat"):
        resolve_env_name(available=["dev", "uat"])
    with pytest.raises(FileNotFoundError, match="available: dev, uat"):
        resolve_env_name(explicit="prod", available=["dev", "uat"])


def test_load_settings_auto_picks_sole_env(tmp_path: Path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text("product: sample\n", encoding="utf-8")
    (config / "env" / "staging.yaml").write_text(
        "http:\n  base_url: https://staging.example\n",
        encoding="utf-8",
    )
    settings = load_settings(config_dir=config)
    assert settings.env == "staging"
    assert settings.http.base_url == "https://staging.example"


def test_load_settings_default_test_when_multiple(tmp_path: Path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text("product: sample\n", encoding="utf-8")
    (config / "env" / "test.yaml").write_text(
        "http:\n  base_url: https://test.example\n",
        encoding="utf-8",
    )
    (config / "env" / "uat.yaml").write_text(
        "http:\n  base_url: https://uat.example\n",
        encoding="utf-8",
    )
    settings = load_settings(config_dir=config)
    assert settings.env == "test"
    assert settings.http.base_url == "https://test.example"


def test_load_settings_unknown_env_lists_available(tmp_path: Path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text("product: sample\n", encoding="utf-8")
    (config / "env" / "uat.yaml").write_text("vars: {}\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="available: uat"):
        load_settings(env="prod", config_dir=config)


def test_load_settings_db_flat(tmp_path: Path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text("product: sample\n", encoding="utf-8")
    (config / "env" / "test.yaml").write_text(
        "db:\n  host: 10.0.0.1\n  user: root\n  password: p\n  database: app\n",
        encoding="utf-8",
    )
    settings = load_settings(env="test", config_dir=config)
    assert settings.db.enabled
    assert settings.db.host == "10.0.0.1"
    assert settings.db.database == "app"


def test_load_settings_db_host_falls_back_to_base_url(tmp_path: Path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text("product: sample\n", encoding="utf-8")
    (config / "env" / "test.yaml").write_text(
        "http:\n"
        "  base_url: http://192.168.1.10:8080\n"
        "db:\n"
        "  user: root\n"
        "  password: p\n"
        "  database: app\n"
        "ssh:\n"
        "  user: deploy\n"
        "  password: deploy\n",
        encoding="utf-8",
    )
    settings = load_settings(env="test", config_dir=config)
    assert settings.db.host == "192.168.1.10"
    assert settings.ssh.host == "192.168.1.10"


def test_load_settings_db_with_ssh(tmp_path: Path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text("product: sample\n", encoding="utf-8")
    (config / "env" / "test.yaml").write_text(
        "db:\n"
        "  host: 10.0.0.1\n"
        "  user: root\n"
        "  password: Test@123\n"
        "  database: app\n"
        "ssh:\n"
        "  user: deploy\n"
        "  password: deploy\n",
        encoding="utf-8",
    )
    settings = load_settings(env="test", config_dir=config)
    assert settings.ssh.enabled
    assert settings.ssh.user == "deploy"
    assert settings.ssh.password == "deploy"
    assert settings.ssh.host == "10.0.0.1"  # fallback from db.host


def test_load_settings_legacy_db_ssh_migrated(tmp_path: Path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text("product: sample\n", encoding="utf-8")
    (config / "env" / "test.yaml").write_text(
        "db:\n"
        "  host: 10.0.0.1\n"
        "  user: root\n"
        "  password: p\n"
        "  database: app\n"
        "  ssh:\n"
        "    user: deploy\n"
        "    password: deploy\n",
        encoding="utf-8",
    )
    settings = load_settings(env="test", config_dir=config)
    assert settings.ssh.user == "deploy"
    assert settings.ssh.host == "10.0.0.1"


def test_load_settings_db_rejects_named(tmp_path: Path):
    config = tmp_path / "config"
    (config / "env").mkdir(parents=True)
    (config / "product.yaml").write_text("product: sample\n", encoding="utf-8")
    (config / "env" / "test.yaml").write_text(
        "db:\n"
        "  default:\n"
        "    host: 127.0.0.1\n"
        "    database: app\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="single flat connection"):
        load_settings(env="test", config_dir=config)
