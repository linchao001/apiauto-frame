"""Public API surface for case repos and product kits.

Prefer importing from ``zframe`` or ``zframe.api`` so internal module
layouts can change without breaking SemVer for consumers.
"""

from zframe.assertx.checkers import check, extract
from zframe.assertx.matchers import ANY, Approx, Regex
from zframe.assertx.soft import SoftAssertions
from zframe.auth.base import AuthProvider, NoAuth
from zframe.auth.factory import build_auth, register_auth, registered_auth_types
from zframe.client.hooks import Hook, RequestHook, ResponseHook
from zframe.client.http import HttpClient
from zframe.client.response import Response
from zframe.client.retry import RetryConfig
from zframe.client.ws import WebSocketSession, normalize_ws_url
from zframe.config.loader import DEFAULT_ENV, discover_envs, load_settings, resolve_env_name
from zframe.config.models import (
    AssertSettings,
    DbSettings,
    HttpSettings,
    NotifySettings,
    Settings,
    SshSettings,
)
from zframe.context.runtime import Context
from zframe.context.session import get_ctx, get_settings
from zframe.data.loader import load_cases
from zframe.data.parametrize import Parametrize, parametrize_from
from zframe.data.render import render
from zframe.db.client import DbClient
from zframe.db.session import get_db
from zframe.notify.factory import build_notifier, register_notifier, registered_notifier_types
from zframe.notify.summary import RunSummary
from zframe.report.capture import remember_last_response, remember_response
from zframe.report.html_utils import attach_response, attach_text, step
from zframe.report.logging import get_logger, register_log_origin_skip, setup_logging
from zframe.ssh.client import SshClient, SshResult
from zframe.ssh.session import get_ssh
from zframe.utils.wait import PollResult, wait_until

__all__ = [
    "ANY",
    "Approx",
    "AssertSettings",
    "AuthProvider",
    "Context",
    "DbClient",
    "DbSettings",
    "Hook",
    "HttpClient",
    "NoAuth",
    "NotifySettings",
    "Parametrize",
    "PollResult",
    "Regex",
    "RequestHook",
    "Response",
    "ResponseHook",
    "RetryConfig",
    "RunSummary",
    "DEFAULT_ENV",
    "Settings",
    "SoftAssertions",
    "SshClient",
    "SshResult",
    "SshSettings",
    "WebSocketSession",
    "attach_response",
    "attach_text",
    "build_auth",
    "build_notifier",
    "discover_envs",
    "check",
    "extract",
    "get_ctx",
    "get_db",
    "get_logger",
    "get_settings",
    "get_ssh",
    "load_cases",
    "load_settings",
    "normalize_ws_url",
    "parametrize_from",
    "register_auth",
    "register_log_origin_skip",
    "register_notifier",
    "registered_auth_types",
    "registered_notifier_types",
    "remember_last_response",
    "remember_response",
    "render",
    "resolve_env_name",
    "setup_logging",
    "step",
    "wait_until",
]
