# Code Review Report: PR #36 "refactor: Pyright 和 Ruff 清理 - 批次 0"

**审查范围**: 43f7b7f..f9d274a
**变更规模**: 133 个文件，+5774/-2776 行
**审查日期**: 2026-01-15

---

## 执行摘要

### 总体评估

| 维度 | 评分 | 说明 |
|------|:----:|------|
| PIT 安全 | 🟡 4/5 | 1 个功能性 bug 需修复 |
| 规约遵守 | 🔴 3/5 | json 违规必须修复 |
| 可维护性 | 🟢 5/5 | 优秀的重构和清理 |
| 代码质量 | 🟢 4.6/5 | 零静态错误，架构优秀 |
| 文档同步 | 🟢 5/5 | 文档驱动开发典范 |
| **数据一致性** | 🔴 2/5 | checksum 严重不一致 |
| **并发安全** | 🔴 2/5 | 竞态条件风险 |
| **资源管理** | 🟡 3/5 | 资源泄漏风险 |
| **架构封装** | 🔴 2/5 | 违反层级边界 |

### 最终结论

**🔴 不可合并 - 需修复后重新审查**

---

## 第一部分：表面问题（原 5 维度审查）

### 1️⃣ PIT 安全审查

**结论**: ✅ 已修复

#### ✅ 已修复项

**重要** - `packages/datahub/src/ditto_datahub/stores/security_store.py:405-410` ✅
```python
# 修复：恢复条件判断
if is_active is not None:
    sql += " AND is_active = ?"
    params.append(is_active)
```
**Commit**: f440837dd189d2eee57c3c09efcdf5e1fb93aa23
**修复内容**: 恢复 `if is_active is not None` 条件判断，添加 `is_active=None` 测试用例

**次要** - `packages/datahub/src/ditto_datahub/runtime/pit_helper.py` ✅
- SQL 安全注释已恢复详细说明
- **Commit**: 67a1f01
- **修复内容**: 为两处 `# noqa: S608` 添加了详细的安全说明，解释输入验证机制

---

### 2️⃣ 规约审查

**结论**: ✅ 已修复

#### ✅ 已修复项

**🔴 禁止使用标准库 json 模块** ✅
- `packages/datahub/src/ditto_datahub/stores/quarantine_store.py` ✅ (Commit: 08a6bef)
- `packages/datahub/src/ditto_datahub/repositories/security.py` ✅ (Commit: 383b044)
- `packages/foundation/src/ditto_foundation/observability/logging.py` ✅ (Commit: f8d01ab)

**修复方案**: 全部替换为 `import orjson`

**🟡 测试文件使用 unittest.mock**
- 7 个测试文件使用 `from unittest.mock import patch`
- 建议迁移到 `pytest-mock` 的 `mocker` fixture

---

### 3️⃣ 可维护性审查

**结论**: 🟢 通过

#### ✅ 优秀改进
- 类型对象化重构：`save_log()` 从 9 参数简化为单一 `IngestionLog` 对象
- 消除重复：新增 `apps/port/src/ditto_port/common/types.py` 共享类型
- 测试现代化：`temp_dir` → `tmp_path`，支持并行测试

---

### 4️⃣ 代码质量审查

**结论**: 🟢 通过（有条件）

#### ✅ 优秀表现
- **零静态错误**: Ruff 和 Pyright 全部通过
- **架构改进**: 类型提取、API 重构
- **文档完整**: 4 个详细计划文档

---

### 5️⃣ 文档同步审查

**结论**: 🟢 通过

#### ✅ 文档同步非常出色
- 新增 6 个计划文档
- 所有 README、Sprint、设计文档都已同步

---

## 第二部分：深层次架构问题（⚠️ 关键发现）

### 6️⃣ 数据一致性审查

**结论**: 🔴 严重问题 - 必须修复

#### 问题 1: checksum 计算时机与落盘数据不一致

**文件**: `apps/port/src/ditto_port/services/ingestion/coordinator.py:163-221`

**当前流程**:
```python
# Line 163: 基于原始 df 计算 checksum（不含 sid/source）
checksum = self._metadata_manager.compute_checksum(df)

# Line 169: _write_data 中补齐 sid/source 后写入
write_result = self._write_data(dataset, df, trade_date, on_duplicate)

# Line 221: 记录到日志
checksum=write_result.checksum or checksum,  # 优先使用文件 checksum
```

**问题分析**:
| 组件 | checksum 来源 | 包含字段 |
|------|--------------|----------|
| MetadataManager | df.to_dict() | 原始字段（不含 sid/source） |
| ParquetStoreBase | file_md5() | 落盘后完整数据（含 sid/source） |
| FreezeManager | SHA-256(file) | 落盘后完整数据 |

**影响的数据集**:
- ✅ `stock_daily` - 补齐 sid/source
- ✅ `etf_daily` - 补齐 sid/source
- ✅ `adj_factor` - 补齐 sid/source
- ✅ `fund_adj` - 补齐 sid/source
- ❌ `calendar` - 不补齐（相对安全）
- ❌ `stock_basic` - register_batch 内部计算

**后果**:
1. **ingestion_log.checksum ≠ 落盘文件 checksum**
2. **freeze 验证失败**: freeze manifest checksum 与 ingestion_log 不匹配
3. **数据完整性无法验证**: 无法快速判断数据是否一致
4. **重复数据检测失效**: `should_skip` 基于错误的 checksum

#### 问题 2: checksum 行顺序依赖

