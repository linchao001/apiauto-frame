# 配置 settings & ctx

## 静态 get_settings() → Settings

| 属性 | 用途 |
|------|------|
| `.product` / `.env` | 配置中的 product 名、当前 env |
| `.http` | `base_url`, `timeout`, `max_retries` |
| `.auth` / `.db` / `.ssh` | 连接与鉴权 |
| `.assertx` | 全局断言默认 |
| `.vars` | 业务变量种子 |

加载：`config/product.yaml` + `config/env/<name>.yaml`；pytest `--env` / `--config-dir`。

工具：`discover_envs`、`load_settings`、`resolve_env_name`。

## 动态 get_ctx() → Context

`set` / `get` / `update` / `as_dict()` — 步骤间 id、token；初始来自 YAML `vars`。**不改** settings。

## Marks

| Mark | 何时 |
|------|------|
| `@pytest.mark.device("dev")` | 仅指定 env |
| `@pytest.mark.case_title(case_id=, title=)` | E2E 报告（无 testdata meta） |
| `@pytest.mark.P0` / `P1` / `P2` | 优先级 |
