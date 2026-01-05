# 代码审查问题修复计划（完整版）

**创建日期**: 2025-01-05
**优先级**: P0 - Critical/High, P1 - Medium/Low
**预计工作量**: 22 小时

---

## 执行摘要

本计划修复代码审查中发现的 **2 个 Critical**、**3 个 High**、**3 个 Medium** 和 **2 个 Low** 级别问题，基于用户的关键决策：

### 已确认的用户决策

1. **SID 分配**: 完全使用 SidAllocator（线程安全），弃用 SecurityMapper 的内存计数器
2. **DQ 阻断游标**: 保持现状（阻断也推进游标），失败数据由重试任务处理
3. **DQ 配置路径**: 统一到 `data_root/config/dq`，支持用户自定义覆盖包内默认配置
4. **多源支持**: 重构游标表支持 `(dataset, source)` 复合主键
5. **Tushare token 环境变量**: 删除 .env.example 中的残留配置
6. **OnDuplicate.ERROR**: 自动去重（保留第一条），检测并处理 batch 内部重复

---

## 问题清单（按优先级）

| # | 问题 | 优先级 | 预估时间 | 状态 |
|---|------|--------|---------|------|
| 1 | IngestionCoordinator 调用不存在的 API | Critical | 3h | 待开始 |
| 2 | SID 分配并发安全问题 | Critical | 4h | 已完成 |
| 3 | 游标多源支持 | High | 5h | 待开始 |
| 4 | DQ 配置路径不统一 | High | 3h | 待开始 |
| 5 | BarsRepository 未传递 context | High | 1h | 待开始 |
| 6 | Tushare token 环境变量残留 | Medium | 0.5h | 待开始 |
| 7 | OnDuplicate.ERROR 未检测 batch 内部重复 | Medium | 2h | 待开始 |
| 8 | SqlEngine 不支持 meta.* 查询 | Medium | 1h | 待开始 |
| 9 | schema.sql 保留已废弃表 | Low | 0.5h | 待开始 |
| 10 | SQL whitelist 未包含摄取表 | Low | 0.5h | 待开始 |
| | **总计** | | **20.5h** | |

---

## 详细任务

### 任务 1-5: Critical 和 High 级别问题

*(详见之前的设计，以下为简要概述)*

#### 任务 1: Critical - IngestionCoordinator API 调用修复
**目标**: 添加 `DataHub.adj_factor` 属性和 `SecurityRepository.register_batch()` 方法

**涉及文件**:
- `packages/datahub/src/ditto_datahub/hub.py`
- `packages/datahub/src/ditto_datahub/repositories/security.py`
- `apps/server/src/ditto_server/ingestion/services/coordinator.py`

---

#### 任务 2: Critical - SID 分配并发安全
**目标**: SecurityMapper 完全委托给 SidAllocator，移除内存计数器

**涉及文件**:
- `apps/server/src/ditto_server/ingestion/services/security_mapper.py`
- `apps/server/src/ditto_server/ingestion/services/coordinator.py`

---

#### 任务 3: High - 游标多源支持
**目标**: 重构游标表支持 `(dataset, source)` 复合主键

**涉及文件**:
- `packages/datahub/src/ditto_datahub/stores/ingestion_cursor.py`
- `packages/datahub/src/ditto_datahub/runtime/schema.sql`
- `packages/datahub/migrations/0002_cursor_multi_source.py` (新建)
- `apps/server/src/ditto_server/ingestion/services/coordinator.py`

**数据迁移**: 包含完整的 upgrade 和 downgrade 脚本

---

#### 任务 4: High - DQ 配置路径统一
**目标**: 统一到 `data_root/config/dq`，支持用户自定义覆盖

**涉及文件**:
- `packages/datahub/src/ditto_datahub/dq/engine.py`
- `apps/server/src/ditto_server/ingestion/tasks/dq_batch.py`
- `packages/datahub/scripts/init_dq_config.py` (新建)
- `packages/datahub/README.md`

---

#### 任务 5: High - BarsRepository context 传递
**目标**: 修复 DQ 检查未传递 context 导致 FK 检查失效

**涉及文件**:
- `packages/datahub/src/ditto_datahub/repositories/bars.py` (line 282-283)

**修改**: 传递 `context={"hub": self._hub}` 给 DQEngine

---

### 任务 6: Medium - Tushare token 环境变量残留清理

**目标**: 删除 .env.example 中的 TUSHARE_TOKEN 配置，清理残留引用