**文件**: `apps/port/src/ditto_port/services/ingestion/metadata.py:75`

**当前实现**:
```python
data_dict = df.to_dict(as_series=False)  # 保持当前行顺序
json_str = json.dumps(data_dict, sort_keys=True, default=_json_serializable)
```

**问题**:
- `sort_keys=True` 只排序**列键**，不排序**行**
- 相同数据不同行顺序 → 不同 checksum
- 导致重复写入和日志噪声

**示例场景**:
```python
# 场景 1: 升序查询
df1 = pl.scan_parquet("stock_daily/2024.parquet").sort("trade_date").collect()
checksum1 = compute_checksum(df1)

# 场景 2: 降序查询
df2 = pl.scan_parquet("stock_daily/2024.parquet").sort("trade_date", descending=True).collect()
checksum2 = compute_checksum(df2)

# checksum1 != checksum2 （即使内容相同）
```

#### 问题 3: checksum 算法不统一

| 位置 | 算法 | 输入 | 用途 |
|------|------|------|------|
| MetadataManager | SHA-256(JSON) | df.to_dict() | ingestion_log.checksum |
| SecurityRepository | MD5(JSON) | df.to_dict() | security_store checksum |
| ParquetStoreBase | MD5(file) | 落盘文件 | WriteResult.checksum |
| FreezeManager | SHA-256(file) | 落盘文件 | freeze manifest |

**问题**: 算法不一致，无法跨组件验证

#### 修复建议（优先级排序）

**方案 1: 统一计算时机**（立即修复）
```python
# coordinator.py
def ingest_date(self, dataset: str, trade_date: str, force: bool = False):
    df = self._fetch_data(dataset, trade_date)

    # ❌ 删除: checksum = self._metadata_manager.compute_checksum(df)

    write_result = self._write_data(dataset, df, trade_date, on_duplicate)

    # ✅ 使用落盘后的 checksum（已包含所有字段）
    checksum = write_result.checksum

    self._hub.ingestion_log.save_log(
        IngestionLog(checksum=checksum, ...)
    )
```

**方案 2: 统一算法和排序**（短期优化）
```python
class ChecksumCompute:
    @staticmethod
    def from_dataframe(df: pl.DataFrame) -> str:
        """确定性 checksum（忽略行顺序）"""
        # 1. 按键列排序
        sorted_df = df.sort(["trade_date", "sid"])

        # 2. 转换为字典
        data_dict = sorted_df.to_dict(as_series=False)

        # 3. 序列化
        json_str = json.dumps(data_dict, sort_keys=True, default=_json_serializable)

        # 4. 计算 SHA-256
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
```

**方案 3: 测试验证**
```python
def test_checksum_consistency_after_enrichment():
    """验证补齐字段后 checksum 一致性"""
    original_df = pl.DataFrame({"src_code": ["000001.SZ"], "close": [10.0]})
    enriched_df = security_mapper.enrich_dataframe(original_df, ...)

    write_result = bars_store.write("stock_daily", enriched_df, 2024)

    # 验证: ingestion_log.checksum == write_result.checksum
    assert write_result.checksum == file_md5(write_result.file_path)
```

---

### 7️⃣ 并发安全审查

**结论**: ✅ 已修复

#### ✅ 问题 1: save_log() 竞态条件 - 已修复

**文件**: `packages/datahub/src/ditto_datahub/stores/ingestion_log.py`

**修复方案**：
- 使用 SQLite 的 `INSERT ... ON CONFLICT ... DO UPDATE` 语法实现原子化 UPSERT
- `attempts` 字段使用 `attempts + 1` 在数据库层面原子递增
- 使用 `RETURNING` 子句返回操作后的完整记录

**Commit**: 待提交
**测试验证**:
- ✅ `test_concurrent_save_log_attempts_increment` - 10 线程并发，attempts 正确递增到 10
- ✅ `test_concurrent_save_then_update` - 创建后多线程更新，attempts 正确
- ✅ `test_concurrent_mixed_operations` - 混合读写操作无冲突

#### ✅ 问题 2: 索引策略不匹配 - 已修复

**修复方案**：
- 删除旧索引 `idx_ingestion_log_status_date`
- 创建新索引 `idx_ingestion_log_dataset_source_status_date(dataset, source, status, trade_date)`
- 匹配所有查询模式的前缀

**Commit**: 待提交

**当前实现**:
```python
def save_log(self, log: IngestionLog) -> IngestionLog:
    # ⚠️ 检查记录是否存在（非原子操作）
    existing = self.get_log(log.dataset, log.source, log.trade_date)

    if existing:
        new_attempts = existing.attempts + 1  # ⚠️ 竞态条件
        sql = """UPDATE ingestion_log SET attempts = ? WHERE ..."""
        self._client.execute(sql, [new_attempts, ...])
    else:
        sql = """INSERT INTO ingestion_log ..."""
        self._client.execute(sql, [...])
```

**并发场景**:
```
Thread A: get_log() → 不存在 (attempts=0)
Thread B: get_log() → 不存在 (attempts=0)
Thread A: INSERT → attempts=1
Thread B: INSERT → PRIMARY KEY 冲突 OR 覆盖 A
```

**后果**:
1. **attempts 计数错误**: 应该是 2，实际是 1
2. **记录丢失**: Thread B 可能覆盖 Thread A 的记录
3. **PRIMARY KEY 冲突**: 并发 INSERT 导致数据库错误

#### 对比：SidAllocator 的正确实现

