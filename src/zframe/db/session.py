"""Session-scoped DB accessors (no fixture params needed)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zframe.db.client import DbClient

_client: DbClient | None = None


def bind_db(client: DbClient | None) -> None:
    """Store the session :class:`~zframe.db.client.DbClient` for :func:`get_db`."""
    global _client
    _client = client


def clear_db() -> None:
    global _client
    if _client is not None:
        _client.close()
    _client = None


def get_db() -> DbClient:
    """Return the session :class:`~zframe.db.client.DbClient`.

    Bound automatically when ``settings.db`` is configured.
    """
    if _client is None:
        raise RuntimeError(
            "DB is not bound; configure ``db`` in env YAML and run under the "
            "zframe pytest plugin, or call bind_db() first"
        )
    return _client
