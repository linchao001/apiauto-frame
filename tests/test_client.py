from typing import Any

import httpx
import pytest
import respx

from zframe import HttpClient, RetryConfig, check
from zframe.auth.base import AuthProvider


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


@respx.mock
def test_get_and_check():
    respx.get("https://api.example.com/ping").mock(
        return_value=httpx.Response(200, json={"code": 0, "msg": "ok"})
    )
    with HttpClient(base_url="https://api.example.com") as client:
        resp = client.get("/ping")
    check(resp).status(200).jsonpath("$.code", 0).jsonpath("$.msg", "ok")


@respx.mock
def test_bearer_auth_header():
    route = respx.get("https://api.example.com/secure").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    with HttpClient(
        base_url="https://api.example.com", auth=_BearerStub("secret")
    ) as client:
        client.get("/secure")
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret"


@respx.mock
def test_retry_on_503_then_success():
    route = respx.get("https://api.example.com/flaky").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    retry = RetryConfig(max_retries=2, backoff_factor=0.01, jitter=False)
    with HttpClient(base_url="https://api.example.com", retry=retry) as client:
        resp = client.get("/flaky")
    assert resp.status_code == 200
    assert route.call_count == 2


@respx.mock
def test_post_not_retried_by_default():
    route = respx.post("https://api.example.com/create").mock(
        return_value=httpx.Response(503)
    )
    retry = RetryConfig(max_retries=3, backoff_factor=0.01, jitter=False)
    with HttpClient(base_url="https://api.example.com", retry=retry) as client:
        resp = client.post("/create", json={"a": 1})
    assert resp.status_code == 503
    assert route.call_count == 1
