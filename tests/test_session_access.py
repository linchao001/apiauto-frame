"""Session accessors for settings / ctx."""

from __future__ import annotations

import pytest

from zframe import Context, Settings, get_ctx, get_settings
from zframe.context import session as session_mod
from zframe.context.session import bind_session, clear_session


@pytest.fixture
def isolated_session():
    """Temporarily clear session state; restore plugin bind afterwards."""
    prev_settings = session_mod._settings
    prev_ctx = session_mod._ctx
    clear_session()
    try:
        yield
    finally:
        session_mod._settings = prev_settings
        session_mod._ctx = prev_ctx


def test_getters_require_bind(isolated_session) -> None:
    with pytest.raises(RuntimeError, match="settings is not bound"):
        get_settings()
    with pytest.raises(RuntimeError, match="ctx is not bound"):
        get_ctx()


def test_bind_and_get(isolated_session) -> None:
    settings = Settings(product="sample", env="test")
    ctx = Context(product="sample", env="test", initial={"k": 1})
    bind_session(settings, ctx)
    assert get_settings() is settings
    assert get_ctx() is ctx
    assert get_ctx().get("k") == 1
