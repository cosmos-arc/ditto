# 架构约束规则全面检测报告

**审查日期**: 2026-01-15
**审查范围**: 全项目架构约束规则
**审查类型**: `/ditto-review --architecture`

---

## 执行摘要

本次审查对项目进行了全面的架构约束规则检测，发现了 **3 大类架构违规**，涉及 **20+ 个文件**。

### 问题统计

| 类别 | 数量 | 严重程度 |
|------|------|----------|
| Server 层跨层导入 | 6 个文件 | 🔴 P0 |
| DataHub 层职责混淆 | 12 处违规 | 🔴 P0/P1 |
| 代码重复和循环依赖 | 11 处违规 | 🔴 P0/P1 |

---

## 一、Server 层跨层导入违规（P0）

### 问题描述
Server 层（`apps/port/`）直接导入 DataHub 内部组件（Store/Runtime），违反了分层架构原则。

**依赖规则**:
```
✅ 正确: Server Flow → Server Service → DataHub Repository → DataHub Store/Runtime → Foundation
❌ 错误: Server → DataHub Store/Runtime (跨层访问)
```

### 违规文件清单

#### 1.1 严重违规（非 TYPE_CHECKING）

| 文件 | 行号 | 违规内容 | 影响 |
|------|------|----------|------|
| [security_mapper.py](apps/port/src/ditto_port/services/ingestion/security_mapper.py) | 14 | `from ditto_data.stores.security_store import SecurityStore` | 直接依赖 Store |
| [security_mapper.py](apps/port/src/ditto_port/services/ingestion/security_mapper.py) | 18 | `from ditto_data.runtime.sid_allocator import SidAllocator` | 直接依赖 Runtime |
| [metadata.py](apps/port/src/ditto_port/services/ingestion/metadata.py) | 11 | `from ditto_data.stores.ingestion_log import IngestionLogStore` | 直接依赖 Store |

#### 1.2 TYPE_CHECKING 违规

| 文件 | 行号 | 违规内容 |
|------|------|----------|
| [backfill.py](apps/port/src/ditto_port/services/ingestion/backfill.py) | 15-16 | 导入 CalendarStore, IngestionLogStore |
| [retry.py](apps/port/src/ditto_port/services/ingestion/retry.py) | 22 | 导入 IngestionLogStore |
| [coordinator.py](apps/port/src/ditto_port/services/ingestion/coordinator.py) | 25-27 | 导入 DataHub 内部模块 |

#### 1.3 测试文件违规

| 文件 | 违规内容 |
|------|----------|
| [test_coordinator_unit.py](apps/port/tests/unit/ingestion/test_coordinator_unit.py) | 直接 mock IngestionLogStore |
| [test_security_mapper_unit.py](apps/port/tests/unit/ingestion/test_security_mapper_unit.py) | 直接 mock SecurityStore |

### 修复方案

**核心原则**：Server 层所有数据访问必须通过 `DataHub` facade，不应直接导入内部组件。

#### 1. 删除 [security_mapper.py](apps/port/src/ditto_port/services/ingestion/security_mapper.py)（功能重复）
   - 该文件功能已被 `SecurityRepository` 完全覆盖
   - 使用 `hub.securities.resolve_or_create_batch()` 替代
   - 使用 `hub.securities.enrich_dataframe_with_sid()` 替代

#### 2. 重构 `MetadataManager`
```python
# 修改前
def __init__(self, log_store: IngestionLogStore | None = None) -> None:
    self._log_store = log_store

# 修改后
def __init__(self, hub: DataHub) -> None:
    self._hub = hub
```

#### 3. 重构 `BackfillManager` 和 `RetryManager`
```python
# 修改前
def __init__(
    self,
    calendar_store: "CalendarStore",
    ingestion_log_store: "IngestionLogStore",
) -> None:
    self._calendar_store = calendar_store
    self._ingestion_log_store = ingestion_log_store

# 修改后
def __init__(self, hub: DataHub) -> None:
    self._hub = hub
```

#### 4. 更新 `Coordinator` 初始化
```python
# 修改前
self._metadata_manager = MetadataManager(log_store=hub.ingestion_log)
self._security_mapper = SecurityMapper(
    security_store=hub.security_store,
    sid_allocator=hub.sid_allocator
)

# 修改后
self._metadata_manager = MetadataManager(hub=hub)
# SecurityMapper 功能由 hub.securities 提供
```

