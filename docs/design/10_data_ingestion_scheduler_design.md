> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Ditto 数据摄取调度设计

**版本：v2.0**

**日期：2025-12-30**

**变更记录**：
- v2.0 (2025-12-30): 重构为融合架构，引入 Ingestion Service 层，T0/T1/T2/T3 分层语义
- v1.0 (2025-12-26): 初始版本

---

## 1. 设计背景

### 1.1 需求

基于 Ditto 数据层设计（02_data_design.md），规划 Port 侧数据摄取定时任务：

- 支持定时自动执行
- 支持手动触发（CLI/API）
- 支持失败重试
- 支持任务依赖编排
- 可观测（执行历史、日志、状态）

### 1.2 技术选型

**选择 Prefect 3 本地 Server 模式**

| 维度 | APScheduler | Prefect |
|------|-------------|---------|
| 可观测性 | ⭐⭐ 需自建 | ⭐⭐⭐⭐⭐ 内置 Dashboard |
| 手动触发 | ⭐⭐ 需开发 API | ⭐⭐⭐⭐⭐ CLI/UI/API |
| 重试机制 | ⭐⭐ 手动实现 | ⭐⭐⭐⭐⭐ 声明式指数退避 |
| DAG 支持 | ⭐ 无 | ⭐⭐⭐⭐⭐ 原生 |
| 历史记录 | ⭐⭐ 需自建 | ⭐⭐⭐⭐⭐ 内置 |

---

## 2. 架构设计（v2.0 融合架构）

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Port 层                                        │
│                                                                              │
│   ┌─────────────────────────────┐   ┌─────────────────────────────────────┐ │
│   │   CLI 入口 (cli/)           │   │   Jobs 入口 (jobs/)                 │ │
│   │  - stock daily             │   │  - Prefect Flows                    │ │
│   │  - stock backfill          │   │  - Prefect Tasks                    │ │
│   │  - etf daily               │   │                                    │ │
│   └─────────────┬───────────────┘   └─────────────────┬───────────────────┘ │
│                 │                                    │                        │
│                 └────────────────┬───────────────────┘                        │
│                                  ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Services 层（services/ingestion/）                │   │
│   │  - IngestionCoordinator  (摄取协调器)                               │   │
│   │  - BackfillManager     (回补管理器)                                  │   │
│   │  - RetryManager        (重试管理器)                                  │   │
│   │  - MetadataManager     (元数据管理器)                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   │                                                                      │   │
│   │   ┌──────────────────────────────────────────────────────────────┐  │   │
│   │   │  T0 → T1 → T2 → T3 分层语义                                    │  │   │
│   │   │                                                               │  │   │
│   │   │  daily_ingestion_flow    (T0→T1→T3)                          │  │   │
│   │   │  backfill_flow          (手动回补)                            │  │   │
│   │   │  repair_holes_flow      (T2 空洞修补)                         │  │   │
│   │   │  retry_failed_flow      (T2 失败重试)                         │  │   │
│   │   │  quality_check_flow     (T3 DQC)                              │  │   │
│   │   └──────────────────────────────────────────────────────────────┘  │   │
│   │                                    │                                 │   │
│   │                                    │ 调用                            │   │
│   │                                    ▼                                 │   │
│   │   ┌──────────────────────────────────────────────────────────────┐  │   │
│   │   │              Prefect Tasks（轻量 wrapper）                    │  │   │
│   │   │                                                               │  │   │
│   │   │   create_ingest_task() → 从 DATASET_REGISTRY 读取配置        │  │   │
│   │   │                         → 调用 IngestionCoordinator           │  │   │
│   │   └──────────────────────────────────────────────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    │ 调用                                    │
│                                    ▼                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DataHub 层                                        │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Sources（轻量无状态）                                               │   │
│   │  - fetch_calendar(), fetch_etf_daily(), fetch_stock_daily() ...    │   │
│   │  - 只负责从外部 API 获取原始数据并转换为标准 schema                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Stores（任务记录）                                                 │   │
│   │  - IngestionLogStore: 事件日志（SUCCESS/FAIL）                       │   │
│   │  - IngestionCursorStore: 进度游标（last_success/last_attempted）     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   hub.bars.write()                 ──→  写入存储（自动触发 DQ L1+L2）       │
│   DQEngine.check_statistical()     ──→  L3 批量检查                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 T0/T1/T2/T3 分层语义

| 层级 | 职责 | 数据集 | 调度时机 |
|------|------|--------|----------|
| **T0 Meta** | 元数据，所有任务的前置 | calendar, stock_basic, etf_basic | 每日 8:00-9:00 |
| **T1 Incremental** | 每日增量数据 | etf_daily, stock_daily, adj_factor | 交易日 18:00 |
| **T2 Repair** | 空洞扫描 + 回填 | (扫描所有数据集) | 每日凌晨 2:00 |
| **T3 Quality** | 数据质量检查 | DQC 检查 | T1 完成后 |

