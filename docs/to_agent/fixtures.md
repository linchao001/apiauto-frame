# Fixtures & Getter

Session 级；多 `--env` 并行时各进程独立实例。

| Fixture | 类型 | 何时用 |
|---------|------|--------|
| `client` / `http_client` | `HttpClient` | HTTP / WS 用例 |
| `settings` | `Settings` | 读 `http`/`auth`/`db`/… |
| `ctx` | `Context` | 步骤间传运行时值 |
| `db` | `DbClient` | env 配了 `db.user` 或 `db.database` |
| `ssh` | `SshClient` | env 配了 `ssh.user` |
| `auth_provider` | `AuthProvider` | 扩展鉴权（少见） |

无 fixture 时：`get_db()`、`get_ssh()`、`get_settings()`、`get_ctx()`。

未配 `db`/`ssh` 时勿注入对应 fixture。纯 HTTP 用例勿依赖 `db`。
