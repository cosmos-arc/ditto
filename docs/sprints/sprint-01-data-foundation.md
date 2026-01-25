# Sprint 1: 数据层基础架构（Phase 0.5）

**时间**: Week 1-3
**Phase**: 0.5 数据摄取打通期
**目标**: 建立数据层基础架构与数据摄取通道

## 参考文档

- 《01_system_design.md》 - 系统架构设计
- 《02_data_design.md》 - 数据层设计文档（v2.0 Final）
- 《09_data_quality_design.md》 - 数据质量设计（DQ 三层架构延后到 Sprint-02）
- 《10_data_ingestion_scheduler_design.md》 - 数据摄取调度设计

## Sprint 目标

1. ✅ 实现 DataHub 统一数据入口（已完成）
2. ✅ 实现 Domain Repositories（已完成）
3. ✅ 实现 Store Layer（已完成）
4. ✅ 实现 Runtime Layer（已完成）
5. ✅ 实现 Sources 层（Tushare 适配器 + 股票/复权因子）
6. ✅ 实现 Server 层骨架（Prefect 调度 + 完整摄取流程）

## 架构概览（更新）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Server 层                                      │
│                                                                              │
│   Prefect Flows/Tasks：任务编排、调度、重试                                   │
│   daily_ingest_flow → 7 tasks并行：                                          │
│     - ingest_stock_basic (可选，初次运行)                                     │
│     - ingest_etf_bars + ingest_stock_daily (并行)                             │
│     - ingest_adj_factor + ingest_fund_adj (并行)                             │
│     ↓                                                                         │
│   hub.sources.tushare.fetch_xxx()                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ 调用
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DataHub（纯 Facade）                             │
│                                                                              │
│   hub.bars / hub.calendar / hub.securities / hub.sources / hub.sql         │
│   (DataSources 提供数据源访问)                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        ▼                                                           ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│      Sources Layer            │    │   Domain Repositories        │
│                              │    │                              │
│   hub.sources.tushare        │    │   BarsAccessor             │
│   - fetch_calendar           │    │   CalendarAccessor         │
│   - fetch_etf_basic/daily    │    │   SecurityAccessor         │
│   - fetch_stock_basic/daily  │    │                              │
│   - fetch_adj_factor         │    │                              │
│   - fetch_fund_adj           │    │                              │
│   hub.sources.akshare（Sprint-02）│                              │
└──────────────────────────────┘    └──────────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Store Layer（数据存取层）                          │
│                                                                              │
│   SQLite Stores（元数据）+ Parquet Stores（年分区事实数据）                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Runtime Layer                                    │
│                                                                              │
│   SQLite Pool │ SID Allocator │ File Lock │ DQ Checker │ SQL Engine        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 任务分解

### P0 - 必须完成

---

#### 任务1: Runtime Layer（基础组件）✅ 已完成

| 组件 | 文件 | 状态 |
|------|------|------|
| SID 分配器 | `runtime/sid_allocator.py` | ✅ |
| SQLite 连接池 | `runtime/sqlite_pool.py` | ✅ |
| 文件锁管理器 | `runtime/file_lock.py` | ✅ |
| DQ 检查器（简单版） | `runtime/dq_checker.py` | ✅ |
| SQL Engine | `runtime/sql_engine.py` | ✅ |

**完成状态**:
- ✅ 18 个单元测试全部通过
- ✅ Ruff/MyPy 检查通过

**注意**: DQ 三层架构（L1/L2/L3）延后到 Sprint-02，当前保留简单 DQChecker

---

#### 任务2: Store Layer（数据存取）✅ 已完成

| 组件 | 文件 | 状态 |
|------|------|------|
| SecurityStore | `stores/security_store.py` | ✅ |
| CalendarStore | `stores/calendar_store.py` | ✅ |
| PipelineStore | `stores/pipeline_store.py` | ✅ |
| BarsStore | `stores/bars_store.py` | ✅ |
| AdjFactorStore | `stores/adj_factor_store.py` | ✅ |

**完成状态**:
- ✅ 83 个单元测试全部通过
- ✅ Ruff/MyPy 检查通过

---

#### 任务3: Domain Repositories ✅ 已完成

