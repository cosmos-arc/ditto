# 0003 - Data Storage Strategy

Status: Accepted

Date: 2024-01-01

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
  - Works with DuckDB SQL engine

### Metadata: SQLite with Thread-Local Pool
- **Format**: SQLite database
- **Connection**: Thread-local connection pool
- **Features**:
  - ACID transactions
  - Foreign key constraints
  - PIT support via effective_from/effective_to columns
  - File locking for concurrent access

### SQL Analytics: DuckDB Views
- **Format**: In-memory DuckDB database
- **Views**: Virtual tables over Parquet files
- **Use case**: Complex analytical queries across years

### Data Organization
```
data_root/
├── meta/
│   └── hub.sqlite              # Metadata (security, calendar, etc.)
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
- **DuckDB integration** enables SQL analytics without ETL
- **PIT support** ensures historical accuracy

### Negative
- **SQLite** has limited write concurrency (acceptable for single-user)
- **Year partitions** require manual management
- **No built-in replication** (acceptable for single-user)
- **Parquet** is not append-only (requires rewrite for updates)

## Alternatives Considered

### PostgreSQL instead of SQLite
**Rejected**: Overkill for single-user system. Requires server setup and adds operational complexity.

### HDF5 instead of Parquet
**Rejected**: HDF5 has worse tooling support and is less flexible for schema changes.

### All data in SQLite
**Rejected**: SQLite is inefficient for large time-series data. Storage and query performance would be poor.

### InfluxDB/TimescaleDB
**Rejected**: Time-series databases are overkill for daily data. Parquet + DuckDB is sufficient and simpler.

### Cloud storage (S3, Azure Blob)
**Rejected**: We're a single-user Windows system. Local storage is simpler and has no latency.

## Related Decisions

- [ADR 0001 - Project Stack Selection](0001-project-stack-selection.md)
- [ADR 0002 - Monorepo Structure](0002-monorepo-structure.md)

## References

- Design docs: `docs/design/02_data_design.md`
