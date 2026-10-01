"""WebSocket client (mocked httpx-ws)."""

from __future__ import annotations

import builtins
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from typing import Any

from zframe import HttpClient, WebSocketSession, check, normalize_ws_url
from zframe.auth.base import AuthProvider
from zframe.client.ws import _require_httpx_ws


class _BearerStub(AuthProvider):
    def __init__(self, token: str) -> None:
        self.token = token

    def ensure_auth(self, client) -> None:
        return None

    def apply(self, request: dict[str, Any]) -> dict[str, Any]:
        headers = dict(request.get("headers") or {})
        headers["Authorization"] = f"Bearer {self.token}"
        request["headers"] = headers
        return request


def test_normalize_ws_url():
    assert normalize_ws_url("ws://host/ws") == "http://host/ws"
    assert normalize_ws_url("wss://host/ws") == "https://host/ws"
    assert normalize_ws_url("http://host/ws") == "http://host/ws"
    assert normalize_ws_url("/ws/events") == "/ws/events"


def test_require_httpx_ws_missing():
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "httpx_ws" or name.startswith("httpx_ws."):
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    saved = sys.modules.pop("httpx_ws", None)
    try:
        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match=r"zframe\[ws\]"):
                _require_httpx_ws()
    finally:
        if saved is not None:
            sys.modules["httpx_ws"] = saved


def test_websocket_session_send_receive():
    raw = MagicMock()
    raw.receive_text.return_value = "pong"
    raw.receive_json.return_value = {"ok": True}
    raw.subprotocol = None
    raw.response = None

    session = WebSocketSession(raw, url="http://example/ws")
    session.send_text("ping")
    session.send_json({"a": 1})
    assert session.receive_text() == "pong"
    assert session.receive_json() == {"ok": True}
    assert session.last_message == {"ok": True}
    raw.send_text.assert_called_once_with("ping")
    raw.send_json.assert_called_once_with({"a": 1}, mode="text")


def test_receive_json_until():
    raw = MagicMock()
    raw.receive_json.side_effect = [
        {"type": "heartbeat"},
        {"type": "result", "code": 0},
    ]
    session = WebSocketSession(raw, url="http://example/ws")
    msg = session.receive_json_until(lambda m: m.get("type") == "result", timeout=5)
    assert msg == {"type": "result", "code": 0}
    check(msg).equals({"type": "result", "code": 0})


def test_receive_json_until_timeout():
    raw = MagicMock()
    raw.receive_json.side_effect = lambda timeout=None, mode="text": {"type": "heartbeat"}
    session = WebSocketSession(raw, url="http://example/ws")
    with pytest.raises(TimeoutError, match="timed out"):
        session.receive_json_until(lambda m: False, timeout=0.05)


def test_http_client_websocket_applies_auth():
    captured: dict = {}

    @contextmanager
    def fake_connect_ws(url, client, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers") or {}
        captured["params"] = kwargs.get("params")
        raw = MagicMock()
        raw.receive_json.return_value = {"hello": True}
        raw.subprotocol = None
        raw.response = SimpleNamespace(status_code=101)
        yield raw

    fake_httpx_ws = SimpleNamespace(connect_ws=fake_connect_ws)

    with patch("zframe.client.ws._require_httpx_ws", return_value=fake_httpx_ws):
        with HttpClient(
            base_url="https://api.example.com",
            auth=_BearerStub("secret"),
        ) as client:
            with client.websocket(
                "ws://ws.example.com/ws/events",
                params={"client_id": "abc"},
            ) as ws:
                assert isinstance(ws, WebSocketSession)
                assert captured["url"] == "http://ws.example.com/ws/events"
                assert captured["params"] == {"client_id": "abc"}
                assert captured["headers"].get("Authorization") == "Bearer secret"
                assert ws.receive_json() == {"hello": True}


def test_http_client_websocket_relative_path():
    captured: dict = {}

    @contextmanager
    def fake_connect_ws(url, client, **kwargs):
        captured["url"] = url
        raw = MagicMock()
        yield raw

    fake_httpx_ws = SimpleNamespace(connect_ws=fake_connect_ws)

    with patch("zframe.client.ws._require_httpx_ws", return_value=fake_httpx_ws):
        with HttpClient(base_url="http://192.168.1.1") as client:
            with client.websocket("/ws/events") as ws:
                assert captured["url"] == "/ws/events"
                ws.send_text("x")
