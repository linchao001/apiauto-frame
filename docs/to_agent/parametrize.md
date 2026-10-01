# 数据驱动 parametrize_from

## 默认（API 用例）

```python
@parametrize_from
def test_xxx(..., meta_data, req, expect, test_data):
```

- 数据：`testdata/<module_stem>.json`（与 `testcases/` 同级；兼容 `.yaml`、`data/`）。
- 键：`meta_data`（`id`/`title`/`exclude`）、`req`、`expect`、可选 `test_data`（默认 `{}`）。
- **禁止**入参名 `request`；用 `req`。

用例：`check(resp).status(200).body(expect, meta=meta_data)`。

## 自定义

| 方式 | 何时 |
|------|------|
| `@parametrize_from(argname="a,b", passthrough=True)` | 一次性扁平字段 |
| 子类 `Parametrize`：`normalize_case` / `filter_cases` / `default_argnames` | 产品统一引擎 |

## 辅助

`load_cases(path)` · `render(template, ctx)`
