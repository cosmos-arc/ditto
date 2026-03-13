# ADR-010: Catalog 完整表结构与存储架构

**状态**: 已决策（2026-03-04，2026-03-07 合并 ADR-016）

---

## 存储架构总览

采用 **SQLite + Kvrocks 混合方案**：

```
data/
├── metadata/
│   └── metadata.sqlite          # 关系型元数据
│       ├── instrument           # 现有
│       ├── trading_calendar     # 现有
│       ├── derived_spec         # 新增：因子/特征定义
│       └── derived_dependency   # 新增：Lineage
│
├── runtime/
│   ├── ingestion.sqlite         # 摄取层（独立事务域）
│   │
│   └── derived.sqlite           # 物化层
│       ├── derived_run          # 运行历史
│       └── derived_partition    # 分区元数据
│
└── (Kvrocks)                    # 状态存储（详见 ADR-029、ADR-031）
    ├── state:feature:{factor_id}:{instrument_id}  # 因子快照（HASH/BLOB）
    ├── state:signal:{strategy}:{instrument_id}    # 最新信号
    ├── state:risk:{account}:{instrument_id}       # 风控状态
    ├── ditto:checkpoint:{source}:{data_type}      # 摄入检查点
    └── ditto:invalidation:{priority}:{ts}:{id}    # 失效队列
```

## 存储职责划分

| 存储 | 表/Key | 访问模式 | 查询需求 |
|-----|-------|---------|---------|
| **metadata.sqlite** | `derived_spec` | 低频读写 | JOIN dependency |
| | `derived_dependency` | 低频写 | WITH RECURSIVE Lineage |
| **derived.sqlite** | `derived_run` | 高频写 | 复杂过滤/排序 |
| | `derived_partition` | 中频写 | 按因子/日期查询 |
| **Kvrocks** | `state:*` | 高频读写 | 精确 key（复用 ADR-012） |
| | `checkpoint:*` | 高频读写 | 精确 key + TTL |
| | `invalidation:*` | 中频写 | 队列模式 |

## 拆分理由

| 决策点 | 选择 | 理由 |
|-------|------|------|
| **元数据 vs 运行时拆分** | 独立文件 | 职责分离、备份策略不同 |
| **ingestion 独立** | 独立文件 | T1/T2 可并行执行，写入隔离 |
| **state/checkpoint 用 Kvrocks** | 复用 ADR-012 | 简单 KV 模式，统一状态管理 |
| **run/partition 用 SQLite** | 独立文件 | 需要复杂查询，事务原子性 |

---

## 详细表结构

### 1. derived_spec: Spec 定义（版本化）

> 存储：metadata.sqlite

```sql
CREATE TABLE IF NOT EXISTS derived_spec (
    entity_type TEXT NOT NULL,         -- "feature" | "factor"
    entity_id TEXT NOT NULL,           -- "rsi_14", "alpha_momentum_12m"
    version INTEGER NOT NULL,          -- 版本号（从 1 开始）

    -- Spec 内容
    expression TEXT NOT NULL,          -- "ts_mean(market.close, 14)"
    spec_json TEXT NOT NULL,           -- 完整 Spec JSON
    spec_hash TEXT NOT NULL,           -- Spec 哈希（用于变更检测）

    -- 服务模式（详见 ADR-029）
    serve_mode TEXT NOT NULL DEFAULT 'OFFLINE',  -- SERIES | STATE | DERIVE | OFFLINE

    -- 状态快照策略（仅 STATE 模式，详见 ADR-031）
    state_snapshot_strategy TEXT,      -- HASH | BLOB

    -- 分析结果（编译时计算）
    lookback INTEGER NOT NULL DEFAULT 0,
    requires_full_day INTEGER NOT NULL DEFAULT 0,
    dependencies TEXT NOT NULL,        -- JSON: ["market.close", "@returns_1"]

    -- 配置
    normalization_preset TEXT DEFAULT 'default',
    -- PIT 由引擎根据 StoreSchema.pit_columns 自动处理（见 ADR-021）
    is_critical INTEGER NOT NULL DEFAULT 0,

    -- 治理字段
    owner TEXT,                        -- 责任人（如 "team-alpha"）
    freshness_sla TEXT,                -- 新鲜度承诺（如 "T+1"）
    validation_policy TEXT DEFAULT 'strict',  -- 校验策略

    -- 元信息
    engine_version TEXT NOT NULL DEFAULT 'v0',
    status TEXT NOT NULL DEFAULT 'active',  -- active | deprecated | archived
    created_at TEXT NOT NULL,
    created_by TEXT,

    PRIMARY KEY (entity_type, entity_id, version),
    UNIQUE (entity_type, entity_id, spec_hash)
);

CREATE INDEX idx_spec_hash ON derived_spec(spec_hash);
CREATE INDEX idx_spec_status ON derived_spec(status);
CREATE INDEX idx_spec_owner ON derived_spec(owner);
```