**设计理念**：
- T0 任务优先级最高，必须先完成
- T1 任务并行执行，按优先级排序
- T2 任务独立运行，用于修补异常
- T3 任务在 T1 完成后触发，进行质量检查
### 2.2. 数据流示意

```
                     Server (Prefect)                    DataHub
                          │
     ┌────────────────────┼────────────────────┐
     │                    │                    │
     ▼                    ▼                    ▼
┌─────────┐        ┌─────────┐         ┌─────────┐
│ daily   │        │ backfill│         │heartbeat│
│ _ingest │        │  _flow  │         │  _flow  │
│  _flow  │        │         │         │         │
└────┬────┘        └────┬────┘         └─────────┘
     │                  │
     ├──────────────────┤
     ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Tasks                                    │
│  ingest_calendar │ ingest_bars │ ingest_adj │ dq_batch_check   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            │ 调用
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                         DataHub                                  │
│                                                                  │
│  hub.sources.tushare.fetch_xxx()  ──→  从外部获取数据            │
│                                                                  │
│  hub.securities.resolve_sids()    ──→  SID 解析                 │
│                                                                  │
│  hub.bars.write()                 ──→  写入存储                 │
│       │                                 │                        │
│       └── DQEngine.check(L1+L2) ────────┘                       │
│           自动执行，L1 失败阻断写入                               │
│                                                                  │
│  DQEngine.check_statistical(L3)   ──→  批量统计检查             │
│       由 Server dq_batch_check Task 触发                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### 2.3 配置驱动设计（新增）

**核心思想**：`DATASET_REGISTRY` 作为单一配置源

```python
# interfaces/src/ditto_interfaces/ingestion/config/datasets.py

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

class TaskTier(str, Enum):
    """任务层级"""
    T0_META = "t0_meta"
    T1_INCREMENTAL = "t1_incr"
    T2_REPAIR = "t2_repair"
    T3_QUALITY = "t3_quality"

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
    ),
    Dataset.ETF_DAILY: DatasetConfig(
        tier=TaskTier.T1_INCREMENTAL,
        priority=20,
        depends_on=[Dataset.ETF_BASIC],
    ),
    # ...
}
```

**好处**：
- Task 工厂函数从注册表读取配置
- Flow 可以动态构建依赖图
- 配置变更不需要改代码

### 2.4 职责边界（更新）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Server (interfaces/)                                  │
│                                                                              │
│   职责：应用层编排                                                           │
│   - Prefect Flows：任务编排、调度、依赖管理                                   │
│   - Prefect Tasks：轻量 wrapper，参数传递和结果包装                          │
│   - Ingestion Service：业务逻辑（增量、回补、重试）                          │
│   - API：手动触发、状态查询                                                  │
│                                                                              │
│   不包含：                                                                   │
│   - 数据获取逻辑（Source 层负责）                                            │
│   - DQ 规则定义（在 DataHub）                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 调用
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DataHub (packages/ditto-data)                            │
│                                                                              │
│   职责：统一数据入口                                                         │
│   - Sources：轻量无状态数据源适配（只获取数据）                              │
│   - Stores：本地存储读写（Parquet/SQLite）                                   │
│   - IngestionLogStore/CursorStore：任务记录                                 │
│   - Repositories：业务聚合，PIT/复权等语义                                   │
│   - DQ Engine：统一的数据质量检查（L1/L2/L3 规则）                           │
└─────────────────────────────────────────────────────────────────────────────┘
```


| 层 | 职责 | 不做 |
|---|---|---|
| **Server/Flows** | 任务编排、依赖管理、调度 | 业务逻辑、数据获取 |
| **Server/Tasks** | 轻量 wrapper，结果包装 | 业务逻辑 |
| **Server/Services** | 增量、回补、重试业务逻辑 | 数据获取（调用 Source） |
| **DataHub/Sources** | 轻量无状态数据获取 | 增量逻辑、存储逻辑 |
| **DataHub/Stores** | 任务记录、数据存储 | 调度逻辑 |
| **DataHub/DQ** | DQ 规则定义和执行 | 调度逻辑 |

---

## 3. 任务记录存储（IngestionLogStore + CursorStore）

### 3.1 设计理念

**新旧对比**：

| 特性 | 旧系统 (IngestionMetadataStore) | 新系统 (Log + Cursor) |
|------|-------------------------------|---------------------|
| 存储粒度 | 数据集级别 | 交易日级别 |
| 增量模式 | QUICK/PRECISE 统一 | 自然支持 |
| 重试支持 | 不支持 | 支持 (attempts 计数) |
| 失败记录 | 不支持 | 支持 (FAIL 状态) |
| 查询性能 | O(1) | Cursor O(1), Log O(log n) |

### 3.2 IngestionLogStore（事件日志）

**职责**：记录每个交易日每个数据集的摄取事件

