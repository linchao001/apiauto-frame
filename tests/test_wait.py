"""wait_until and DbClient poll helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zframe.config.models import DbSettings
from zframe.db.client import DbClient
from zframe.utils.wait import PollResult, wait_until


def test_wait_until_success():
    calls = {"n": 0}

    def predicate():
        calls["n"] += 1
        return calls["n"] >= 3

    with patch("zframe.utils.wait.time.sleep"):
        result = wait_until(
            "sample",
            predicate,
            timeout_sec=5,
            interval_sec=0.1,
            on_poll=lambda: calls["n"],
        )

    assert isinstance(result, PollResult)
    assert result.label == "sample"
    assert result.attempts == 3
    assert result.last_snapshot == 3
    assert result.elapsed_sec >= 0


def test_wait_until_timeout_raises_assertion_error():
    with patch("zframe.utils.wait.time.sleep"):
        with pytest.raises(AssertionError, match="wait_until timed out"):
            wait_until(
                "slow",
                lambda: False,
                timeout_sec=0.2,
                interval_sec=0.05,
                on_poll=lambda: "stuck",
            )


def test_wait_until_invalid_timeout():
    with pytest.raises(ValueError, match="timeout_sec"):
        wait_until("x", lambda: True, timeout_sec=0)


def test_wait_until_invalid_interval():
    with pytest.raises(ValueError, match="interval_sec"):
        wait_until("x", lambda: True, interval_sec=0)


def test_db_wait_absent(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.fetchall.side_effect = [
        [{"id": 1}],
        [{"id": 1}],
        [],
    ]
    client = DbClient(db_config)
    client._conn = conn

    with patch("zframe.utils.wait.time.sleep"):
        result = client.wait_absent("audios", where={"id": "a1"}, timeout_sec=5, interval_sec=0.1)

    assert result.attempts == 3
    assert result.last_snapshot is None


def test_db_wait_present(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.fetchall.side_effect = [
        [],
        [{"id": 42, "status": 1}],
    ]
    client = DbClient(db_config)
    client._conn = conn

    with patch("zframe.utils.wait.time.sleep"):
        result = client.wait_present("audios", where={"id": "a1"}, timeout_sec=5, interval_sec=0.1)

    assert result.attempts == 2
    assert result.last_snapshot == {"id": 42, "status": 1}


def test_db_wait_count(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.fetchone.side_effect = [
        {"cnt": 2},
        {"cnt": 0},
    ]
    client = DbClient(db_config)
    client._conn = conn

    with patch("zframe.utils.wait.time.sleep"):
        result = client.wait_count("audios", 0, where={"user_id": 1}, timeout_sec=5, interval_sec=0.1)

    assert result.attempts == 2
    assert result.last_snapshot == 0


def test_db_wait_field(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.fetchall.side_effect = [
        [{"id": 1, "status": 1}],
        [{"id": 1, "status": 3}],
    ]
    client = DbClient(db_config)
    client._conn = conn

    with patch("zframe.utils.wait.time.sleep"):
        result = client.wait_field(
            "audios",
            "status",
            3,
            where={"id": "a1"},
            timeout_sec=5,
            interval_sec=0.1,
        )

    assert result.attempts == 2
    assert result.last_snapshot == {"id": 1, "status": 3}


def test_db_wait_absent_timeout(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.fetchall.return_value = [{"id": 1}]
    client = DbClient(db_config)
    client._conn = conn

    with patch("zframe.utils.wait.time.sleep"):
        with pytest.raises(AssertionError, match="audios absent"):
            client.wait_absent("audios", where={"id": "a1"}, timeout_sec=0.2, interval_sec=0.05)


@pytest.fixture
def db_config() -> DbSettings:
    return DbSettings(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="secret",
        database="testdb",
        autocommit=True,
    )


@pytest.fixture
def mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    conn.ping = MagicMock()
    return conn, cur
