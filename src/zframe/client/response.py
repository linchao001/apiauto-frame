"""Response wrapper around httpx.Response."""

from __future__ import annotations

from typing import Any

import httpx
from jsonpath_ng import parse as jsonpath_parse


class Response:
    """Uniform response view for assertions, extraction, and reporting."""

    def __init__(self, raw: httpx.Response, *, elapsed_ms: float | None = None) -> None:
        self._raw = raw
        self.elapsed_ms = elapsed_ms if elapsed_ms is not None else raw.elapsed.total_seconds() * 1000

    @property
    def raw(self) -> httpx.Response:
        return self._raw

    @property
    def status_code(self) -> int:
        return self._raw.status_code

    @property
    def headers(self) -> httpx.Headers:
        return self._raw.headers

    @property
    def text(self) -> str:
        return self._raw.text

    @property
    def content(self) -> bytes:
        return self._raw.content

    @property
    def url(self) -> httpx.URL:
        return self._raw.url

    @property
    def request(self) -> httpx.Request:
        return self._raw.request

    def json(self) -> Any:
        return self._raw.json()

    def extract(self, path: str, default: Any = None) -> Any:
        """Extract value with JSONPath from JSON body."""
        try:
            data = self.json()
        except Exception:
            return default
        matches = [m.value for m in jsonpath_parse(path).find(data)]
        if not matches:
            return default
        return matches[0] if len(matches) == 1 else matches

    def to_dict(self) -> dict[str, Any]:
        body: Any
        try:
            body = self.json()
        except Exception:
            body = self.text
        return {
            "status_code": self.status_code,
            "url": str(self.url),
            "headers": dict(self.headers),
            "elapsed_ms": round(self.elapsed_ms, 2),
            "body": body,
        }
