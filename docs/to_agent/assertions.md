# 断言 check()

`from zframe import check, ANY, Approx, Regex, SoftAssertions, extract`

## 分流

- `check(resp)` → HTTP 链式
- `check(row|rows|dict|list)` → 通用（DB 等）

## check(resp)

| 方法 | 何时 |
|------|------|
| `.status(code, msg=)` / `.status_in(*codes, msg=)` | HTTP 码 |
| `.body(expect, meta=meta_data, path=, exclude=, mode=, allow_extra=, msg=)` | **主路径**：testdata `expect` |
| `.jsonpath(path, expected=None, exists=True, msg=)` | 少数字段 |
| `.header(name, expected=None, msg=)` | 响应头 |
| `.contains(text, msg=)` | 非 JSON 文本 |
| `.schema(schema, msg=)` | 结构契约 |

默认 `mode="loose"`、`allow_extra=True`。exclude = 全局 `assertx.exclude` ∪ `meta_data.exclude` ∪ 调用处。

## check(通用)

| 方法 | 何时 |
|------|------|
| `.is_not_none(msg=)` / `.is_none(msg=)` | `select_one` 前置 |
| `.equals(expected, ..., msg=)` | DB 行 / dict |
| `.count(n, msg=)` / `.count_at_least` / `.count_at_most` | 列表长度 |
| `.contains(item, ..., msg=)` | 列表含一行 |

## `msg=` 失败提示（推荐）

所有公开断言方法均支持可选关键字 **`msg: str | None`**。失败时：

- **有 diff 表**（status / body / equals / header 值不等）：标题变为 `Assertion failed: {msg}`，diff 表与 response body 上下文不变
- **纯文本失败**（is_not_none / count / contains 文本等）：细节变为 `{msg}: {原错误}`
- **未传 `msg`**：行为与旧版一致

```python
check(resp).status(200, msg="create should return HTTP 200")
check(resp).body(expect, meta=meta_data, msg="create body should succeed")
check(row).is_not_none(msg="row should exist").equals(
    {"code": req["code"]},
    msg="persisted fields should match request",
)
```

Agent 写用例时：关键断言尽量带 `msg=`，报告里可直接看到意图。

## 匹配器（expect 内）

`ANY` / `{"$any": true}` · `Regex` / `{"$regex": "..."}` · `Approx` / `{"$approx": x, "abs": ...}`

## 其它

- `extract(resp, path)` — 取值不断言
- `SoftAssertions().check(...).run(lambda: ...).assert_all()` — 软断言（`.check(cond, message)` 本身已有文案）

**DB 期望写在用例代码**，勿塞进 JSON `expect`。