**问题分析**:
- 核心代码已删除环境变量支持（client.py 第 35 行）
- 只支持 keyring 和 `~/.ditto/secrets.toml`
- .env.example 第 33 行仍保留 `TUSHARE_TOKEN=your_tushare_token_here`

**影响范围**:
- 用户可能误认为可以通过环境变量配置 token
- 配置文件与代码实现不一致

**涉及文件**:
- `.env.example` (line 33) - 删除 TUSHARE_TOKEN 配置
- `packages/datahub/README.md` - 更新 token 配置说明
- `docs/design/*.md` - 清理过时的环境变量引用

**实现步骤**:

1. **删除 .env.example 中的配置**:
   ```bash
   # 删除或注释以下行：
   # TUSHARE_TOKEN=your_tushare_token_here
   ```

2. **更新 README.md**:
   ```markdown
   ## Tushare Token 配置

   Ditto 支持以下方式配置 Tushare token（按优先级排序）：

   1. **Keyring（推荐）**:
      ```bash
      pixi run -e dev python -c "
      import keyring
      keyring.set_password('ditto', 'tushare', 'your_token_here')
      "
      ```

   2. **~/.ditto/secrets.toml**:
      ```toml
      [tushare]
      token = "your_token_here"
      ```

   注意：不再支持通过 .env 文件或环境变量配置 token。
   ```

3. **搜索并清理其他残留**:
   ```bash
   # 搜索可能的残留引用
   grep -r "TUSHARE_TOKEN" docs/
   grep -r "getenv.*TUSHARE" packages/
   ```

**验收标准**:
- [ ] .env.example 中无 TUSHARE_TOKEN 配置
- [ ] README.md 更新为只支持 keyring 和 secrets.toml
- [ ] 文档中无过时的环境变量引用
- [ ] 测试文件中的 mock 代码已更新

**预估时间**: 0.5 小时

---

### 任务 7: Medium - OnDuplicate.ERROR 检测 batch 内部重复

**目标**: 检测并自动处理 incoming batch 内部的重复记录

**问题分析**:
- 当前只检测新数据与现有数据的重复
- 未检测 batch 内部重复（如同一 sid+trade_date 出现多次）
- OnDuplicate.ERROR 模式下可能导致数据不一致

**影响范围**:
- `BarsStore.write()` - stock_daily, etf_daily, index_daily
- `AdjFactorStore.write()` - adj_factor 数据
- 所有使用 OnDuplicate.ERROR 的写入操作

**涉及文件**:
- `packages/datahub/src/ditto_datahub/stores/bars_store.py` (line 123)
- `packages/datahub/src/ditto_datahub/stores/adj_factor_store.py` (line 174)

**用户决策**: 自动去重（保留第一条）

**实现步骤**:

1. **BarsStore 修复**:
   ```python
   # stores/bars_store.py

   def write(
       self,
       df: pl.DataFrame,
       dataset: str,
       year: int,
       on_duplicate: OnDuplicate = OnDuplicate.ERROR,
   ) -> WriteResult:
       """
       Write OHLCV data to parquet files.

       Args:
           df: Data to write (must contain sid, trade_date, open, high, low, close, volume).
           dataset: Dataset name (e.g., "stock_daily").
           year: Year partition for parquet file.
           on_duplicate: Strategy for handling duplicates.

       Returns:
           WriteResult with file path, checksum, and any blocked records.

       """
       # 1. ✅ 新增：检测并处理 batch 内部重复
       key_columns = ["sid", "trade_date"]
       batch_duplicates = df.groupby(key_columns).agg(
           pl.len().alias("_count")
       ).filter(pl.col("_count") > 1)

       if not batch_duplicates.is_empty():
           logger.warning(
               "检测到 batch 内部重复，自动去重（保留第一条）",
               event="batch_internal_duplicates",
               dataset=dataset,
               year=year,
               duplicate_count=len(batch_duplicates),
           )

           # 自动去重（保留第一条）
           df = df.unique(subset=key_columns, keep="first")

       # 2. 原有的新旧重复检测逻辑...
   ```

2. **AdjFactorStore 修复**:
   ```python
   # stores/adj_factor_store.py

   def write(
       self,
       df: pl.DataFrame,
       dataset: str,
       year: int,
       on_duplicate: OnDuplicate = OnDuplicate.ERROR,
   ) -> WriteResult:
       """
       Write adjustment factor data.

       """
       key_columns = ["sid", "trade_date"]

       # ✅ 新增：检测并处理 batch 内部重复
       df = df.unique(subset=key_columns, keep="first")

       # 原有逻辑...
   ```