| 组件 | 文件 | 状态 |
|------|------|------|
| SecurityAccessor | `accessors/security.py` | ✅ |
| BarsAccessor | `accessors/bars.py` | ✅ |
| CalendarAccessor | `accessors/calendar.py` | ✅ |

**完成状态**:
- ✅ 8 个单元测试全部通过
- ✅ 覆盖率 80.30%

---

#### 任务4: DataHub Facade ✅ 已完成

| 组件 | 文件 | 状态 |
|------|------|------|
| DataHub | `hub.py` | ✅ |
| SQL Engine | `runtime/sql_engine.py` | ✅ |

**完成状态**:
- ✅ PR: https://github.com/cosmos-arc/ditto/pull/7

---

#### 任务5: Sources 层（新增）✅ 已完成

**5.1 DataSource 基类** [S] ✅
- 文件：`packages/datahub/src/ditto_datahub/sources/base.py`
- 功能：
  - DataSource 抽象基类定义
  - DataSourceError 异常体系
  - get_source() 工厂函数
- 抽象方法（8个）：
  ```python
  @abstractmethod
  def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame
  @abstractmethod
  def fetch_etf_basic(self) -> pl.DataFrame
  @abstractmethod
  def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame
  @abstractmethod
  def fetch_stock_basic(self) -> pl.DataFrame
  @abstractmethod
  def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame
  @abstractmethod
  def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame
  @abstractmethod
  def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame
  ```
- 验收标准：
  - ✅ 基类定义完整（8 个抽象方法）
  - ✅ 工厂函数支持 "tushare", "akshare"
  - ✅ 异常体系定义完整

**5.2 Tushare 适配器完整实现** [L] ✅
- 文件：
  - `packages/datahub/src/ditto_datahub/sources/tushare/__init__.py`
  - `packages/datahub/src/ditto_datahub/sources/tushare/client.py`
  - `packages/datahub/src/ditto_datahub/sources/tushare/source.py`
- 功能：
  - **TushareClient**：
    - Token fallback 链：keyring → secrets.toml → env var
    - 实现基础限流（每分钟 200 次）
    - 实现重试机制（指数退避）
  - **TushareSource**（7 个 fetch 方法）：
    - fetch_calendar() - 交易日历
    - fetch_etf_basic() - ETF 基础信息
    - fetch_etf_daily() - ETF 日线行情
    - fetch_stock_basic() - 股票基本信息
    - fetch_stock_daily() - 股票日线行情
    - fetch_adj_factor() - 股票复权因子
    - fetch_fund_adj() - ETF/基金复权因子
  - 数据格式统一为 Ditto 标准 Schema
- 验收标准：
  - ✅ 19 个单元测试全部通过（Calendar: 3, ETF: 5, Stock: 9, AdjFactor: 6）
  - ✅ TushareSource 测试覆盖率 95.95%
  - ✅ 限流和重试机制生效

**5.3 DataHub 集成 sources** [S] ✅
- 文件：修改 `packages/datahub/src/ditto_datahub/hub.py`
- 功能：
  - 添加 `@cached_property sources`
  - 返回 DataSources 实例
  - DataSources 提供 `tushare` 属性和 `get()` 方法
- 验收标准：
  - ✅ `hub.sources.tushare.fetch_etf_daily()` 可调用
  - ✅ 单例模式生效（多次调用返回同一实例）

**完成状态**:
- ✅ PR 已合并到 main
- ✅ 所有单元测试通过（49/49）
- ✅ Lint/Format/Typecheck 通过

---

#### 任务6: Server 层骨架（新增）✅ 已完成

**6.1 Prefect 基础设施** [S] ✅
- 文件：
  - `apps/port/pyproject.toml`（新增包）
  - `apps/port/src/ditto_port/__init__.py`
  - `apps/port/src/ditto_port/main.py`
- 功能：
  - FastAPI 基础应用
  - Prefect 本地 Server 启动
  - 健康检查端点
  - 依赖：
    ```toml
    dependencies = [
        "fastapi>=0.100",
        "uvicorn>=0.23",
        "prefect>=3.0",
        "keyring>=25.0",
        "ditto-data-hub",
    ]
    ```