**表结构**：
```sql
CREATE TABLE ingestion_log (
    dataset TEXT NOT NULL,          -- 数据集名称 (etf_daily, stock_daily...)
    source TEXT NOT NULL,           -- 数据源 (tushare, akshare)
    trade_date TEXT NOT NULL,       -- 交易日期 (YYYY-MM-DD)
    status TEXT NOT NULL,           -- SUCCESS / FAIL
    checksum TEXT,                  -- 数据校验和 (SUCCESS 时有值)
    rows INTEGER,                   -- 行数 (SUCCESS 时有值)
    error_code TEXT,                -- 错误代码 (FAIL 时有值)
    error_message TEXT,             -- 错误消息 (FAIL 时有值)
    attempts INTEGER DEFAULT 1,     -- 尝试次数
    first_attempt_at TEXT,          -- 首次尝试时间
    last_attempt_at TEXT,           -- 最后尝试时间
    PRIMARY KEY (dataset, source, trade_date)
);

-- 状态查询索引
CREATE INDEX idx_ingestion_log_status_date
    ON ingestion_log(status, trade_date);
```

**关键方法**：
```python
class IngestionLogStore:
    def save_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
        status: IngestionStatus,
        checksum: str | None = None,
        rows: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> IngestionLog:
        """保存或更新日志 (UPSERT)，重试时增加 attempts"""

    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None:
        """获取特定日期的日志"""

    def get_failed_dates(
        self,
        dataset: str,
        source: str = "tushare",
        limit: int = 10,
        max_attempts: int = 3,
    ) -> list[str]:
        """获取需要重试的失败日期"""

    def get_successful_dates(
        self,
        dataset: str,
        source: str = "tushare",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[str]:
        """获取成功的日期列表（用于空洞扫描）"""
```

**数据模型**：
```python
@dataclass(frozen=True)
class IngestionLog:
    dataset: str
    source: str
    trade_date: str
    status: IngestionStatus  # SUCCESS / FAIL
    checksum: str | None = None
    rows: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempts: int = 1
    first_attempt_at: str | None = None
    last_attempt_at: str | None = None
```

### 3.3 IngestionCursorStore（已废弃）

> **废弃说明**: 此表已从 schema 中移除（2026-01），游标功能已整合到 `IngestionLog` 中。

**原职责**：快速查询最后成功/尝试日期（去规范化缓存）

**原表结构**（仅供参考）：
```sql
-- 已废弃，不再存在于 schema.sql 中
CREATE TABLE ingestion_cursor (
    dataset TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    last_success TEXT,
    last_attempted TEXT,
    updated_at TEXT NOT NULL
);
```

**替代方案**：使用 `IngestionLog` 的 `last_success` 和 `last_attempt_at` 字段。

### 3.4 使用场景

#### 场景 1：增量摄取

```python
# 获取最后成功日期（快速查询）
cursor = cursor_store.get_cursor("etf_daily")
if cursor and cursor.last_success:
    last_date = cursor.last_success
    # 只需要获取 last_date 之后的交易日
```

#### 场景 2：空洞扫描

```python
# 1. 获取应有数据的交易日
expected_dates = set(calendar_repo.get_trading_days(start, end))

# 2. 获取实际有数据的日期
existing_dates = set(log_store.get_successful_dates("etf_daily", start, end))

# 3. 找出空洞
holes = expected_dates - existing_dates
```

#### 场景 3：失败重试

```python
# 获取需要重试的失败日期
failed_dates = log_store.get_failed_dates(
    dataset="etf_daily",
    max_attempts=3,  # 只重试 3 次以内的
    limit=10,
)
```

### 3.5 存储方式

**存储引擎**：SQLite

**文件位置**：`{data_root}/meta/hub.sqlite`

**优点**：
- 轻量级，无需额外服务
- 支持事务，保证一致性
- 支持并发读（写通过 FileLock 保护）
- 查询性能足够（日志表有索引）

**备份策略**：
- 随 DataHub 一起备份
- 可选：定期导出到 Parquet 归档

---

## 4. 任务依赖关系（更新）

```
T0 → T1 → T3 分层架构

daily_ingestion_flow
├── [T0] Meta Layer (顺序执行)
│   ├── ingest_calendar
│   ├── ingest_stock_basic
│   └── ingest_etf_basic
│
├── [T1] Incremental Layer (并行执行，按优先级排序)
│   ├── ingest_adj_factor      (priority=25, depends on T0)
│   ├── ingest_etf_daily       (priority=20, depends on T0)
│   └── ingest_stock_daily     (priority=10, depends on T0)
│
└── [T3] Quality Layer
    └── run_quality_checks     (在 T1 成功数据集上执行)

独立 Flows:
├── backfill_flow              (手动触发，全量回补)
├── repair_holes_flow          (T2: 空洞扫描 + 回补)
├── retry_failed_flow          (T2: 失败重试)
└── daily_repair_flow          (T2: 每日凌晨运行，先重试后扫描)
```

---