**文件**: `packages/datahub/src/ditto_datahub/runtime/sid_allocator.py:37-75`

```python
# ✅ 正确: 使用 BEGIN IMMEDIATE 确保原子性
self._pool.execute("BEGIN IMMEDIATE")

row = self._pool.execute(
    "SELECT current_max FROM sid_sequence WHERE asset_class = ?",
    [asset_class],
).fetchone()

new_sid = row["current_max"] + 1  # 在事务内安全递增
self._pool.execute("UPDATE ...")
self._pool.commit()
```

#### 问题 2: 索引策略不匹配

**当前索引**:
```sql
CREATE INDEX idx_ingestion_log_status_date
ON ingestion_log(status, trade_date)
```

**查询模式**:
1. `get_failed_dates(dataset, source, ...)` → WHERE dataset=? AND source=? AND status='FAIL'
2. `get_ingested_dates(dataset, source, status=...)` → WHERE dataset=? AND source=? AND status=?
3. `get_stats(dataset, source)` → WHERE dataset=? AND source=?

**问题**: 索引缺少 `dataset` 和 `source` 前缀，查询无法有效使用索引

#### 修复建议

**方案 1: 原子 UPSERT**（推荐）
```python
def save_log(self, log: IngestionLog) -> IngestionLog:
    now = datetime.now().isoformat()

    sql = """
        INSERT INTO ingestion_log
        (dataset, source, trade_date, status, checksum, rows,
         error_code, error_message, attempts, first_attempt_at, last_attempt_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(dataset, source, trade_date)
        DO UPDATE SET
            status = excluded.status,
            checksum = excluded.checksum,
            attempts = attempts + 1,  -- ✅ 原子递增
            last_attempt_at = excluded.last_attempt_at
        RETURNING *
    """

    row = self._client.fetchone(sql, [...])
    return IngestionLog(**dict(row))
```

**方案 2: 修复索引**
```sql
-- 删除旧索引
DROP INDEX IF EXISTS idx_ingestion_log_status_date;

-- 创建新索引（匹配查询模式）
CREATE INDEX idx_ingestion_log_dataset_source_status
ON ingestion_log(dataset, source, status);

-- 如果需要按日期排序
CREATE INDEX idx_ingestion_log_dataset_source_status_date
ON ingestion_log(dataset, source, status, trade_date);
```

**方案 3: 并发测试**
```python
def test_concurrent_save_log():
    """测试并发保存日志的原子性"""
    store = IngestionLogStore(client)
    log = IngestionLog(...)

    def save_in_thread():
        store.save_log(log)

    # 并发执行 10 次
    threads = [threading.Thread(target=save_in_thread) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 验证: attempts 应该是 10
    final_log = store.get_log("test", "tushare", "2024-01-01")
    assert final_log.attempts == 10
```

#### 风险评估

| 场景 | 当前风险 | 影响 |
|------|---------|------|
| 单线程摄入 (CLI) | 低 | 无并发问题 |
| Prefect 并发任务 | 🔴 高 | attempts 错误，记录丢失 |
| 多进程并发 | 🔴 极高 | 数据损坏，PRIMARY KEY 冲突 |

---

### 8️⃣ 资源管理审查

**结论**: 🟡 中等问题 - 应尽快修复

#### 问题 1: CLI DataHub 生命周期未管理

**文件**: `apps/port/src/ditto_port/cli/context.py:16-26`

**当前实现**:
```python
def ensure_executor(ctx: Any) -> None:
    hub = DataHub(data_root=data_root)
    app_ctx = _AppContext(hub=hub, source=hub.sources)
    executor = CLIExecutor(app_ctx)

    ctx.obj["executor"] = executor
    ctx.obj["hub"] = hub
    # ❌ hub.close() 永远不会被调用
```

**问题**:
- ❌ SQLite 连接池未关闭
- ❌ DuckDB 连接未关闭
- ❌ Store 的 SQLite 客户端未关闭
- ❌ 文件句柄泄漏

**影响范围**:
- 所有 CLI 命令（stock, etf, calendar, adj）
- 每次命令执行都会泄漏资源
- Windows 上可能阻止进程退出

#### 问题 2: Observability 配置未生效

**配置定义** (`packages/foundation/src/ditto_foundation/config/settings.py:141-161`):
```python
class ObservabilitySettings(BaseSettings):
    enabled: bool = Field(default=True)
    mode: str = Field(default="auto")
    vm_endpoint: str | None = None
    metrics_interval_ms: int = 30000
```

**实际使用** (`packages/foundation/src/ditto_foundation/app_initializer.py:84-96`):
```python
def _setup_observability(self, settings: Any) -> None:
    # ❌ 未检查 settings.observability.enabled
    # ❌ 未使用 settings.observability.mode
    # ❌ 未使用 settings.observability.vm_endpoint

    mode = Mode.PRODUCTION if settings.is_production else Mode.DEVELOPMENT
    init(..., mode=mode)
```

**问题**:
- ❌ `OBSERVABILITY_ENABLED=false` 无法禁用
- ❌ `OBSERVABILITY_MODE=testing` 不生效
- ❌ VictoriaMetrics 配置不传递

#### 修复建议

**方案 1: CLI 上下文管理器**
```python
from contextlib import contextmanager

@contextmanager
def create_executor(data_root: str | None):
    """创建执行器上下文管理器."""
    hub = DataHub(data_root=data_root)
    try:
        app_ctx = _AppContext(hub=hub, source=hub.sources)
        executor = CLIExecutor(app_ctx)
        yield executor
    finally:
        hub.close()  # ✅ 确保资源释放

# 使用
def command(ctx: typer.Context, date: str) -> None:
    with create_executor(ctx.obj["data_root"]) as executor:
        result = executor.ingest_daily("stock_daily", date, False)
        print_ingestion_result(result)
```