3. **添加测试**:
   ```python
   # tests/unit/stores/test_bars_store.py

   @pytest.mark.unit
   def test_write_auto_dedup_batch_internal():
       """验证写入时自动处理 batch 内部重复"""
       # Arrange: 创建包含重复记录的 batch
       df = pl.DataFrame({
           "sid": [1000001, 1000001, 1000002],
           "trade_date": ["2024-01-02", "2024-01-02", "2024-01-02"],
           "open": [10.0, 11.0, 20.0],  # 同一 sid+date 的不同值
           "high": [11.0, 12.0, 21.0],
           "low": [9.0, 10.0, 19.0],
           "close": [10.5, 11.5, 20.5],
           "volume": [1000, 1100, 2000],
           "amount": [10500.0, 11550.0, 41000.0],
       })

       # Act: 写入数据
       result = bars_store.write(df, dataset="stock_daily", year=2024)

       # Assert: 验证只保留了第一条记录
       written_data = bars_store.read("stock_daily", year=2024)
       assert len(written_data) == 2  # 1000001 和 1000002
       assert written_data.filter(pl.col("sid") == 1000001)["close"][0] == 10.5  # 第一条的值
   ```

**验收标准**:
- [ ] BarsStore 自动检测并处理 batch 内部重复
- [ ] AdjFactorStore 自动检测并处理 batch 内部重复
- [ ] 测试覆盖重复检测逻辑
- [ ] 日志记录去重操作
- [ ] 分支覆盖率 >= 80%

**预估时间**: 2 小时

---

### 任务 8: Medium - SqlEngine 支持 meta.* 查询

**目标**: 修复 SqlEngine 对显式 `meta.*` 查询不会自动 attach SQLite 的问题

**问题分析**:
- 当前实现：只有查询不包含 `meta.` 前缀时才自动 attach SQLite
- 用户写 `SELECT * FROM meta.security` 会失败
- 违背了元数据表自动透明的原则

**影响范围**:
- 所有直接查询元数据表的 SQL
- 降低了 SQL 的一致性和易用性

**涉及文件**:
- `packages/datahub/src/ditto_datahub/runtime/sql_engine.py` (line 282)

**实现步骤**:

1. **修改 `_needs_sqlite` 方法**:
   ```python
   # runtime/sql_engine.py

   def _needs_sqlite(self, sql: str) -> bool:
       """
       Check if SQL query needs SQLite metadata tables.

       Supports both:
       - SELECT * FROM security
       - SELECT * FROM meta.security

       """
       # 提取所有表名（去除 meta. 前缀）
       table_pattern = r'\b(?:meta\.)?(\w+)\b'
       tables = re.findall(table_pattern, sql.lower())

       # 检查是否是 SQLite 表
       return any(table in self.SQLITE_TABLES for table in tables)
   ```

2. **添加测试**:
   ```python
   # tests/unit/runtime/test_sql_engine.py

   @pytest.mark.unit
   def test_query_with_meta_prefix():
       """验证支持 meta.table 前缀查询"""
       engine = SqlEngine(data_root=tmp_path)

       # 两种写法应该等效
       result1 = engine.query("SELECT * FROM security LIMIT 1")
       result2 = engine.query("SELECT * FROM meta.security LIMIT 1")

       assert len(result1) == len(result2) == 1
       assert result1.columns == result2.columns
   ```

**验收标准**:
- [ ] 支持 `meta.table` 前缀查询
- [ ] 不带前缀的查询仍然正常工作
- [ ] 测试覆盖两种查询方式
- [ ] 文档更新说明

**预估时间**: 1 小时

---

### 任务 9: Low - schema.sql 删除已废弃表

**目标**: 从 schema.sql 中删除已废弃的 `ingestion_metadata` 表定义

**问题分析**:
- schema.sql 第 186 行仍定义了 `ingestion_metadata` 表
- 运行时实际使用 `ingestion_log` 和 `ingestion_cursor` 表
- 初始化与运行时行为不一致

**影响范围**:
- 数据库中存在未使用的表
- 可能造成混淆

**涉及文件**:
- `packages/datahub/src/ditto_datahub/runtime/schema.sql` (line 186+)

**实现步骤**:

