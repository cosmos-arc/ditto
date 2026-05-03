> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Ditto 系统设计文档

**版本：v2.1（Phase 0–1：ETF 行业轮动）**

**日期：2025-12-26**

---

## 1. 设计目标与约束

### 1.1 主要目标

1. 固化一套**清晰、可扩展**的架构骨架，支持 Phase 0–3 的渐进演进
2. 让"半年后的你"和 LLM 工具都能看懂、接得上
3. 降低"改一点点策略 → 牵一发动全身"的风险
4. **组合层作为一等公民**，即使当前只有一个策略

### 1.2 关键约束

- 单机 Windows 环境，禁止强依赖云基础设施
- 日线数据为主，不引入分钟级数据
- 当期仅支持 ETF 行业轮动，但抽象要支持未来扩展
- **数据必须支持 PIT（Point-in-Time）查询**
- **回测引擎必须支持涨跌停过滤**

---

## 2. 系统上下文

```
┌──────────────────────────────────────────────────────────────┐
│                          用户（你）                          │
│  - 策略研究、回测                                            │
│  - 查看调仓建议                                              │
│  - 手工在券商交易系统下单                                    │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ 浏览器 (HTTP)
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                        Ditto Web UI                          │
│   Next.js 前端，展示 Regime / 回测 / 调仓 / 风控等           │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ HTTP/WS
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                        DittoPort (API/CLI/Jobs)                │
│   FastAPI：                                                  │
│   - 调用 Application Services                                │
│   - 编排引擎执行                                             │
│   - Prefect 调度（数据摄取、心跳）                           │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ 函数调用
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                    Application Services Layer                │
│   RegimeSvc / RotationSvc / BacktestSvc / RiskSvc            │
│   PortfolioSvc / FactorHealthSvc / HeartbeatSvc              │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ 调用 Engine + Data 层
                             ▼
┌──────────────────────────────────────────────────────────────┐
│   Engine + Data Layer                                        │
│   - SQLite + Parquet + DuckDB 存储                           │
│   - PIT 数据查询                                             │
│   - 复权价动态计算                                           │
│   - 外部数据源适配（Tushare/AkShare）                        │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ SDK/HTTP 请求
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                         外部系统                             │
│  - Tushare Pro / AkShare（数据）                             │
│  - 券商终端 / MiniQMT (Phase 2+ 实盘)                        │
│  - Telegram/钉钉（心跳通知）                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 分层架构

### 3.1 层次划分

| 层 | 职责 | 包/目录 |
|---|---|---|
| **Domain Layer** | 业务逻辑、领域知识、算法模型 | `packages/engine/`, `packages/kernel/`, `packages/analytics/` |
| ├── quality | 数据质量规则（OHLC、涨跌停检测） | `data/quality/` |
| ├── factor | 因子计算算法（RS、动量、波动率） | `analytics/factors/` |
| ├── ml | ML 算法实现（训练、预测、评估） | `kernel/ml/` |
| ├── risk | 风险模型（回撤检测、风险度量） | `engine/risk/` |
| ├── strategy | 策略逻辑、信号生成、执行逻辑 | `engine/alpha/` |
| ├── signal | 信号生成逻辑 | `engine/alpha/signal/` |
| └── execution | 执行逻辑（订单拆分、路由） | `engine/execution/` |
| **Infrastructure Layer** | 数据访问、存储、持久化 | `packages/data/` |
| ├── stores | 数据存储（parquet、sqlite） | `data/storage/` |
| ├── accessors | 业务聚合层 | `data/accessors/` |
| └── sources | 外部数据源适配 | `data/sources/` |
| **Application Services** | 用例编排、事务边界 | `interfaces/services/` |
| ├── ingestion | 数据摄入编排（dq 检查、存储） | `services/ingestion/` |
| ├── factor | 因子计算编排（获取、计算、保存） | `services/factor/` |
| ├── ml | ML 训练编排（特征工程、训练、部署） | `services/ml/` |
| ├── risk | 风险监控编排（监控、告警） | `services/risk/` |
| ├── trading | 交易执行编排（信号、订单、执行） | `services/trading/` |
| ├── signal | 信号管理编排 | `services/signal/` |
| └── execution | 执行编排 | `services/execution/` |
| **Port Layer** | 统一入口层（API/CLI/Jobs） | `interfaces/api\|cli\|jobs/` |
| **Foundation Layer** | 基础设施横切层 | `packages/infra/src/ditto_infra/foundation/` |
| ├── config | 配置管理 | `foundation/config/` |
| ├── observability | 可观测性 | `foundation/observability/` |
| ├── util | 通用工具 | `foundation/util/` |
| ├── cache | 通用缓存 | `foundation/cache.py` |
| ├── concurrency | 并发控制 | `foundation/concurrency.py` |
| ├── db | 数据库连接 | `foundation/db/` |
| └── version | 版本管理 | `foundation/version.py` |

### 3.2 目录结构

```
interfaces/                        # 应用入口层（API/CLI/Jobs）
  src/
    ditto_interfaces/
      api/                     # HTTP API 入口
        routes/                # FastAPI 路由
      cli/                     # CLI 入口
        commands/              # 命令实现
        utils/                 # CLI 工具
      jobs/                    # 定时任务入口
        flows/                 # Prefect Flow 定义
        tasks/                 # Prefect Task 定义
      registry/                # DI Composition Root
      main.py                  # FastAPI 启动入口

