# 模板 & 反模式

## 标准 API 用例

```python
from zframe import check, get_db, parametrize_from

@parametrize_from
def test_create_item(item_api, meta_data, req, expect, test_data):
    cleanup = test_data.get("cleanup")
    if cleanup:
        get_db().delete(cleanup["table"], where=cleanup["where"])
    resp = item_api.create(**req)
    check(resp).status(200, msg="create HTTP 200").body(
        expect, meta=meta_data, msg="create response body"
    )
    row = get_db().select_one("items", where={"code": req["code"]})
    check(row).is_not_none(msg="row should exist").equals(
        {"code": req["code"], "name": req["name"]},
        msg="persisted fields should match request",
    )
```

## 反模式

1. 写死 IP — 用 `settings.http.base_url` + `services`。
2. `time.sleep` 等异步 — `wait_until` / `db.wait_*`。
3. POST 重试当业务等待 — 请求重试只治网络/网关。
4. DB 期望进 JSON `expect` — `check(row).equals(...)`。
5. 入参名 `request` — 用 `req`。
6. 未配 `db` 却 `get_db()`。
7. 本地开飞书 — 默认 `notify.enabled: false`。
8. 关键断言不写 `msg=` — 失败报告难读意图（见 [assertions.md](assertions.md)）。
