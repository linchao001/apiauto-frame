"""WebSocket session wrapper built on httpx-ws (sync)."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Generator, Mapping

from zframe.report.logging import get_logger

if TYPE_CHECKING:
    import httpx

    from zframe.auth.base import AuthProvider
    from zframe.client.hooks import Hook

logger = get_logger("zframe.client.ws")


def _require_httpx_ws():
    try:
        import httpx_ws
    except ImportError as exc:  # pragma: no cover - exercised when extra missing
        raise ImportError(
            "httpx-ws is required for zframe WebSocket support. "
            "Install with: pip install 'zframe[ws]'"
        ) from exc
    return httpx_ws


def normalize_ws_url(url: str) -> str:
    """Map ``ws://`` / ``wss://`` to ``http://`` / ``https://`` for httpx-ws upgrade."""
    lower = url.lower()
    if lower.startswith("ws://"):
        return "http://" + url[5:]
    if lower.startswith("wss://"):
        return "https://" + url[6:]
    return url


class WebSocketSession:
    """Case-facing WebSocket API around ``httpx_ws.WebSocketSession``.

    Prefer ``HttpClient.websocket(...)`` so auth / headers / base_url are shared
    with HTTP traffic.
    """

    def __init__(self, raw: Any, *, url: str) -> None:
        self._raw = raw
        self.url = url
        self.last_message: Any = None

    @property
    def raw(self) -> Any:
        return self._raw

    @property
    def subprotocol(self) -> str | None:
        return getattr(self._raw, "subprotocol", None)

    @property
    def response(self) -> httpx.Response | None:
        return getattr(self._raw, "response", None)

    def send_text(self, data: str) -> None:
        logger.info(">>> WS SEND text %s len=%s", self.url, len(data))
        self._raw.send_text(data)

    def send_bytes(self, data: bytes) -> None:
        logger.info(">>> WS SEND bytes %s len=%s", self.url, len(data))
        self._raw.send_bytes(data)

    def send_json(self, data: Any, mode: str = "text") -> None:
        logger.info(">>> WS SEND json %s data=%s", self.url, data)
        self._raw.send_json(data, mode=mode)

    def receive_text(self, timeout: float | None = None) -> str:
        data = self._raw.receive_text(timeout=timeout)
        self.last_message = data
        logger.info("<<< WS RECV text %s len=%s", self.url, len(data))
        return data

    def receive_bytes(self, timeout: float | None = None) -> bytes:
        data = self._raw.receive_bytes(timeout=timeout)
        self.last_message = data
        logger.info("<<< WS RECV bytes %s len=%s", self.url, len(data))
        return data

    def receive_json(self, timeout: float | None = None, mode: str = "text") -> Any:
        data = self._raw.receive_json(timeout=timeout, mode=mode)
        self.last_message = data
        logger.info("<<< WS RECV json %s data=%s", self.url, data)
        return data

    def receive_json_until(
        self,
        predicate: Callable[[Any], bool],
        *,
        timeout: float = 30.0,
        mode: str = "text",
    ) -> Any:
        """Receive JSON messages until ``predicate(msg)`` is true or timeout."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"WebSocket receive_json_until timed out after {timeout}s on {self.url}"
                )
            msg = self.receive_json(timeout=remaining, mode=mode)
            if predicate(msg):
                return msg

    def ping(self, payload: bytes = b"") -> Any:
        return self._raw.ping(payload)

    def close(self, code: int = 1000, reason: str | None = None) -> None:
        if reason is None:
            self._raw.close(code)
        else:
            self._raw.close(code, reason)


@contextmanager
def connect_websocket(
    client: httpx.Client,
    url: str,
    *,
    params: Any = None,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
    subprotocols: list[str] | None = None,
    auth_provider: AuthProvider | None = None,
    auth: bool = True,
    http_client: Any = None,
    hooks: Hook | None = None,
    **ws_kwargs: Any,
) -> Generator[WebSocketSession, None, None]:
    """Open a sync WebSocket using the given httpx client (shared cookies/TLS)."""
    httpx_ws = _require_httpx_ws()
    http_url = normalize_ws_url(url)

    prep: dict[str, Any] = {
        "method": "WS",
        "url": http_url,
        "params": params,
        "headers": dict(headers or {}),
    }
    if auth and auth_provider is not None:
        if http_client is not None:
            auth_provider.ensure_auth(http_client)
        prep = auth_provider.apply(prep)
    if hooks is not None:
        prep = hooks.apply_request(prep)

    kwargs: dict[str, Any] = {
        "headers": prep.get("headers") or None,
        "params": prep.get("params"),
        **ws_kwargs,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    if subprotocols is not None:
        kwargs["subprotocols"] = subprotocols

    with httpx_ws.connect_ws(http_url, client, **kwargs) as raw:
        session = WebSocketSession(raw, url=http_url)
        try:
            yield session
        finally:
            logger.info("WS CLOSE %s", http_url)