---

## 二、DataHub 层职责混淆（P0/P1）

### 问题描述
DataHub 内部各层的职责边界模糊，Store 层包含业务逻辑，Repository 层直接访问文件系统。

**分层职责定义**:

| 层级 | 职责 | 禁止 | 必须 |
|------|------|------|------|
| Store | 数据持久化 | 包含业务逻辑 | @traced 装饰器 |
| Repository | 业务封装 | 直接访问文件系统 | 通过 Store 访问 |
| Runtime | 基础设施 | 包含业务逻辑 | - |
| Source | 外部数据源 | 包含业务逻辑 | 重试、限流、监控埋点 |

### 2.1 Store 层违规：包含业务逻辑

| 文件 | 违规方法 | 问题 | 优先级 |
|------|----------|------|--------|
| [stores/security_store.py](packages/data/src/ditto_data/stores/security_store.py) | `enrich_with_symbol()` (469-493) | 数据增强和 join 逻辑 | P0 |
| [stores/security_store.py](packages/data/src/ditto_data/stores/security_store.py) | `_build_in_clause()` (21-63) | SQL 构建逻辑 | P1 |
| [stores/security_store.py](packages/data/src/ditto_data/stores/security_store.py) | `resolve_sid()` 缓存策略 (114-148) | 缓存失效策略 | P1 |
| [stores/calendar_store.py](packages/data/src/ditto_data/stores/calendar_store.py) | `_build_cache_data()` (117-174) | 复杂数据结构构建 | P1 |
| [stores/calendar_store.py](packages/data/src/ditto_data/stores/calendar_store.py) | `get_range()` 缓存管理 (343-377) | 缓存键生成/失效 | P1 |
| [stores/ingestion_log.py](packages/data/src/ditto_data/stores/ingestion_log.py) | `_row_to_log()` (80-94) | 领域对象转换 | P1 |
| [stores/ingestion_log.py](packages/data/src/ditto_data/stores/ingestion_log.py) | `get_success_rate()` (231-268) | 聚合计算逻辑 | P1 |
| [stores/pipeline_store.py](packages/data/src/ditto_data/stores/pipeline_store.py) | `_row_to_dict()` (18-42) | 业务级类型转换 | P2 |
| [stores/pipeline_store.py](packages/data/src/ditto_data/stores/pipeline_store.py) | `ALLOWED_COLUMNS` 白名单 (53-65) | 业务规则验证 | P2 |

### 2.2 Repository 层违规：直接访问文件系统

| 文件 | 违规方法 | 问题 | 优先级 |
|------|----------|------|--------|
| [repositories/bars.py](packages/data/src/ditto_data/repositories/bars.py) | `_save_to_quarantine()` (815-850) | 直接构建文件路径 | P0 |
| [repositories/bars.py](packages/data/src/ditto_data/repositories/bars.py) | 创建 reports 目录 (896-898) | 直接文件系统操作 | P1 |
| [repositories/security.py](packages/data/src/ditto_data/repositories/security.py) | Checksum 计算 (342-349) | DataFrame 转换应在 Store | P1 |

### 2.3 Runtime 层违规：包含业务逻辑

| 文件 | 违规方法 | 问题 | 优先级 |
|------|----------|------|--------|
| [runtime/pit_helper.py](packages/data/src/ditto_data/runtime/pit_helper.py) | `add_pit_filter()` (63-111) | SQL 解析和重写 | P0 |
| [runtime/pit_helper.py](packages/data/src/ditto_data/runtime/pit_helper.py) | `get_safe_trade_date()` (228-267) | PIT 业务规则 | P1 |
| [runtime/sql_engine.py](packages/data/src/ditto_data/runtime/sql_engine.py) | `_register_macros()` 复权逻辑 (130-185) | 复权计算是业务逻辑 | P0 |
| [runtime/sql_engine.py](packages/data/src/ditto_data/runtime/sql_engine.py) | `pit_query()` (396-435) | PIT 查询逻辑 | P1 |

### 2.4 Source 层违规：缺少监控埋点

