"""Unified HttpClient built on httpx."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator, Mapping

import httpx

from zframe.auth.base import AuthProvider, NoAuth
from zframe.client.hooks import Hook, logging_request_hook, logging_response_hook
from zframe.client.response import Response
from zframe.client.retry import RetryConfig, is_retryable_exception
from zframe.client.ws import WebSocketSession, connect_websocket
from zframe.report.capture import remember_last_response
from zframe.report.logging import get_logger

logger = get_logger("zframe.client")


class HttpClient:
    """Session-style HTTP client with auth, hooks, and request retry."""

    def __init__(
        self,
        *,
        base_url: str = "",
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        verify: bool = True,
        auth: AuthProvider | None = None,
        retry: RetryConfig | None = None,
        hooks: Hook | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.default_headers = dict(headers or {})
        self.timeout = timeout
        self.verify = verify
        self.auth: AuthProvider = auth or NoAuth()
        self.retry = retry or RetryConfig()
        self.hooks = hooks or Hook(
            on_request=[logging_request_hook],
            on_response=[logging_response_hook],
        )
        self.last_response: Response | None = None
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self.default_headers,
            timeout=self.timeout,
            verify=self.verify,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Any = None,
        headers: Mapping[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        files: Any = None,
        content: Any = None,
        timeout: float | None = None,
        auth: bool = True,
        **kwargs: Any,
    ) -> Response:
        prep: dict[str, Any] = {
            "method": method.upper(),
            "url": url,
            "params": params,
            "headers": dict(headers or {}),
            "json": json,
            "data": data,
            "files": files,
            "content": content,
            "timeout": timeout if timeout is not None else self.timeout,
            **kwargs,
        }

        if auth:
            self.auth.ensure_auth(self)
            prep = self.auth.apply(prep)

        prep = self.hooks.apply_request(prep)
        return self._send_with_retry(prep)

    def _send_with_retry(self, prep: dict[str, Any]) -> Response:
        method = prep["method"]
        attempts = self.retry.max_retries + 1 if self.retry.should_retry_method(method) else 1
        last_exc: BaseException | None = None

        for attempt in range(attempts):
            try:
                started = time.perf_counter()
                raw = self._client.request(
                    prep["method"],
                    prep["url"],
                    params=prep.get("params"),
                    headers=prep.get("headers") or None,
                    json=prep.get("json"),
                    data=prep.get("data"),
                    files=prep.get("files"),
                    content=prep.get("content"),
                    timeout=prep.get("timeout"),
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                response = Response(raw, elapsed_ms=elapsed_ms)
                response = self.hooks.apply_response(response)
                self.last_response = response
                remember_last_response(response)

                if (
                    attempt < attempts - 1
                    and self.retry.should_retry_status(response.status_code)
                ):
                    logger.warning(
                        "retryable status %s on %s %s (attempt %s/%s)",
                        response.status_code,
                        method,
                        prep["url"],
                        attempt + 1,
                        attempts,
                    )
                    self.retry.sleep(attempt)
                    continue
                return response
            except Exception as exc:
                last_exc = exc
                if attempt < attempts - 1 and is_retryable_exception(exc, self.retry.retry_exceptions):
                    logger.warning(
                        "retryable error %s on %s %s (attempt %s/%s)",
                        type(exc).__name__,
                        method,
                        prep["url"],
                        attempt + 1,
                        attempts,
                    )
                    self.retry.sleep(attempt)
                    continue
                raise

        assert last_exc is not None
        raise last_exc

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Response:
        return self.request("DELETE", url, **kwargs)

    @contextmanager
    def websocket(
        self,
        url: str,
        *,
        params: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        subprotocols: list[str] | None = None,
        auth: bool = True,
        **ws_kwargs: Any,
    ) -> Generator[WebSocketSession, None, None]:
        """Open a WebSocket on the shared httpx session (requires ``zframe[ws]``).

        ``url`` may be a path (joined with ``base_url``), ``http(s)://...``, or
        ``ws(s)://...`` (normalized to HTTP for the upgrade handshake).

        Auth headers from the configured :class:`~zframe.auth.base.AuthProvider`
        are applied the same way as HTTP requests when ``auth=True``.
        """
        with connect_websocket(
            self._client,
            url,
            params=params,
            headers=headers,
            timeout=timeout if timeout is not None else self.timeout,
            subprotocols=subprotocols,
            auth_provider=self.auth,
            auth=auth,
            http_client=self,
            hooks=self.hooks,
            **ws_kwargs,
        ) as session:
            yield session
