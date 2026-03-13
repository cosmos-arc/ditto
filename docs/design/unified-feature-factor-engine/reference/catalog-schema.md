# Catalog 表结构参考

> **注意**: 本文档是**参考资料**，规范定义以 [ADR-010: Catalog 完整表结构与存储架构](../decisions/adr-010-catalog-schema.md) 为准。
>
> **2026-03-13 对齐说明**: Hot/Cold retention、state namespace 与研究数据集契约的较新口径以 [ADR-040](../decisions/adr-040-hot-cold-retention-state-namespace-policy.md) 和 [ADR-041](../decisions/adr-041-research-dataset-spine-availability-contract.md) 为准。

本文档定义了 Ditto 衍生数据 Catalog 的完整表结构。

## 概述

Catalog 采用 **SQLite + Kvrocks 混合存储**：
- **SQLite**：关系型元数据（Spec、Run、Partition、Dependency）
- **Kvrocks**：键值型状态（State、Checkpoint、Invalidation）

---

## SQLite 表结构

### 1. derived_spec（因子/特征规格表）

存储因子/特征的规格定义。

```sql
CREATE TABLE IF NOT EXISTS derived_spec (
    -- 主键
    entity_type       TEXT NOT NULL,     -- 'feature' | 'factor'
    entity_id         TEXT NOT NULL,     -- 'alpha_001', 'rsi_14'
    version           INTEGER NOT NULL,  -- 1, 2, 3...

    -- 规格定义
    spec_json         TEXT NOT NULL,     -- JSON 序列化的 Spec
    spec_hash         TEXT NOT NULL,     -- SHA256 of spec_json
    engine_version    TEXT NOT NULL,     -- 'expr-v0'

    -- 版本管理字段
    status            TEXT NOT NULL DEFAULT 'draft',  -- 'draft' | 'active' | 'deprecated' | 'archived'
    online            INTEGER NOT NULL DEFAULT 0,     -- 0 = offline, 1 = online
    primary           INTEGER NOT NULL DEFAULT 0,     -- 是否为默认查询版本
    referenced_by     TEXT DEFAULT '[]',              -- JSON array of引用者

    -- 元信息
    created_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    updated_at        TEXT,

    PRIMARY KEY (entity_type, entity_id, version)
);

-- 唯一约束：相同 spec_hash + engine_version 的版本去重
CREATE UNIQUE INDEX idx_spec_hash
ON derived_spec(entity_type, entity_id, spec_hash, engine_version);

-- 快速查询在线版本
CREATE INDEX idx_spec_online
ON derived_spec(entity_type, entity_id, online)
WHERE online = 1;

-- 快速查询主版本
CREATE INDEX idx_spec_primary
ON derived_spec(entity_type, entity_id, primary)
WHERE primary = 1;
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| entity_type | TEXT | 实体类型：'feature' 或 'factor' |
| entity_id | TEXT | 实体标识符，如 'alpha_001' |
| version | INTEGER | 版本号，从 1 开始 |
| spec_json | TEXT | 完整 Spec 的 JSON 序列化 |
| spec_hash | TEXT | 规格哈希，用于去重 |
| engine_version | TEXT | 引擎版本，用于兼容性 |
| status | TEXT | 生命周期状态 |
| online | INTEGER | 是否上线 |
| primary | INTEGER | 是否为默认查询版本 |
| referenced_by | TEXT | 引用列表（JSON 数组） |

---

### 2. derived_state（运行状态表）

> **重要**: `derived_state` 实际存储在 **Kvrocks** 而非 SQLite，此处仅作参考。

存储因子/特征的运行时状态。

**Kvrocks Key 格式**：
```
ditto:derived:state:{entity_type}:{entity_id}
```

**值格式（JSON）**：
```json
{
  "watermark": "2024-03-01",
  "coverage_start": "2024-01-01",
  "coverage_end": "2024-03-01",
  "coverage_gaps": [],
  "total_rows": 125000,
  "latest_run_id": "run-uuid-here",
  "latest_run_status": "SUCCESS",
  "updated_at": "2024-03-01T12:00:00Z"
}
```

**per-instance latest snapshot**：
```
ditto:derived:state:{entity_type}:{entity_id}:snapshot:{instance_key}
```

用于保存 HASH / BLOB 形式的最新状态快照；默认 TTL 7 天，仅用于热状态与冷启动，不承担长期权威语义。

**SQLite 副本（可选，用于复杂查询）**：
```sql
CREATE TABLE IF NOT EXISTS derived_state (
    -- 主键（与 derived_spec 关联）
    entity_type       TEXT NOT NULL,
    entity_id         TEXT NOT NULL,
    active_version    INTEGER,

    -- 覆盖范围
    coverage_start    TEXT,              -- ISO date: '2024-01-01'
    coverage_end      TEXT,              -- ISO date: '2024-03-01'
    watermark         TEXT,              -- 最新物化日期

    -- 运行引用
    latest_run_id     TEXT,              -- 最新成功的 run_id

    -- 统计信息
    total_rows        INTEGER DEFAULT 0,
    last_duration_ms  INTEGER,

    -- 时间戳
    updated_at        TEXT NOT NULL,

    PRIMARY KEY (entity_type, entity_id)
);

