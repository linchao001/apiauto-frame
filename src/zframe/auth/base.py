"""Auth provider interface.

Case repositories subclass :class:`AuthProvider` and register factories via
``register_auth`` / ``auth.type``. The framework ships only :class:`NoAuth`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zframe.client.http import HttpClient


class AuthProvider(ABC):
    """Auth strategy applied by HttpClient before each request."""

    @abstractmethod
    def ensure_auth(self, client: HttpClient) -> None:
        """Obtain / refresh credentials before a request."""

    @abstractmethod
    def apply(self, request: dict[str, Any]) -> dict[str, Any]:
        """Mutate prepared request (headers, params, body signature, etc.)."""


class NoAuth(AuthProvider):
    def ensure_auth(self, client: HttpClient) -> None:
        return None

    def apply(self, request: dict[str, Any]) -> dict[str, Any]:
        return request
