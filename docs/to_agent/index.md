# Agent 文档索引

**Agent 请先读本文件**，再按场景打开 `to_agent/<模块>.md`。人类可读说明见仓库根目录 [README.md](../../README.md)。

导入：`from zframe import ...`（公开面见 `zframe.api.__all__`）。

## 场景 → 读哪个文件

| 我要做… | 文件 |
|--------|------|
| 选 fixture / getter | [fixtures.md](fixtures.md) |
| 发 HTTP / WS / 鉴权 | [http.md](http.md) |
| 断言响应或 DB | [assertions.md](assertions.md) |
| 数据驱动 / testdata | [parametrize.md](parametrize.md) |
| YAML / settings / ctx | [config.md](config.md) |
| CRUD / 轮询等 DB | [db.md](db.md) |
| 远程命令 / SFTP | [ssh.md](ssh.md) |
| 报告 / 日志 / 通知 / 并行 / 脚手架 / 从报告重跑失败 | [ops.md](ops.md) |
| 标准模板 / 反模式 | [patterns.md](patterns.md) |

## CLI

```bash
zframe --docs agent              # 本索引
zframe --docs agent/http         # Agent 模块
zframe --docs http               # 同上（裸 stem → to_agent）
```
