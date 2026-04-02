# ditto-port ingestion 服务分层架构重构设计

## 1. 问题分析

### 1.1 当前架构违例

**security_mapper.py 的定位问题：**

| 问题 | 当前实现 | 应该归属 |
|------|---------|---------|
| 证券映射逻辑 (src_code → sid) | Server 层 | DataHub Accessor |
| 新证券注册 | Server 层 | DataHub Accessor |
| SID 分配协调 | Server 层 | DataHub Accessor |
| DataFrame 丰富 (enrich_dataframe) | Server 层 | DataHub Accessor |

**代码重复：**
- `SecuritiesAccessor.register_batch()` 已实现批量注册逻辑
- `SecurityMapper._register_security()` 重复实现相同逻辑
- `IngestionCoordinator._write_stock_basic()` 调用 Accessor
- `IngestionCoordinator._write_etf_basic()` 调用 Accessor

### 1.2 当前 ingestion services 职责分析

| 组件 | 当前职责 | 是否合适 |
|------|---------|---------|
| `security_mapper.py` | 证券映射 + 注册 + SID 分配 | ❌ 越界 |
| `coordinator.py` | 摄取流程编排 | ✅ 合适 |
| `metadata.py` | 增量摄取逻辑（游标/跳过判断） | ✅ 合适 |
| `retry.py` | 失败任务重试 | ✅ 合适 |
| `backfill.py` | 历史数据回补 | ✅ 合适 |
| `result_utils.py` | 结果统计工具 | ✅ 合适 |

### 1.3 依赖关系图（当前）

```
ditto-port/services/ingestion/
├── security_mapper.py  ─────┐
│   ↓                       │
│   SecurityStore (datahub)  │ ← 跨层依赖
│   SidAllocator (datahub)   │
│                            │
├── coordinator.py           │
│   ↓                        │
│   SecurityMapper ──────────┘
│   DataSource (datahub)
│   MetadataManager
│
├── metadata.py
│   ↓
│   IngestionLogStore (datahub)
│
├── retry.py
│   ↓
│   IngestionCoordinator
│   IngestionLogStore
│
└── backfill.py
    ↓
    IngestionCoordinator
    CalendarStore (datahub)
    IngestionLogStore
```

## 2. 架构分层规范

### 2.1 理想分层职责

| 层级 | 职责 | 典型组件 |
|------|------|----------|
| **DataHub Store** | 数据持久化、基础查询 | SecurityStore, BarsStore |
| **DataHub Accessor** | 业务封装、领域接口 | SecuritiesAccessor, BarsAccessor |
| **Server Service** | 流程编排、任务协调 | IngestionCoordinator |
| **Server Flow** | 应用层用例组合 | DailyFlow, BackfillFlow |

### 2.2 依赖方向规则

```
Server Flow (应用层)
    ↓
Server Service (服务层)
    ↓
DataHub Accessor (领域层)
    ↓
DataHub Store (存储层)
    ↓
基础设施 (Foundation)
```

**禁止：** 跨层直接访问 Store、跨层反向依赖

## 3. 重构方案

### 3.1 方案 A：彻底下沉（推荐）

**核心思想：** 将 `security_mapper.py` 的核心逻辑完全下沉到 DataHub Accessor 层

**变更内容：**

1. **扩展 `SecuritiesAccessor`** (datahub):
   - 添加 `resolve_or_create_batch()` 方法
   - 添加 `enrich_dataframe_with_sid()` 方法
   - 内部协调 `SecurityStore` 和 `SidAllocator`

2. **删除 `security_mapper.py`** (port):
   - 移除文件
   - 所有调用方改为使用 `SecuritiesAccessor`

3. **更新 `IngestionCoordinator`**:
   - 移除 `SecurityMapper` 依赖
   - 直接调用 `hub.securities.resolve_or_create_batch()`
   - 直接调用 `hub.securities.enrich_dataframe_with_sid()`

**优点：**
- ✅ 严格的分层架构
- ✅ 消除代码重复
- ✅ 数据访问逻辑集中在 DataHub
- ✅ 便于其他应用复用

**缺点：**
- ⚠️ 需要修改 datahub 公共 API
- ⚠️ Accessor 层略重（包含 DataFrame 处理）

### 3.2 方案 B：轻量下沉（折中）

**核心思想：** 只将映射逻辑下沉，保留 Server 层的协调封装

**变更内容：**

1. **扩展 `SecuritiesAccessor`** (datahub):
   - 添加 `resolve_or_create_batch()` 方法
   - 返回简单的 `dict[str, int]` 映射

2. **简化 `security_mapper.py`** (port):
   - 移除 `_register_security()`、`_allocate_sid()`
   - 只保留 `enrich_dataframe()` 作为 DataFrame 处理的便利方法
   - 内部调用 `hub.securities.resolve_or_create_batch()`