## 5. 代码结构（更新）

```
interfaces/
  pyproject.toml

  src/
    ditto_interfaces/
      __init__.py
      main.py                     # FastAPI 入口

      # ============ API 层 ============
      api/
        __init__.py
        router.py                 # 主路由
        health.py                 # 健康检查（含 Prefect 状态）
        ingestion.py              # 摄取触发 API

      # ============ 数据摄取模块 ============
      jobs/
        __init__.py

        # Prefect Flows（编排层）
        flows/
          __init__.py
          daily.py                # 每日增量 Flow (T0→T1→T3)
          backfill.py             # 全量回补 Flow
          repair.py               # 空洞修补 + 重试 Flow (T2)
          quality.py              # 独立 DQC Flow (T3)

        # Prefect Tasks（轻量 wrapper）
        tasks/
          __init__.py
          t0_meta.py              # T0: 日历、标的
          t1_bars.py              # T1: 行情摄取
          t1_adj_factor.py        # T1: 复权因子
          t3_quality.py           # T3: DQC 检查

        # 调度配置
        schedules.py              # Prefect Deployment 定义
        hooks.py                  # Flow/Task 状态变化钩子（告警）

      # ============ 部署脚本 ============
      deploy.py                   # Prefect 部署脚本

      # ============ 其他服务 ============
      services/
        __init__.py
        notification.py           # 告警通知（钉钉/Telegram）
```

**关键变化**：
- 新增 `services/` 目录：Ingestion Service 层
- 新增 `config/` 目录：数据集注册表
- 重构 `flows/` 目录：体现 T0/T1/T2/T3 分层
- 重构 `tasks/` 目录：按层级组织
- 新增 `deploy.py`：统一部署脚本

---

## 6. Flow 实现（更新）

### 6.1 每日增量 Flow (flows/daily.py)

```python
# flows/daily.py

from datetime import date
from typing import Literal

from prefect import flow, get_run_logger
from prefect.futures import wait

from ditto_interfaces.ingestion.config.datasets import (
    Dataset,
    TaskTier,
    DATASET_REGISTRY,
)
from ditto_interfaces.ingestion.tasks import (
    ingest_calendar,
    ingest_etf_basic,
    ingest_stock_basic,
    ingest_etf_daily,
    ingest_stock_daily,
    ingest_adj_factor,
)
from ditto_interfaces.ingestion.tasks.t0_meta import check_trading_day
from ditto_interfaces.ingestion.tasks.t3_quality import run_quality_checks
from ditto_interfaces.ingestion.hooks import on_flow_failure


# Task 注册表
INGEST_TASKS = {
    Dataset.CALENDAR: ingest_calendar,
    Dataset.ETF_BASIC: ingest_etf_basic,
    Dataset.STOCK_BASIC: ingest_stock_basic,
    Dataset.ETF_DAILY: ingest_etf_daily,
    Dataset.STOCK_DAILY: ingest_stock_daily,
    Dataset.ADJ_FACTOR: ingest_adj_factor,
}


@flow(
    name="daily-ingestion",
    description="每日增量摄取 - T0 → T1 → T3",
    timeout_seconds=3600,
    on_failure=[on_flow_failure],
)
def daily_ingestion_flow(
    trade_date: date | None = None,
    datasets: list[Dataset] | Literal["all"] = "all",
    run_quality_checks: bool = True,
    source: str = "tushare",
    data_root: str = "data",
) -> dict:
    """
    每日增量摄取 Flow

    执行顺序：
    1. T0: 检查交易日 → 更新标的列表
    2. T1: 并行摄取行情、复权因子
    3. T3: 数据质量检查
    """
    logger = get_run_logger()

    if trade_date is None:
        trade_date = date.today()

    logger.info(f"Starting daily ingestion for {trade_date}")

    # ========== T0: Meta ==========
    is_trading = check_trading_day(trade_date, source=source, data_root=data_root)
    if not is_trading:
        logger.info(f"{trade_date} is not a trading day, skipping")
        return {"trade_date": trade_date.isoformat(), "status": "skipped", "reason": "not_trading_day"}

    # 确定目标数据集
    if datasets == "all":
        target_datasets = list(INGEST_TASKS.keys())
    else:
        target_datasets = datasets

    results = {}

    # T0 数据集（顺序执行，因为是其他任务的前置）
    t0_datasets = [d for d in target_datasets if DATASET_REGISTRY[d].tier == TaskTier.T0_META]
    for dataset in sorted(t0_datasets, key=lambda d: DATASET_REGISTRY[d].priority, reverse=True):
        task_fn = INGEST_TASKS.get(dataset)
        if task_fn:
            results[dataset.value] = task_fn(trade_date=trade_date, source=source, data_root=data_root)

    # ========== T1: Incremental（并行执行）==========
    t1_datasets = [d for d in target_datasets if DATASET_REGISTRY[d].tier == TaskTier.T1_INCREMENTAL]
    if t1_datasets:
        logger.info(f"T1 Incremental: {[d.value for d in t1_datasets]}")
        futures = {}

        for dataset in t1_datasets:
            task_fn = INGEST_TASKS.get(dataset)
            if task_fn:
                futures[dataset] = task_fn.submit(
                    trade_date=trade_date,
                    source=source,
                    data_root=data_root,
                )

        # 等待完成并收集结果
        for dataset, future in futures.items():
            try:
                results[dataset.value] = future.result()
            except Exception as e:
                logger.error(f"{dataset.value} failed: {e}")
                results[dataset.value] = {"status": "failed", "error": str(e)}

    # ========== T3: Quality ==========
    if run_quality_checks:
        successful_datasets = [
            Dataset(k) for k, v in results.items()
            if isinstance(v, dict) and v.get("status") == "success"
        ]
        if successful_datasets:
            logger.info(f"T3 Quality: checking {len(successful_datasets)} datasets")
            quality_result = run_quality_checks(
                trade_date=trade_date,
                datasets=successful_datasets,
                data_root=data_root,
            )
            results["quality_report"] = quality_result

    # 汇总
    success_count = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "success")
    failed_count = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "failed")

    return {
        "trade_date": trade_date.isoformat(),
        "status": "completed" if failed_count == 0 else "partial",
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
    }
```

