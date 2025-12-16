---
paths: packages/core/data/**/*.py
---

# SQLite 规范

> 事务型数据库，用于配置、状态和交易记录

## 定位与职责

```
SQLite (事务)              DuckDB (分析)
├── 用户配置                ├── 历史行情
├── 策略参数                ├── 因子数据
├── 交易记录                ├── 回测结果
├── 系统状态                └── 大规模分析
├── Kill Switch 状态
└── 审计日志
```

**原则**：写多读少、需要 ACID 事务的数据用 SQLite。

## 连接管理

### 基本连接

```python
import sqlite3
from pathlib import Path

# 标准连接
conn = sqlite3.connect("data/ditto_state.db")

# 启用外键约束（重要）
conn.execute("PRAGMA foreign_keys = ON")

# 启用 WAL 模式（并发性能）
conn.execute("PRAGMA journal_mode = WAL")

# 返回字典形式的行
conn.row_factory = sqlite3.Row
```

### 连接池/服务模式

```python
from contextlib import contextmanager
from threading import local

_thread_local = local()

def get_db_path() -> Path:
    return Path(config.DATA_DIR) / "ditto_state.db"

@contextmanager
def get_connection():
    """线程安全的连接获取"""
    if not hasattr(_thread_local, "conn"):
        conn = sqlite3.connect(str(get_db_path()))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.row_factory = sqlite3.Row
        _thread_local.conn = conn

    try:
        yield _thread_local.conn
    except Exception:
        _thread_local.conn.rollback()
        raise
    else:
        _thread_local.conn.commit()

# 使用
with get_connection() as conn:
    conn.execute("INSERT INTO ...")
```

### FastAPI 集成

```python
from functools import lru_cache

class StateRepository:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

@lru_cache
def get_state_repo() -> StateRepository:
    return StateRepository(get_db_path())
```

## 表设计规范

### 命名约定

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| 表名 | snake_case，复数 | `trade_orders` |
| 列名 | snake_case | `created_at` |
| 主键 | `id` 或 `{table}_id` | `order_id` |
| 外键 | `{ref_table}_id` | `strategy_id` |
| 布尔 | `is_` 或 `has_` 前缀 | `is_active` |

### 核心表结构

```sql
-- 策略配置表
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    config_json TEXT NOT NULL,       -- JSON 格式的策略参数
    is_active INTEGER DEFAULT 1,     -- SQLite 无 BOOLEAN
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 交易订单表
CREATE TABLE IF NOT EXISTS trade_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    code TEXT NOT NULL,              -- ETF 代码
    direction TEXT NOT NULL,         -- 'buy' | 'sell'
    quantity INTEGER NOT NULL,
    price REAL,
    status TEXT DEFAULT 'pending',   -- 'pending' | 'filled' | 'cancelled'
    created_at TEXT DEFAULT (datetime('now')),
    filled_at TEXT,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

-- Kill Switch 状态表
CREATE TABLE IF NOT EXISTS kill_switch_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- 单例表
    level INTEGER DEFAULT 0,         -- 0: normal, 1-3: kill switch levels
    triggered_at TEXT,
    reason TEXT,
    peak_value REAL,                 -- 触发时的峰值净值
    current_drawdown REAL,           -- 当前回撤
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 初始化单例
INSERT OR IGNORE INTO kill_switch_state (id, level) VALUES (1, 0);

-- 审计日志表
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,        -- 'order_created' | 'kill_switch_triggered' | ...
    entity_type TEXT,                -- 'order' | 'strategy' | ...
    entity_id INTEGER,
    old_value TEXT,                  -- JSON
    new_value TEXT,                  -- JSON
    created_at TEXT DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_orders_strategy ON trade_orders(strategy_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON trade_orders(status);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
```

## CRUD 操作

### 参数化查询（必须）

```python
# Good: 参数化
cursor = conn.execute(
    "SELECT * FROM strategies WHERE name = ? AND is_active = ?",
    (strategy_name, 1)
)

# Bad: 字符串拼接（SQL 注入风险）
cursor = conn.execute(
    f"SELECT * FROM strategies WHERE name = '{strategy_name}'"  # 危险！
)
```

### 插入

```python
# 单条插入
cursor = conn.execute(
    """
    INSERT INTO trade_orders (strategy_id, code, direction, quantity, price)
    VALUES (?, ?, ?, ?, ?)
    """,
    (strategy_id, code, direction, quantity, price)
)
order_id = cursor.lastrowid

# 批量插入
orders = [
    (1, "510300", "buy", 1000, 4.5),
    (1, "510500", "buy", 2000, 6.8),
]
conn.executemany(
    """
    INSERT INTO trade_orders (strategy_id, code, direction, quantity, price)
    VALUES (?, ?, ?, ?, ?)
    """,
    orders
)
```

### 查询

```python
# 单条
row = conn.execute(
    "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
).fetchone()

if row:
    strategy = dict(row)  # Row 对象转 dict

# 多条
rows = conn.execute(
    "SELECT * FROM trade_orders WHERE status = ?", ("pending",)
).fetchall()

orders = [dict(row) for row in rows]
```

