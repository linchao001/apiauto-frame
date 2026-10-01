"""Last-response capture for HTML failure attachments."""

from __future__ import annotations

import httpx
import respx

from zframe.client.http import HttpClient
from zframe.report.capture import (
    bind_test_item,
    get_remembered_response,
    remember_last_response,
    remember_response,
    reset_test_item,
)


class _FakeItem:
    pass


@respx.mock
def test_http_client_auto_remembers_on_active_item():
    respx.get("https://api.example.com/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    item = _FakeItem()
    token = bind_test_item(item)
    try:
        with HttpClient(base_url="https://api.example.com") as client:
            resp = client.get("/ping")
        assert client.last_response is resp
        assert get_remembered_response(item) is resp
    finally:
        reset_test_item(token)


@respx.mock
def test_http_client_noop_remember_without_item():
    respx.get("https://api.example.com/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    with HttpClient(base_url="https://api.example.com") as client:
        resp = client.get("/ping")
    assert client.last_response is resp


def test_remember_helpers():
    item = _FakeItem()
    remember_response(item, {"x": 1})
    assert get_remembered_response(item) == {"x": 1}

    token = bind_test_item(item)
    try:
        remember_last_response({"y": 2})
        assert get_remembered_response(item) == {"y": 2}
    finally:
        reset_test_item(token)
