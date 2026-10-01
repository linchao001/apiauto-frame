"""Generic poll-until-predicate helpers for async side effects."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PollResult:
    """Outcome of a successful :func:`wait_until` call."""

    label: str
    elapsed_sec: float
    attempts: int
    last_snapshot: Any = None


def wait_until(
    label: str,
    predicate: Callable[[], bool],
    *,
    timeout_sec: float = 30.0,
    interval_sec: float = 0.5,
    on_poll: Callable[[], Any] | None = None,
) -> PollResult:
    """Poll ``predicate`` until it returns true or ``timeout_sec`` elapses.

    ``on_poll`` is called after each ``predicate`` evaluation to capture the
    latest observable snapshot for diagnostics (typically the same cached value
    the predicate just read).

    Raises ``AssertionError`` on timeout with label, elapsed time, attempts,
    and the last snapshot embedded in the message.
    """
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be positive")
    if interval_sec <= 0:
        raise ValueError("interval_sec must be positive")

    deadline = time.monotonic() + timeout_sec
    attempts = 0
    last_snapshot: Any = None
    start = time.monotonic()

    while True:
        attempts += 1
        if predicate():
            if on_poll is not None:
                last_snapshot = on_poll()
            elapsed = time.monotonic() - start
            return PollResult(
                label=label,
                elapsed_sec=elapsed,
                attempts=attempts,
                last_snapshot=last_snapshot,
            )

        if on_poll is not None:
            last_snapshot = on_poll()

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            elapsed = time.monotonic() - start
            raise AssertionError(
                f"wait_until timed out: {label!r} "
                f"(timeout={timeout_sec}s, elapsed={elapsed:.2f}s, "
                f"attempts={attempts}, last_snapshot={last_snapshot!r})"
            )

        time.sleep(min(interval_sec, remaining))