### 6.2 回补 Flow (flows/backfill.py)

```python
# flows/backfill.py

from datetime import date
from prefect import flow, get_run_logger

from ditto_interfaces.ingestion.config.datasets import Dataset
from ditto_interfaces.ingestion.tasks import backfill_chunk
from ditto_data import DataHub


@task(name="backfill_chunk")
def backfill_chunk(
    dataset: Dataset,
    dates: list[date],
    source: str,
    data_root: str,
) -> dict:
    """回补一批日期"""
    logger = get_run_logger()
    logger.info(f"Backfilling {dataset.value}: {len(dates)} dates")

    hub = DataHub(data_root=data_root)
    try:
        from ditto_interfaces.ingestion.services.backfill import BackfillManager

        manager = BackfillManager(hub, source)
        result = manager.backfill_dates(
            dataset=dataset.value,
            dates=[d.isoformat().replace("-", "") for d in dates],
        )
        return result.to_dict()
    finally:
        hub.close()


@flow(name="backfill_dataset")
def backfill_flow(
    dataset: Dataset,
    start_date: date,
    end_date: date,
    chunk_size: int = 20,
    source: str = "tushare",
    data_root: str = "data",
) -> dict:
    """
    全量回补 Flow

    将日期范围分块，利用 Prefect 的：
    - 进度可视化
    - 失败隔离（单块失败不影响其他）
    - 可断点续传
    """
    logger = get_run_logger()

    # 获取交易日
    hub = DataHub(data_root=data_root)
    try:
        calendar = hub.calendar_repository.get_trading_days(
            start_date=start_date.isoformat().replace("-", ""),
            end_date=end_date.isoformat().replace("-", ""),
        )
        trading_days = [
            date.fromisoformat(d) for d in calendar["trade_date"].to_list()
        ]
    finally:
        hub.close()

    logger.info(
        f"Backfilling {dataset.value}: "
        f"{start_date} to {end_date}, "
        f"{len(trading_days)} trading days"
    )

    # 分块
    chunks = [
        trading_days[i:i + chunk_size]
        for i in range(0, len(trading_days), chunk_size)
    ]

    # 执行
    results = []
    for i, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {i + 1}/{len(chunks)}")
        result = backfill_chunk(
            dataset=dataset,
            dates=chunk,
            source=source,
            data_root=data_root,
        )
        results.append(result)

    # 汇总
    total_success = sum(r.get("success_count", 0) for r in results)
    total_failed = sum(r.get("failed_count", 0) for r in results)

    return {
        "dataset": dataset.value,
        "date_range": [start_date.isoformat(), end_date.isoformat()],
        "chunks": len(chunks),
        "total_trading_days": len(trading_days),
        "success_count": total_success,
        "failed_count": total_failed,
    }
```

### 6.3 修补 Flow (flows/repair.py)