### 2. derived_state: 运行时状态

> 存储：Kvrocks（复用 ADR-012 状态管理架构）

```
ditto:derived:state:{entity_type}:{entity_id}
    → JSON {
        "watermark": "2026-03-03",
        "coverage_start": "2024-01-01",
        "coverage_end": "2026-03-03",
        "coverage_gaps": ["2026-01-15", "2026-02-20:2026-02-22"],
        "latest_run_id": "uuid",
        "latest_run_status": "success",
        "total_rows": 123456,
        "updated_at": "2026-03-03T10:00:00Z"
    }
```

**访问模式**：高频读写，精确 key 访问

### 3. derived_run: 运行记录（每次物化）

> 存储：derived.sqlite

```sql
CREATE TABLE IF NOT EXISTS derived_run (
    run_id TEXT PRIMARY KEY,           -- UUID

    -- 实体标识
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    spec_hash TEXT NOT NULL,

    -- 运行配置
    mode TEXT NOT NULL,                -- full | incremental
    request_start TEXT NOT NULL,
    request_end TEXT NOT NULL,
    compute_start TEXT NOT NULL,       -- 实际计算开始（含预热）
    compute_end TEXT NOT NULL,

    -- 状态
    status TEXT NOT NULL,              -- running | success | failed
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_ms INTEGER,

    -- 输入
    source_snapshot_id TEXT,           -- 输入数据快照
    input_partitions TEXT,             -- JSON: 读取的分区列表

    -- 输出
    partitions_written TEXT,           -- JSON: 写入的分区列表
    rows_written INTEGER DEFAULT 0,
    rows_skipped INTEGER DEFAULT 0,
    output_checksum TEXT,

    -- 错误
    error_message TEXT,
    error_stacktrace TEXT,

    -- 元信息
    triggered_by TEXT,                 -- manual | schedule | dependency
    parent_run_id TEXT                 -- 父运行（级联时）
);

CREATE INDEX idx_run_entity ON derived_run(entity_type, entity_id, version);
CREATE INDEX idx_run_status ON derived_run(status, started_at);
CREATE INDEX idx_run_time ON derived_run(started_at);
```

### 4. derived_partition: 分区级元数据

> 存储：derived.sqlite

```sql
CREATE TABLE IF NOT EXISTS derived_partition (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    partition_key TEXT NOT NULL,       -- "2026" 或 "2026-02"

    -- 文件信息
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    row_count INTEGER NOT NULL,

    -- 校验
    checksum TEXT,

    -- 统计
    null_rate REAL,                    -- 空值率
    min_value TEXT,
    max_value TEXT,
    mean_value TEXT,
    std_value TEXT,

    -- 时间
    written_at TEXT NOT NULL,
    run_id TEXT NOT NULL,

    PRIMARY KEY (entity_type, entity_id, version, partition_key)
);

CREATE INDEX idx_partition_run ON derived_partition(run_id);
```

### 5. derived_checkpoint: 分区级 Checkpoint（幂等）

> 存储：Kvrocks（复用 ADR-012 状态管理架构）

```
ditto:derived:checkpoint:{entity_type}:{entity_id}:{partition_key}
    → JSON {
        "status": "done",              -- pending | done | failed
        "rows_written": 5000,
        "checksum": "abc123",
        "error_message": null,
        "started_at": "2026-03-03T09:00:00Z",
        "completed_at": "2026-03-03T09:05:00Z"
    }
```

**访问模式**：高频读写，精确 key 访问，TTL 7 天

### 6. derived_invalidation: 失效记录

> 存储：Kvrocks（队列模式）