1. **定位并删除 ingestion_metadata 表定义**:
   ```sql
   -- ❌ 删除以下已废弃的表定义：
   -- CREATE TABLE IF NOT EXISTS ingestion_metadata (
   --     dataset TEXT NOT NULL,
   --     source TEXT NOT NULL,
   --     ...
   -- );
   ```

2. **验证**: 确保没有任何代码引用 `ingestion_metadata` 表
   ```bash
   grep -r "ingestion_metadata" packages/
   ```

**验收标准**:
- [ ] schema.sql 中无 ingestion_metadata 表定义
- [ ] 代码中无引用
- [ ] 数据库初始化测试通过

**预估时间**: 0.5 小时

---

### 任务 10: Low - SQL whitelist 添加摄取表

**目标**: 在 SQL whitelist 中添加 `ingestion_log` 和 `ingestion_cursor` 表

**问题分析**:
- 当前 `ALLOWED_DATASETS` 不包含摄取相关表
- 限制了运维侧 SQL 自查能力
- 无法直接查询摄取日志和游标

**影响范围**:
- 数据库运维和调试
- 系统透明度

**涉及文件**:
- `packages/datahub/src/ditto_datahub/runtime/sql_engine.py` (line 48)

**实现步骤**:

1. **更新 ALLOWED_DATASETS**:
   ```python
   # runtime/sql_engine.py

   ALLOWED_DATASETS = frozenset(
       [
           "stock_daily",
           "etf_daily",
           "index_daily",
           "index_weight",
           "adj_factor",
           "stock_status",  # 新增
           # ✅ 新增摄取相关表
           "ingestion_log",
           "ingestion_cursor",
       ]
   )
   ```

2. **测试验证**:
   ```python
   @pytest.mark.unit
   def test_query_ingestion_log():
       """验证可以直接查询 ingestion_log"""
       engine = SqlEngine(data_root=tmp_path)

       # 应该能够查询
       result = engine.query("SELECT * FROM ingestion_log LIMIT 10")
       assert isinstance(result, pl.DataFrame)
   ```

**验收标准**:
- [ ] ALLOWED_DATASETS 包含 ingestion_log 和 ingestion_cursor
- [ ] 测试验证可以查询这些表
- [ ] 文档更新说明

**预估时间**: 0.5 小时

---

## 执行顺序建议

### 阶段 1: Critical 问题（必须优先）
- **Day 1**: 任务 2 (SID 并发安全) + 任务 5 (Context 传递) = 5h
- **Day 2**: 任务 1 (API 调用) = 3h

### 阶段 2: High 问题（核心功能）
- **Day 3**: 任务 3 (游标多源) = 5h
- **Day 4**: 任务 4 (DQ 配置) = 3h

### 阶段 3: Medium 问题（数据完整性）
- **Day 5**: 任务 7 (OnDuplicate 去重) + 任务 8 (meta.* 查询) = 3h
- **Day 5**: 任务 6 (Token 清理) = 0.5h

### 阶段 4: Low 问题（清理和文档）
- **Day 5**: 任务 9 (schema 清理) + 任务 10 (whitelist) = 1h

**总计**: 约 4.5 天（20.5 小时）

---

## 数据迁移计划

### 游标表多源迁移（任务 3）

**迁移时机**: 任务 3 实施后立即执行

**迁移脚本位置**: `packages/datahub/migrations/0002_cursor_multi_source.py`

**详细步骤**:

```sql
-- 1. 备份现有数据
CREATE TABLE ingestion_cursor_backup AS SELECT * FROM ingestion_cursor;

-- 2. 删除旧表
DROP TABLE ingestion_cursor;

-- 3. 创建新表（复合主键）
CREATE TABLE ingestion_cursor (
    dataset TEXT NOT NULL,
    source TEXT NOT NULL,
    last_success TEXT,
    last_attempted TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (dataset, source)
);

-- 4. 迁移数据（旧数据默认为 "tushare" 源）
INSERT INTO ingestion_cursor (dataset, source, last_success, last_attempted, updated_at)
SELECT dataset, 'tushare', last_success, last_attempted, updated_at
FROM ingestion_cursor_backup;

-- 5. 验证
SELECT COUNT(*) FROM ingestion_cursor;
SELECT COUNT(*) FROM ingestion_cursor_backup;

-- 6. 清理
DROP TABLE ingestion_cursor_backup;
```

**回滚计划**:
```sql
-- 如果出现问题，立即回滚
DROP TABLE ingestion_cursor;
CREATE TABLE ingestion_cursor_backup AS SELECT * FROM ingestion_cursor;
-- ... 恢复原表结构
```