packages/
  engine/                       # 核心引擎（alpha/portfolio/backtest/execution/risk/accounting）
    src/
      ditto_engine/
  data/                         # 数据层（storage/sources/query/quality/ingestion）
    src/
      ditto_data/
  app/                          # 应用编排层（CQRS: query/process/command/builders）
    src/
      ditto_app/
  analytics/                    # 表达式编译 + 物化 + 因子 + 研究
    src/
      ditto_analytics/
  kernel/                       # 共享内核（零业务依赖类型）
    src/
      ditto_kernel/
  infra/                        # 基础设施
    src/
      ditto_infra/
        foundation/             # 纯技术组件（无领域概念）
          config/               # 配置管理
          observability/        # 可观测性
          util/                 # 通用工具
          cache.py              # 通用缓存
          concurrency.py        # 并发控制
          db/                   # 数据库连接
            sqlite_pool.py
          version.py            # 版本管理
```

### 3.3 依赖关系

```
┌─────────────────────────────────────────────────┐
│ Application Layer (interfaces/services/)         │
│                                                  │
│  IngestionService                                │
│  FactorService                                   │
│  MLTrainingService                               │
│  RiskService                                     │
│  TradingService                                  │
└─────────────────────────────────────────────────┘
         │
         ├──→ quality.QualityEngine.check()
         ├──→ factor.FactorEngine.calc()
         ├──→ ml.MLEngine.train()
         ├──→ risk.RiskEngine.check()
         ├──→ strategy.Strategy.generate_signals()
         └──→ execution.ExecutionEngine.execute_orders()
         │
         ↓ 依赖
┌─────────────────────────────────────────────────┐
│ Domain Layer (packages/engine/, packages/kernel/) │
│                                                  │
│  quality/  factor/  ml/  risk/  strategy/       │
│  （业务逻辑、算法、规则）                         │
└─────────────────────────────────────────────────┘
         │
         ↓ 依赖
┌─────────────────────────────────────────────────┐
│ Infrastructure Layer (packages/data/)        │
│                                                  │
│  stores/  accessors/  sources/             │
│  （数据访问、存储、持久化）                       │
└─────────────────────────────────────────────────┘
         │
         ↓ 依赖
