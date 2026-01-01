# Ingestion 系统重构计划（融合方案）

> **日期**: 2025-12-30
> **目标**: 重构 ingestion 任务流程，实现清晰的层级职责分离
> **关键问题**: Source 层职责过重、任务记录混乱、缺少全量回补/重试能力
> **融合思路**: Ingestion Service (业务逻辑) + Prefect (编排与状态管理)

---

## 融合架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                    Prefect Flows Layer (NEW)                    │
│  - 定时触发、依赖编排、状态可视化                                  │
│  - 体现 T0 → T1 → T2 → T3 分层语义                               │
└─────────────────────────────────────────────────────────────────┘
                              │ 调用
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Prefect Tasks Layer                          │
│  - 轻量 wrapper，只做参数传递和结果包装                           │
│  - 利用 Prefect 的重试、超时、并发控制                            │
└─────────────────────────────────────────────────────────────────┘
                              │ 调用
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Ingestion Service Layer (Core)                  │
│  - IngestionCoordinator: 单日/范围摄取                           │
│  - MetadataManager: checksum、增量判断                           │
│  - BackfillManager: 全量回补                                     │
│  - RetryManager: 重试管理                                        │
└─────────────────────────────────────────────────────────────────┘
                              │ 调用
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         DataHub                                  │
│  - Sources: 轻量无状态数据获取                                    │
│  - Stores: IngestionLogStore + CursorStore                      │
│  - Repositories: 业务逻辑                                        │
└─────────────────────────────────────────────────────────────────┘
```

## T0/T1/T2/T3 分层语义

| 层级 | 职责 | 数据集 | 调度时机 |
|------|------|--------|----------|
| T0 Meta | 元数据，所有任务的前置 | calendar, stock_basic, etf_basic | 每日 8:00-9:00 |
| T1 Incremental | 每日增量数据 | etf_daily, stock_daily, adj_factor | 交易日 18:00 |
| T2 Repair | 空洞扫描 + 回填 | (扫描所有数据集) | 每日凌晨 2:00 |
| T3 Quality | 数据质量检查 | DQC 检查 | T1 完成后 |

---

## 一、当前问题分析

### 1.1 Source 层职责过重（不符合期望）

**问题**：
- `DataSource.ingest_date()` 在 Source 层实现了增量逻辑、checksum 计算、交易日验证
- `fetch_etf_daily_incremental()` 已废弃但仍在使用
- Source 层不再是无状态的纯数据获取层

**用户期望**：
- Source 层应该轻量、无状态
- 只负责从外部 API 获取原始数据并转换为标准 schema
- 增量逻辑应该在 Ingestion 层处理

### 1.2 任务记录混乱

**三套系统并存**：
- `IngestionMetadataStore` - 已废弃但仍被 Task 层使用
- `IngestionLogStore` - 新系统，事件日志
- `IngestionCursorStore` - 新系统，游标

**当前 Task 层仍在使用**：
```python
# apps/server/ingestion/tasks/bars.py:99-100
metadata_store = hub.ingestion_metadata_store
metadata = metadata_store.get_metadata("etf_daily", source)
```

### 1.3 增量模式不统一

- 旧的 `IncrementalMode` (QUICK/PRECISE) + `fetch_etf_daily_incremental()`
- 新的 `ingest_date()` 接口
- 两套系统并存，造成混乱

### 1.4 缺少全量回补和重试能力

- 只有日增量摄取
- 没有专门的全量回补流程
- 没有全量重试任务的支持
- `get_failed_dates()` 只支持失败重试

---

## 二、重构目标

### 2.1 层级职责清晰

参见上方的「融合架构概览」

### 2.2 配置驱动设计

**核心思想**：`DATASET_REGISTRY` 作为单一配置源

```python
# apps/server/src/ditto_server/ingestion/config/datasets.py

class Dataset(str, Enum):
    """数据集枚举"""
    # T0: Meta
    CALENDAR = "calendar"
    STOCK_BASIC = "stock_basic"
    ETF_BASIC = "etf_basic"
    # T1: Daily
    ETF_DAILY = "etf_daily"
    STOCK_DAILY = "stock_daily"
    ADJ_FACTOR = "adj_factor"
    # ...

class DatasetConfig(BaseModel):
    """数据集配置"""
    dataset: Dataset
    tier: TaskTier
    description: str
    update_frequency: str
    typical_available_time: time
    priority: int
    depends_on: list[Dataset]
    retry_limit: int
    timeout_seconds: int
    quality_checks_enabled: bool
    critical_fields: list[str]