- 验收标准：
  - ✅ `pixi run -e dev server` 启动成功
  - ✅ 访问 http://localhost:8000/health 返回 OK
  - ✅ 访问 http://localhost:4200（Prefect UI）可访问

**6.2 完整摄取 Flow 实现** [L] ✅
- 文件：
  - `apps/port/src/ditto_port/ingestion/flows/__init__.py`
  - `apps/port/src/ditto_port/ingestion/flows/daily_ingest.py`
  - `apps/port/src/ditto_port/ingestion/tasks/__init__.py`
  - `apps/port/src/ditto_port/ingestion/tasks/bars.py`
  - `apps/port/src/ditto_port/ingestion/tasks/stock.py`
  - `apps/port/src/ditto_port/ingestion/tasks/adj_factor.py`
- 功能：
  - **daily_ingest_flow**：
    - 完整版本，支持 7 个摄取任务
    - 并行执行：etf_bars + stock_bars，adj_factor + fund_adj
    - 参数：trade_date, source（默认 "tushare"），run_stock_basic（可选）
    - 返回：摄取结果统计
  - **Tasks（7个）**：
    1. ingest_stock_basic - 股票基本信息摄取（可选）
    2. ingest_etf_bars - ETF 日线摄取
    3. ingest_stock_daily - 股票日线摄取
    4. ingest_adj_factor - 股票复权因子摄取
    5. ingest_fund_adj - ETF/基金复权因子摄取
- 验收标准：
  - ✅ 所有 7 个任务实现完成
  - ✅ Lint/Format/Typecheck 通过
  - ✅ Pre-commit hooks 通过
  - ✅ 提交 commit: `873c2b5`

**完成状态**:
- ✅ Server 层骨架完整
- ✅ 完整的数据摄取流程实现

---

### P1 - 延后到 Sprint-02

---

#### 任务7: DQ 三层架构重构 🔄

**原因**: 当前简单 DQChecker 已满足基本需求，三层架构复杂度高

**Sprint-02 实现**：
- `dq/engine.py` - DQEngine 统一执行引擎
- `dq/result.py` - DQResult, DQIssue 等模型
- `dq/checkers/technical.py` - L1 技术校验（非空、唯一、外键）
- `dq/checkers/business.py` - L2 业务规则（OHLC、涨跌幅）
- `dq/checkers/statistical.py` - L3 统计异常（Z-score、完整性）
- `config/dq_rules.yaml` - YAML 规则配置
- Accessor 集成 DQEngine
- 隔离区机制实现

---

#### 任务8: Server 调度完善 🔄

**原因**: Phase 0 重点是打通数据流，调度功能可以后续完善

**Sprint-02 实现**：
- 完整的 Flow/Task 实现（calendar, securities, derived）
- dq_batch_flow（L3 批量检查）
- backfill_flow（补数据）
- heartbeat_flow（心跳）
- 定时调度配置（CronSchedule）
- 告警 Hook（Telegram/钉钉）
- API 触发端点

---

#### 任务9: AkShare 适配器 🔄

**Sprint-02 实现**：
- `sources/akshare/client.py`
- `sources/akshare/source.py`
- 作为 Tushare 的降级备选

---

### Bug 修复与技术债务清理

#### Bug Fix #1: Windows SQLite 文件锁定问题 ✅

**问题描述**:
- Windows 环境下测试 teardown 时出现 `PermissionError: [WinError 32]`
- SQLite WAL 模式的 `-wal` 和 `-shm` 文件未被正确释放

**根本原因**:
- `SQLiteClient` 缺少 `close()` 方法
- `DataHub.close()` 未关闭 store 层资源
- Windows 文件句柄需要显式释放

**解决方案**:
1. 为 `SQLiteClient` 添加 `close()` 方法
2. 为所有 Stores 添加 `close()` 方法：
   - `SecurityStore.close()`
   - `CalendarStore.close()`
   - `PipelineStore.close()`
3. 更新 `DataHub.close()` 按依赖顺序关闭资源：
   - Stores (hold SQLiteClient) → sql_engine → sqlite_pool
4. 测试 teardown 添加 `gc.collect()` 和延迟确保 Windows 释放句柄

