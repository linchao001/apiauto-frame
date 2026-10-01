"""SSH client (mocked paramiko)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zframe.config.models import SshSettings
from zframe.ssh import session as ssh_session
from zframe.ssh.client import SshClient, SshResult
from zframe.ssh.session import bind_ssh, clear_ssh, get_ssh


@pytest.fixture
def ssh_config() -> SshSettings:
    return SshSettings(
        host="10.0.0.1",
        user="deploy",
        password="deploy",
    )


def test_ssh_result_check():
    ok = SshResult(command="true", exit_code=0, stdout="", stderr="")
    assert ok.check() is ok
    bad = SshResult(command="false", exit_code=1, stdout="", stderr="boom")
    with pytest.raises(RuntimeError, match="exit=1"):
        bad.check()


def test_run_command(ssh_config: SshSettings):
    stdout = MagicMock()
    stdout.read.return_value = b"hello\n"
    stdout.channel.recv_exit_status.return_value = 0
    stderr = MagicMock()
    stderr.read.return_value = b""
    stdin = MagicMock()

    raw = MagicMock()
    raw.exec_command.return_value = (stdin, stdout, stderr)

    with patch("zframe.ssh.client._require_paramiko") as require:
        paramiko = MagicMock()
        paramiko.SSHClient.return_value = raw
        paramiko.AutoAddPolicy.return_value = object()
        require.return_value = paramiko

        client = SshClient(ssh_config)
        result = client.run("uname -a", check=True)

    assert result.ok
    assert result.stdout == "hello\n"
    raw.connect.assert_called_once()
    assert raw.connect.call_args.kwargs["hostname"] == "10.0.0.1"
    assert raw.connect.call_args.kwargs["username"] == "deploy"


def test_sudo_wraps_command(ssh_config: SshSettings):
    client = SshClient(ssh_config)
    with patch.object(client, "run") as run:
        run.return_value = SshResult("x", 0, "", "")
        client.sudo("systemctl restart nginx")
    cmd = run.call_args[0][0]
    assert "sudo -S" in cmd
    assert "systemctl restart nginx" in cmd


def test_bind_and_get_ssh(ssh_config: SshSettings):
    prev = ssh_session._client
    clear_ssh()
    try:
        client = SshClient(ssh_config)
        bind_ssh(client)
        assert get_ssh() is client
    finally:
        clear_ssh()
        ssh_session._client = prev
