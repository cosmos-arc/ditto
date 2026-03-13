# ADR-026: DuckDB 定位与使用规范

**状态**: 已决策（2026-03-10）

---

## 背景

在统一因子引擎设计中，需要明确 DuckDB 的角色定位。DuckDB 是一个高性能的嵌入式分析数据库，但其并发模型和进程模型限制了它在生产环境中的使用方式。

**DuckDB 的技术约束**：
- 单进程写/多进程只读的并发模型
- 不适合作为常驻服务扛主并发读写
- 与 SQLite 共享数据库文件时有跨进程锁问题

**现有设计参考**：
- ADR-020 中将 DuckDB 作为可选分析引擎
- ADR-025（已废弃）曾将 DuckDB 作为统一数据架构核心

---

## 决策

**DuckDB 降级为 ADHOC/审计工具，不作为常驻服务或 API 后端。**

### 一句话定位

> **DuckDB 是临时刀，不是主仓库。**

### 使用场景矩阵

| 场景 | 是否允许 | 说明 |
|------|---------|------|
| ADHOC SQL 查询 | ✅ 允许 | 临时分析、快速探索、数据探查 |
| 审计对拍 | ✅ 允许 | 独立视角验证数据，作为第三方校验 |
| Parquet/SQLite 联查 | ✅ 允许 | DuckDB 直接读取 Parquet/SQLite 很方便 |
| 常驻服务 | ❌ 禁止 | 并发模型不支持 |
| API 后端 | ❌ 禁止 | 单进程读写/多进程只读限制 |
| 共享热层 | ❌ 禁止 | 不适合扛主并发读写 |
| 研究场景 | ⚠️ 不推荐 | 优先统一用 Polars，保持研究/生产一致性 |

---

## 允许的使用模式

### 1. ADHOC SQL 分析

```python
# 临时数据分析脚本
import duckdb

conn = duckdb.connect()

# 直接查询 Parquet 文件
df = conn.execute("""
    SELECT trade_date, instrument_id, close
    FROM read_parquet('data/market/cn/bar_1d/*.parquet')
    WHERE trade_date >= '2026-01-01'
""").df()

# 联查 SQLite 元数据
df_with_meta = conn.execute("""
    SELECT b.trade_date, i.symbol, i.name, b.close
    FROM read_parquet('data/market/cn/bar_1d/*.parquet') b
    JOIN sqlite_scan('data/metadata/metadata.sqlite', 'instrument') i
      ON b.instrument_id = i.instrument_id
    WHERE b.trade_date = '2026-03-10'
""").df()
```

### 2. 审计对拍

```python
# 独立视角验证 Polars 计算结果
import duckdb

conn = duckdb.connect()

# 用 DuckDB SQL 验证因子计算结果
polars_result = factor_engine.compute(...)  # Polars 计算

duckdb_result = conn.execute("""
    SELECT instrument_id, trade_date, factor_value
    FROM read_parquet('data/factors/factors_narrow/2026.parquet')
    WHERE trade_date = '2026-03-10'
    ORDER BY instrument_id
""").df()

# 对比结果
assert polars_result.sort("instrument_id").equals(
    duckdb_result.sort("instrument_id")
)
```

### 3. 快速数据探查

```python
# CLI 工具中的快速探查
def explore_data(parquet_path: str) -> None:
    conn = duckdb.connect()

    # 快速统计
    stats = conn.execute(f"""
        SELECT
            COUNT(*) as total_rows,
            COUNT(DISTINCT instrument_id) as instruments,
            MIN(trade_date) as min_date,
            MAX(trade_date) as max_date,
            AVG(volume) as avg_volume
        FROM read_parquet('{parquet_path}')
    """).df()

    print(stats)
```

---

## 禁止的使用模式

### ❌ 禁止：作为常驻服务

```python
# 错误示例：DuckDB 作为 API 后端
app = FastAPI()
conn = duckdb.connect("data.duckdb", read_only=False)  # ❌ 单进程写限制

@app.get("/query")
def query(sql: str):
    return conn.execute(sql).df()  # ❌ 并发问题
```

### ❌ 禁止：作为共享热层

```python
# 错误示例：多进程共享 DuckDB
# 进程 A
conn_a = duckdb.connect("shared.duckdb", read_only=False)

# 进程 B（同时运行）
conn_b = duckdb.connect("shared.duckdb", read_only=False)  # ❌ 锁冲突
```

### ⚠️ 不推荐：研究场景优先用 DuckDB

```python
# 不推荐
conn = duckdb.connect()
research_df = conn.execute("SELECT * FROM ...").df()

# 推荐：研究场景也用 Polars，保持研究/生产一致性
import polars as pl
research_df = pl.read_parquet("data/...").filter(...)
```

---

## 与其他存储组件的对比

| 能力 | DuckDB | Polars | QuestDB | SQLite |
|------|--------|--------|---------|--------|
| **SQL 接口** | ✅ 完整 | ❌ 无 | ✅ 完整 | ✅ 完整 |
| **Parquet 读取** | ✅ 原生 | ✅ 原生 | ⚠️ 需导入 | ❌ 需转换 |
| **并发写入** | ❌ 单进程 | ❌ 无存储 | ✅ 支持 | ⚠️ 锁竞争 |
| **常驻服务** | ❌ 不适合 | ❌ 无存储 | ✅ 适合 | ⚠️ 有限制 |
| **ADHOC 分析** | ✅ 极佳 | ✅ 极佳 | ⚠️ 一般 | ⚠️ 一般 |
| **研究/生产一致性** | ⚠️ 低 | ✅ 高 | ⚠️ 中 | ⚠️ 中 |

---

## 设计原则

### 1. 临时性

- DuckDB 连接应该在脚本/函数级别创建和销毁
- 不维护长期存在的 DuckDB 数据库文件
- 每次使用都是临时的、独立的

### 2. 辅助性

- DuckDB 是辅助工具，不是数据管道的主路径
- 主数据流走 Parquet + Polars + QuestDB
- DuckDB 用于边缘场景的快速验证

### 3. 一致性

- 研究场景优先使用 Polars，保持与生产环境一致
- 只有在需要 SQL 便利性或联查 SQLite 时才用 DuckDB
- 避免研究代码深度依赖 DuckDB 特有功能

---

## 相关 ADR

- [ADR-020: 部署与运维设计](adr-020-deployment-ops.md) - DuckDB 依赖配置
- [ADR-025: DuckDB 统一数据架构](adr-025-duckdb-unified-architecture.md) - **已废弃**，本 ADR 替代
- [ADR-027: 表达式 Pushdown 策略](adr-027-pushdown-strategy.md) - QuestDB 下推策略
- [ADR-028: QuestDB 热表与物化视图 DDL](adr-028-questdb-hot-tables.md) - 热层存储设计