```
ditto:derived:invalidation:{priority}:{timestamp}:{id}
    → JSON {
        "source_domain": "market",
        "source_dataset": "daily",
        "change_date": "2026-01-15",
        "source_snapshot_id": "snap-123",
        "entity_type": "factor",
        "entity_id": "alpha_momentum_20",
        "affected_start": "2026-01-10",
        "affected_end": "2026-01-15",
        "scope": "full_day",
        "status": "pending",
        "created_at": "2026-03-03T10:00:00Z"
    }
```

**访问模式**：中频写，队列模式（按 priority + timestamp 排序扫描）

### 7. derived_dependency: 依赖关系（Lineage）

> 存储：metadata.sqlite

```sql
CREATE TABLE IF NOT EXISTS derived_dependency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 依赖方
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,

    -- 被依赖方
    dep_type TEXT NOT NULL,            -- source | feature | factor
    dep_domain TEXT,                   -- source: "market", "fundamental"
    dep_column TEXT,                   -- source: "close"
    dep_entity_id TEXT,                -- feature/factor: "rsi_14"

    created_at TEXT NOT NULL,

    UNIQUE (entity_type, entity_id, version, dep_type, dep_domain, dep_column, dep_entity_id)
);

CREATE INDEX idx_dependency_entity ON derived_dependency(entity_type, entity_id);
CREATE INDEX idx_dependency_dep ON derived_dependency(dep_type, dep_entity_id);
```

---

## 常用查询模式

### SQLite 查询（metadata.sqlite / derived.sqlite）

```sql
-- 1. 查询实体的下游依赖（级联失效）
SELECT entity_type, entity_id
FROM derived_dependency
WHERE dep_type = 'source' AND dep_domain = 'market' AND dep_column = 'close';

-- 2. 查询因子的完整 Lineage（递归）
WITH RECURSIVE lineage AS (
    SELECT entity_type, entity_id, dep_type, dep_entity_id, 1 AS depth
    FROM derived_dependency
    WHERE entity_id = 'alpha_momentum_12m'

    UNION ALL

    SELECT d.entity_type, d.entity_id, d.dep_type, d.dep_entity_id, l.depth + 1
    FROM derived_dependency d
    JOIN lineage l ON d.entity_id = l.dep_entity_id
    WHERE l.depth < 10
)
SELECT * FROM lineage;

-- 3. 查询运行历史（排障）
SELECT * FROM derived_run
WHERE entity_id = 'alpha_momentum_12m'
ORDER BY started_at DESC
LIMIT 10;

-- 4. 查询分区元数据
SELECT * FROM derived_partition
WHERE entity_id = 'alpha_momentum_12m'
ORDER BY partition_key DESC;
```

### Kvrocks 查询（state/checkpoint/invalidation）

```python
# 1. 获取实体状态
state = kv.get("ditto:derived:state:factor:alpha_momentum_12m")

# 2. 检查分区 checkpoint
checkpoint = kv.get("ditto:derived:checkpoint:factor:alpha_momentum_12m:2026-03")

# 3. 扫描待处理失效记录（按 priority + timestamp）
invalidations = kv.scan("ditto:derived:invalidation:0:*", count=100)
```

---

## 技术选型分析

| 技术 | 优势 | 劣势 | 适用场景 |
|-----|------|------|---------|
| **SQLite** | SQL 查询、ACID 事务、成熟稳定 | 写入串行化 | 复杂查询、低频写入 |
| **RocksDB/Kvrocks** | 高吞吐写入、LSM-Tree 优化 | 仅 KV 操作、无 SQL | 高频写入、简单访问 |

**Ditto 场景分析**：

| 需求 | 特点 | 推荐 |
|-----|------|------|
| 复杂查询 | Lineage (WITH RECURSIVE)、运行历史过滤 | SQL 能力必需 |
| 事务原子性 | 物化完成时多表原子更新 | ACID 事务 |
| 写入频率 | ~300-800 次/天 | SQLite 绰绰有余 |
| 状态高频读写 | watermark/checkpoint 频繁更新 | Kvrocks 优化 |
| 部署简单 | 本地盘场景 | 嵌入式优先 |

---

## 业界对标

| 平台 | Registry 存储 | Ditto 选择 |
|------|-------------|-----------|
| Feast | SQLite (dev) / PostgreSQL (prod) | SQLite + Kvrocks |
| RisingWave | etcd → PostgreSQL | SQLite（规模较小） |
| Qlib | 自定义二进制 + DuckDB | SQLite（SQL 查询） |
| DolphinDB | 分布式 KV | Kvrocks（状态管理） |
