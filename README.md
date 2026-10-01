# ZFrame

Python 接口自动化框架：与用例仓库分离，面向多产品线复用。

## 打包

```bash
pip install build
python -m build
```

产物在 `dist/`（wheel / sdist）。

## 定位

| 仓库 | 职责 |
|------|------|
| **ZFrame（本仓）** | HTTP / WebSocket 客户端、鉴权抽象、DB（PyMySQL）、SSH（paramiko）、配置、上下文、断言、参数化、pytest 插件、报告钩子 |
| **用例仓** | 业务用例、测试数据、环境配置、产品鉴权实现、产品适配（`services/`）、共用辅助 |
| **产品 Kit（可选）** | 多仓复用时，将 `services/` / 鉴权抽成独立包 |

## 文档

人类可读说明以本 README 为准。面向代码 Agent 的精简 API 索引：

| 文档 | 说明 |
|------|------|
| [Agent API 索引](docs/to_agent/index.md) | `zframe --docs agent` |
| [fixtures](docs/to_agent/fixtures.md) | pytest fixtures / getter |
| [HTTP / 鉴权](docs/to_agent/http.md) | `client`、`AuthProvider`、`services/` |
| [断言](docs/to_agent/assertions.md) | `check()` |
| [参数化](docs/to_agent/parametrize.md) | `@parametrize_from` |
| [配置](docs/to_agent/config.md) | YAML / settings / ctx |
| [DB](docs/to_agent/db.md) | `db` fixture、CRUD、轮询 |
| [SSH](docs/to_agent/ssh.md) | 远程命令、SFTP |
| [运维](docs/to_agent/ops.md) | 报告、日志、通知、并行、脚手架、`--from-report` |
| [模板与反模式](docs/to_agent/patterns.md) | 标准写法 |

```bash
zframe --docs              # 列出主题
zframe --docs agent        # Agent 索引
zframe --docs agent/http   # 单模块
```

## 安装

```bash
# 本地开发（含 pytest-cov / respx）
pip install -e ".[dev]"

# 用例仓 / 打包 wheel：主依赖已含 pytest-html、PyMySQL、paramiko、httpx-ws
pip install zframe==0.3.0
# 或本地路径 / 未发布 wheel
pip install /path/to/zframe-0.3.0-py3-none-any.whl
pip install -e /path/to/ZFrame
```

## 快速开始

### 脚手架生成用例仓

`zframe --init` 按框架模板即时生成中性骨架，并附带**与业务无关**的 httpbin 示例（`API/Sample`、`E2E/Sample`）：

```bash
pip install -e ".[dev]"

zframe --init --name acme-api-auto
zframe -h
# 等价
python -m zframe --init --name acme-api-auto
```

```bash
cd acme-api-auto
# Sample 默认 auth.type=none + https://httpbin.org，可直接跑通：
pytest -q --env dev
# 接真实产品时：实现 auth.py 中的 ProductAuth，再改 env 的 base_url / auth.type
```

生成目录约定：

```text
acme-api-auto/
  conftest.py              # register_auth + 默认 config/
  auth.py                  # ProductAuth(AuthProvider) 桩
  config/
    product.yaml
    env/
      dev.yaml             # httpbin base_url + auth.type=none（示例）
  helpers/
  acme/                    # 由 --name 推导的产品包
    WEB/
      services/            # SampleApi → GET /get、POST /post
      API/Sample/{testcases,testdata}/   # @parametrize_from + check()
      E2E/Sample/{testcases,testdata}/   # GET→POST 串联示例
```

参数化约定见 [parametrize.md](docs/to_agent/parametrize.md)：`@parametrize_from` 在 `testcases/` 同级 `testdata/` 下按模块名匹配。

**默认结构**：`meta_data` / `req` / `expect` / `test_data`（`test_data` 可选）。

**自定义结构**：

```python
@parametrize_from(argname="username,password,expect_code", passthrough=True)
def test_login(username, password, expect_code):
    ...
```

## 上层常用入口

```python
from zframe import (
    HttpClient,
    WebSocketSession,
    AuthProvider,
    NoAuth,
    build_auth,
    register_auth,
    Settings,
    load_settings,
    Context,
    DbClient,
    get_db,
    SshClient,
    get_ssh,
    check,
    SoftAssertions,
    ANY,
    Regex,
    Approx,
    load_cases,
    parametrize_from,
    render,
    Parametrize,
    RetryConfig,
    get_logger,
)
```

pytest fixtures：`client` / `settings` / `ctx` / `auth_provider` / `db` / `ssh`

```bash
zframe --init --name acme-api-auto
pytest --env dev --config-dir ./config
# optional: --report / --from-report PATH / --notify / --no-notify
```

## 多设备并行

详见 [ops.md](docs/to_agent/ops.md)。一台设备 = 一个 `config/env/<name>.yaml`（各自 `http.base_url`）。

```bash
pytest -q --env dev --config-dir ./config

python -m zframe.parallel --envs dev,env-b,env-c \
  --config-dir ./config -- pytest -q

zframe-parallel --envs dev,env-c --config-dir ./config -- pytest -q
```

```python
@pytest.mark.device("dev")
def test_dev_only(client):
    ...
```

## 鉴权（用例仓实现）

详见 [http.md](docs/to_agent/http.md)。

框架**不内置**产品登录鉴权，只提供：

| API | 说明 |
|-----|------|
| `AuthProvider` | 抽象：`ensure_auth` / `apply` |
| `NoAuth` | 无鉴权 |
| `register_auth` / `build_auth` | 按 `auth.type` 注册与构建 |

用例仓步骤：

1. 子类化 `AuthProvider`（`zframe --init` 已生成 `auth.py` 桩）
2. 在根 `conftest.py` `register_auth("<pkg>", ProductAuth.from_config)`
3. env 配置 `auth.type: <pkg>` 及产品自有字段

```yaml
# config/env/dev.yaml（接真实产品时）
http:
  base_url: https://example.com
auth:
  type: acme
```

脚手架默认 `auth.type: none` + `https://httpbin.org`，便于先跑通 Sample；接产品后改回上表。

## 配置分层

详见 [config.md](docs/to_agent/config.md)。典型结构：

```text
config/
  product.yaml
  env/
    dev.yaml
```

## HTTP / DB / SSH / 断言 / 报告

- HTTP：`client` + `services/` — [http.md](docs/to_agent/http.md)
- DB：`db` / `get_db()` — [db.md](docs/to_agent/db.md)
- SSH：`ssh` / `get_ssh()` — [ssh.md](docs/to_agent/ssh.md)
- 断言：`check(resp)` — [assertions.md](docs/to_agent/assertions.md)
- 报告 / 通知 / 并行： [ops.md](docs/to_agent/ops.md)

## 版本

当前版本见 `pyproject.toml`（`0.3.0`）。变更见 [CHANGELOG.md](CHANGELOG.md)。
