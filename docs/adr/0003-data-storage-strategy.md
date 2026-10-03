# 0003 - Data Storage Strategy

Status: Accepted

Date: 2024-01-01（2026-10-03 修订：移除 DuckDB 查询轨承诺，见 #396）

## Context

A quantitative trading system needs to store:
1. **Market data**: Daily OHLCV for stocks/ETFs (large volume, time-series)
2. **Metadata**: Security master, trading calendar (small volume, relational)
3. **Point-in-Time (PIT) data**: Historical identifier mappings
4. **Pipeline state**: Data ingestion tracking

We need a storage strategy that balances:
- Query performance
- Storage efficiency
- Data integrity
- Simplicity (single-user, Windows environment)

## Decision

We adopt a **hybrid storage approach**:

### Market Data: Parquet with Year Partitioning
- **Format**: Apache Parquet with zstd compression
- **Partitioning**: By year (e.g., `stock_daily/2024.parquet`)
- **Library**: Polars for read/write
- **Advantages**:
  - Columnar compression (10-100x smaller than CSV)
  - Fast partial reads (column projection)
  - Random access via year partitions

### Metadata: SQLite with Thread-Local Pool
- **Format**: SQLite database
- **Connection**: Thread-local connection pool
- **Features**:
  - ACID transactions
  - Foreign key constraints
  - PIT support via effective_from/effective_to columns
  - File locking for concurrent access

### Query Path: Polars Only（2026-10-03 修订）
- 分析查询统一经 Polars DataFrame 管道（含 `PITQueryService` 的快照绑定
  PIT 可见性过滤），不存在第三条 SQL 查询轨。
- 原承诺的"DuckDB Views over Parquet"查询轨从未在生产路径接线，库文件
  从未生成；#396 删除其引擎、装配与 `duckdb` 依赖。

### Data Organization
```
data_root/
├── metadata/
│   └── metadata.sqlite         # Metadata (security, calendar, etc.)
├── stock_daily/
│   ├── 2020.parquet
│   ├── 2021.parquet
│   └── ...
├── etf_daily/
│   └── ...
└── adj_factor/
    └── ...
```

## Consequences

### Positive
- **Parquet** provides excellent compression and query performance
- **Year partitioning** allows efficient date-range queries
- **SQLite** is lightweight, requires no server setup
- **PIT support** ensures historical accuracy
- **单一查询轨**（Polars）减少引擎与依赖维护面

### Negative
- **SQLite** has limited write concurrency (acceptable for single-user)
- **Year partitions** require manual management
- **No built-in replication** (acceptable for single-user)
- **Parquet** is not append-only (requires rewrite for updates)
- 跨年复杂分析失去 SQL 引擎选项（当前无此类生产查询；如出现按需评估）

## Alternatives Considered

### PostgreSQL instead of SQLite
**Rejected**: Overkill for single-user system. Requires server setup and adds operational complexity.

### HDF5 instead of Parquet
**Rejected**: HDF5 has worse tooling support and is less flexible for schema changes.

### All data in SQLite
**Rejected**: SQLite is inefficient for large time-series data. Storage and query performance would be poor.

### InfluxDB/TimescaleDB
**Rejected**: Time-series databases are overkill for daily data. Parquet + Polars is sufficient and simpler.

### DuckDB SQL analytics track
**Rejected (2026-10-03)**: 引擎、DI 装配与依赖从未被任何生产查询消费，
作为第三查询轨只会误导方向；分析查询由 Polars 管道承担。

### Cloud storage (S3, Azure Blob)
**Rejected**: We're a single-user Windows system. Local storage is simpler and has no latency.

## Related Decisions

- [ADR 0001 - Project Stack Selection](0001-project-stack-selection.md)
- [ADR 0002 - Monorepo Structure](0002-monorepo-structure.md)

## References

- Design docs: `docs/design/02_data_design.md`
- [数据层精简审阅](../data/data-layer-review-2026-10.md)（D11：移除无消费者的 DuckDB 第三查询轨）