### 更新

```python
# 带条件更新
conn.execute(
    """
    UPDATE trade_orders
    SET status = ?, filled_at = datetime('now')
    WHERE id = ? AND status = 'pending'
    """,
    ("filled", order_id)
)

# 检查是否更新成功
if conn.total_changes == 0:
    raise ValueError(f"Order {order_id} not found or already processed")
```

### 删除

```python
# 软删除（推荐）
conn.execute(
    "UPDATE strategies SET is_active = 0 WHERE id = ?",
    (strategy_id,)
)

# 硬删除
conn.execute("DELETE FROM trade_orders WHERE id = ?", (order_id,))
```

## 事务处理

### 显式事务

```python
# 方式1: 手动控制
conn.execute("BEGIN")
try:
    conn.execute("INSERT INTO ...")
    conn.execute("UPDATE ...")
    conn.execute("COMMIT")
except Exception:
    conn.execute("ROLLBACK")
    raise

# 方式2: 上下文管理器（推荐）
with conn:  # 自动 commit，异常时 rollback
    conn.execute("INSERT INTO ...")
    conn.execute("UPDATE ...")
```

### Kill Switch 事务示例

```python
def trigger_kill_switch(
    conn: sqlite3.Connection,
    level: int,
    reason: str,
    peak_value: float,
    current_drawdown: float,
) -> None:
    """触发 Kill Switch，事务性更新"""
    with conn:
        # 更新状态
        conn.execute(
            """
            UPDATE kill_switch_state SET
                level = ?,
                triggered_at = datetime('now'),
                reason = ?,
                peak_value = ?,
                current_drawdown = ?,
                updated_at = datetime('now')
            WHERE id = 1
            """,
            (level, reason, peak_value, current_drawdown)
        )

        # 记录审计日志
        conn.execute(
            """
            INSERT INTO audit_logs (event_type, entity_type, entity_id, new_value)
            VALUES ('kill_switch_triggered', 'kill_switch', 1, ?)
            """,
            (json.dumps({
                "level": level,
                "reason": reason,
                "drawdown": current_drawdown,
            }),)
        )

        # 取消所有待执行订单
        conn.execute(
            """
            UPDATE trade_orders
            SET status = 'cancelled'
            WHERE status = 'pending'
            """
        )
```

## JSON 数据处理

```python
import json

# 存储 JSON
config = {"param1": 100, "param2": 0.05}
conn.execute(
    "INSERT INTO strategies (name, config_json) VALUES (?, ?)",
    ("my_strategy", json.dumps(config))
)

# 读取 JSON
row = conn.execute(
    "SELECT config_json FROM strategies WHERE name = ?",
    ("my_strategy",)
).fetchone()
config = json.loads(row["config_json"])

# SQLite JSON 函数（3.38+）
conn.execute("""
    SELECT json_extract(config_json, '$.param1') as param1
    FROM strategies
""")
```

## 性能优化

### PRAGMA 设置

```python
# 生产环境推荐设置
conn.execute("PRAGMA journal_mode = WAL")      # 并发读写
conn.execute("PRAGMA synchronous = NORMAL")    # 性能与安全平衡
conn.execute("PRAGMA cache_size = -64000")     # 64MB 缓存
conn.execute("PRAGMA temp_store = MEMORY")     # 临时表放内存
conn.execute("PRAGMA mmap_size = 268435456")   # 256MB 内存映射
```

### 批量操作

```python
# 大批量插入时关闭同步
conn.execute("PRAGMA synchronous = OFF")
conn.execute("BEGIN")
try:
    for batch in chunks(data, 1000):
        conn.executemany("INSERT INTO ...", batch)
    conn.execute("COMMIT")
finally:
    conn.execute("PRAGMA synchronous = NORMAL")
```

## 测试模式

```python
import pytest
import tempfile

@pytest.fixture
def test_db():
    """创建测试数据库"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    # 初始化 schema
    conn.executescript("""
        CREATE TABLE strategies (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE trade_orders (
            id INTEGER PRIMARY KEY,
            strategy_id INTEGER,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (strategy_id) REFERENCES strategies(id)
        );
    """)

    yield conn

    conn.close()
    Path(db_path).unlink()

def test_create_order(test_db):
    # 先创建策略
    test_db.execute("INSERT INTO strategies (name) VALUES ('test')")
    strategy_id = test_db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 创建订单
    test_db.execute(
        "INSERT INTO trade_orders (strategy_id) VALUES (?)",
        (strategy_id,)
    )
    test_db.commit()

    # 验证
    count = test_db.execute("SELECT COUNT(*) FROM trade_orders").fetchone()[0]
    assert count == 1
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 字符串拼接 SQL | SQL 注入 | 参数化 `?` 占位符 |
| 存储大量分析数据 | 性能差 | 用 DuckDB |
| 不启用外键 | 数据完整性 | `PRAGMA foreign_keys = ON` |
| 忽略事务 | 数据不一致 | 用 `with conn:` |
| PRAGMA synchronous = OFF 生产使用 | 数据丢失风险 | 仅批量导入时临时使用 |