-- 按更新时间查询
CREATE INDEX idx_state_updated
ON derived_state(updated_at);
```

---

### 3. derived_run（运行记录表）

存储每次物化运行的详细记录。

```sql
CREATE TABLE IF NOT EXISTS derived_run (
    -- 主键
    run_id            TEXT PRIMARY KEY,  -- UUID

    -- 实体关联
    entity_type       TEXT NOT NULL,
    entity_id         TEXT NOT NULL,
    version           INTEGER NOT NULL,

    -- 运行模式
    mode              TEXT NOT NULL,     -- 'full' | 'incremental'
    trigger           TEXT DEFAULT 'manual',  -- 'manual' | 'scheduled' | 'cascade'

    -- 请求边界
    request_start     TEXT NOT NULL,     -- 用户请求的开始日期
    request_end       TEXT NOT NULL,     -- 用户请求的结束日期

    -- 计算边界（考虑 lookback）
    compute_start     TEXT NOT NULL,     -- 实际计算的开始日期
    compute_end       TEXT NOT NULL,     -- 实际计算的结束日期

    -- 依赖快照
    source_snapshot_id TEXT,             -- 输入数据快照标识

    -- 状态
    status            TEXT NOT NULL,     -- 'RUNNING' | 'SUCCESS' | 'FAILED'

    -- 结果统计
    rows_written      INTEGER DEFAULT 0,
    partitions_written TEXT DEFAULT '[]', -- JSON array of partition keys

    -- 错误信息
    error_message     TEXT,
    error_stacktrace  TEXT,

    -- 时间戳
    created_at        TEXT NOT NULL,
    started_at        TEXT,
    finished_at       TEXT,

    FOREIGN KEY (entity_type, entity_id, version)
    REFERENCES derived_spec(entity_type, entity_id, version)
);

-- 按状态查询
CREATE INDEX idx_run_status
ON derived_run(status, created_at);

-- 按实体查询最近运行
CREATE INDEX idx_run_entity
ON derived_run(entity_type, entity_id, version, created_at DESC);
```

---

### 4. derived_partition（分区记录表）

存储每次运行写入的分区详情。

```sql
CREATE TABLE IF NOT EXISTS derived_partition (
    -- 关联运行
    run_id            TEXT NOT NULL,

    -- 实体关联
    entity_type       TEXT NOT NULL,
    entity_id         TEXT NOT NULL,
    version           INTEGER NOT NULL,

    -- 分区信息
    partition_key     TEXT NOT NULL,     -- '2024' or '2024-03'
    partition_path    TEXT NOT NULL,     -- 文件相对路径
    file_path         TEXT NOT NULL,     -- 完整文件路径

    -- 统计信息
    row_count         INTEGER NOT NULL,
    size_bytes        INTEGER,

    -- 校验
    checksum          TEXT,              -- MD5/SHA256

    -- 时间戳
    written_at        TEXT NOT NULL,

    PRIMARY KEY (run_id, partition_key),

    FOREIGN KEY (run_id) REFERENCES derived_run(run_id),
    FOREIGN KEY (entity_type, entity_id, version)
    REFERENCES derived_spec(entity_type, entity_id, version)
);