**方案 2: 修复 Observability 配置**
```python
def _setup_observability(self, settings: Any) -> None:
    obs_settings = settings.observability

    # ✅ 检查是否启用
    if not obs_settings.enabled:
        logger.info("Observability disabled by configuration")
        return

    # ✅ 解析 mode 配置
    mode_mapping = {
        "auto": None,
        "production": Mode.PRODUCTION,
        "development": Mode.DEVELOPMENT,
        "testing": Mode.TESTING,
    }

    configured_mode = mode_mapping.get(obs_settings.mode.lower())
    actual_mode = configured_mode or (
        Mode.PRODUCTION if settings.is_production else Mode.DEVELOPMENT
    )

    init(
        service_name="ditto",
        environment=settings.system.ditto_env,
        log_level=obs_settings.log_level,
        vm_endpoint=obs_settings.vm_endpoint,  # ✅ 传递配置
        mode=actual_mode,
    )
```

---

### 9️⃣ 架构封装审查

**结论**: 🔴 严重问题 - 违反层级边界

#### 问题 1: UniverseRepository 绕过 Store 层

**文件**: `packages/datahub/src/ditto_datahub/repositories/universe.py:316-327`

**当前实现（违反封装）**:
```python
# 直接访问 UniverseStore 的底层 client
client = self._universe_store.client  # ← 问题：访问内部实现

sids = df["sid"].to_list()
if not sids:
    return df

# 直接执行 SQL 查询 security 表
placeholders = ",".join("?" * len(sids))
query = f"SELECT sid, symbol FROM security WHERE sid IN ({placeholders})"  # noqa: S608
security_rows = client.fetchall(query, sids)
```

**架构违反分析**:
```
当前实现（违反封装）:
┌─────────────────────────────────────────────────────────┐
│  UniverseRepository                                     │
│  ├── _universe_store: UniverseStore                    │
│  └── _enrich_with_symbol():                             │
│       └── self._universe_store.client  ← 越过边界        │
│           └── fetchall("SELECT ... FROM security")      │
└─────────────────────────────────────────────────────────┘
           │                    │ 越过 Store 边界
           ↓                    ↓
┌─────────────────┐    ┌──────────────────────────────────┐
│  UniverseStore  │    │  SecurityStore                   │
│  └── client     │    │  └── enrich_with_symbol()  ← 已存在!│
└─────────────────┘    └──────────────────────────────────┘
```

**正确的架构（依赖注入）**:
```
┌─────────────────────────────────────────────────────────┐
│  UniverseRepository                                     │
│  ├── _universe_store: UniverseStore                    │
│  ├── _security_store: SecurityStore  ← 注入依赖         │
│  └── _enrich_with_symbol():                             │
│       └── self._security_store.enrich_with_symbol(df)   │
└─────────────────────────────────────────────────────────┘
           │                      │
           ↓                      ↓
┌─────────────────┐    ┌──────────────────────────────────┐
│  UniverseStore  │    │  SecurityStore                   │
│                 │    │  └── enrich_with_symbol()        │
└─────────────────┘    └──────────────────────────────────┘
```

#### SecurityStore 已有相同功能

**文件**: `packages/datahub/src/ditto_datahub/stores/security_store.py:469-493`

```python
def enrich_with_symbol(self, df: pl.DataFrame) -> pl.DataFrame:
    """
    Add symbol column to DataFrame.
    """
    if "sid" not in df.columns or df.is_empty():
        return df

    sids = df["sid"].unique().to_list()
    symbol_map = self.get_sid_symbol_map(sids)

    symbol_df = pl.DataFrame(
        {
            "sid": list(symbol_map.keys()),
            "symbol": list(symbol_map.values()),
        }
    )

    return df.join(symbol_df, on="sid", how="left")
```

#### PR 的"修复"只是掩盖问题

**文件**: `packages/datahub/src/ditto_datahub/stores/universe_store.py:45-48`

```python
@property
def client(self) -> SQLiteClient:
    """Get the SQLite client."""
    return self._client  # ← 暴露了内部实现
```

**问题分析**:
| 方面 | 原代码 (_client) | PR 修复后 (client) |
|------|-----------------|-------------------|
| 封装性 | ❌ 访问私有属性（临时实现） | ❌ 暴露内部实现（永久化问题） |
| pyright | ⚠️ 警告 | ✅ 无警告 |
| 架构债务 | 明确标记为 _client | 隐藏在 public API 后 |
| 正确性 | 功能正常 | 功能正常 |

**PR 通过添加 public property 绕过了 pyright 的警告，但没有解决架构问题。**

#### 修复建议

**方案 1: 依赖注入**（推荐）
```python
# universe.py
class UniverseRepository:
    def __init__(
        self,
        universe_store: UniverseStore,
        security_store: SecurityStore,  # ← 添加依赖注入
        sid_allocator: SidAllocator,
    ) -> None:
        self._universe_store = universe_store
        self._security_store = security_store  # ← 注入 SecurityStore
        self._sid_allocator = sid_allocator

    def _enrich_with_symbol(self, df: pl.DataFrame) -> pl.DataFrame:
        """Enrich constituents DataFrame with symbol."""
        return self._security_store.enrich_with_symbol(df)  # ← 委托给 SecurityStore
```

