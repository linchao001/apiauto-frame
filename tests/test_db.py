"""DB client CRUD / raw SQL (mocked PyMySQL)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zframe.config.models import DbSettings
from zframe.db.client import DbClient, quote_ident
from zframe.db import session as db_session
from zframe.db.session import bind_db, clear_db, get_db


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


def test_quote_ident_rejects_injection():
    assert quote_ident("users") == "`users`"
    with pytest.raises(ValueError):
        quote_ident("users; drop")


def test_insert_select_update_delete(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.lastrowid = 42
    cur.execute.return_value = 1
    cur.fetchall.side_effect = [
        [{"id": 42, "name": "Alice"}],
        [{"id": 42, "name": "Bob"}],
    ]
    cur.fetchone.return_value = {"cnt": 1}

    with patch("pymysql.connect", return_value=conn):
        db = DbClient(db_config)
        user_id = db.insert("users", {"name": "Alice", "phone": "5550100"})
        assert user_id == 42

        row = db.select_one("users", where={"id": 42})
        assert row == {"id": 42, "name": "Alice"}

        assert db.count("users", where={"name": "Alice"}) == 1

        affected = db.update("users", {"name": "Bob"}, where={"id": 42})
        assert affected == 1

        assert db.delete("users", where={"id": 42}) == 1

    assert cur.execute.call_count >= 5


def test_update_delete_require_where(db_config: DbSettings, mock_conn):
    conn, _cur = mock_conn
    with patch("pymysql.connect", return_value=conn):
        db = DbClient(db_config)
        with pytest.raises(ValueError, match="force=True"):
            db.update("users", {"name": "x"})
        with pytest.raises(ValueError, match="force=True"):
            db.delete("users")


def test_where_in_and_null(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.fetchall.return_value = []
    with patch("pymysql.connect", return_value=conn):
        db = DbClient(db_config)
        db.select("users", where={"id": [1, 2], "deleted_at": None})
    sql, args = cur.execute.call_args[0]
    assert "`id` IN (%s, %s)" in sql
    assert "`deleted_at` IS NULL" in sql
    assert args == [1, 2]


def test_raw_fetch(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.fetchone.return_value = {"n": 3}
    cur.fetchall.return_value = [{"n": 1}, {"n": 2}]
    with patch("pymysql.connect", return_value=conn):
        db = DbClient(db_config)
        assert db.fetch_value("SELECT COUNT(*) AS n FROM users") == 3
        assert db.fetch_all("SELECT n FROM t") == [{"n": 1}, {"n": 2}]


def test_bind_and_get_db(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.fetchone.return_value = {"ok": 1}
    prev = db_session._client
    clear_db()
    try:
        client = DbClient(db_config)
        bind_db(client)
        with patch("pymysql.connect", return_value=conn):
            assert get_db().fetch_one("SELECT 1 AS ok") == {"ok": 1}
    finally:
        clear_db()
        db_session._client = prev


def test_insert_many(db_config: DbSettings, mock_conn):
    conn, cur = mock_conn
    cur.executemany.return_value = 2
    with patch("pymysql.connect", return_value=conn):
        db = DbClient(db_config)
        n = db.insert_many(
            "users",
            [{"name": "a", "phone": "1"}, {"name": "b", "phone": "2"}],
        )
    assert n == 2
    cur.executemany.assert_called_once()


def test_order_by_rejected(db_config: DbSettings, mock_conn):
    conn, _cur = mock_conn
    with patch("pymysql.connect", return_value=conn):
        db = DbClient(db_config)
        with pytest.raises(ValueError, match="order_by"):
            db.select("users", order_by="id; DROP TABLE users")


def test_connect_retries_after_ssh_remote_setup(mock_conn):
    from zframe.config.models import SshSettings

    conn, _cur = mock_conn
    cfg = DbSettings(
        host="example.com",
        user="root",
        password="Test@123",
        database="app",
    )
    ssh = SshSettings(user="deploy", password="deploy", host="example.com")
    with (
        patch("pymysql.connect", side_effect=[OSError("refused"), conn]) as connect,
        patch("zframe.db.remote_setup.setup_mariadb_remote") as setup,
    ):
        db = DbClient(cfg, ssh=ssh)
        assert db.connect() is conn
    setup.assert_called_once_with(cfg, ssh)
    assert connect.call_count == 2
    assert db._remote_setup_done is True


def test_connect_skips_ssh_when_not_configured(db_config: DbSettings):
    with patch("pymysql.connect", side_effect=OSError("refused")):
        db = DbClient(db_config)
        with pytest.raises(OSError, match="refused"):
            db.connect()


def test_build_mariadb_remote_script_contains_steps():
    from zframe.db.remote_setup import build_mariadb_remote_script

    script = build_mariadb_remote_script(
        db_user="root",
        db_password="Test@123",
        sudo_password="deploy",
    )
    assert "bind-address = 0.0.0.0" in script
    assert "systemctl restart mariadb" in script
    assert "GRANT ALL PRIVILEGES" in script
    assert "root'@'%'" in script
    assert "Test@123" in script
    assert "sudo -S" in script


def test_setup_mariadb_remote_uses_ssh_client():
    from zframe.config.models import SshSettings
    from zframe.db.remote_setup import setup_mariadb_remote
    from zframe.ssh.client import SshClient, SshResult

    cfg = DbSettings(
        host="10.0.0.1",
        user="root",
        password="Test@123",
        database="app",
    )
    ssh = SshClient(
        SshSettings(host="10.0.0.1", user="deploy", password="deploy")
    )
    result = SshResult(
        command="bash -s",
        exit_code=0,
        stdout="[5/5] done\n",
        stderr="",
    )
    with (
        patch.object(ssh, "run_script", return_value=result) as run_script,
        patch("zframe.db.remote_setup.time.sleep"),
    ):
        setup_mariadb_remote(cfg, ssh, settle_seconds=0)
    run_script.assert_called_once()
    script = run_script.call_args[0][0]
    assert "systemctl restart mariadb" in script