3. **更新 `IngestionCoordinator`**:
   - 保持现有接口不变
   - 内部实现委托给 Accessor

**优点：**
- ✅ 数据访问逻辑下沉到 DataHub
- ✅ 保持 Server 层 API 稳定
- ✅ DataFrame 处理仍在 Server 层（职责清晰）

**缺点：**
- ⚠️ 仍然有一层薄封装
- ⚠️ `security_mapper.py` 存在但职责简化

### 3.3 方案 C：维持现状 + 文档说明

**核心思想：** 保持现有架构，通过文档明确职责边界

**变更内容：**
1. 更新架构文档，说明 `security_mapper.py` 作为 "DataHub Client Helper" 的定位
2. 添加明确的依赖说明和演进计划

**优点：**
- ✅ 无需代码变更
- ✅ 避免重构风险

**缺点：**
- ❌ 架构违例持续存在
- ❌ 代码重复无法消除
- ❌ 违反分层原则

## 4. 推荐方案：方案 A（彻底下沉）

### 4.1 设计理由

1. **职责清晰：** 证券映射和注册是数据访问层的核心业务逻辑
2. **消除重复：** `SecuritiesAccessor.register_batch()` 已有类似实现，统一后消除重复
3. **可复用性：** 其他应用（如 Web）可直接使用 Accessor 能力
4. **架构一致性：** 符合分层架构原则

### 4.2 实现计划

**Phase 1: 扩展 SecuritiesAccessor**
```python
# packages/data/src/ditto_data/accessors/securities.py

class SecuritiesAccessor:
    def resolve_or_create_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf"],
        src_code_col: str = "ts_code",
    ) -> dict[str, int]:
        """批量解析 src_code，不存在则自动创建证券。

        返回: {src_code: sid} 映射字典
        """
        ...

    def enrich_dataframe_with_sid(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf"],
        src_code_col: str = "ts_code",
    ) -> pl.DataFrame:
        """为 DataFrame 添加 sid 和 source 列。

        不存在的证券会自动创建。
        """
        ...
```

**Phase 2: 删除 security_mapper.py**
```bash
rm apps/port/src/ditto_port/services/ingestion/security_mapper.py
```

**Phase 3: 更新 IngestionCoordinator**
```python
# apps/port/src/ditto_port/services/ingestion/coordinator.py

class IngestionCoordinator:
    def __init__(self, hub: DataHub, source: DataSource, ...):
        self._hub = hub
        # 移除 security_mapper

    def _write_data(self, dataset, df, trade_date, on_duplicate):
        if dataset in ("etf_daily", "stock_daily"):
            # 直接使用 Accessor
            df = self._hub.securities.enrich_dataframe_with_sid(
                df,
                source=self._source_name,
                asset_class="etf" if dataset == "etf_daily" else "stock",
                src_code_col="src_code",
            )
            ...
```

### 4.3 其他 ingestion services 分析

| 组件 | 职责 | 是否需要调整 |
|------|------|-------------|
| `coordinator.py` | 流程编排 | ✅ 调整为使用 Accessor |
| `metadata.py` | 增量逻辑 | ❌ 保持现状 |
| `retry.py` | 重试逻辑 | ❌ 保持现状 |
| `backfill.py` | 回补逻辑 | ❌ 保持现状 |
| `result_utils.py` | 工具函数 | ❌ 保持现状 |

## 5. 实施计划

### Phase 1: 架构约束规则（已完成）

**任务 1.1: 更新 core.md 添加架构约束规则** ✅

已在 `.claude/rules/core.md` 中添加新的"架构分层约束"章节：
- 分层职责定义
- 依赖方向规则
- 跨层检测规则
- 代码重复检测

**任务 1.2: 更新 ditto-review.md 添加架构检查** ✅

已在 `.claude/commands/ditto-review.md` 中添加"架构"审查维度：
- 并行审查从 5 个 Task 扩展到 6 个 Task
- 架构检查项：导入语句、职责、代码重复

### Phase 2: 代码重构（已完成）

**任务 2.1: 扩展 SecuritiesAccessor** ✅

添加新方法到 `packages/data/src/ditto_data/accessors/securities.py`：
- `resolve_or_create_batch()`: 批量解析 src_code，不存在则创建
- `enrich_dataframe_with_sid()`: 为 DataFrame 添加 sid 列

**任务 2.2: 更新 IngestionCoordinator** ✅

修改 `apps/port/src/ditto_port/services/ingestion/coordinator.py`：
- 移除 `SecurityMapper` 依赖
- 使用 `hub.securities.enrich_dataframe_with_sid()`

**任务 2.3: 删除 security_mapper.py** ✅