**修改文件**:
- `packages/datahub/src/ditto_datahub/stores/sqlite_client.py`
- `packages/datahub/src/ditto_datahub/stores/security_store.py`
- `packages/datahub/src/ditto_datahub/stores/calendar_store.py`
- `packages/datahub/src/ditto_datahub/stores/pipeline_store.py`
- `packages/datahub/src/ditto_datahub/hub.py`
- `packages/datahub/tests/unit/test_hub.py`

**验收**:
- ✅ 所有测试通过（8 passed）
- ✅ teardown 无 PermissionError

---

#### Bug Fix #2: TushareClient 类型注解 ✅

**问题描述**:
- Pylance 报告 `len(response)` 类型未知
- `TushareClient.query()` 返回类型是 `Any`

**解决方案**:
- 将返回类型从 `Any` 改为 `pd.DataFrame`
- 添加 `import pandas as pd`

**修改文件**:
- `packages/datahub/src/ditto_datahub/sources/tushare/client.py`

**验收**:
- ✅ Pylance 类型检查通过
- ✅ mypy typecheck 通过

---

#### Bug Fix #3: XDG 路径规范化 ✅

**问题描述**:
- 代码中存在硬编码的 C 盘路径
- 不符合 XDG Base Directory 规范
- Windows 环境下应默认使用 D 盘

**解决方案**:
1. 新增 `XDGPaths` 类实现跨平台路径管理
2. 使用 `computed_field` 实现延迟路径解析
3. 支持环境变量覆盖（`DITTO_*_DIR` 优先级最高）

**修改文件**:
- `packages/foundation/src/ditto_foundation/config/paths.py` (新增)
- `packages/foundation/src/ditto_foundation/config/settings.py`
- `packages/foundation/src/ditto_foundation/config/__init__.py`
- `packages/foundation/src/ditto_foundation/observability/logging.py`

**验收**:
- ✅ Windows 默认使用 `D:\data\ditto`
- ✅ 环境变量覆盖生效
- ✅ 所有测试通过

---

## 关键文件清单

### 新增文件

```
packages/datahub/
├── src/ditto_datahub/sources/
│   ├── __init__.py                 # 导出 get_source, DataSource
│   ├── base.py                     # DataSource 基类 + 异常（8个抽象方法）
│   ├── README.md                   # Sources 模块说明
│   └── tushare/
│       ├── __init__.py
│       ├── client.py               # Tushare 客户端（限流、重试、keyring）
│       └── source.py               # TushareSource 实现（7个fetch方法）
│
apps/port/
├── README.md                       # Server 模块说明
├── pyproject.toml                  # Server 包配置
└── src/ditto_port/
    ├── __init__.py
    ├── main.py                     # FastAPI 入口 + Prefect 启动
    └── ingestion/
        ├── __init__.py
        ├── flows/
        │   ├── __init__.py
        │   └── daily_ingest.py     # 完整每日摄取 Flow（7 tasks）
        └── tasks/
            ├── __init__.py
            ├── bars.py             # ETF K线摄取 Task
            ├── stock.py            # 股票摄取 Tasks（basic + daily）
            └── adj_factor.py       # 复权因子 Tasks（adj + fund）
```

### 修改文件

```
packages/datahub/src/ditto_datahub/
└── hub.py                          # 添加 sources 属性
```

---

## 验收标准

### Sprint-01 Phase 0.5 完成标准

- ✅ **Sources 层**：DataSource 基类 + Tushare 适配器完整实现（7个fetch方法）
- ✅ **Server 层**：可启动，Prefect UI 可访问
- ✅ **数据流**：完整摄取流程实现（ETF + Stock + AdjFactor）
- ✅ **单元测试**：49/49 测试通过（TushareSource 95.95% 覆盖率）
- ✅ **代码质量**：ci-check 全部通过

---

## 依赖关系

```
sources/base.py（基类 - 8个抽象方法）
    ↓
sources/tushare（实现 - 7个fetch方法）
    ↓
hub.py（集成 sources）
    ↓
Server/tasks/（5个task文件，7个任务）
    ↓
Server/flows/daily_ingest.py（编排并行执行）
```

---

## 下一步（Sprint-02）

1. DQ 三层架构重构
2. Server 调度完善（定时调度、告警、回填）
3. AkShare 适配器实现
4. Golden Dataset 验证
5. 更多数据源集成（指数、成分股、财务数据）