---

## 验证清单

### Critical 问题验证

- [ ] **Critical 1**:
  - [ ] `hub.adj_factor` 属性存在
  - [ ] `securities.register_batch()` 可用
  - [ ] coordinator.py 无 `# type: ignore[attr-defined]`
  - [ ] 类型检查通过

- [ ] **Critical 2**:
  - [ ] SecurityMapper 委托给 SidAllocator
  - [ ] 无内存计数器
  - [ ] 并发测试通过
  - [ ] 文档更新

### High 问题验证

- [ ] **High 1**: 游标表使用复合主键，多源独立，数据迁移成功
- [ ] **High 2**: DQ 配置路径统一，初始化脚本可用
- [ ] **High 3**: BarsRepository 传递 context，FK 检查生效

### Medium 问题验证

- [ ] **Medium 1**: .env.example 删除 TUSHARE_TOKEN，文档更新
- [ ] **Medium 2**: OnDuplicate 检测 batch 内部重复，自动去重
- [ ] **Medium 3**: SqlEngine 支持 meta.* 查询

### Low 问题验证

- [ ] **Low 1**: schema.sql 删除 ingestion_metadata
- [ ] **Low 2**: SQL whitelist 包含 ingestion_log/cursor

### 整体验证

- [ ] 所有测试通过 (`pixi run -e dev pytest`)
- [ ] 分支覆盖率 >= 80% (`pytest --cov`)
- [ ] 类型检查通过 (`mypy`)
- [ ] Lint 检查通过 (`ruff check`)
- [ ] 文档更新（README.md + 设计文档）
- [ ] 代码审查通过

---

## 关键文件清单

### 必须修改的核心文件（10 个）

1. `apps/server/src/ditto_server/ingestion/services/security_mapper.py` - Critical 2
2. `packages/datahub/src/ditto_datahub/repositories/security.py` - Critical 1
3. `packages/datahub/src/ditto_datahub/hub.py` - Critical 1
4. `packages/datahub/src/ditto_datahub/stores/ingestion_cursor.py` - High 1
5. `packages/datahub/src/ditto_datahub/dq/engine.py` - High 2
6. `packages/datahub/src/ditto_datahub/repositories/bars.py` - High 3
7. `packages/datahub/src/ditto_datahub/stores/bars_store.py` - Medium 2
8. `packages/datahub/src/ditto_datahub/stores/adj_factor_store.py` - Medium 2
9. `packages/datahub/src/ditto_datahub/runtime/sql_engine.py` - Medium 3, Low 2
10. `packages/datahub/src/ditto_datahub/runtime/schema.sql` - Low 1

### 配置和文档文件（3 个）

11. `.env.example` - Medium 1
12. `packages/datahub/README.md` - High 2, Medium 1
13. `docs/design/*.md` - 多处更新

### 新建文件（2 个）

14. `packages/datahub/migrations/0002_cursor_multi_source.py` - High 1
15. `packages/datahub/scripts/init_dq_config.py` - High 2

---

## 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 数据迁移失败 | 高 | 中 | 1. 完整备份<br>2. 测试环境验证<br>3. 可回滚脚本 |
| 并发 SID 冲突 | 高 | 低 | 1. 充分的并发测试<br>2. SQLite 事务保护 |
| OnDuplicate 去重误删 | 中 | 低 | 1. 详细的单元测试<br>2. 日志记录所有去重操作 |
| FK 检查误判 | 中 | 低 | 1. 详细的单元测试<br>2. 集成测试验证 |
| 配置加载失败 | 中 | 低 | 1. Fallback 机制<br>2. 清晰的错误提示 |

---

## 注意事项

### 重构原则

1. **删除遗留代码**: 不保留兼容性代码，直接删除
2. **TDD 流程**: RED → GREEN → REFACTOR
3. **测试覆盖**: 分支覆盖率 >= 80%
4. **文档同步**: 代码修改后立即更新文档

### 并发安全

- 所有 SID 分配必须通过 SidAllocator
- 使用 SQLite 事务保证原子性
- 充分的并发测试（10 线程 x 100 次）

### 数据完整性

- OnDuplicate 模式下检测 batch 内部重复
- FK 检查必须正常工作
- 游标更新语义保持一致

---

**文档状态**: ✅ 准备就绪，包含所有 Critical + High + Medium + Low 问题
**下一步**: 用户审批后开始实施，优先执行 Critical 问题
