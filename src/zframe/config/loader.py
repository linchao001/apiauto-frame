"""Layered config loader: defaults < product.yaml < env.yaml < overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml

from zframe.config.models import (
    AssertSettings,
    DbSettings,
    HttpSettings,
    NotifySettings,
    Settings,
    SshSettings,
)
from zframe.utils.dictutil import deep_merge

DEFAULT_ENV = "test"

DEFAULTS: dict[str, Any] = {
    "product": "",
    "env": DEFAULT_ENV,
    "http": {
        "base_url": "",
        "timeout": 30.0,
        "verify_ssl": True,
        "default_headers": {},
        "max_retries": 0,
        "retry_backoff": 0.5,
    },
    "auth": {},
    "vars": {},
    "assertx": {
        "mode": "loose",
        "allow_extra": True,
        "exclude": [],
    },
    "db": {},
    "ssh": {},
    "notify": {},
}

_ENV_SUFFIXES = (".yaml", ".yml")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must be a mapping: {path}")
    return data


def discover_config_root(start: Path | None = None) -> Path | None:
    """Walk upward looking for a ``config/`` directory."""
    cur = (start or Path.cwd()).resolve()
    for path in [cur, *cur.parents]:
        candidate = path / "config"
        if candidate.is_dir():
            return candidate
    return None


def discover_envs(config_dir: str | Path) -> list[str]:
    """Return sorted env names discovered under ``config_dir/env/*.y{a}ml``."""
    env_dir = Path(config_dir) / "env"
    if not env_dir.is_dir():
        return []
    names: set[str] = set()
    for path in env_dir.iterdir():
        if path.is_file() and path.suffix.lower() in _ENV_SUFFIXES:
            names.add(path.stem)
    return sorted(names)


def _env_file(root: Path, env_name: str) -> Path | None:
    for suffix in _ENV_SUFFIXES:
        candidate = root / "env" / f"{env_name}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def resolve_env_name(
    *,
    explicit: str | None = None,
    configured: str | None = None,
    available: list[str] | None = None,
    default: str = DEFAULT_ENV,
) -> str:
    """Resolve which env to load.

    Priority: explicit CLI/arg > product.yaml ``env`` > sole discovered file > default.
    When discovered envs exist, the resolved name must be among them.
    """
    found = list(available or [])
    if explicit:
        name = str(explicit)
    elif configured:
        name = str(configured)
    elif len(found) == 1:
        name = found[0]
    else:
        name = default

    if found and name not in found:
        options = ", ".join(found)
        raise FileNotFoundError(f"Unknown env {name!r}; available: {options}")
    return name


def normalize_db_section(
    raw: Any,
    *,
    fallback_host: str = "",
) -> DbSettings:
    """Normalize ``db`` YAML into a single :class:`DbSettings` connection.

    When ``host`` is omitted (or empty), ``fallback_host`` is used — typically
    the hostname from ``http.base_url``.

    Example::

        db:
          database: app
          user: root
          password: secret
    """
    if raw is None or raw == {}:
        return DbSettings()
    if not isinstance(raw, Mapping):
        raise ValueError("Config key 'db' must be a mapping")
    data = dict(raw)
    # Legacy: db.ssh moved to top-level ``ssh``; strip if still present.
    data.pop("ssh", None)
    if any(isinstance(v, Mapping) for v in data.values()):
        raise ValueError(
            "Config key 'db' must be a single flat connection "
            "(multi-DB / named connections are not supported)"
        )
    if not data.get("host") and fallback_host:
        data["host"] = fallback_host
    return DbSettings.model_validate(data)


def normalize_ssh_section(
    raw: Any,
    *,
    fallback_host: str = "",
) -> SshSettings:
    """Normalize ``ssh`` YAML into :class:`SshSettings`.

    Example::

        ssh:
          host: 192.168.1.10
          user: deploy
          password: deploy
    """
    if raw is None or raw == {}:
        data: dict[str, Any] = {}
    elif not isinstance(raw, Mapping):
        raise ValueError("Config key 'ssh' must be a mapping")
    else:
        data = dict(raw)
    if not data.get("host") and fallback_host:
        data["host"] = fallback_host
    return SshSettings.model_validate(data)


def _host_from_http_base_url(base_url: str) -> str:
    if not base_url:
        return ""
    try:
        parsed = urlparse(base_url)
    except Exception:
        return ""
    return parsed.hostname or ""


def _extract_legacy_db_ssh(merged: dict[str, Any]) -> dict[str, Any]:
    """Pull nested ``db.ssh`` into a dict (without mutating caller's db forever)."""
    db_raw = merged.get("db")
    if not isinstance(db_raw, Mapping):
        return {}
    nested = db_raw.get("ssh")
    if isinstance(nested, Mapping):
        return dict(nested)
    return {}


def load_settings(
    *,
    product: str | None = None,
    env: str | None = None,
    config_dir: str | Path | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Settings:
    """Load and merge configuration layers into :class:`Settings`."""
    root = Path(config_dir).resolve() if config_dir else discover_config_root()
    merged: dict[str, Any] = deep_merge({}, DEFAULTS)

    if root is not None:
        product_data = _read_yaml(root / "product.yaml")
        merged = deep_merge(merged, product_data)
        available = discover_envs(root)
        configured = product_data.get("env")
        env_name = resolve_env_name(
            explicit=env,
            configured=str(configured) if configured is not None else None,
            available=available,
        )
        env_path = _env_file(root, env_name)
        if env_path is not None:
            merged = deep_merge(merged, _read_yaml(env_path))
    else:
        env_name = resolve_env_name(explicit=env)

    if product:
        merged["product"] = product
    merged["env"] = env if env else env_name

    if overrides:
        merged = deep_merge(merged, dict(overrides))

    http_data = merged.get("http") or {}
    assert_data = merged.get("assertx") or {}
    notify_data = merged.get("notify") or {}

    http_host = _host_from_http_base_url(str(http_data.get("base_url") or ""))

    legacy_ssh = _extract_legacy_db_ssh(merged)
    db_settings = normalize_db_section(
        merged.get("db"),
        fallback_host=http_host,
    )

    ssh_raw = merged.get("ssh") or {}
    if not ssh_raw and legacy_ssh:
        ssh_raw = legacy_ssh
    elif isinstance(ssh_raw, Mapping) and legacy_ssh:
        # Top-level wins; fill missing keys from legacy db.ssh.
        ssh_raw = {**legacy_ssh, **dict(ssh_raw)}

    if isinstance(ssh_raw, Mapping) and ssh_raw.get("host"):
        ssh_fallback_host = str(ssh_raw["host"])
    elif db_settings.enabled:
        ssh_fallback_host = db_settings.host
    else:
        ssh_fallback_host = http_host

    ssh_settings = normalize_ssh_section(
        ssh_raw,
        fallback_host=ssh_fallback_host,
    )

    return Settings(
        product=str(merged.get("product") or ""),
        env=str(merged.get("env") or DEFAULT_ENV),
        http=HttpSettings.model_validate(http_data),
        auth=dict(merged.get("auth") or {}),
        vars=dict(merged.get("vars") or {}),
        assertx=AssertSettings.model_validate(assert_data),
        db=db_settings,
        ssh=ssh_settings,
        notify=NotifySettings.model_validate(notify_data),
        extra={
            k: v
            for k, v in merged.items()
            if k
            not in {
                "product",
                "env",
                "http",
                "auth",
                "vars",
                "assertx",
                "db",
                "ssh",
                "notify",
            }
        },
    )