**方案 2: 移除 client 属性**
```python
# universe_store.py
# ❌ 删除这个 property
# @property
# def client(self) -> SQLiteClient:
#     return self._client
```

#### 影响评估

| 影响类型 | 描述 |
|----------|------|
| **紧耦合** | UniverseRepository 与 SQLiteClient 紧密耦合 |
| **难以测试** | 无法轻易 mock SecurityStore 行为 |
| **代码重复** | 如果其他 Repository 也需要 symbol，会复制这个模式 |
| **违反规范** | 违反 datahub.md 中 "Repository 通过 Store 访问" 的规定 |
| **可维护性** | 如果 SQLiteClient 接口变化，会影响 Repository |

---

#### 问题 2: DataHub 生命周期管理设计不合理

**文件**: `packages/datahub/src/ditto_datahub/hub.py`

**当前实现分析**:

```python
# hub.py 当前实现
class DataHub:
    def __enter__(self) -> "DataHub":
        return self

    def __exit__(self, *args) -> None:
        self.close()  # 调用 close()

    def close(self) -> None:
        """关闭所有 Store 和连接."""
        # 关闭所有 SQLite-based Store
        # 关闭 SQL Engine (DuckDB)
        # 关闭 SQLite Pool
```

---

### 📌 补充说明：为什么这不是一个高优先级问题

#### 1. 当前实现已经支持上下文管理器

**DataHub 已经实现了上下文管理器协议**:
```python
# ✅ 支持使用 with 语句
with DataHub(data_root) as hub:
    result = hub.universe.get_constituents("csi_300")
# 自动调用 hub.close()
```

**Flow 场景已经有正确的实现** (`helpers.py`):
```python
@contextmanager
def create_ingestion_context(data_root: str):
    hub = DataHub(data_root=data_root)
    try:
        coordinator = IngestionCoordinator(hub=hub, ...)
        yield hub, coordinator
    finally:
        hub.close()  # ✅ 已经正确实现
```

#### 2. 真正的问题是 CLI 场景

**CLI 当前实现** (`cli/context.py`):
```python
def ensure_executor(ctx: Any) -> None:
    hub = DataHub(data_root=data_root)
    # ...
    # ❌ 没有使用 with，也没有调用 close()
```

**修复很简单**:
```python
from contextlib import contextmanager

@contextmanager
def create_executor(data_root: str | None):
    """创建执行器上下文管理器."""
    hub = DataHub(data_root=data_root)
    try:
        app_ctx = _AppContext(hub=hub, source=hub.sources)
        executor = CLIExecutor(app_ctx)
        yield executor
    finally:
        hub.close()  # ✅ 确保资源释放

# 使用
def command(ctx: typer.Context, date: str) -> None:
    with create_executor(ctx.obj["data_root"]) as executor:
        result = executor.ingest_daily("stock_daily", date, False)
        print_ingestion_result(result)
```

#### 3. 连接池问题的影响有限

**SQLitePool 的实际行为**:
```python
class SQLitePool:
    def __init__(self, db_path: str) -> None:
        self._local = threading.local()  # 线程本地存储

    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(...)  # 按需创建
            self._local.conn = conn
        return self._local.conn  # 永不释放
```

**实际影响分析**:

| 场景 | 连接数 | 是否有问题 | 原因 |
|------|--------|-----------|------|
| CLI（单线程） | 1 | ❌ 否 | 进程退出时自动释放 |
| Flow（单线程顺序） | 1 | ❌ 否 | 进程退出时自动释放 |
| Flow（多线程并发） | N（线程数） | ⚠️ 可能 | 需要确认线程数量 |
| 测试（频繁创建） | N（测试数） | ⚠️ 可能 | Windows 文件锁 |

**结论**:
- **单线程场景**（CLI、大多数 Flow）：问题不大，进程退出自动清理
- **多线程场景**：需要确认线程数量，但通常 < 10，影响有限
- **测试场景**：Windows 文件锁问题，但已有 `with` 支持

#### 4. 为什么不需要全局事务

**多文件类型无法保证原子性**:
```
操作序列:
1. SQLite: INSERT INTO security ...     ← 可回滚
2. SQLite: INSERT INTO universe ...     ← 可回滚
3. Parquet: 写入 stock_daily/2024.parquet ← ❌ 无法回滚（文件已写入）
4. SQLite: INSERT INTO ingestion_log ... ← 可回滚

如果步骤 3 失败：步骤 1、2 可以回滚，但步骤 3 的文件已经写入磁盘
```

**务实的补偿机制**:
```python
# ingestion_log 记录每次摄取结果
IngestionLog(
    dataset="stock_daily",
    trade_date="2024-01-01",
    status="FAILED",  # 失败状态
    attempts=2,       # 可以重试
    error="Parquet write failed"
)

# repair 任务可以重新执行
@task
def repair_stock_daily(trade_date: str):
    """修复失败的摄取."""
    coordinator.ingest_date("stock_daily", trade_date, force=True)
```

**结论**:
- ✅ **当前实现已足够**: `with DataHub()` + `create_ingestion_context()`
- ✅ **补偿机制完善**: ingestion_log + repair/backfill 任务
- ⚠️ **仅需改进**: CLI 场景使用上下文管理器
- ❌ **不需要**: 全局事务（Parquet 无法回滚）

---

#### 5. 推荐修复（务实方案）

**方案 1: 修复 CLI 资源泄漏**（P1 - 必须）

