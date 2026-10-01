"""PyMySQL-backed DB client for case-layer CRUD."""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator, Iterable, Mapping, Sequence

from zframe.config.models import DbSettings, SshSettings
from zframe.report.logging import get_logger
from zframe.utils.wait import PollResult, wait_until

logger = get_logger("zframe.db")

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ORDER_BY_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\s+(ASC|DESC))?(\s*,\s*[A-Za-z_][A-Za-z0-9_]*(\s+(ASC|DESC))?)*$",
    re.IGNORECASE,
)

if TYPE_CHECKING:
    from zframe.ssh.client import SshClient


def _require_pymysql():
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:  # pragma: no cover - exercised when extra missing
        raise ImportError(
            "PyMySQL is required for zframe DB support. Install with: pip install 'zframe[db]'"
        ) from exc
    return pymysql, DictCursor


def quote_ident(name: str) -> str:
    """Validate and backtick-quote a table/column identifier."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f"`{name}`"


def _build_where(
    where: Mapping[str, Any] | None,
) -> tuple[str, list[Any]]:
    if not where:
        return "", []
    parts: list[str] = []
    args: list[Any] = []
    for key, value in where.items():
        col = quote_ident(key)
        if value is None:
            parts.append(f"{col} IS NULL")
        elif isinstance(value, (list, tuple, set)):
            values = list(value)
            if not values:
                parts.append("1=0")
            else:
                placeholders = ", ".join(["%s"] * len(values))
                parts.append(f"{col} IN ({placeholders})")
                args.extend(values)
        else:
            parts.append(f"{col} = %s")
            args.append(value)
    return " WHERE " + " AND ".join(parts), args


class DbClient:
    """Case-facing DB API: table CRUD + raw SQL.

    Connection / cursor / commit / reconnect are handled here; cases only call
    :meth:`insert` / :meth:`select` / :meth:`update` / :meth:`delete` or raw helpers.

    When ``auto_setup_remote`` is on and session ``ssh`` is configured, a failed
    first TCP connect triggers MariaDB remote-access setup over SSH, then retries once.
    """

    def __init__(
        self,
        config: DbSettings,
        ssh: SshSettings | SshClient | None = None,
    ) -> None:
        self.config = config
        self.ssh = ssh
        self._conn: Any | None = None
        self._remote_setup_done = False

    @property
    def _ssh_ready(self) -> bool:
        if not self.config.auto_setup_remote or self.ssh is None:
            return False
        cfg = self.ssh.config if hasattr(self.ssh, "config") else self.ssh
        return bool(getattr(cfg, "configured", False))

    # ------------------------------------------------------------------ connect
    def _open_connection(self) -> Any:
        pymysql, DictCursor = _require_pymysql()
        kwargs: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "database": self.config.database,
            "charset": self.config.charset,
            "connect_timeout": self.config.connect_timeout,
            "autocommit": self.config.autocommit,
            "cursorclass": DictCursor,
        }
        if self.config.read_timeout is not None:
            kwargs["read_timeout"] = self.config.read_timeout
        if self.config.write_timeout is not None:
            kwargs["write_timeout"] = self.config.write_timeout
        self._conn = pymysql.connect(**kwargs)
        logger.info(
            "db connected %s@%s:%s/%s",
            self.config.user,
            self.config.host,
            self.config.port,
            self.config.database,
        )
        return self._conn

    def connect(self) -> Any:
        if self._conn is not None:
            return self._conn
        try:
            return self._open_connection()
        except Exception as exc:
            if not self._ssh_ready or self._remote_setup_done:
                raise
            logger.warning(
                "db connect failed (%s); attempting SSH MariaDB remote setup",
                exc,
            )
            from zframe.db.remote_setup import setup_mariadb_remote

            self._remote_setup_done = True
            try:
                assert self.ssh is not None
                setup_mariadb_remote(self.config, self.ssh)
            except Exception as setup_exc:
                raise RuntimeError(
                    f"DB connect failed ({exc}); MariaDB remote setup via SSH "
                    f"also failed: {setup_exc}"
                ) from setup_exc
            return self._open_connection()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
                logger.info("db closed")

    def __enter__(self) -> DbClient:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def ping(self, *, reconnect: bool = True) -> None:
        conn = self.connect()
        conn.ping(reconnect=reconnect)

    @contextmanager
    def cursor(self) -> Generator[Any, None, None]:
        self.ping(reconnect=True)
        assert self._conn is not None
        cur = self._conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()

    # ------------------------------------------------------------------ raw SQL
    def execute(self, sql: str, args: Sequence[Any] | Mapping[str, Any] | None = None) -> int:
        """Execute a write/DDL statement; returns affected row count."""
        with self.cursor() as cur:
            affected = cur.execute(sql, args)
            if not self.config.autocommit:
                self.commit()
            logger.debug("db execute affected=%s sql=%s", affected, sql)
            return int(affected or 0)

    def executemany(self, sql: str, args_seq: Iterable[Sequence[Any] | Mapping[str, Any]]) -> int:
        with self.cursor() as cur:
            affected = cur.executemany(sql, list(args_seq))
            if not self.config.autocommit:
                self.commit()
            return int(affected or 0)

    def fetch_one(
        self, sql: str, args: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self.cursor() as cur:
            cur.execute(sql, args)
            row = cur.fetchone()
            return dict(row) if row is not None else None

    def fetch_all(
        self, sql: str, args: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]

    def fetch_value(
        self, sql: str, args: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> Any:
        """Return the first column of the first row (or ``None``)."""
        row = self.fetch_one(sql, args)
        if row is None:
            return None
        return next(iter(row.values()))

    # ------------------------------------------------------------------ table CRUD
    def insert(self, table: str, data: Mapping[str, Any]) -> int:
        """Insert one row; returns ``lastrowid`` (0 if none)."""
        if not data:
            raise ValueError("insert data must not be empty")
        cols = ", ".join(quote_ident(k) for k in data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO {quote_ident(table)} ({cols}) VALUES ({placeholders})"
        with self.cursor() as cur:
            cur.execute(sql, tuple(data.values()))
            last_id = int(cur.lastrowid or 0)
            if not self.config.autocommit:
                self.commit()
            logger.debug("db insert table=%s id=%s", table, last_id)
            return last_id

    def insert_many(self, table: str, rows: Sequence[Mapping[str, Any]]) -> int:
        """Insert multiple rows sharing the same columns; returns affected count."""
        if not rows:
            return 0
        keys = list(rows[0].keys())
        if not keys:
            raise ValueError("insert_many rows must not be empty mappings")
        cols = ", ".join(quote_ident(k) for k in keys)
        placeholders = ", ".join(["%s"] * len(keys))
        sql = f"INSERT INTO {quote_ident(table)} ({cols}) VALUES ({placeholders})"
        args_seq = [tuple(row[k] for k in keys) for row in rows]
        return self.executemany(sql, args_seq)

    def select(
        self,
        table: str,
        *,
        fields: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        if fields:
            cols = ", ".join(quote_ident(f) for f in fields)
        else:
            cols = "*"
        sql = f"SELECT {cols} FROM {quote_ident(table)}"
        where_sql, args = _build_where(where)
        sql += where_sql
        if order_by:
            if not _ORDER_BY_RE.match(order_by.strip()):
                raise ValueError(f"Invalid order_by: {order_by!r}")
            sql += f" ORDER BY {order_by.strip()}"
        if limit is not None:
            sql += " LIMIT %s"
            args.append(int(limit))
            if offset is not None:
                sql += " OFFSET %s"
                args.append(int(offset))
        elif offset is not None:
            raise ValueError("offset requires limit")
        return self.fetch_all(sql, args)

    def select_one(
        self,
        table: str,
        *,
        fields: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(
            table, fields=fields, where=where, order_by=order_by, limit=1
        )
        return rows[0] if rows else None

    def count(self, table: str, *, where: Mapping[str, Any] | None = None) -> int:
        sql = f"SELECT COUNT(*) AS cnt FROM {quote_ident(table)}"
        where_sql, args = _build_where(where)
        sql += where_sql
        value = self.fetch_value(sql, args)
        return int(value or 0)

    def update(
        self,
        table: str,
        data: Mapping[str, Any],
        *,
        where: Mapping[str, Any] | None = None,
        force: bool = False,
    ) -> int:
        if not data:
            raise ValueError("update data must not be empty")
        if not where and not force:
            raise ValueError("update without where requires force=True")
        sets = ", ".join(f"{quote_ident(k)} = %s" for k in data.keys())
        sql = f"UPDATE {quote_ident(table)} SET {sets}"
        args: list[Any] = list(data.values())
        where_sql, where_args = _build_where(where)
        sql += where_sql
        args.extend(where_args)
        return self.execute(sql, args)

    def delete(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        force: bool = False,
    ) -> int:
        if not where and not force:
            raise ValueError("delete without where requires force=True")
        sql = f"DELETE FROM {quote_ident(table)}"
        where_sql, args = _build_where(where)
        sql += where_sql
        return self.execute(sql, args)

    # ------------------------------------------------------------------ async poll
    def wait_absent(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        timeout_sec: float = 30.0,
        interval_sec: float = 0.5,
        label: str | None = None,
    ) -> PollResult:
        """Poll until no row matches ``where`` (async delete / cleanup)."""
        poll_label = label or f"{table} absent where={where!r}"
        row_holder: list[dict[str, Any] | None] = [None]

        def predicate() -> bool:
            row_holder[0] = self.select_one(table, where=where)
            return row_holder[0] is None

        return wait_until(
            poll_label,
            predicate,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            on_poll=lambda: row_holder[0],
        )

    def wait_present(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        timeout_sec: float = 30.0,
        interval_sec: float = 0.5,
        label: str | None = None,
    ) -> PollResult:
        """Poll until a row matches ``where`` (async insert / materialization)."""
        poll_label = label or f"{table} present where={where!r}"
        row_holder: list[dict[str, Any] | None] = [None]

        def predicate() -> bool:
            row_holder[0] = self.select_one(table, where=where, order_by=order_by)
            return row_holder[0] is not None

        return wait_until(
            poll_label,
            predicate,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            on_poll=lambda: row_holder[0],
        )

    def wait_count(
        self,
        table: str,
        expected: int,
        *,
        where: Mapping[str, Any] | None = None,
        timeout_sec: float = 30.0,
        interval_sec: float = 0.5,
        label: str | None = None,
    ) -> PollResult:
        """Poll until ``count(table, where=...)`` equals ``expected``."""
        poll_label = label or f"{table} count={expected} where={where!r}"
        count_holder: list[int] = [0]

        def predicate() -> bool:
            count_holder[0] = self.count(table, where=where)
            return count_holder[0] == expected

        return wait_until(
            poll_label,
            predicate,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            on_poll=lambda: count_holder[0],
        )

    def wait_field(
        self,
        table: str,
        field: str,
        expected: Any,
        *,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        timeout_sec: float = 30.0,
        interval_sec: float = 0.5,
        label: str | None = None,
    ) -> PollResult:
        """Poll until the selected row's ``field`` equals ``expected``.

        Keeps polling while the row is missing or the field differs (e.g. async
        status transitions). Use :meth:`wait_absent` when the terminal state is
        row deletion.
        """
        poll_label = label or f"{table}.{field}={expected!r} where={where!r}"
        row_holder: list[dict[str, Any] | None] = [None]

        def predicate() -> bool:
            row_holder[0] = self.select_one(table, where=where, order_by=order_by)
            if row_holder[0] is None:
                return False
            return row_holder[0].get(field) == expected

        return wait_until(
            poll_label,
            predicate,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            on_poll=lambda: row_holder[0],
        )