```python
# flows/repair.py

from datetime import date, timedelta
from prefect import flow, get_run_logger

from ditto_interfaces.ingestion.config.datasets import Dataset, DATASET_REGISTRY
from ditto_interfaces.ingestion.services.retry import RetryManager
from ditto_data import DataHub


@flow(name="repair_holes")
def repair_holes_flow(
    dataset: Dataset,
    lookback_days: int = 365,
    source: str = "tushare",
    data_root: str = "data",
) -> dict:
    """
    空洞修补 Flow - T2 层

    扫描"应有数据但没有"的情况，比单纯重试更全面
    """
    logger = get_run_logger()

    hub = DataHub(data_root=data_root)
    try:
        # 获取应有数据的交易日
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        calendar = hub.calendar_repository.get_trading_days(
            start_date=start_date.isoformat().replace("-", ""),
            end_date=end_date.isoformat().replace("-", ""),
        )
        expected_dates = set(calendar["trade_date"].to_list())

        # 获取实际有数据的日期
        log_store = hub.ingestion_log_store
        existing_dates = set(log_store.get_successful_dates(dataset.value))
        existing_dates = set(d.replace("-", "") for d in existing_dates)

        # 找出空洞
        holes = expected_dates - existing_dates

        logger.info(
            f"Hole scan for {dataset.value}: "
            f"expected={len(expected_dates)}, "
            f"existing={len(existing_dates)}, "
            f"holes={len(holes)}"
        )

        if not holes:
            return {"dataset": dataset.value, "holes_found": 0, "repaired": 0}

        # 触发回补
        from ditto_interfaces.ingestion.flows.backfill import backfill_chunk

        sorted_holes = sorted(holes)
        result = backfill_chunk(
            dataset=dataset,
            dates=[date.fromisoformat(d) for d in sorted_holes],
            source=source,
            data_root=data_root,
        )

        return {
            "dataset": dataset.value,
            "holes_found": len(holes),
            "repaired": result.get("success_count", 0),
        }

    finally:
        hub.close()


@flow(name="retry_failed")
def retry_failed_flow(
    dataset: Dataset | None = None,
    max_attempts: int = 3,
    limit: int = 50,
    source: str = "tushare",
    data_root: str = "data",
) -> dict:
    """失败重试 Flow"""
    logger = get_run_logger()

    hub = DataHub(data_root=data_root)
    try:
        from ditto_interfaces.ingestion.services.retry import RetryManager

        manager = RetryManager(hub, source)

        if dataset:
            datasets = [dataset]
        else:
            datasets = list(DATASET_REGISTRY.keys())

        total_retried = 0
        total_success = 0
        results = {}

        for ds in datasets:
            result = manager.retry_failed(
                dataset=ds.value,
                max_attempts=max_attempts,
                limit=limit,
            )
            results[ds.value] = result.to_dict()
            total_retried += result.retried_count
            total_success += result.success_count

        logger.info(f"Retry completed: {total_success}/{total_retried} succeeded")

        return {
            "total_retried": total_retried,
            "total_success": total_success,
            "by_dataset": results,
        }

    finally:
        hub.close()


@flow(name="daily_repair")
def daily_repair_flow(
    source: str = "tushare",
    data_root: str = "data",
) -> dict:
    """
    每日修补 Flow - 凌晨运行

    1. 重试失败任务
    2. 扫描空洞
    """
    logger = get_run_logger()

    # 1. 重试失败
    retry_result = retry_failed_flow(
        max_attempts=3,
        limit=100,
        source=source,
        data_root=data_root,
    )

    # 2. 空洞扫描（只扫描最近30天）
    hole_results = {}
    for dataset in DATASET_REGISTRY.keys():
        if DATASET_REGISTRY[dataset].quality_checks_enabled:
            result = repair_holes_flow(
                dataset=dataset,
                lookback_days=30,
                source=source,
                data_root=data_root,
            )
            hole_results[dataset.value] = result

    return {
        "retry": retry_result,
        "holes": hole_results,
    }
```

---

## 7. Task 实现（更新）

### 7.1 轻量 Wrapper Tasks

**关键设计**：Task 只是轻量 wrapper，真正逻辑在 IngestionCoordinator

```python
# tasks/t1_bars.py

from datetime import date
from typing import Any

from prefect import task, get_run_logger
from prefect.tasks import exponential_backoff

from ditto_interfaces.ingestion.config.datasets import Dataset, DATASET_REGISTRY
from ditto_interfaces.ingestion.services.coordinator import IngestionCoordinator
from ditto_data import DataHub


def create_ingest_task(dataset: Dataset):
    """
    工厂函数：为每个数据集创建 Prefect Task

    关键设计：
    - Task 只是 wrapper，真正逻辑在 IngestionCoordinator
    - 从 DATASET_REGISTRY 读取重试/超时配置
    - 返回标准化结果字典
    """
    config = DATASET_REGISTRY[dataset]

    @task(
        name=f"ingest_{dataset.value}",
        description=config.description,
        retries=config.retry_limit,
        retry_delay_seconds=exponential_backoff(
            backoff_factor=config.retry_delay_seconds
        ),
        timeout_seconds=config.timeout_seconds,
        tags=[dataset.value, config.tier.value, "ingest"],
    )
    def ingest_task(
        trade_date: date,
        source: str = "tushare",
        data_root: str = "data",
        force: bool = False,
    ) -> dict[str, Any]:
        """
        摄取单日数据

        Args:
            trade_date: 交易日期
            source: 数据源
            data_root: 数据根目录
            force: 是否强制重新摄取

        Returns:
            标准化结果字典
        """
        logger = get_run_logger()
        logger.info(f"Ingesting {dataset.value} for {trade_date}")

        hub = DataHub(data_root=data_root)
        try:
            coordinator = IngestionCoordinator(hub, source)
            result = coordinator.ingest_date(
                dataset=dataset.value,
                trade_date=trade_date.isoformat().replace("-", ""),
                force=force,
            )

            logger.info(
                f"Completed: status={result.status}, "
                f"records={result.records_count}"
            )
            return result.to_dict()

        except Exception as e:
            logger.error(f"Failed: {e}")
            raise  # 让 Prefect 处理重试

        finally:
            hub.close()

    return ingest_task


# 导出各数据集的 Task
ingest_etf_daily = create_ingest_task(Dataset.ETF_DAILY)
ingest_stock_daily = create_ingest_task(Dataset.STOCK_DAILY)
ingest_adj_factor = create_ingest_task(Dataset.ADJ_FACTOR)
```

