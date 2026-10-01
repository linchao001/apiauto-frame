"""Pydantic settings models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HttpSettings(BaseModel):
    base_url: str = ""
    timeout: float = 30.0
    verify_ssl: bool = True
    default_headers: dict[str, str] = Field(default_factory=dict)
    max_retries: int = 0
    retry_backoff: float = 0.5


class AssertSettings(BaseModel):
    """Defaults for ``check(...).body(...)`` / ``check(...).equals(...)``."""

    mode: Literal["loose", "strict"] = "loose"
    allow_extra: bool = True
    exclude: list[str] = Field(default_factory=list)


class SshSettings(BaseModel):
    """SSH connection for case-layer remote ops and DB auto remote-setup.

    Empty / default instance means SSH is not configured (see :attr:`enabled`).
    """

    host: str = ""
    port: int = 22
    user: str = ""
    password: str = ""
    key_filename: str = ""
    connect_timeout: float = 10.0
    command_timeout: float = 120.0

    @property
    def enabled(self) -> bool:
        return bool(self.user)

    # Alias used by DB remote-setup checks.
    @property
    def configured(self) -> bool:
        return self.enabled


class DbSettings(BaseModel):
    """Single MySQL / MariaDB connection (PyMySQL).

    Empty / default instance means DB is not configured (see :attr:`enabled`).
    When loading from YAML, omitted ``host`` falls back to ``http.base_url``'s
    hostname (see ``normalize_db_section``).
    """

    host: str = "127.0.0.1"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = ""
    charset: str = "utf8mb4"
    connect_timeout: float = 10.0
    read_timeout: float | None = None
    write_timeout: float | None = None
    autocommit: bool = True
    auto_setup_remote: bool = True

    @property
    def enabled(self) -> bool:
        return bool(self.database or self.user)


class NotifySettings(BaseModel):
    """Session-end test result notification (e.g. Feishu webhook).

    Default is off so local/IDE runs do not spam the chat. Put ``webhook`` in
    YAML and enable with ``enabled: true`` (CI product overlay) or CLI
    ``--notify``. Empty / default instance means notify is off (see
    :attr:`configured`).
    """

    enabled: bool = False
    on: Literal["always", "failure", "success"] = "always"
    type: str = "feishu"
    webhook: str = ""
    title: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.webhook.strip())


class Settings(BaseModel):
    """Merged runtime settings for a test session."""

    product: str = ""
    env: str = "test"
    http: HttpSettings = Field(default_factory=HttpSettings)
    auth: dict[str, Any] = Field(default_factory=dict)
    vars: dict[str, Any] = Field(default_factory=dict)
    assertx: AssertSettings = Field(default_factory=AssertSettings)
    db: DbSettings = Field(default_factory=DbSettings)
    ssh: SshSettings = Field(default_factory=SshSettings)
    notify: NotifySettings = Field(default_factory=NotifySettings)
    extra: dict[str, Any] = Field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.vars:
            return self.vars[key]
        if key in self.extra:
            return self.extra[key]
        return default