┌─────────────────────────────────────────────────┐
│ Infra Layer (packages/infra/)                   │
│                                                  │
│  foundation/  runtime/                           │
│  （基础设施服务）                                 │
└─────────────────────────────────────────────────┘
```

**依赖规则**：
- ✅ Application → Domain
- ✅ Application → Infrastructure
- ✅ Domain → Infrastructure
- ✅ Infrastructure → Infra
- ❌ Infrastructure → Domain（禁止反向依赖）
- ❌ Infra → 其他层（零依赖）

**Infra Layer** 包含：
- **foundation**：纯技术组件（无领域概念）
  - **config**：配置管理（Settings、路径管理）
  - **observability**：可观测性（日志、追踪、指标）
  - **util**：通用工具（校验和、日期处理）
  - **cache**：通用缓存（DataCache）
  - **concurrency**：并发控制（FileLockManager）
  - **db**：数据库连接管理（SQLitePool）
  - **version**：版本管理（Checksum、版本标识）
- **runtime**：领域相关技术组件，依赖 data 层模型

Scripts 目录：
- **scripts**：项目脚本文件（SQL、Shell 等），与代码模块分离

### 3.4 配置文件位置

| 组件 | 配置类型 | 位置 |
|------|---------|------|
| **quality** | 业务规则 | `data_root/config/dq/*.yaml` |
| **factor** | 因子定义 | `data_root/config/factors/*.yaml` |
| **ml** | 模型配置 | `data_root/config/ml/*.yaml` |
| **risk** | 风险参数 | `data_root/config/risk/*.yaml` |

---

## 4. 核心领域模型

### 4.1 关键实体

```python
class LifecycleState(Enum):
    """策略生命周期状态"""
    RESEARCH = "research"
    PAPER = "paper"
    LIVE_SMALL = "live_small"
    LIVE_FULL = "live_full"
    DEPRECATED = "deprecated"

@dataclass
class StrategyInstance:
    """策略实例"""
    strategy_id: str
    name: str
    strategy_type: str
    lifecycle_state: LifecycleState
    risk_budget_pct: float
    config: dict

@dataclass
class Signal:
    """交易信号"""
    symbol: str
    signal_type: SignalType
    target_weight: float
    confidence: float
    reason: str

@dataclass
class RebalancePlan:
    """调仓计划"""
    plan_id: str
    trade_date: date
    strategy_id: str
    orders: list[Order]
    risk_check_result: RiskDecision
```

### 4.2 实体关系

```
Portfolio (1) ────── (N) StrategyInstance
                           │
                           │ generates
                           ▼
                      Signal (N)
                           │
                           │ aggregates to
                           ▼
                    RebalancePlan (1)
                           │
                           │ contains
                           ▼
                      Order (N)
```

---

## 5. 关键流程

### 5.1 每日数据更新（Prefect Flow）

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│Scheduler│     │  Flow   │     │   Data  │     │ Storage │
└────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘
     │               │               │               │
     │ trigger daily_ingest_flow     │               │
     │──────────────>│               │               │
     │               │               │               │
     │               │ hub.sources.tushare.fetch_xxx │
     │               │──────────────>│               │
     │               │               │               │
     │               │ hub.bars.write (with DQ L1+L2)│
     │               │──────────────>│───────────────>
     │               │               │               │
     │               │ calc_regime   │               │
     │               │──────────────>│               │
     │               │               │               │
     │ send_heartbeat│               │               │
     │<──────────────│               │               │
```

### 5.2 回测流程（含涨跌停过滤）

```
User → BacktestSvc → FastBacktester → Data Layer
           │              │               │
           │ load_data    │               │
           │─────────────────────────────>│
           │              │               │
           │ kline + factors + limit_status
           │<─────────────────────────────│
           │              │               │
           │ run          │               │
           │─────────────>│               │
           │              │               │
           │              │ for each rebalance_date:
           │              │   calc_signals
           │              │   filter_limit_locked
           │              │   apply_cost_model
           │              │   update_positions
           │              │
           │ BacktestResult               │
           │<─────────────│               │
```

### 5.3 Kill Switch 触发

```
RiskSvc → RiskEngine → KillSwitchSvc → SQLite
    │          │             │            │
    │ post_trade_check       │            │
    │─────────>│             │            │
    │          │             │            │
    │          │ calc_drawdown            │
    │          │ calc_drawdown_velocity   │
    │          │             │            │
    │          │ if 3d_drawdown > 5%:     │
    │          │   trigger Level1         │
    │          │────────────>│            │
    │          │             │            │
    │          │ elif drawdown >= 10%:    │
    │          │   trigger Level1         │
    │          │────────────>│            │
    │          │             │            │
    │          │ elif drawdown >= 18%:    │
    │          │   trigger Level2         │
    │          │             │            │
    │          │ elif drawdown >= 20%:    │
    │          │   trigger Level3         │
    │          │             │────────────>
```

---

## 6. 测试与质量门槛

### 6.1 测试类型

| 类型 | 覆盖范围 | 要求 |
|------|----------|------|
| **单元测试** | 各引擎、因子、数据管道 | 正常路径 + 边界 + 异常 |
| **集成测试** | 日常流程端到端 | Golden Case 结果一致 |
| **对齐测试** | Fast vs Production 回测 | 误差 < 0.1% |
| **风险规则测试** | Kill Switch 响应 | 各 Level 正确触发 |

### 6.2 生产就绪门槛

| 门槛 | 标准 |
|------|------|
| 对齐测试 | Fast vs Production 误差 < 0.1% |
| Walk-Forward | 平均测试 Sharpe > 0.5，稳定性 > 0.6 |
| 成本敏感性 | 3x 成本下 Sharpe > 0.3 |
| 压力测试 | 2015 股灾回撤 < 25%，2020 新冠 < 15% |

---

## 7. 质量属性

| 质量属性 | 实现方式 |
|----------|----------|
| **性能** | DuckDB 向量化查询 + FastBacktester |
| **可用性** | 单机 + 定期备份 + 心跳监控 |
| **可维护性** | 清晰分层；kernel + packages 架构；文档齐全 |
| **可测试性** | 引擎与 DataService 隔离；严格对齐测试 |
| **可扩展性** | Strategy/Factor 抽象；Portfolio 层预留 |
| **数据完整性** | PIT 查询；复权分离存储；DQ 三层校验 |

---

## 8. 未来扩展点（Phase 2–3）

### 8.1 策略层扩展

- 新增 SelectionEngine、ConvertibleBondEngine
- 多策略组合层（PortfolioEngine 启用）
- 因子墓地：记录失效因子，检测风格切换

### 8.2 实盘层扩展

- 新增 TradingSvc + BrokerAdapter（MiniQMT）
- 券商持仓为 Source of Truth
- 订单状态同步、成交回报落地

### 8.3 ML 层扩展

- MLModelEngine 用于因子权重学习
- Walk-Forward 训练期/验证期划分
- 数据版本化支持 ML 实验可复现

---

## 9. 相关文档

### 设计文档

| 文档 | 内容 |
|------|------|
| `02_data_design.md` | 数据层详细设计 |
| `03_engine_design.md` | 引擎层详细设计 |
| `04_deployment_topology.md` | 部署拓扑 |
| `05_observability.md` | 可观测性方案 |
| `07_research_playground.md` | 研究环境使用说明 |
| `09_data_quality_design.md` | 数据质量设计 |
| `10_data_ingestion_scheduler_design.md` | 数据摄取任务设计 |

### 架构规范

### 架构规范

| 文档 | 内容 |
|------|------|
| [.claude/rules/architecture.md](../../.claude/rules/architecture.md) | 架构设计规范（含子领域分层标准） |
| [.claude/rules/core.md](../../.claude/rules/core.md) | Python 核心规范 |

---

*本文档与其他设计文档共同构成 Ditto 的技术架构基础。*

**最后更新**：2026-01-17（更新分层架构，添加子领域完整定义）
