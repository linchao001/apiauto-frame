"""Neutral case-repo file templates for ``zframe --init``."""

from __future__ import annotations


def render_files(*, package: str) -> dict[str, str]:
    """Return relative path → UTF-8 text for a generated case repository."""
    pkg = package
    return {
        "auth.py": _AUTH,
        "conftest.py": _CONFTEST.format(package=pkg),
        "config/product.yaml": _PRODUCT_YAML.format(package=pkg),
        "config/env/dev.yaml": _ENV_DEV_YAML.format(package=pkg),
        "helpers/__init__.py": "",
        "helpers/logging.py": _HELPERS_LOGGING,
        f"{pkg}/__init__.py": "",
        f"{pkg}/WEB/__init__.py": "",
        f"{pkg}/WEB/conftest.py": _WEB_CONFTEST.format(package=pkg),
        f"{pkg}/WEB/services/__init__.py": _SERVICES_INIT,
        f"{pkg}/WEB/services/sample_api.py": _SAMPLE_API,
        f"{pkg}/WEB/helpers/__init__.py": "",
        f"{pkg}/WEB/API/Sample/testcases/__init__.py": "",
        f"{pkg}/WEB/API/Sample/testcases/test_sample.py": _API_TEST.format(
            package=pkg
        ),
        f"{pkg}/WEB/API/Sample/testdata/test_sample.json": _API_DATA,
        f"{pkg}/WEB/E2E/Sample/testcases/__init__.py": "",
        f"{pkg}/WEB/E2E/Sample/testcases/test_sample_flow.py": _E2E_TEST.format(
            package=pkg
        ),
        f"{pkg}/WEB/E2E/Sample/testdata/test_sample_flow.json": _E2E_DATA,
    }


_AUTH = '''\
"""Product auth — subclass AuthProvider and implement login / signing."""

from __future__ import annotations

from typing import Any

from zframe.auth.base import AuthProvider


class ProductAuth(AuthProvider):
    """Replace with your product-line login, token refresh, and request signing.

    Scaffold ``config/env/dev.yaml`` defaults to ``auth.type: none`` so the
    bundled httpbin Sample cases run without this class. Switch to your
    registered type after implementing ``ensure_auth`` / ``apply``.
    """

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "ProductAuth":
        return cls(cfg)

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = dict(cfg or {})

    def ensure_auth(self, client) -> None:
        raise NotImplementedError(
            "Implement ProductAuth.ensure_auth in the case repo "
            "(obtain / refresh credentials before requests)"
        )

    def apply(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            "Implement ProductAuth.apply in the case repo "
            "(attach headers / signature to each request)"
        )
'''

_CONFTEST = '''\
"""Case repo root fixtures — register product auth and default config dir."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from auth import ProductAuth
from zframe.auth.factory import register_auth
from zframe.config.loader import load_settings
from zframe.config.models import Settings

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

register_auth("{package}", ProductAuth.from_config)


@pytest.fixture(scope="session")
def zframe_settings(pytestconfig: pytest.Config) -> Settings:
    """Default to this product's config/ so IDE runs work without CLI flags."""
    return load_settings(
        product=pytestconfig.getoption("--product"),
        env=pytestconfig.getoption("--env"),
        config_dir=pytestconfig.getoption("--config-dir") or (ROOT / "config"),
    )
'''

_PRODUCT_YAML = """\
product: {package}
env: dev
http:
  timeout: 15
  max_retries: 1
  retry_backoff: 0.2
assertx:
  mode: loose
  allow_extra: true
notify:
  enabled: false
  on: always
  type: feishu
  webhook: ""
  title: "ZFrame · ${{product}}/${{env}}"
"""

_ENV_DEV_YAML = """\
# Scaffold Sample cases hit a public echo API (not a real product).
http:
  base_url: https://httpbin.org
auth:
  type: none
  # After ProductAuth is implemented, switch to:
  # type: {package}
vars:
  device: dev
"""

