# Sprint 1: 数据层与数据摄取（Phase 0.5）

**时间**: Week 1-3
**Phase**: 0.5 数据摄取打通期
**目标**: 实现数据层基础 + 数据摄取管道

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
5. 🆕 实现 Sources 层（Tushare 适配器）
6. 🆕 实现 Server 层骨架（Prefect 调度）

## 架构概览（更新）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Server 层（新增）                                │
│                                                                              │
│   Prefect Flows/Tasks：任务编排、调度、重试                                   │
│   daily_ingest_flow → ingest_etf_bars → hub.sources.tushare.fetch_etf_daily │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ 调用
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DataHub（纯 Facade）                             │
│                                                                              │
│   hub.bars / hub.calendar / hub.securities / hub.sources / hub.sql         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        ▼                                                           ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│      Sources Layer（新增）    │    │   Domain Repositories        │
│                              │    │                              │
│   hub.sources.tushare        │    │   BarsRepository             │
│   hub.sources.akshare（Sprint-02）│   CalendarRepository         │
│                              │    │   SecurityRepository         │
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
| SecurityRepository | `repositories/security.py` | ✅ |
| BarsRepository | `repositories/bars.py` | ✅ |
| CalendarRepository | `repositories/calendar.py` | ✅ |

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
- 文件：`packages/ditto-data-hub/src/ditto_data_hub/sources/base.py`
- 功能：
  - DataSource 抽象基类定义
  - DataSourceError 异常体系
  - get_source() 工厂函数
- 抽象方法：
  ```python
  @abstractmethod
  def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame
  @abstractmethod
  def fetch_etf_basic(self) -> pl.DataFrame
  @abstractmethod
  def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame
  ```
- 验收标准：
  - [ ] 基类定义完整
  - [ ] 工厂函数支持 "tushare", "akshare"
  - [ ] 异常体系定义完整

**5.2 Tushare 适配器基础** [M] ✅
- 文件：
  - `packages/ditto-data-hub/src/ditto_data_hub/sources/tushare/__init__.py`
  - `packages/ditto-data-hub/src/ditto_data_hub/sources/tushare/client.py`
  - `packages/ditto-data-hub/src/ditto_data_hub/sources/tushare/source.py`
- 功能：
  - **TushareClient**：
    - 从环境变量 `TUSHARE_TOKEN` 读取凭证
    - 实现基础限流（每分钟 200 次）
    - 实现重试机制（指数退避）
  - **TushareSource**：
    - 实现 fetch_calendar()（交易日历）
    - 实现 fetch_etf_basic()（ETF 基础信息）
    - 实现 fetch_etf_daily()（ETF 日线行情）
    - 数据格式统一为 Ditto 标准 Schema
- 验收标准：
  - [ ] TushareClient 单元测试通过
  - [ ] fetch_etf_daily() 返回标准格式数据
  - [ ] 限流和重试机制生效

**5.3 DataHub 集成 sources** [S] ✅
- 文件：修改 `packages/ditto-data-hub/src/ditto_data_hub/hub.py`
- 功能：
  - 添加 `@cached_property sources`
  - 返回 SourcesAccessor 实例
  - SourcesAccessor 提供 `tushare` 属性和 `get()` 方法
- 验收标准：
  - ✅ `hub.sources.tushare.fetch_etf_daily()` 可调用
  - ✅ 单例模式生效（多次调用返回同一实例）

**完成状态**:
- ✅ PR 已合并到 main
- ✅ 单元测试通过

---

#### 任务6: Server 层骨架（新增）🆕

**6.1 Prefect 基础设施** [S]
- 文件：
  - `apps/server/pyproject.toml`（新增包）
  - `apps/server/src/ditto_server/__init__.py`
  - `apps/server/src/ditto_server/main.py`
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
    "ditto-data-hub",
  ]
  ```
- 验收标准：
  - [ ] `pixi run -e dev server` 启动成功
  - [ ] 访问 http://localhost:8000/health 返回 OK
  - [ ] 访问 http://localhost:4200（Prefect UI）可访问

**6.2 摄取 Flow 基础** [M]
- 文件：
  - `apps/server/src/ditto_server/ingestion/__init__.py`
  - `apps/server/src/ditto_server/ingestion/flows/__init__.py`
  - `apps/server/src/ditto_server/ingestion/flows/daily_ingest.py`
  - `apps/server/src/ditto_server/ingestion/tasks/__init__.py`
  - `apps/server/src/ditto_server/ingestion/tasks/bars.py`
- 功能：
  - **daily_ingest_flow**：
    - 基础版本，仅支持 ETF 日线摄取
    - 参数：trade_date, source（默认 "tushare"）
    - 返回：摄取结果统计
  - **ingest_etf_bars Task**：
    - 调用 hub.sources.tushare.fetch_etf_daily()
    - 调用 hub.securities.resolve_sids_batch() 解析 SID
    - 调用 hub.bars.write() 写入数据
- 验收标准：
  - [ ] 手动触发 Flow 成功执行
  - [ ] 数据成功写入 DataHub
  - [ ] Prefect UI 显示 Flow Run 历史

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
- Repository 集成 DQEngine
- 隔离区机制实现

---

#### 任务8: Server 调度完善 🔄

**原因**: Phase 0 重点是打通数据流，调度功能可以后续完善

**Sprint-02 实现**：
- 完整的 Flow/Task 实现（calendar, securities, adj_factor, derived）
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

## 关键文件清单

### 新增文件

```
packages/ditto-data-hub/
├── src/ditto_data_hub/sources/
│   ├── __init__.py                 # 导出 get_source, DataSource
│   ├── base.py                     # DataSource 基类 + 异常
│   └── tushare/
│       ├── __init__.py
│       ├── client.py               # Tushare 客户端（限流、重试）
│       └── source.py               # TushareSource 实现
│
apps/server/
├── pyproject.toml                  # Server 包配置
└── src/ditto_server/
    ├── __init__.py
    ├── main.py                     # FastAPI 入口 + Prefect 启动
    └── ingestion/
        ├── __init__.py
        ├── flows/
        │   ├── __init__.py
        │   └── daily_ingest.py     # 每日摄取 Flow
        └── tasks/
            ├── __init__.py
            └── bars.py             # K线摄取 Task
```

### 修改文件

```
packages/ditto-data-hub/src/ditto_data_hub/
└── hub.py                          # 添加 sources 属性
```

---

## 验收标准

### Sprint-01 Phase 0.5 完成标准

- [ ] **Sources 层**：DataSource 基类 + Tushare 适配器实现完成
- [ ] **Server 层**：可启动，Prefect UI 可访问
- [ ] **数据流**：手动触发 daily_ingest_flow 成功执行
- [ ] **数据写入**：数据成功写入 DataHub（通过现有 DQ 检查）
- [ ] **单元测试**：所有新增代码有单元测试覆盖
- [ ] **代码质量**：ci-check 全部通过

---

## 依赖关系

```
sources/base.py（基类）
    ↓
sources/tushare（实现）
    ↓
hub.py（集成 sources）
    ↓
Server/tasks/bars.py（调用 hub.sources）
    ↓
Server/flows/daily_ingest.py（编排 tasks）
```

---

## 下一步（Sprint-02）

1. DQ 三层架构重构
2. Server 调度完善（完整 Flows/Tasks、定时调度、告警）
3. AkShare 适配器实现
4. Golden Dataset 验证