移除 `apps/port/src/ditto_port/services/ingestion/security_mapper.py`

**任务 2.4: 更新测试和文档** ✅

- 添加新方法的单元测试（已在 test_security_repository_unit.py）
- 更新 coordinator 测试（使用新的 mock 方式）

## 6. 验证标准

- [x] 所有测试通过（1346 个单元测试通过）
- [x] 不再存在跨层依赖（移除了 Server → Store/Runtime 的依赖）
- [x] 代码重复已消除（统一使用 SecuritiesAccessor API）
- [x] 架构图更新完成（见下方新架构图）

### 重构后的依赖关系图

```
ditto-port/services/ingestion/
├── coordinator.py (已更新)
│   ↓
│   Securities Accessor (datahub) ✅ 正确的分层依赖
│   DataSource (datahub)
│   MetadataManager
│
├── metadata.py
│   ↓
│   IngestionLogStore (datahub)
│
├── retry.py
│   ↓
│   IngestionCoordinator
│   IngestionLogStore
│
└── backfill.py
    ↓
    IngestionCoordinator
    CalendarStore (datahub)
    IngestionLogStore

packages/data/accessors/
└── securities.py (已扩展)
    ├── resolve_or_create_batch()  ✅ 新增方法
    └── enrich_dataframe_with_sid()  ✅ 新增方法
```

## 7. 架构审核规则（预防机制）

### 7.1 分层职责检查清单

**在添加新组件时，必须确认：**

| 检查项 | DataHub | Server |
|--------|---------|-------|
| 是否依赖外部数据源？ | ✅ Source 层 | ❌ 应委托给 DataHub |
| 是否直接访问存储文件？ | ✅ Store 层 | ❌ 应通过 Accessor |
| 是否包含数据映射逻辑？ | ✅ Accessor 层 | ❌ 应下沉到 DataHub |
| 是否包含业务规则验证？ | ✅ Accessor 层 | ❌ 应下沉到 DataHub |
| 是否是流程编排？ | ❌ 应在 Server | ✅ Service/Flow 层 |
| 是否是应用层用例？ | ❌ 应在 Server | ✅ Flow 层 |

### 7.2 依赖方向规则

**允许的依赖：**
```
Server Flow → Server Service → DataHub Accessor → DataHub Store → Foundation
```

**禁止的依赖：**
```
❌ Server → DataHub Store (跨层访问)
❌ Server → DataHub Runtime (跨层访问)
❌ DataHub → Server (反向依赖)
❌ 同层组件间的循环依赖
```

### 7.3 代码审查检查点

**在 PR 审查时检查：**

1. **导入语句检查**
   ```python
   # ❌ Server 层不应直接导入 Store
   from ditto_data.stores.security_store import SecurityStore

   # ✅ 应该使用 Accessor
   from ditto_data.accessors.securities import SecuritiesAccessor
   ```

2. **职责检查**
   - 这个类是处理"怎么做"还是"做什么"？
   - 数据访问逻辑应该在 DataHub
   - 流程编排逻辑应该在 Server

3. **重复代码检查**
   - 是否与 DataHub 中已有逻辑重复？
   - 检查 `accessors/` 目录下的类似实现

4. **跨层调用检查**
   - Server 层是否直接调用 `xxx_store`？
   - Server 层是否直接使用 `sid_allocator`、`sqlite_pool`？

### 7.4 架构决策记录（ADR）

创建新的 ADR 文档记录此次重构：

```markdown
# ADR: ingestion 服务分层架构重构

## 状态
已采纳

## 上下文
ditto-port 的 security_mapper.py 承担了证券映射和注册职责，
这些职责属于 DataHub Accessor 层，导致：
1. 架构分层不清晰
2. 代码重复（SecuritiesAccessor.register_batch）
3. 跨层依赖（Server → Store/Runtime）

## 决策
将证券映射和注册逻辑完全下沉到 DataHub Accessor 层：
1. 扩展 SecuritiesAccessor 添加 resolve_or_create_batch()
2. 删除 security_mapper.py
3. 更新 IngestionCoordinator 使用 Accessor API

## 后果
- 正面：清晰的分层架构、消除重复、更好的可复用性
- 负面：Accessor 层略重（包含 DataFrame 处理）
```

## 8. 后续架构演进方向

### 8.1 短期（本次重构）
- [x] Phase 1: 架构约束规则
- [x] Phase 2: 代码重构

### 8.2 中期（架构加固）
- [ ] 添加导入限制 Linter 规则
- [ ] 创建架构测试套件
- [ ] 编写架构审查指南

### 8.3 长期（架构治理）
- [ ] 建立架构委员会审查机制
- [ ] 定期架构健康度检查
- [ ] 自动化依赖分析工具链
