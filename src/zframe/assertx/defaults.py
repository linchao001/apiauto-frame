"""Session assert defaults (bound from Settings by the pytest plugin)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zframe.config.models import AssertSettings

_assert_settings: ContextVar[AssertSettings | None] = ContextVar(
    "zframe_assert_settings",
    default=None,
)


def bind_assert_settings(settings: AssertSettings) -> Token[AssertSettings | None]:
    return _assert_settings.set(settings)


def reset_assert_settings(token: Token[AssertSettings | None]) -> None:
    _assert_settings.reset(token)


def get_assert_settings() -> AssertSettings:
    from zframe.config.models import AssertSettings

    current = _assert_settings.get()
    return current if current is not None else AssertSettings()