``` python
# tasks/t0_meta.py

from datetime import date
from prefect import task, get_run_logger

from ditto_data import DataHub


@task(
    name="check_trading_day",
    description="检查是否为交易日",
    tags=["t0_meta", "calendar"],
)
def check_trading_day(
    trade_date: date,
    source: str = "tushare",
    data_root: str = "data",
) -> bool:
    """
    检查指定日期是否为交易日

    这是所有摄取任务的 Gate，非交易日直接跳过
    """
    logger = get_run_logger()

    hub = DataHub(data_root=data_root)
    try:
        is_trading = hub.calendar_repository.is_trading_day(
            trade_date.isoformat().replace("-", "")
        )
        logger.info(f"{trade_date} is_trading_day={is_trading}")
        return is_trading
    finally:
        hub.close()


@task(
    name="ingest_calendar",
    description="摄取交易日历",
    retries=3,
    retry_delay_seconds=60,
    tags=["t0_meta", "calendar"],
)
def ingest_calendar(
    source: str = "tushare",
    data_root: str = "data",
) -> dict:
    """摄取交易日历（全量更新）"""
    logger = get_run_logger()
    logger.info("Ingesting calendar")

    hub = DataHub(data_root=data_root)
    try:
        # 日历是全量更新，不需要 trade_date 参数
        from ditto_interfaces.ingestion.services.coordinator import IngestionCoordinator

        coordinator = IngestionCoordinator(hub, source)
        result = coordinator.ingest_calendar()
        return result.to_dict()
    finally:
        hub.close()
```

---

## 8. 调度配置（更新）

```python
# deploy.py

from prefect import serve
from prefect.client.schemas.schedules import CronSchedule

from ditto_interfaces.ingestion.flows.daily import daily_ingestion_flow
from ditto_interfaces.ingestion.flows.backfill import backfill_flow
from ditto_interfaces.ingestion.flows.repair import daily_repair_flow, retry_failed_flow
from ditto_interfaces.ingestion.flows.quality import standalone_quality_flow


def deploy():
    """部署所有 Ingestion Flows"""

    # 每日增量：交易日 18:00
    daily_deployment = daily_ingestion_flow.to_deployment(
        name="daily-ingestion",
        schedule=CronSchedule(
            cron="0 18 * * 1-5",  # 周一到周五 18:00
            timezone="Asia/Shanghai",
        ),
        tags=["production", "scheduled", "daily"],
        parameters={
            "datasets": "all",
            "run_quality_checks": True,
        },
    )

    # 每日修补：凌晨 2:00
    repair_deployment = daily_repair_flow.to_deployment(
        name="daily-repair",
        schedule=CronSchedule(
            cron="0 2 * * *",  # 每天凌晨 2:00
            timezone="Asia/Shanghai",
        ),
        tags=["production", "scheduled", "repair"],
    )

    # 失败重试：每4小时检查一次（作为兜底）
    retry_deployment = retry_failed_flow.to_deployment(
        name="retry-failed",
        schedule=CronSchedule(
            cron="0 */4 * * *",
            timezone="Asia/Shanghai",
        ),
        tags=["production", "scheduled", "retry"],
        parameters={"max_attempts": 3, "limit": 50},
    )

    # Backfill: 手动触发
    backfill_deployment = backfill_flow.to_deployment(
        name="backfill",
        tags=["manual", "backfill"],
    )

    # 独立 DQC: 手动触发
    quality_deployment = standalone_quality_flow.to_deployment(
        name="quality-check",
        tags=["manual", "quality"],
    )

    serve(
        daily_deployment,
        repair_deployment,
        retry_deployment,
        backfill_deployment,
        quality_deployment,
    )


if __name__ == "__main__":
    deploy()
```

---

## 8. 告警 Hook

