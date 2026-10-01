"""AuthProvider registry — no builtin product providers."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from zframe import HttpClient, Settings, build_auth, register_auth, registered_auth_types
from zframe.auth.base import AuthProvider, NoAuth


def test_build_auth_none():
    assert isinstance(build_auth({"type": "none"}), NoAuth)
    assert isinstance(build_auth(Settings()), NoAuth)


def test_build_auth_unknown_raises():
    with pytest.raises(ValueError, match="Unknown auth type"):
        build_auth({"type": "bearer"})


def test_register_auth_extension():
    class Stub(AuthProvider):
        def ensure_auth(self, client):
            return None

        def apply(self, request: dict[str, Any]) -> dict[str, Any]:
            headers = dict(request.get("headers") or {})
            headers["X-Stub"] = "1"
            request["headers"] = headers
            return request

    register_auth("stub_ext", lambda cfg: Stub())
    assert "stub_ext" in registered_auth_types()
    assert isinstance(build_auth({"type": "stub_ext"}), Stub)


@respx.mock
def test_registered_auth_applies_headers():
    class Stub(AuthProvider):
        def ensure_auth(self, client):
            return None

        def apply(self, request: dict[str, Any]) -> dict[str, Any]:
            headers = dict(request.get("headers") or {})
            headers["Authorization"] = "Bearer stub-token"
            request["headers"] = headers
            return request

    register_auth("header_stub", lambda cfg: Stub())
    route = respx.get("https://api.example.com/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    with HttpClient(
        base_url="https://api.example.com",
        auth=build_auth({"type": "header_stub"}),
    ) as client:
        client.get("/ping")
    assert route.calls.last.request.headers["Authorization"] == "Bearer stub-token"