# 数据集注册表
DATASET_REGISTRY: dict[Dataset, DatasetConfig] = {
    Dataset.CALENDAR: DatasetConfig(
        tier=TaskTier.T0_META,
        priority=100,
        depends_on=[],
        # ...
    ),
    Dataset.ETF_DAILY: DatasetConfig(
        tier=TaskTier.T1_INCREMENTAL,
        priority=20,
        depends_on=[Dataset.ETF_BASIC],
        # ...
    ),
    # ...
}
```

**好处**：
- Task 工厂函数从注册表读取配置
- Flow 可以动态构建依赖图
- 配置变更不需要改代码

### 2.3 Source 层轻量化

- 移除 `DataSource.ingest_date()` 方法
- 移除 `fetch_etf_daily_incremental()` 方法
- Source 只保留纯数据获取方法：`fetch_xxx()`
- 增量逻辑完全移到 Ingestion Service

### 2.4 统一任务记录

- 完全迁移到 `IngestionLogStore` + `IngestionCursorStore`
- 废弃 `IngestionMetadataStore`
- 废弃 `IncrementalMode` 枚举

### 2.5 支持全量回补和重试

- 新增 `BackfillManager` 支持全量回补
- 新增 `RetryManager` 支持全量重试
- 支持按日期范围回补
- 支持按失败日期重试

---

## 三、重构方案

### 3.1 新增 Ingestion Service 层

**目录结构**：
```
apps/server/src/ditto_server/ingestion/services/
├── __init__.py
├── coordinator.py      # IngestionCoordinator - 统一摄取协调器
├── metadata.py         # MetadataManager - 元数据管理
├── backfill.py         # BackfillManager - 全量回补管理器
└── retry.py            # RetryManager - 重试管理器
```

#### 3.1.1 IngestionCoordinator

**职责**：
- 统一的摄取入口
- 调用 Source 获取数据
- 调用 Metadata 管理增量逻辑
- 调用 DataHub 写入数据
- 记录摄取日志

**接口设计**：
```python
class IngestionCoordinator:
    def ingest_date(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> IngestionResult:
        """摄取单个交易日数据"""

    def ingest_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> list[IngestionResult]:
        """摄取日期范围数据"""
```

#### 3.1.2 MetadataManager

**职责**：
- 计算 checksum
- 比较数据是否变化
- 判断是否需要跳过

**接口设计**：
```python
class MetadataManager:
    def compute_checksum(self, df: pl.DataFrame) -> str:
        """计算数据 checksum"""

    def should_skip(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> tuple[bool, str | None]:
        """判断是否跳过"""

    def compare_data(
        self,
        new_df: pl.DataFrame,
        existing_log: IngestionLog,
    ) -> bool:
        """比较新旧数据是否相同"""
```

#### 3.1.3 BackfillManager

**职责**：
- 全量回补任务管理
- 支持按日期范围回补
- 支持并行回补

**接口设计**：
```python
class BackfillManager:
    def backfill_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        parallel: int = 1,
    ) -> BackfillResult:
        """全量回补指定日期范围"""

    def backfill_missing(
        self,
        dataset: str,
        parallel: int = 1,
    ) -> BackfillResult:
        """回补缺失的交易日"""
```

#### 3.1.4 RetryManager

**职责**：
- 重试失败任务
- 支持按最大重试次数筛选

**接口设计**：
```python
class RetryManager:
    def retry_failed(
        self,
        dataset: str,
        max_attempts: int = 3,
        limit: int = 10,
    ) -> RetryResult:
        """重试失败的任务"""
```

### 3.2 Prefect 集成

#### 3.2.1 数据集注册表 (`config/datasets.py`)

**文件**: `apps/server/src/ditto_server/ingestion/config/datasets.py`

**职责**：
- 定义 `Dataset` 枚举
- 定义 `DatasetConfig` 配置模型
- 维护 `DATASET_REGISTRY` 注册表
- 提供 `get_datasets_by_tier()` 等查询函数

#### 3.2.2 Prefect Tasks (`tasks/`)

**关键设计**：
- Task 只是轻量 wrapper，真正逻辑在 IngestionCoordinator
- 使用工厂函数 `create_ingest_task()` 为每个数据集创建 Task
- 从 `DATASET_REGISTRY` 读取重试/超时配置

**示例** (`tasks/t1_bars.py`):
```python
def create_ingest_task(dataset: Dataset):
    config = DATASET_REGISTRY[dataset]

    @task(
        name=f"ingest_{dataset.value}",
        retries=config.retry_limit,
        timeout_seconds=config.timeout_seconds,
    )
    def ingest_task(trade_date, source, data_root, force) -> dict:
        hub = DataHub(data_root=data_root)
        try:
            coordinator = IngestionCoordinator(hub, source)
            result = coordinator.ingest_date(dataset.value, trade_date, force)
            return result.to_dict()
        finally:
            hub.close()

    return ingest_task
```

#### 3.2.3 每日增量 Flow (`flows/daily.py`)

**职责**：
- 实现 T0 → T1 → T3 的依赖编排
- 处理非交易日跳过逻辑
- 汇总所有数据集的结果
- 触发 DQC 检查

#### 3.2.4 回补 Flow (`flows/backfill.py`)

**职责**：
- 调用 `BackfillManager` 执行全量回补
- 将日期范围分块，利用 Prefect 的进度可视化
- 失败隔离（单块失败不影响其他）
- 支持断点续传

#### 3.2.5 修补 Flow (`flows/repair.py`)

**职责**：
- `repair_holes_flow`: 扫描空洞并回补
- `retry_failed_flow`: 调用 `RetryManager` 重试失败任务
- `daily_repair_flow`: 每日凌晨运行，先重试后扫描空洞

#### 3.2.6 部署配置 (`deploy.py`)

**部署的 Flows**：
1. `daily-ingestion`: 交易日 18:00
2. `daily-repair`: 每日凌晨 2:00
3. `retry-failed`: 每 4 小时检查一次
4. `backfill`: 手动触发
5. `quality-check`: 手动触发

### 3.3 Source 层简化

**移除方法**：
```python
# 移除
DataSource.ingest_date()
DataSource.fetch_etf_daily_incremental()

# 保留纯数据获取方法
DataSource.fetch_calendar()
DataSource.fetch_etf_basic()
DataSource.fetch_etf_daily()
DataSource.fetch_stock_basic()
DataSource.fetch_stock_daily()
DataSource.fetch_adj_factor()
DataSource.fetch_fund_adj()
```

### 3.4 废弃旧组件

**标记废弃**：
- `IngestionMetadataStore` - 添加 `DeprecationWarning`
- `IncrementalMode` - 已废弃
- `IngestionMetadata` - 已废弃
- `fetch_etf_daily_incremental()` - 已废弃
- `ingest_date()` (Source 层) - 移除

---

## 四、实施步骤（融合版）

### Phase 1: Ingestion Service 层（核心）

- [x] **Task 1.1**: 创建 Ingestion Service 目录结构
- [x] **Task 1.2**: 实现 MetadataManager
- [x] **Task 1.3**: 实现 IngestionCoordinator

### Phase 2: 全量回补和重试能力

- [x] **Task 2.1**: 实现 BackfillManager
- [x] **Task 2.2**: 实现 RetryManager

### Phase 3: Prefect 集成（新增）

- [x] **Task 3.1**: 创建 config/datasets.py (数据集注册表)
- [x] **Task 3.2**: 创建 Tasks 层 (轻量 wrapper)
- [x] **Task 3.3**: 创建 flows/daily.py (每日增量 Flow)
- [ ] **Task 3.4**: 创建 flows/backfill.py (全量回补 Flow)
- [ ] **Task 3.5**: 创建 flows/repair.py (修补 Flow)
- [ ] **Task 3.6**: 创建 deploy.py (部署脚本)

### Phase 4: Source 层简化

- [ ] **Task 4.1**: 移除 DataSource.ingest_date()
- [ ] **Task 4.2**: 移除 TushareSource.ingest_date()
- [ ] **Task 4.3**: 废弃 fetch_etf_daily_incremental()

### Phase 5: 清理和文档

- [ ] **Task 5.1**: 标记废弃组件
- [ ] **Task 5.2**: 更新测试
- [ ] **Task 5.3**: 更新文档

---

## 五、关键文件路径

### 新增文件 - Ingestion Service
- `apps/server/src/ditto_server/ingestion/services/__init__.py`
- `apps/server/src/ditto_server/ingestion/services/metadata.py`
- `apps/server/src/ditto_server/ingestion/services/coordinator.py`
- `apps/server/src/ditto_server/ingestion/services/backfill.py`
- `apps/server/src/ditto_server/ingestion/services/retry.py`

### 新增文件 - Config
- `apps/server/src/ditto_server/ingestion/config/__init__.py`
- `apps/server/src/ditto_server/ingestion/config/datasets.py`

### 新增文件 - Tasks
- `apps/server/src/ditto_server/ingestion/tasks/__init__.py`
- `apps/server/src/ditto_server/ingestion/tasks/t0_meta.py`
- `apps/server/src/ditto_server/ingestion/tasks/t1_bars.py`
- `apps/server/src/ditto_server/ingestion/tasks/t1_adj_factor.py`

### 新增文件 - Flows
- `apps/server/src/ditto_server/ingestion/flows/daily.py`
- `apps/server/src/ditto_server/ingestion/flows/backfill.py`
- `apps/server/src/ditto_server/ingestion/flows/repair.py`

### 新增文件 - Deploy
- `apps/server/deploy.py`

### 修改文件 - Source 层
- `packages/datahub/src/ditto_datahub/sources/base.py`
- `packages/datahub/src/ditto_datahub/sources/tushare/source.py`
- `packages/datahub/src/ditto_datahub/sources/metadata.py`

---

## 六、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Task 层改动较大 | 高 | 保持新旧并存，渐进式迁移 |
| 测试覆盖不足 | 中 | 先编写测试，再重构代码 |
| Source 层破坏性变更 | 中 | 先废弃，后移除，保留过渡期 |
| 性能回归 | 低 | 增量逻辑保持一致，性能不变 |

---

## 七、验收标准

### 功能验收
- [ ] 支持单日增量摄取
- [ ] 支持日期范围全量回补
- [ ] 支持失败任务重试
- [ ] Source 层只负责数据获取
- [ ] 任务记录使用 IngestionLogStore + CursorStore

### 质量验收
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 集成测试通过
- [ ] 代码审查通过
- [ ] 文档更新完整

### 性能验收
- [ ] 单日摄取性能不低于重构前
- [ ] 内存使用无明显增加