```python
# hooks.py

from prefect import flow
from prefect.blocks.notifications import SlackWebhook
import httpx


async def on_flow_failure(flow, flow_run, state):
    """Flow 失败时发送告警"""
    message = f"""
🚨 **Ditto 任务失败告警**

**Flow**: {flow.name}
**Run ID**: {flow_run.id}
**State**: {state.name}
**Error**: {state.message}

请及时检查处理！
"""
    await send_notification(message)


def send_dq_alert(trade_date: str, issues: list):
    """发送 DQ 告警"""
    issue_summary = "\n".join(
        f"- {i.rule_name}: {i.message} ({i.affected_rows} 条)"
        for i in issues[:10]
    )

    message = f"""
⚠️ **Ditto 数据质量告警**

**日期**: {trade_date}
**问题数**: {len(issues)}

**详情**:
{issue_summary}
"""
    send_notification_sync(message)


async def send_notification(message: str):
    """异步发送通知"""
    # Telegram
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if telegram_token and telegram_chat_id:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
            })

    # 钉钉
    dingtalk_webhook = os.environ.get("DINGTALK_WEBHOOK")
    if dingtalk_webhook:
        async with httpx.AsyncClient() as client:
            await client.post(dingtalk_webhook, json={
                "msgtype": "markdown",
                "markdown": {"title": "Ditto 告警", "text": message},
            })
```

---

## 9. FastAPI 集成

```python
# interfaces/src/ditto_interfaces/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from prefect.client import get_client

from .ingestion.schedules import create_deployments


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # Startup: 注册 Prefect Deployments
    async with get_client() as client:
        deployments = create_deployments()
        for deployment in deployments:
            await deployment.apply()

    yield

    # Shutdown: 清理资源


app = FastAPI(
    title="Ditto API",
    lifespan=lifespan,
)


# 手动触发 API
@app.post("/api/v1/ingestion/trigger")
async def trigger_flow(request: TriggerRequest):
    """手动触发摄取任务"""
    from prefect.deployments import run_deployment

    deployment_map = {
        "daily_ingest": "daily-ingest/daily-ingest-scheduled",
        "dq_batch": "dq-batch/dq-batch-scheduled",
        "backfill": "backfill/backfill-manual",
    }

    deployment_name = deployment_map.get(request.flow)
    if not deployment_name:
        raise HTTPException(400, f"Unknown flow: {request.flow}")

    flow_run = await run_deployment(
        name=deployment_name,
        parameters=request.params,
    )

    return {
        "flow_run_id": str(flow_run.id),
        "status": "triggered",
    }
```

---

## 10. 手动操作

### 10.1 CLI 触发

```bash
# 每日摄取
prefect deployment run "daily-ingest/daily-ingest-scheduled"

# 指定日期
prefect deployment run "daily-ingest/daily-ingest-scheduled" \
    --param trade_date="2024-12-20"

# L3 检查
prefect deployment run "dq-batch/dq-batch-scheduled"

# 补数据
prefect deployment run "backfill/backfill-manual" \
    --param start_date="2024-01-01" \
    --param end_date="2024-01-31"
```

### 10.2 查看状态

```bash
# 查看所有 Deployments
prefect deployment ls

# 查看最近运行
prefect flow-run ls --limit 10

# 查看日志
prefect flow-run logs <run-id>

# 取消运行
prefect flow-run cancel <run-id>
```

### 10.3 Prefect UI

访问 http://localhost:4200：

- 查看 Flow Runs 列表
- DAG 可视化
- 日志查看
- 手动触发 Run
- 查看参数

---

## 11. 迁移计划（更新）

### Phase 0（已完成）
1. 安装 Prefect：`pip install prefect`
2. 本地启动 Prefect Server
3. 基础 Flows/Tasks 已实现

### Phase 0.5（进行中）
1. 完善所有 Tasks
2. 实现告警（Telegram/钉钉）
3. 与 DataHub PipelineStore 集成

### Phase 1（本次重构 - Ingestion 系统重构）

**目标**：Source 层轻量化 + Ingestion Service 层 + T0/T1/T2/T3 分层

#### 1.1 Ingestion Service 层
- [ ] 实现 IngestionCoordinator
- [ ] 实现 MetadataManager
- [ ] 实现 BackfillManager
- [ ] 实现 RetryManager

#### 1.2 Prefect 集成
- [ ] 创建 DATASET_REGISTRY（配置驱动）
- [ ] 重构 Tasks 为轻量 wrapper
- [ ] 重构 Flows 体现 T0/T1/T2/T3 分层
- [ ] 创建 deploy.py

#### 1.3 Source 层简化
- [ ] 移除 `DataSource.ingest_date()`
- [ ] 移除 `fetch_etf_daily_incremental()`
- [ ] 废弃 `IngestionMetadataStore`

### Phase 2（后续）
1. 实现独立 DQC Flow
2. 集成 OpenTelemetry Trace
3. 完善监控和告警
4. 性能优化

---

*本文档定义了 Ditto 数据摄取的调度设计，使用 Prefect 3 作为任务调度框架。v2.0 引入融合架构，Ingestion Service 负责业务逻辑，Prefect 负责编排和状态管理。*
