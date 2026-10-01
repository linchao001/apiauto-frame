# 报告 / 日志 / 通知 / 并行 / 脚手架

## Pytest CLI

| 参数 | 何时 |
|------|------|
| `--env` / `--config-dir` / `--product` | 环境与配置 |
| `--report` / `--report-dir` | HTML → `reports/<env>/<ts>/` |
| `--from-report PATH` | 只跑报告中 Failed/Error（`PATH`=report.html 或 run 目录） |
| `--notify` / `--no-notify` | 飞书汇总（默认不发） |
| `--no-live-log` | 关终端实时日志 |
| `--tb=…`（显式） | 恢复 pytest 源码 traceback；默认失败只打调用点 + 原因 |
| `-m P0` 等 | 按优先级筛选 |

### 从报告重跑失败

```bash
pytest -q --from-report reports/<env>/<ts>/report.html \
  --env <env> --config-dir ./config --report
```

解析 pytest-html `data-jsonblob`；仅 Failed/Error；无失败或零匹配 → exit 2。

## 代码

| API | 何时 |
|-----|------|
| `get_logger(name)` | 业务日志 |
| `register_log_origin_skip(__file__)` | helper 内打日志对齐行号 |
| `step` / `attach_response` / `attach_text` | 报告步骤（可选） |
| `remember_response(resp)` | 失败附 last HTTP |

通知扩展：`register_notifier` / `build_notifier`（session 结束框架已调）。

## 并行

```bash
zframe-parallel --envs dev,env-b --config-dir ./config -- pytest -q
```

## 脚手架

```bash
zframe --init  --name my-repo
```

生成中性骨架 + httpbin Sample（`auth.type: none`，API/E2E 各一可跑示例）。接产品：实现 `ProductAuth`，改 `base_url` / `auth.type`。
