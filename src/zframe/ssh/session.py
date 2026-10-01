"""Session-scoped SSH accessors (no fixture params needed)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zframe.ssh.client import SshClient

_client: SshClient | None = None


def bind_ssh(client: SshClient | None) -> None:
    """Store the session :class:`~zframe.ssh.client.SshClient` for :func:`get_ssh`."""
    global _client
    _client = client


def clear_ssh() -> None:
    global _client
    if _client is not None:
        _client.close()
    _client = None


def get_ssh() -> SshClient:
    """Return the session :class:`~zframe.ssh.client.SshClient`.

    Bound automatically when ``settings.ssh`` is configured.
    """
    if _client is None:
        raise RuntimeError(
            "SSH is not bound; configure ``ssh`` in env YAML and run under the "
            "zframe pytest plugin, or call bind_ssh() first"
        )
    return _client