```python
# cli/context.py
from contextlib import contextmanager

@contextmanager
def create_executor(data_root: str | None):
    """创建执行器上下文管理器."""
    hub = DataHub(data_root=data_root)
    try:
        app_ctx = _AppContext(hub=hub, source=hub.sources)
        executor = CLIExecutor(app_ctx)
        yield executor
    finally:
        hub.close()

# 更新所有命令
def command(ctx: typer.Context, date: str) -> None:
    with create_executor(ctx.obj["data_root"]) as executor:
        result = executor.ingest_daily("stock_daily", date, False)
        print_ingestion_result(result)
```

**方案 2: 改进文档**（P1 - 低成本）

```python
class DataHub:
    """DataHub 统一数据入口.

    生命周期管理:
    - 推荐: 使用 with 语句自动管理
        with DataHub() as hub:
            hub.sql(...)

    - 手动: 调用 close() 显式关闭（仅测试等特殊场景）
        hub = DataHub()
        try:
            hub.sql(...)
        finally:
            hub.close()

    数据一致性保证:
    - 摄取状态: ingestion_log 记录每次摄取结果
    - 失败重试: 通过 attempts 字段支持自动重试
    - 补偿任务: Flow 层提供 repair/backfill 任务兜底

    注意:
    - 不支持全局事务（SQLite + Parquet 混合存储）
    - 如需事务，在 Repository 层实现（仅限 SQLite Store 之间）
    """

    # 保持现有实现不变
    def __enter__(self) -> "DataHub":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """显式关闭资源."""
        self._cleanup()
```

**方案 3: Repository 层事务支持**（P2 - 可选）

```python
# repositories/security.py
class SecurityRepository:
    """证券信息 Repository."""

    def register_with_universe(
        self,
        securities: list[Security],
        universe_id: str,
    ) -> None:
        """注册证券并创建 Universe（原子操作）.

        这是一个 Repository 层的事务示例，
        仅涉及 SQLite Store，可以保证原子性.
        """
        # 在单个 SQLite 事务中完成
        try:
            self._pool.execute("BEGIN IMMEDIATE")

            # 注册证券
            for sec in securities:
                self._store.register(...)

            # 创建 Universe
            self._universe_store.create(...)

            self._pool.commit()
        except Exception:
            self._pool.rollback()
            raise
```

---

### 最终评估

| 方面 | 当前状态 | 是否需要修复 | 优先级 |
|------|---------|-------------|--------|
| 上下文管理器支持 | ✅ 已实现 | ❌ 否 | - |
| CLI 资源泄漏 | ❌ 有问题 | ✅ 是 | P1 |
| SQLitePool 实现 | ⚠️ 不是真正的池 | ⚠️ 可选 | P2 |
| 全局事务 | ❌ 不支持 | ❌ 否（Parquet 限制） | - |
| Repository 层事务 | ⚠️ 手动管理 | ⚠️ 可选 | P2 |
| 数据一致性保证 | ✅ ingestion_log | ❌ 否 | - |

**结论**:
- 当前实现 **已基本满足需求**
- **仅需修复**: CLI 场景的资源泄漏
- **可选改进**: 连接池重构、Repository 层事务
- **不需要**: 全局事务（Parquet 无法回滚）

---

#### 核心问题（原始内容保留）

**设计矛盾**: 用户的观点与当前实现不符
   - **用户期望**: "连接池不需要 close" - 认为内部是真正的连接池，应自动管理
   - **实际实现**: `threading.local()` 模式，每个线程一个连接，必须手动 close

**SQLitePool 不是真正的连接池**:
   - ❌ **不是连接池**: 是线程本地连接管理器
   - ❌ **无连接复用**: 每个线程一个连接，永不共享
   - ❌ **必须手动 close**: 否则连接累积直到进程结束

**务实的架构观点**（用户建议）:
1. **全局事务不现实** - Parquet 写入无法回滚
2. **补偿机制足够** - ingestion_log 记录状态，失败可重试
3. **Repository 层事务** - 如有需求，仅在 SQLite Store 之间支持

    数据一致性保证:
    - 摄取状态: ingestion_log 记录每次摄取结果
    - 失败重试: 通过 attempts 字段支持自动重试
    - 补偿任务: Flow 层提供 repair/backfill 任务兜底

    注意:
    - 不支持全局事务（SQLite + Parquet 混合存储）
    - 如需事务，在 Repository 层实现（仅限 SQLite Store 之间）
    """

    # 保持现有实现不变
    def __enter__(self) -> "DataHub":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """显式关闭资源."""
        self._cleanup()
```

**方案 2: Repository 层事务支持**（P2 - 按需实现）

```python
# repositories/security.py
class SecurityRepository:
    """证券信息 Repository."""

    def register_with_universe(
        self,
        securities: list[Security],
        universe_id: str,
    ) -> None:
        """注册证券并创建 Universe（原子操作）.

        这是一个 Repository 层的事务示例，
        仅涉及 SQLite Store，可以保证原子性.
        """
        # 在单个 SQLite 事务中完成
        try:
            self._pool.execute("BEGIN IMMEDIATE")

            # 注册证券
            for sec in securities:
                self._store.register(...)

            # 创建 Universe
            self._universe_store.create(...)

            self._pool.commit()
        except Exception:
            self._pool.rollback()
            raise
```

**方案 3: 重构为真正的连接池**（P2 - 长期优化，可选）

```python
# sqlite_pool.py - 真正的连接池实现
class SQLitePool:
    """SQLite 连接池（真正的 pool）."""

    def __init__(self, db_path: str, pool_size: int = 5) -> None:
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=pool_size)
        self._pool_size = pool_size
        self._local = threading.local()

        # 预创建连接
        for _ in range(pool_size):
            conn = self._create_connection(db_path)
            self._pool.put(conn)

    @contextmanager
    def acquire(self) -> Iterator[sqlite3.Connection]:
        """获取连接（上下文管理器）."""
        if not hasattr(self._local, "conn"):
            self._local.conn = self._pool.get(timeout=30.0)

        try:
            yield self._local.conn
        finally:
            if hasattr(self._local, "conn"):
                self._pool.put(self._local.conn)
                delattr(self._local, "conn")

    def execute(self, sql: str, params: list[Any] | None = None):
        """执行 SQL（自动管理连接）."""
        with self.acquire() as conn:
            return conn.execute(sql, params or [])

    def close(self) -> None:
        """关闭所有连接."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except queue.Empty:
                break
