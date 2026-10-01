# Changelog

## Unreleased

- Scaffold: `zframe --init` Sample cases are a runnable, business-agnostic httpbin demo (`auth.type: none`, `@parametrize_from` + `check()`); `ProductAuth` remains a stub for real products
- **Breaking:** Remove builtin auth providers (`bearer` / `basic` and any product-specific ones); case repos must subclass `AuthProvider` and `register_auth`
- **Breaking:** Remove `examples/` and `--line` blueprints; `zframe --init --name` generates a neutral skeleton from templates
- **Breaking:** Remove product automation-account bootstrap and SUT version probing from the pytest plugin
- Version: `0.3.0`
- Logging / reports: call-phase failures default to compact output (`at file:line` + reason / assertion diff); no test-source dump. Escape with explicit `--tb=...`
- Reports: `--from-report PATH` re-runs only Failed/Error cases from a pytest-html `report.html` (or run directory); does not rely on `--lf` / `.pytest_cache`
- Docs: agent modules under `docs/to_agent/` (`index.md` router); `zframe --docs agent`, `agent/http`, or bare stem → agent doc; human guide is README
- Packaging: bundle `docs/` into wheel/sdist (`zframe/docs/`); `zframe --docs` lists topics, `zframe --docs TOPIC [--open]` prints or opens a doc file
- Poll: `wait_until(label, predicate, timeout_sec=30, interval_sec=0.5)` for async side effects; raises `AssertionError` on timeout with last snapshot
- DB: `DbClient.wait_absent` / `wait_present` / `wait_count` / `wait_field` — poll until row/count/field reaches expected state (defaults match `wait_until`)

## 0.1.3

- Reports: `resolve_case_meta` merges parametrize row `meta_data` (`id`/`title`/`priority`) with method-level `@case_title` / `P0`/`P1`/`P2`; row wins for id/title; conflicting priority warns and keeps highest (P0 > P1 > P2)

## 0.1.2

- Parametrize: default case shape adds optional `test_data` for seed/cleanup/factory payloads; injected as fourth param alongside `meta_data`, `req`, `expect` (defaults to `{}`)
- Config: `db.host` optional — falls back to hostname from `http.base_url` when omitted
- Case marks: `@pytest.mark.case_title(case_id=..., title=...)` and `@pytest.mark.P0`/`P1`/`P2`; HTML report shows Case ID / Priority / Title columns plus inline case/step HTML; Environment only shows `base_url`; multiple priorities warn and keep the highest; independent of `meta_data`
- Packaging: promote `pytest-html` / `paramiko` / `PyMySQL` / `httpx-ws` to main dependencies so a plain `.whl` install includes DB/SSH/WS/HTML; extras `[html]`/`[ssh]`/`[db]`/`[ws]` remain as aliases; `dev` is only pytest-cov + respx
- Scaffold: `zframe --init --line <name> --name <repo>` copies a blueprint from `examples/` into the current directory; `zframe -h` / `python -m zframe`
- WebSocket: `HttpClient.websocket()` via optional `httpx-ws` (`pip install 'zframe[ws]'`); shares auth/headers/`base_url` with HTTP; `WebSocketSession` helpers (`send_*` / `receive_*` / `receive_json_until`)
- Auth: optional session-start hook to reset a dedicated automation account so parallel runs do not share the same admin session
- Multi-device: treat each device as `config/env/<name>.yaml`; `@pytest.mark.device(...)` filters by `--env`; `zframe-parallel` / `python -m zframe.parallel` runs one pytest subprocess per env
- Reports: `--report` archives to `reports/<env>/<timestamp>/report.html` with per-env `latest.json` (parallel-safe)
- Notify: session-end Feishu webhook cards (`notify` in product/env YAML); default `enabled: false` (local/dev silent); CI use `--notify` or `enabled: true`; CLI `--no-notify` to force off; no per-case failure list
- SSH: first-class case capability (`SshClient` / `get_ssh()` / fixture `ssh`); top-level `ssh` in env YAML; optional extra `zframe[ssh]`; legacy `db.ssh` still migrated
- DB: on connect failure with `ssh` configured, auto-runs MariaDB remote setup over the shared SSH client, then retries once; `zframe[db]` includes paramiko
- Reports: replace Allure with pytest-html; `pytest --report` writes self-contained HTML (+ `latest.json`)
- Remove Allure / npm CLI (`package.json`, `allure-pytest`); optional extra is now `zframe[html]`
- DB: PyMySQL-backed `DbClient` for case-layer CRUD (`insert`/`select`/`update`/`delete` + raw SQL); single-DB config via `db` in env YAML; fixture `db` and `get_db()`; optional extra `zframe[db]`
- Data-driven: custom case shapes via `passthrough=True` + `argname=...`, or subclass `Parametrize` (`default_argnames` / `normalize_case` / `arg_fields` / `filter_cases`); `parametrize_from` is the default instance
- `jsonpath` supports the same matchers as `body` (`ANY` / `Regex` / `Approx` + JSON markers)
- `check(resp).body(expect)`: default `allow_extra=True`; matchers (`ANY`/`Regex`/`Approx` + JSON markers); global `assertx.exclude` + `meta_data.exclude`; loose hashable list multiset
- Add `check(resp).body(expect)` full-payload JSON assert (`loose`/`strict`, `exclude`, `allow_extra`, optional `path`)
- Rename fluent assertion entry `expect` → `check` (avoids clash with parametrize field `expect`)
- Scaffold sample exercises an authenticated API call via registered `auth.type`
- Default env renamed from `sit` to `test`
- Auto-discover `config/env/*.y{a}ml`: validate `--env`, auto-pick when only one file exists
- Auth centralized in framework via `auth.type` registry (`build_auth` / `register_auth`)
- Built-in sample auth providers (`type` registry): login for access token, then apply Bearer and common request headers
- `parametrize_from` auto-resolves data by test module stem + method name (class-aware); path no longer required
- Test data unified on JSON (`.json` preferred over YAML); scaffold sample and framework tests updated accordingly
- `parametrize_from` expands cases as `meta_data` / `req` / `expect` / `test_data` (JSON: same keys; `test_data` optional, defaults to `{}`; legacy JSON `request` still accepted; pytest reserved name `request` is not used)
- Case-repo layout: `{Product}/{WEB,...}/{services,API,E2E}/`，`API`/`E2E` 下再按模块分目录，各自 `testcases/` + `testdata/`（单接口 vs 链路）；`parametrize_from` resolves sibling `testdata/` of enclosing `testcases/` (legacy `data/` fallback)
- Auto-discover `config/` from pytest target path (IDE runs without `--config-dir`); case-repo conftest defaults to local config


## 0.1.0

- Initial release: HttpClient (httpx), AuthProvider, layered config, Context
- Request retry, assertions, soft assert, data-driven parametrize
- pytest plugin (`--env` / `--product` / `--config-dir`)
- Sample case-repo layout