_HELPERS_LOGGING = '''\
"""Cross-module case-step logging helpers."""

from __future__ import annotations

import inspect
import json
import logging
from pathlib import Path
from types import FrameType
from typing import Any

from zframe import get_logger, register_log_origin_skip

_REPO_ROOT = Path(__file__).resolve().parent.parent

register_log_origin_skip(__file__)


def _suite_from_path(file: str) -> str:
    try:
        rel = Path(file).resolve().relative_to(_REPO_ROOT)
    except ValueError:
        return ""

    parts = list(rel.parts[:-1])
    for marker in ("testcases", "testdata", "helpers"):
        if marker in parts:
            parts = parts[: parts.index(marker)]
            break
    return ".".join(p.lower() for p in parts)


def _caller_frame() -> FrameType | None:
    frame = inspect.currentframe()
    return frame.f_back.f_back if frame and frame.f_back else None


def _logger_for_frame(caller: FrameType) -> logging.Logger:
    func = caller.f_code.co_name
    file = caller.f_globals.get("__file__")
    suite = _suite_from_path(str(file)) if file else ""
    name = f"{suite}.{func}" if suite else func
    return get_logger(name)


def log_step(
    step: str,
    meta_data: dict[str, Any],
    resp,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Log one case step with status and pretty-printed response body."""
    caller = None if logger else _caller_frame()
    log = logger or (_logger_for_frame(caller) if caller else get_logger("case"))
    log.info(
        "case %s | step=%s | status=%s response=\\n%s",
        meta_data.get("id"),
        step,
        resp.status_code,
        json.dumps(resp.to_dict(), ensure_ascii=False, indent=2, default=str),
    )
'''

_WEB_CONFTEST = '''\
"""WEB module fixtures."""

from __future__ import annotations

import pytest

from {package}.WEB.services import WebServices


@pytest.fixture(scope="session")
def services(client) -> WebServices:
    return WebServices.create(client)


@pytest.fixture(scope="class")
def services_on_cls(request: pytest.FixtureRequest, services: WebServices) -> None:
    request.cls.services = services  # type: ignore[union-attr]
'''

_SERVICES_INIT = '''\
"""WEB HTTP adaptation layer."""

from __future__ import annotations

from zframe import HttpClient

from .sample_api import SampleApi


class WebServices:
    def __init__(self, client: HttpClient) -> None:
        self.client = client
        self.sample = SampleApi(client)

    @classmethod
    def create(cls, client: HttpClient) -> "WebServices":
        return cls(client)
'''

_SAMPLE_API = '''\
"""Sample HTTP adaptation against httpbin echo endpoints (not real product APIs)."""

from __future__ import annotations

from typing import Any

from zframe import HttpClient, Response


class SampleApi:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def get_echo(self, *, params: dict[str, Any] | None = None, **kwargs) -> Response:
        """GET /get — echo query string."""
        return self.client.get("/get", params=params, **kwargs)

    def post_echo(self, *, json: dict[str, Any] | None = None, **kwargs) -> Response:
        """POST /post — echo JSON body."""
        return self.client.post("/post", json=json, **kwargs)
'''

_API_TEST = '''\
"""Business-agnostic Sample: data-driven GET echo via httpbin."""

from __future__ import annotations

import pytest

from {package}.WEB.services import WebServices
from helpers.logging import log_step
from zframe import check, parametrize_from


@pytest.mark.usefixtures("services_on_cls")
class TestSample:
    services: WebServices

    @parametrize_from
    def test_get_echo(self, meta_data, req, expect, test_data):
        resp = self.services.sample.get_echo(params=req.get("params") or {{}})
        log_step("get_echo", meta_data, resp)
        check(resp).status(200, msg="httpbin GET /get should return 200").body(
            expect, meta=meta_data, msg="echoed query args should match req"
        )
'''

_API_DATA = """\
[
  {
    "meta_data": {"id": "S01", "title": "httpbin GET echo", "priority": "P2"},
    "req": {"params": {"q": "zframe"}},
    "expect": {"args": {"q": "zframe"}}
  }
]
"""

_E2E_TEST = '''\
"""Business-agnostic Sample E2E: GET then POST echo via httpbin."""

from __future__ import annotations

import pytest

from {package}.WEB.services import WebServices
from helpers.logging import log_step
from zframe import check, parametrize_from


@pytest.mark.usefixtures("services_on_cls")
class TestSampleFlow:
    services: WebServices

    @parametrize_from
    def test_echo_flow(self, meta_data, req, expect, test_data):
        get_resp = self.services.sample.get_echo(params=req.get("get_params") or {{}})
        log_step("get_echo", meta_data, get_resp)
        check(get_resp).status(200, msg="step1 GET /get").body(
            expect.get("get") or {{}},
            meta=meta_data,
            msg="step1 echoed query should match",
        )

        post_resp = self.services.sample.post_echo(json=req.get("post_json") or {{}})
        log_step("post_echo", meta_data, post_resp)
        check(post_resp).status(200, msg="step2 POST /post").body(
            expect.get("post") or {{}},
            meta=meta_data,
            msg="step2 echoed json should match",
        )
'''

_E2E_DATA = """\
[
  {
    "meta_data": {"id": "E01", "title": "httpbin GET+POST echo flow", "priority": "P2"},
    "req": {
      "get_params": {"step": "1"},
      "post_json": {"name": "demo", "ok": true}
    },
    "expect": {
      "get": {"args": {"step": "1"}},
      "post": {"json": {"name": "demo", "ok": true}}
    },
    "test_data": {}
  }
]
"""