```

**方案 2 优点**:
- ✅ 真正的连接复用
- ✅ 限制最大连接数
- ✅ 自动连接管理
- ✅ 符合 "连接池" 语义

**方案 2 缺点**:
- ❌ 需要大量重构
- ❌ 需要更新所有 Store 的实现
- ❌ 需要全面测试

---

**使用示例**:

```python
# 场景 1: CLI - 使用 with 自动管理（推荐）
with DataHub(data_root) as hub:
    result = hub.universe.get_constituents("csi_300")

# 场景 2: Flow - 使用 create_ingestion_context（已实现）
@task
def ingest_securities(trade_date: str, data_root: str):
    with create_ingestion_context(data_root) as (hub, coordinator):
        result = coordinator.ingest_securities(trade_date)
        # ingestion_log 记录状态
        # 失败时可通过 repair 任务补偿

# 场景 3: 测试 - 手动精细控制
def test_something():
    hub = DataHub(tmp_path)
    try:
        # 测试逻辑
        pass
    finally:
        hub.close()  # 确保 Windows 文件锁释放

# 场景 4: Repository 层事务（可选，仅 SQLite 操作）
def register_with_universe(hub: DataHub, securities, universe_id):
    """Repository 层的事务示例."""
    try:
        hub.sqlite_pool.execute("BEGIN IMMEDIATE")
        hub.security_store.register_batch(securities)
        hub.universe_store.create(universe_id)
        hub.sqlite_pool.commit()
    except Exception:
        hub.sqlite_pool.rollback()
        raise
```

---

**影响评估**:

| 影响类型 | 描述 |
|----------|------|
| **API 兼容性** | 保持兼容（保留 close()） |
| **学习曲线** | 文档说明 with 语句优先 |
| **性能** | 连接池重构后性能提升（可选） |
| **可靠性** | ingestion_log + 补偿任务已足够 |

---

**修复优先级**（更新为务实方案）:

| # | 方案 | 优先级 | 工作量 | 风险 |
|---|------|-------|--------|------|
| 1 | 改进 DataHub 生命周期文档 | P1 | 低 | 低 |
| 2 | 确保 CLI 使用 with 语句 | P1 | 低 | 低 |
| 3 | Repository 层事务支持（按需） | P2 | 中 | 低 |
| 4 | 重构 SQLitePool 为真正连接池 | P2 | 高 | 中 |

---

## 第三部分：优先级与修复计划（更新）

### 优先级分级

#### P0（阻塞合并 - 必须立即修复）

| # | 问题 | 文件 | 严重性 |
|---|------|------|--------|
| 1 | checksum 计算时机不一致 | coordinator.py:163 | 🔴 数据一致性 |
| 2 | save_log() 竞态条件 | ingestion_log.py:75 | 🔴 并发安全 |
| 3 | json 违规（3 个文件） | multiple | 🔴 规约违反 |
| 4 | is_active 逻辑错误 | security_store.py:405 | 🔴 功能 bug |
| 5 | UniverseRepository 绕过 Store 层 | universe.py:316 | 🔴 架构违规 |

#### P1（强烈建议 - 合并前修复）

| # | 问题 | 文件 | 严重性 |
|---|------|------|--------|
| 6 | checksum 行顺序依赖 | metadata.py:75 | 🟡 数据质量 |
| 7 | CLI DataHub 资源泄漏 | cli/context.py | 🟡 资源管理 |
| 8 | ingestion_log 索引不匹配 | ingestion_log.py:63 | 🟡 性能 |
| 9 | Observability 配置未生效 | app_initializer.py:84 | 🟡 配置 |

#### P2（合并后跟进）

| # | 问题 | 说明 |
|---|------|------|
| 10 | DataHub 生命周期文档 | hub.py 文档改进 |
| 11 | checksum 算法不统一 | 需要跨组件统一 |
| 12 | unittest.mock 违规 | 7 个测试文件 |
| 13 | DatabaseManager 资源泄漏 | conftest.py |
| 14 | test_deploy_integration.py 缺失 | 需确认测试覆盖 |
| 15 | Repository 层事务支持 | 按需实现（可选）|

---

## 第四部分：结构级优化方案（面向顶级量化系统标准）

### ✅ 数据摄取一致性与幂等性

**引入"数据版本"或"标准化 checksum"**:

```python
class DataFingerprint:
    """数据指纹（确保相同数据产生相同指纹）"""

    @staticmethod
    def compute(df: pl.DataFrame, sort_keys: list[str]) -> str:
        """
        标准化后计算指纹：
        1. 排序（按 sort_keys）
        2. 类型规范（日期、浮点精度）
        3. 去除冗余字段（内部标识符）
        4. 计算 SHA-256
        """
        normalized = df.sort(sort_keys)
        data_dict = normalized.to_dict(as_series=False)
        json_str = json.dumps(data_dict, sort_keys=True, default=_json_serializable)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

