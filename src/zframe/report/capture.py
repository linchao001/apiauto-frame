"""Capture last HTTP response for the active pytest item (no pytest import)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_current_item: ContextVar[Any | None] = ContextVar("zframe_pytest_item", default=None)


def bind_test_item(item: Any) -> Token[Any | None]:
    """Bind the current pytest item for the duration of a test."""
    return _current_item.set(item)


def reset_test_item(token: Token[Any | None]) -> None:
    _current_item.reset(token)


def get_test_item() -> Any | None:
    return _current_item.get()


def remember_response(item: Any, response: Any) -> None:
    """Store ``response`` on ``item`` for failure attachment."""
    item._zframe_last_response = response  # type: ignore[attr-defined]


def remember_last_response(response: Any) -> None:
    """Record response on the active pytest item; no-op outside a test."""
    item = get_test_item()
    if item is not None:
        remember_response(item, response)


def get_remembered_response(item: Any) -> Any | None:
    return getattr(item, "_zframe_last_response", None)
