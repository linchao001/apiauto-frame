"""Session-scoped accessors for settings / ctx (no fixture params needed)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zframe.config.models import Settings
    from zframe.context.runtime import Context

_settings: Settings | None = None
_ctx: Context | None = None


def bind_session(settings: Settings, ctx: Context) -> None:
    """Store the session settings/ctx for :func:`get_settings` / :func:`get_ctx`."""
    global _settings, _ctx
    _settings = settings
    _ctx = ctx


def clear_session() -> None:
    global _settings, _ctx
    _settings = None
    _ctx = None


def get_settings() -> Settings:
    """Return the session :class:`~zframe.config.models.Settings`.

    Bound automatically by the pytest plugin; call only during a test run.
    """
    if _settings is None:
        raise RuntimeError(
            "settings is not bound; use within a pytest session "
            "(zframe plugin autouse fixture) or call bind_session() first"
        )
    return _settings


def get_ctx() -> Context:
    """Return the session :class:`~zframe.context.runtime.Context`.

    Bound automatically by the pytest plugin; call only during a test run.
    """
    if _ctx is None:
        raise RuntimeError(
            "ctx is not bound; use within a pytest session "
            "(zframe plugin autouse fixture) or call bind_session() first"
        )
    return _ctx