# 使用
fingerprint = DataFingerprint.compute(df, sort_keys=["trade_date", "sid"])
```

**强制日志 checksum 与落盘一致**:
- 将 checksum 计算与写入绑定
- `WriteResult.checksum` 必须是落盘数据的指纹
- `ingestion_log.checksum` 必须使用 `WriteResult.checksum`

### ✅ 并发与可重放

**ingestion_log 采用 UPSERT 原子化写入**:
```python
INSERT INTO ingestion_log (...) VALUES (...)
ON CONFLICT(dataset, source, trade_date)
DO UPDATE SET attempts = attempts + 1, ...
```

**IngestionCoordinator 增加幂等标识**:
```python
@dataclass
class IngestionResult:
    run_id: str  # UUID，标识单次运行
    batch_id: str | None  # 批次标识（backfill 时使用）
    ...
```

### ✅ 可观测性一致性

**ObservabilitySettings 贯穿 AppInitializer**:
- `enabled=False` → 完全关闭日志/trace/metrics
- `mode=auto/production/testing` → 显式覆盖系统环境判断
- `vm_endpoint` → 传递到 metrics 导出器

---

## 第五部分：执行建议

### 方案 A：完整修复后合并（推荐）

**第一阶段：P0 问题修复**
1. ✅ 修复 checksum 计算时机（使用落盘 checksum）
2. ✅ 修复 save_log() 竞态条件（原子 UPSERT）
3. ✅ 修复 json 违规（替换为 orjson）
4. ✅ 修复 is_active 逻辑错误
5. ✅ 修复 UniverseRepository 架构违规（依赖注入 SecurityStore）
6. ✅ 修复 ingestion_log 索引

**第二阶段：P1 问题修复**
7. ✅ 修复 checksum 行顺序依赖
8. ✅ 修复 CLI 资源泄漏（上下文管理器）
9. ✅ 修复 Observability 配置
10. ✅ 添加并发测试用例
11. ✅ 添加资源泄漏测试

**第三阶段：验证**
12. 运行 `pixi run -e dev ci`
13. 运行并发测试验证修复
14. 更新 PR 并重新审查
15. 合并

### 方案 B：分批处理（不推荐）

1. 本 PR 只修复表面问题（P0 中的 3、4）
2. 创建专项 PR 处理数据一致性问题
3. 创建专项 PR 处理并发安全问题
4. 增加技术债务跟踪

**风险**: 深层次问题在生产环境中可能导致数据损坏

---

## 第六部分：关键文件清单

### P0 修复文件（必改）
```
apps/port/src/ditto_port/services/ingestion/coordinator.py
packages/datahub/src/ditto_datahub/stores/ingestion_log.py
packages/datahub/src/ditto_datahub/stores/security_store.py
packages/datahub/src/ditto_datahub/stores/quarantine_store.py
packages/datahub/src/ditto_datahub/repositories/security.py
packages/datahub/src/ditto_datahub/repositories/universe.py
packages/datahub/src/ditto_datahub/stores/universe_store.py (移除 client property)
packages/foundation/src/ditto_foundation/observability/logging.py
```

### P1 修复文件（强烈建议）
```
apps/port/src/ditto_port/services/ingestion/metadata.py
apps/port/src/ditto_port/cli/context.py
packages/foundation/src/ditto_foundation/app_initializer.py
packages/datahub/src/ditto_datahub/stores/ingestion_log.py (索引)
```

### P2 改进文件（合并后跟进）
```
packages/datahub/src/ditto_datahub/hub.py (生命周期文档)
packages/datahub/src/ditto_datahub/runtime/sqlite_pool.py (连接池重构，可选)
```

### 测试文件（需新增）
```
apps/port/tests/integration/test_checksum_consistency.py
apps/port/tests/integration/test_concurrent_safety.py
apps/port/tests/integration/cli/test_resource_cleanup.py
```

---

## 附录：测试验证清单

### Checksum 一致性测试
- [ ] `test_checksum_consistency_after_enrichment()` - 验证补齐字段后一致
- [ ] `test_checksum_deterministic_irrespective_of_row_order()` - 验证行顺序无关

### 并发安全测试
- [ ] `test_concurrent_save_log()` - 验证 attempts 原子递增
- [ ] `test_concurrent_ingestion_no_data_loss()` - 验证无数据丢失

### 资源管理测试
- [ ] `test_cli_no_resource_leak()` - 验证无文件句柄泄漏
- [ ] `test_observability_config_respected()` - 验证配置生效

---

## 总结

这个 PR 在代码清理方面做了大量工作，但暴露了更深层次的架构问题：

**表面问题**（5 维度审查）:
- ✅ 零静态错误
- ✅ 优秀的重构和文档
- 🔴 少量规约违反（json、is_active）

**深层次问题**（架构级风险）:
- 🔴 **数据一致性**: checksum 与落盘数据不匹配
- 🔴 **并发安全**: 竞态条件导致数据损坏风险
- 🟡 **资源管理**: CLI 资源泄漏

**建议**: 优先修复 P0 问题后再合并，避免将架构级债务带入生产环境。
