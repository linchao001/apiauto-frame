# DB DbClient

`get_db()` / fixture `db`。勿 `pymysql.connect`。

## CRUD

```python
db.insert(table, data) -> lastrowid
db.insert_many(table, rows)
db.select / select_one(table, *, fields, where, order_by, limit, offset)
db.count(table, where=...)
db.update / delete(table, ..., where=..., force=False)  # 无 where 须 force=True
```

`where`：标量 `=`、`None`→`IS NULL`、list→`IN`。

Raw：`execute` / `fetch_one` / `fetch_all` / `fetch_value`（`%s` 占位）。

## 异步终态（勿 sleep / HTTP 重试）

| API | 等到 |
|-----|------|
| `wait_until(label, predicate, timeout_sec=30, interval_sec=0.5)` | 任意条件 True |
| `db.wait_absent(table, where=...)` | 行消失 |
| `db.wait_present(...)` | 行出现 |
| `db.wait_count(table, n, where=...)` | 行数 |
| `db.wait_field(table, field, expected, where=...)` | 字段值 |

超时 → `AssertionError`（含 last snapshot）。

`ssh` + `db` 且 `auto_setup_remote`（默认）：TCP 失败可自动远程开 MariaDB。
