"""Build AuthProvider from settings via a type registry.

Builtin providers are not shipped — case repos ``register_auth`` their own
``AuthProvider`` subclasses and select them with ``auth.type``.
"""

from __future__ import annotations

from typing import Any, Callable

from zframe.auth.base import AuthProvider, NoAuth
from zframe.config.models import Settings

AuthFactory = Callable[[dict[str, Any]], AuthProvider]

_REGISTRY: dict[str, AuthFactory] = {}


def register_auth(kind: str, factory: AuthFactory) -> None:
    """Register or override an auth provider factory for ``auth.type``."""
    key = kind.strip().lower()
    if not key:
        raise ValueError("auth type name must be non-empty")
    _REGISTRY[key] = factory


def registered_auth_types() -> list[str]:
    return sorted(_REGISTRY)


def build_auth(settings: Settings | dict[str, Any]) -> AuthProvider:
    """Create an AuthProvider from ``Settings.auth`` or a raw auth dict.

    Unknown ``auth.type`` raises ``ValueError`` so misconfiguration fails fast.
    """
    if isinstance(settings, Settings):
        cfg = dict(settings.auth or {})
    else:
        cfg = dict(settings or {})

    kind = str(cfg.get("type") or cfg.get("kind") or "none").strip().lower()
    if kind in {"", "none", "noauth"}:
        return NoAuth()

    factory = _REGISTRY.get(kind)
    if factory is None:
        known = ", ".join(registered_auth_types()) or "(none)"
        raise ValueError(f"Unknown auth type {kind!r}. Registered: {known}")
    return factory(cfg)