| 文件 | 缺失内容 | 优先级 |
|------|----------|--------|
| [sources/tushare/client.py](packages/data/src/ditto_data/sources/tushare/client.py) | 结构化指标（M.api_calls_total, M.api_duration 等） | P2 |

### 修复方案

#### P0 修复
1. **将 `SecurityStore.enrich_with_symbol()` 移至 `SecurityRepository`**
2. **创建 `AdjustmentService`，将复权逻辑从 `SqlEngine` 移出**
3. **注入 `QuarantineStore`，消除 `BarsRepository._save_to_quarantine()` 的文件操作**

#### P1 修复
4. **将缓存策略统一到 Repository 层**
5. **Store 层返回原始数据，对象转换移至 Repository**
6. **将 PIT 逻辑移至专门的 Repository 或 Service**

---

## 三、代码重复和循环依赖（P0/P1）

### 3.1 循环依赖（TYPE_CHECKING 违规）

使用 TYPE_CHECKING 绕过真正的循环依赖是架构问题的信号。

| 文件 | 行号 | 问题 | 建议 |
|------|------|------|------|
| [repositories/adj_factor.py](packages/data/src/ditto_data/repositories/adj_factor.py) | 94-96 | 行内导入 WriteResult | 移至独立的 `types.py` |
| [repositories/security.py](packages/data/src/ditto_data/repositories/security.py) | 13-14 | TYPE_CHECKING 导入 SidAllocator | 重构分层 |
| [repositories/universe.py](packages/data/src/ditto_data/repositories/universe.py) | 18-19 | TYPE_CHECKING 导入未使用的依赖 | 删除未使用代码 |
| [runtime/sql_engine.py](packages/data/src/ditto_data/runtime/sql_engine.py) | 15-17 | Runtime 依赖 Store（违反分层） | 定义抽象接口 |
| [services/ingestion/security_mapper.py](apps/port/src/ditto_port/services/ingestion/security_mapper.py) | 17-18 | Server 依赖 Runtime | 删除此文件 |
| [services/ingestion/coordinator.py](apps/port/src/ditto_port/services/ingestion/coordinator.py) | 25-27 | Server 依赖 DataHub 内部 | 定义 Protocol 接口 |

### 3.2 代码重复

#### 严重重复：Security Mapper 功能

| 位置 | 重复内容 |
|------|----------|
| [apps/port/.../security_mapper.py](apps/port/src/ditto_port/services/ingestion/security_mapper.py) | map_or_create(), enrich_dataframe() |
| [packages/data/.../repositories/security.py](packages/data/src/ditto_data/repositories/security.py) | resolve_or_create_batch(), enrich_dataframe_with_sid() |

**问题**：Server 层重复实现了 DataHub Repository 已有功能
**建议**：删除 [security_mapper.py](apps/port/src/ditto_port/services/ingestion/security_mapper.py)，使用 `hub.securities` 接口

#### 其他重复
- Checksum 计算逻辑在多处重复
- 日期处理辅助函数应提取到 Foundation 层

### 3.3 行内导入违规（circular import avoidance）

| 文件 | 行数 | 违规内容 |
|------|------|----------|
| [repositories/adj_factor.py](packages/data/src/ditto_data/repositories/adj_factor.py) | 1 处 | 导入 WriteResult |
| [repositories/bars.py](packages/data/src/ditto_data/repositories/bars.py) | 4 处 | datetime、QuarantineStore、DQReportGenerator |
| [hub.py](packages/data/src/ditto_data/hub.py) | 1 处 | get_paths |

### 修复方案

#### P0 修复
1. **删除 [security_mapper.py](apps/port/src/ditto_port/services/ingestion/security_mapper.py)**（功能重复且架构违规）
2. **将 `WriteResult` 提取到独立的 `types.py`**
3. **重构行内导入，通过分层或模块拆解消除循环依赖**

#### P1 修复
4. **Server 层通过 DataHub Facade 访问数据，定义 Protocol 解耦**
5. **Runtime 层不应依赖 Store 层**
6. **统一 Checksum 计算位置**

---

## 四、修复优先级和时间表

### 阶段 1：紧急修复（P0）

1. **删除 [apps/port/src/ditto_port/services/ingestion/security_mapper.py](apps/port/src/ditto_port/services/ingestion/security_mapper.py)**
   - 使用 `hub.securities` 接口替代
   - 更新 `Coordinator` 和相关测试

