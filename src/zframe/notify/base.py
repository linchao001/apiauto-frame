"""Notifier protocol and shared helpers."""

from __future__ import annotations

from typing import Protocol

from zframe.notify.summary import RunSummary


class Notifier(Protocol):
    """Send a session-end run summary to an external channel."""

    def send(self, summary: RunSummary) -> None: ...
