"""Soft assertion collector."""

from __future__ import annotations

from typing import Any, Callable

from zframe.assertx.checkers import AssertionErrorX


class SoftAssertions:
    """Collect multiple assertion failures and raise once at ``assert_all``."""

    def __init__(self) -> None:
        self._failures: list[str] = []

    def check(self, condition: bool, message: str) -> SoftAssertions:
        if not condition:
            self._failures.append(message)
        return self

    def run(self, fn: Callable[[], Any]) -> SoftAssertions:
        try:
            fn()
        except AssertionError as exc:
            if isinstance(exc, AssertionErrorX):
                self._failures.extend(exc.compact_lines())
            else:
                self._failures.append(str(exc))
        return self

    @property
    def failures(self) -> list[str]:
        return list(self._failures)

    def assert_all(self) -> None:
        if self._failures:
            raise AssertionErrorX(
                label="Soft assertion",
                diffs=self._failures,
            )
