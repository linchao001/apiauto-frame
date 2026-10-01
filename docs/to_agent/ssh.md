# SSH SshClient

`get_ssh()` / fixture `ssh`。env 需 `ssh.user`。

```python
ssh.run(cmd, check=False, timeout=None) -> SshResult  # .stdout .stderr .ok
ssh.sudo(cmd, check=True)
ssh.run_script(script, interpreter="bash -s", ...)
ssh.put(local, remote) / ssh.get(remote, local)
```

成功命令用 `check=True` 或判断 `result.ok`。

与 DB 共用 session 客户端时可触发 MariaDB 远程开通（见 [db.md](db.md)）。
