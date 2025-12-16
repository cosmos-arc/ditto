---
paths: packages/core/data/**/*.py
---

# DuckDB 规范

> 分析型数据库，用于因子计算和回测数据

## 定位与职责

```
DuckDB (分析)              SQLite (事务)
├── 历史行情数据            ├── 用户配置
├── 因子数据                ├── 交易记录
├── 回测结果                ├── 系统状态
└── 大规模聚合计算          └── 元数据
```

**原则**：读多写少用 DuckDB，写多读少用 SQLite。

## 连接管理

### 基本连接

```python
import duckdb

# 文件数据库（推荐）
conn = duckdb.connect("data/ditto.db")

# 内存数据库（测试用）
conn = duckdb.connect(":memory:")

# 只读模式（并发安全）
conn = duckdb.connect("data/ditto.db", read_only=True)
```

### 连接池模式

```python
from contextlib import contextmanager
from functools import lru_cache

@lru_cache(maxsize=1)
def get_db_path() -> Path:
    return Path(config.DATA_DIR) / "ditto.db"

@contextmanager
def get_connection(read_only: bool = False):
    """获取数据库连接的上下文管理器"""
    conn = duckdb.connect(str(get_db_path()), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()

# 使用
with get_connection() as conn:
    result = conn.execute("SELECT * FROM prices").pl()
```

### 应用服务中的连接

```python
class DataService:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(str(self._db_path))
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
```

## 表设计规范

### 命名约定

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| 表名 | snake_case，复数 | `etf_daily_prices` |
| 列名 | snake_case | `trade_date`, `close_price` |
| 索引 | `idx_{table}_{columns}` | `idx_prices_date_code` |
| 视图 | `v_{name}` | `v_latest_prices` |

### 核心表结构

```sql
-- 日线行情表
CREATE TABLE IF NOT EXISTS etf_daily_prices (
    code VARCHAR NOT NULL,           -- ETF代码
    trade_date DATE NOT NULL,        -- 交易日期
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume BIGINT,
    amount DOUBLE,
    adj_factor DOUBLE DEFAULT 1.0,   -- 复权因子
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, trade_date)
);

-- 因子表（PIT 安全设计）
CREATE TABLE IF NOT EXISTS factors (
    code VARCHAR NOT NULL,
    trade_date DATE NOT NULL,        -- 因子对应的交易日
    knowledge_date DATE NOT NULL,    -- 因子可知的日期（≥ trade_date）
    factor_name VARCHAR NOT NULL,
    factor_value DOUBLE,
    PRIMARY KEY (code, trade_date, factor_name)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_prices_date ON etf_daily_prices(trade_date);
CREATE INDEX IF NOT EXISTS idx_factors_knowledge ON factors(knowledge_date);
```

### PIT 安全的因子表设计

```sql
-- 财务因子表：必须包含 knowledge_date
CREATE TABLE IF NOT EXISTS financial_factors (
    code VARCHAR NOT NULL,
    report_period DATE NOT NULL,     -- 报告期（如 2024-03-31）
    announce_date DATE NOT NULL,     -- 实际披露日期
    knowledge_date DATE NOT NULL,    -- = announce_date，数据可用日
    pe_ttm DOUBLE,
    pb DOUBLE,
    roe DOUBLE,
    PRIMARY KEY (code, report_period)
);

-- 查询时使用 knowledge_date 而非 report_period
SELECT * FROM financial_factors
WHERE knowledge_date <= '2024-06-30'  -- PIT 安全查询
  AND code = '510300';
```

## 查询模式

### 基本查询

```python
# 返回 Polars DataFrame（推荐）
df = conn.execute("""
    SELECT code, trade_date, close, volume
    FROM etf_daily_prices
    WHERE trade_date >= '2024-01-01'
    ORDER BY trade_date
""").pl()

# 参数化查询（防 SQL 注入）
df = conn.execute("""
    SELECT * FROM etf_daily_prices
    WHERE code = $1 AND trade_date BETWEEN $2 AND $3
""", [code, start_date, end_date]).pl()
```

### 高效聚合

