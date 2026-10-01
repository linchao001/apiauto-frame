"""Paramiko-backed SSH client for case-layer remote commands / file transfer."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zframe.config.models import SshSettings
from zframe.report.logging import get_logger

logger = get_logger("zframe.ssh")


def _require_paramiko():
    try:
        import paramiko
    except ImportError as exc:  # pragma: no cover - exercised when extra missing
        raise ImportError(
            "paramiko is required for zframe SSH support. "
            "Install with: pip install 'zframe[ssh]' or pip install 'zframe[db]'"
        ) from exc
    return paramiko


@dataclass(frozen=True)
class SshResult:
    """Outcome of a remote command."""

    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def check(self) -> SshResult:
        """Raise :class:`RuntimeError` when the remote exit code is non-zero."""
        if not self.ok:
            detail = (self.stderr or self.stdout).strip() or "no output"
            raise RuntimeError(
                f"SSH command failed (exit={self.exit_code}): {self.command!r}\n{detail}"
            )
        return self


class SshClient:
    """Case-facing SSH API: run commands, scripts, sudo, and SFTP put/get.

    Connection is opened lazily on first use. Prefer ``get_ssh()`` / fixture ``ssh``
    when running under the zframe pytest plugin.
    """

    def __init__(self, config: SshSettings) -> None:
        self.config = config
        self._client: Any | None = None

    @property
    def host(self) -> str:
        if not self.config.host:
            raise RuntimeError(
                "SSH host is not set; configure ``ssh.host`` in env YAML "
                "(or rely on db/http host fallback at load time)"
            )
        return self.config.host

    def connect(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.config.configured:
            raise RuntimeError(
                "SSH is not configured; add ``ssh.user`` (and usually host/password) "
                "to config/env/<env>.yaml"
            )
        paramiko = _require_paramiko()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.config.port,
            username=self.config.user,
            password=self.config.password or None,
            key_filename=self.config.key_filename or None,
            timeout=self.config.connect_timeout,
            allow_agent=False,
            look_for_keys=bool(self.config.key_filename),
        )
        self._client = client
        logger.info(
            "ssh connected %s@%s:%s",
            self.config.user,
            self.host,
            self.config.port,
        )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None
                logger.info("ssh closed")

    def __enter__(self) -> SshClient:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def run(
        self,
        command: str,
        *,
        check: bool = False,
        get_pty: bool = False,
        timeout: float | None = None,
    ) -> SshResult:
        """Execute a remote shell command and return :class:`SshResult`."""
        client = self.connect()
        cmd_timeout = self.config.command_timeout if timeout is None else timeout
        logger.debug("ssh run %s", command)
        stdin, stdout, stderr = client.exec_command(
            command, get_pty=get_pty, timeout=cmd_timeout
        )
        stdin.close()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = int(stdout.channel.recv_exit_status())
        result = SshResult(
            command=command, exit_code=exit_code, stdout=out, stderr=err
        )
        if check:
            result.check()
        return result

    def run_script(
        self,
        script: str,
        *,
        check: bool = True,
        interpreter: str = "bash -s",
        get_pty: bool = True,
        timeout: float | None = None,
    ) -> SshResult:
        """Pipe ``script`` to a remote interpreter (default ``bash -s``)."""
        client = self.connect()
        cmd_timeout = self.config.command_timeout if timeout is None else timeout
        logger.debug("ssh run_script via %s (%s bytes)", interpreter, len(script))
        stdin, stdout, stderr = client.exec_command(
            interpreter, get_pty=get_pty, timeout=cmd_timeout
        )
        stdin.write(script if script.endswith("\n") else script + "\n")
        stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = int(stdout.channel.recv_exit_status())
        result = SshResult(
            command=interpreter, exit_code=exit_code, stdout=out, stderr=err
        )
        if check:
            result.check()
        return result

    def sudo(
        self,
        command: str,
        *,
        check: bool = True,
        password: str | None = None,
        timeout: float | None = None,
    ) -> SshResult:
        """Run ``command`` with sudo (password via ``sudo -S`` when available)."""
        pw = self.config.password if password is None else password
        if pw:
            remote = (
                f"echo {shlex.quote(pw)} | sudo -S -p '' "
                f"bash -lc {shlex.quote(command)}"
            )
        else:
            remote = f"sudo -n bash -lc {shlex.quote(command)}"
        return self.run(remote, check=check, get_pty=True, timeout=timeout)

    def put(self, local: str | Path, remote: str) -> None:
        """Upload a local file to ``remote`` path via SFTP."""
        client = self.connect()
        local_path = Path(local)
        with client.open_sftp() as sftp:
            sftp.put(str(local_path), remote)
        logger.debug("ssh put %s -> %s", local_path, remote)

    def get(self, remote: str, local: str | Path) -> None:
        """Download ``remote`` file to a local path via SFTP."""
        client = self.connect()
        local_path = Path(local)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with client.open_sftp() as sftp:
            sftp.get(remote, str(local_path))
        logger.debug("ssh get %s -> %s", remote, local_path)