2. **重构 Server 层组件构造函数**
   - `MetadataManager`: 接收 `hub: DataHub`
   - `BackfillManager`: 接收 `hub: DataHub`
   - `RetryManager`: 接收 `hub: DataHub`

3. **消除 DataHub 内部循环依赖**
   - 将 `WriteResult` 移至 `packages/data/src/ditto_data/types.py`
   - 重构行内导入

### 阶段 2：重要修复（P1）

4. **Store 层职责清理**
   - 将 `enrich_with_symbol()` 移至 Repository
   - 将缓存策略移至 Repository
   - Store 返回原始数据，转换移至 Repository

5. **Runtime 层职责清理**
   - 创建 `AdjustmentService` 处理复权逻辑
   - 将 PIT 逻辑移至 Repository 层

6. **Repository 层文件操作修复**
   - 注入 `QuarantineStore`

### 阶段 3：优化改进（P2）

7. **添加 Source 层监控埋点**
8. **统一 Checksum 计算**
9. **提取通用辅助函数到 Foundation**

---

## 五、验证方案

### 架构验证

1. **依赖方向检查**
   ```bash
   # 检查 Server 层不应导入 DataHub 内部
   grep -r "from ditto_data.stores" apps/port/
   grep -r "from ditto_data.runtime" apps/port/
   # 预期：无结果
   ```

2. **循环依赖检查**
   ```bash
   # 检查行内导入
   grep -r "noqa: PLC0415" packages/data/
   # 预期：结果显著减少
   ```

### 功能验证

```bash
# 运行相关测试
pixi run -e dev test apps/port/tests/unit/ingestion/
pixi run -e dev test packages/data/tests/unit/repositories/

# 类型检查
pixi run -e dev type

# 代码质量
pixi run -e dev lint
```

---

## 六、影响文件清单

### 需要修改的文件

**Server 层（apps/port/）**：
- [services/ingestion/coordinator.py](apps/port/src/ditto_port/services/ingestion/coordinator.py)
- [services/ingestion/security_mapper.py](apps/port/src/ditto_port/services/ingestion/security_mapper.py) (删除)
- [services/ingestion/metadata.py](apps/port/src/ditto_port/services/ingestion/metadata.py)
- [services/ingestion/backfill.py](apps/port/src/ditto_port/services/ingestion/backfill.py)
- [services/ingestion/retry.py](apps/port/src/ditto_port/services/ingestion/retry.py)
- [tests/unit/ingestion/test_coordinator_unit.py](apps/port/tests/unit/ingestion/test_coordinator_unit.py)
- [tests/unit/ingestion/test_security_mapper_unit.py](apps/port/tests/unit/ingestion/test_security_mapper_unit.py)

**DataHub 层（packages/data/）**：
- [src/ditto_data/types.py](packages/data/src/ditto_data/types.py) (新建)
- [repositories/bars.py](packages/data/src/ditto_data/repositories/bars.py)
- [repositories/adj_factor.py](packages/data/src/ditto_data/repositories/adj_factor.py)
- [repositories/security.py](packages/data/src/ditto_data/repositories/security.py)
- [stores/security_store.py](packages/data/src/ditto_data/stores/security_store.py)
- [stores/calendar_store.py](packages/data/src/ditto_data/stores/calendar_store.py)
- [runtime/sql_engine.py](packages/data/src/ditto_data/runtime/sql_engine.py)
- [runtime/pit_helper.py](packages/data/src/ditto_data/runtime/pit_helper.py)
- [sources/tushare/client.py](packages/data/src/ditto_data/sources/tushare/client.py)

---

## 七、结论

### 审查结论

🔴 **架构违规严重，建议立即修复**

### 主要问题

1. **Server 层跨层访问**：6 个文件直接导入 DataHub 内部组件
2. **职责混淆**：Store 层包含业务逻辑，Repository 层直接操作文件
3. **循环依赖**：多处使用 TYPE_CHECKING 和行内导入绕过真正的架构问题
4. **代码重复**：SecurityMapper 功能与 SecurityRepository 完全重复

### 建议行动

1. 立即停止在 Server 层添加新的跨层导入
2. 按优先级分阶段修复
3. 添加架构验证检测到 CI/CD
4. 更新开发文档说明正确的分层模式
