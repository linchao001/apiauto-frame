# HTTP & WebSocket

## 何时用

- 业务接口：**`services/` 封装** + 用例 `**req`；勿在用例 `HttpClient(...)` 或写死 IP。
- 探活：`client.get("/health")`。
- 获取凭证等跳过鉴权：`client.post(url, json=..., auth=False)`。

## HttpClient（`client`）

```python
client.get/post/put/patch/delete(url, *, params, json, data, headers, timeout, auth=True)
client.request(method, url, **kwargs)
client.websocket(url, **kwargs)  # → WebSocketSession
```

- 相对 URL 拼 `settings.http.base_url`。
- `http.max_retries`：仅网络/502–504；**不等**业务异步（用 `db.wait_*` / `wait_until`）。

## Response

`status_code`, `headers`, `text`, `json()`, `extract("$.path")`, `elapsed_ms`, `to_dict()`

## WebSocketSession

`send_text` / `send_json` · `receive_text` / `receive_json(timeout=...)` · `receive_json_until(...)`

## 鉴权

框架不内置产品鉴权。用例仓：

1. 子类化 `AuthProvider`
2. `register_auth("<type>", factory)`（init 已生成桩）
3. env 配 `auth.type: <type>`

| API | 何时 |
|-----|------|
| `AuthProvider` / `NoAuth` | 实现 / 无鉴权 |
| `build_auth(settings.auth)` | 非 pytest 脚本 |
| `register_auth("type", factory)` | 注册产品鉴权 |

`auth.type`：`none`（默认）或用例仓已注册的类型。