```python
# 利用 DuckDB 的分析函数
df = conn.execute("""
    SELECT
        code,
        trade_date,
        close,
        AVG(close) OVER (
            PARTITION BY code
            ORDER BY trade_date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS ma20,
        close / LAG(close, 1) OVER (
            PARTITION BY code ORDER BY trade_date
        ) - 1 AS returns
    FROM etf_daily_prices
    WHERE trade_date >= '2024-01-01'
""").pl()
```

### 与 Polars 互操作

```python
# Polars DataFrame 注册为临时表
conn.register("temp_signals", signals_df)

# 在 SQL 中使用
result = conn.execute("""
    SELECT p.*, s.signal
    FROM etf_daily_prices p
    JOIN temp_signals s ON p.code = s.code AND p.trade_date = s.trade_date
""").pl()

# 用完注销
conn.unregister("temp_signals")
```

## 数据导入导出

### 批量导入

```python
# 从 Polars DataFrame 导入
conn.execute("""
    INSERT INTO etf_daily_prices
    SELECT * FROM df
    ON CONFLICT (code, trade_date) DO UPDATE SET
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        updated_at = CURRENT_TIMESTAMP
""")

# 从 Parquet 文件导入
conn.execute("""
    INSERT INTO etf_daily_prices
    SELECT * FROM read_parquet('data/prices/*.parquet')
""")

# 从 CSV 导入
conn.execute("""
    COPY etf_daily_prices FROM 'data/prices.csv' (HEADER, DELIMITER ',')
""")
```

### 导出

```python
# 导出到 Parquet（推荐）
conn.execute("""
    COPY (SELECT * FROM etf_daily_prices WHERE trade_date >= '2024-01-01')
    TO 'export/prices_2024.parquet' (FORMAT PARQUET)
""")

# 导出到 CSV
conn.execute("""
    COPY etf_daily_prices TO 'export/prices.csv' (HEADER, DELIMITER ',')
""")
```

## 事务处理

```python
# 显式事务
conn.begin()
try:
    conn.execute("INSERT INTO ...")
    conn.execute("UPDATE ...")
    conn.commit()
except Exception:
    conn.rollback()
    raise

# 上下文管理器方式
with conn.cursor() as cur:
    cur.execute("INSERT INTO ...")
    # 自动 commit，异常时 rollback
```

## 性能优化

### 查询优化

```python
# 使用 EXPLAIN 分析查询计划
plan = conn.execute("EXPLAIN ANALYZE SELECT ...").fetchall()

# 创建合适的索引
conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_prices_code_date
    ON etf_daily_prices(code, trade_date)
""")
```

### 内存管理

```python
# 设置内存限制
conn.execute("SET memory_limit = '4GB'")

# 设置线程数
conn.execute("SET threads = 4")

# 启用进度条（长查询）
conn.execute("SET enable_progress_bar = true")
```

### 分区表（大数据量）

```sql
-- 按年分区（如果数据量很大）
CREATE TABLE etf_daily_prices_2024 AS
SELECT * FROM etf_daily_prices WHERE trade_date >= '2024-01-01';
```

## 测试模式

```python
import pytest

@pytest.fixture
def test_db():
    """创建测试用的内存数据库"""
    conn = duckdb.connect(":memory:")

    # 初始化 schema
    conn.execute("""
        CREATE TABLE etf_daily_prices (
            code VARCHAR,
            trade_date DATE,
            close DOUBLE,
            PRIMARY KEY (code, trade_date)
        )
    """)

    # 插入测试数据
    conn.execute("""
        INSERT INTO etf_daily_prices VALUES
        ('510300', '2024-01-02', 100.0),
        ('510300', '2024-01-03', 101.5),
        ('510300', '2024-01-04', 99.8)
    """)

    yield conn
    conn.close()

def test_query_prices(test_db):
    result = test_db.execute("""
        SELECT * FROM etf_daily_prices WHERE code = '510300'
    """).pl()

    assert result.height == 3
    assert result["close"].mean() == pytest.approx(100.43, rel=0.01)
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 字符串拼接 SQL | SQL 注入风险 | 参数化查询 `$1, $2` |
| 不关闭连接 | 资源泄露 | 使用上下文管理器 |
| 生产环境用 `:memory:` | 数据丢失 | 文件数据库 |
| 无索引的大表查询 | 性能差 | 创建合适索引 |
| 忽略 knowledge_date | PIT 泄露 | 必须按 knowledge_date 过滤 |
