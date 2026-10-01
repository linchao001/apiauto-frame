"""Report helpers: logging + optional pytest-html + last-response capture."""

from zframe.report.capture import (
    get_remembered_response,
    remember_last_response,
    remember_response,
)
from zframe.report.html_utils import attach_response, attach_text, step
from zframe.report.logging import get_logger, register_log_origin_skip, setup_logging

__all__ = [
    "attach_response",
    "attach_text",
    "get_logger",
    "get_remembered_response",
    "register_log_origin_skip",
    "remember_last_response",
    "remember_response",
    "setup_logging",
    "step",
]