-- 按分区查询最新版本
CREATE INDEX idx_partition_latest
ON derived_partition(entity_type, entity_id, partition_key, written_at DESC);
```

---

### 5. derived_invalidation（失效记录）

> **存储**: Kvrocks（队列模式）
>
> 详细定义见 [ADR-010 §6](../decisions/adr-010-catalog-schema.md#6-derived_invalidation-失效记录)

存储输入数据变更导致的失效记录，采用 Kvrocks 键值存储实现队列模式。

```
ditto:derived:invalidation:{priority}:{timestamp}:{id}
    → JSON {
        "source_domain": "market",
        "source_dataset": "daily",
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

-- 按实体查询失效记录
CREATE INDEX idx_invalidation_entity
ON derived_invalidation(entity_type, entity_id, created_at DESC);
```

---

### 6. derived_dependency（依赖关系表）

存储因子/特征之间的依赖关系。

```sql
CREATE TABLE IF NOT EXISTS derived_dependency (
    -- 主键
    id                INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 依赖方
    entity_type       TEXT NOT NULL,
    entity_id         TEXT NOT NULL,
    version           INTEGER NOT NULL,

    -- 被依赖方
    depends_on_type   TEXT NOT NULL,     -- 'source' | 'feature' | 'factor'
    depends_on_id     TEXT NOT NULL,     -- 数据集名或实体ID
    depends_on_version INTEGER,          -- NULL 表示最新版本

    -- 依赖元数据
    dependency_type   TEXT NOT NULL,     -- 'direct' | 'indirect'
    columns_used      TEXT DEFAULT '[]', -- JSON array of column names

    -- 时间戳
    created_at        TEXT NOT NULL,

    UNIQUE(entity_type, entity_id, version, depends_on_type, depends_on_id),

    FOREIGN KEY (entity_type, entity_id, version)
    REFERENCES derived_spec(entity_type, entity_id, version)
);

-- 反向依赖查询
CREATE INDEX idx_dependency_reverse
ON derived_dependency(depends_on_type, depends_on_id);
```

---

### 7. derived_checkpoint（检查点表）

存储增量计算的检查点信息（SQLite 副本，主存储在 Kvrocks）。

```sql
CREATE TABLE IF NOT EXISTS derived_checkpoint (
    -- 主键
    entity_type       TEXT NOT NULL,
    entity_id         TEXT NOT NULL,
    version           INTEGER NOT NULL,
    checkpoint_type   TEXT NOT NULL,     -- 'watermark' | 'state' | 'partial'

    -- 检查点数据
    checkpoint_key    TEXT NOT NULL,     -- Kvrocks 键
    checkpoint_data   TEXT,              -- JSON 序列化状态（小型）
    checkpoint_hash   TEXT,              -- 校验哈希

    -- 时间戳
    created_at        TEXT NOT NULL,
    expires_at        TEXT,              -- 过期时间（可选）

    PRIMARY KEY (entity_type, entity_id, version, checkpoint_type)
);
```

---

## Kvrocks 键设计

### 键命名规范

```
ditto:derived:{family}:{entity_type}:{entity_id}:{suffix}
```

### 检查点键

```
ditto:derived:checkpoint:factor:alpha_001:ts_rank:close_20
ditto:derived:checkpoint:factor:alpha_001:ts_mean:volume_10
```

**值格式**：MessagePack 序列化的状态对象

### 状态快照键

```
ditto:derived:state:factor:alpha_001:snapshot:000001.SZ
```

**值格式**：
```json
{
  "schema_ver": 1,
  "instrument_id": "000001.SZ",
  "ts": "2024-03-01T14:30:00Z",
  "trade_date": "2024-03-01",
  "calc_ver": 3,
  "data": {
    "value": 0.75
  }
}
```

### 锁键

```
ditto:lock:derived:factor:alpha_001:v1
ditto:lock:derived:factor:alpha_001:v1:2024-03
```

---

## 查询示例

### 查询主版本因子

```sql
SELECT * FROM derived_spec
WHERE entity_type = 'factor'
  AND entity_id = 'alpha_001'
  AND primary = 1;
```

### 查询所有在线因子

```sql
SELECT entity_id, version, status
FROM derived_spec
WHERE entity_type = 'factor'
  AND online = 1
  AND status = 'active';
```

### 查询最近失败的运行

```sql
SELECT run_id, entity_id, error_message, created_at
FROM derived_run
WHERE status = 'FAILED'
  AND created_at > datetime('now', '-7 days')
ORDER BY created_at DESC;
```

### 查询因子依赖

```sql
SELECT d.depends_on_type, d.depends_on_id
FROM derived_dependency d
WHERE d.entity_type = 'factor'
  AND d.entity_id = 'alpha_001';
```

### 查询反向依赖（谁依赖这个数据集）

```sql
SELECT d.entity_type, d.entity_id, d.version
FROM derived_dependency d
WHERE d.depends_on_type = 'source'
  AND d.depends_on_id = 'market/daily_bar';
```

---

## 事务模式

### 物化提交事务

```sql
BEGIN IMMEDIATE;

-- 1. 插入运行记录
INSERT INTO derived_run (...) VALUES (...);

-- 2. 插入分区记录
INSERT INTO derived_partition (...) VALUES (...), (...);

-- 3. 更新状态表
INSERT OR REPLACE INTO derived_state (...) VALUES (...);

-- 4. 更新检查点（如果增量）
INSERT OR REPLACE INTO derived_checkpoint (...) VALUES (...);

COMMIT;
```

### 失效处理事务

```sql
BEGIN IMMEDIATE;

-- 1. 标记失效记录为已处理
UPDATE derived_invalidation
SET status = 'processed', processed_at = datetime('now')
WHERE id IN (...);

-- 2. 插入新的运行记录（级联触发）
INSERT INTO derived_run (...) VALUES (...);

COMMIT;
```

---

## 数据保留策略

| 表 | 保留策略 |
|------|---------|
| derived_spec | 永久保留，archived 状态 7 天后可清理 |
| derived_state | 永久保留 |
| derived_run | 成功记录 90 天，失败记录 30 天 |
| derived_partition | 随运行记录清理 |
| derived_invalidation | 已处理记录 30 天后清理 |
| derived_dependency | 随 spec 清理 |
| derived_checkpoint | 随 spec 清理 |
