"""Shared utilities."""

from zframe.utils.dictutil import deep_merge
from zframe.utils.wait import PollResult, wait_until

__all__ = ["PollResult", "deep_merge", "wait_until"]
