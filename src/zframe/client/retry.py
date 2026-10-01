"""HTTP request retry configuration and helper."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Iterable

import httpx


@dataclass
class RetryConfig:
    """Request-level retry for transport / gateway instability."""

    max_retries: int = 0
    backoff_factor: float = 0.5
    max_backoff: float = 8.0
    jitter: bool = True
    retry_on_status: tuple[int, ...] = (502, 503, 504)
    retry_methods: tuple[str, ...] = ("GET", "HEAD", "OPTIONS", "PUT", "DELETE")
    retry_exceptions: tuple[type[BaseException], ...] = field(
        default_factory=lambda: (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        )
    )

    def should_retry_method(self, method: str) -> bool:
        return method.upper() in {m.upper() for m in self.retry_methods}

    def should_retry_status(self, status_code: int) -> bool:
        return status_code in self.retry_on_status

    def sleep(self, attempt: int) -> None:
        delay = min(self.backoff_factor * (2**attempt), self.max_backoff)
        if self.jitter:
            delay = delay * (0.5 + random.random() / 2)
        time.sleep(delay)


def is_retryable_exception(exc: BaseException, retryable: Iterable[type[BaseException]]) -> bool:
    return isinstance(exc, tuple(retryable))
