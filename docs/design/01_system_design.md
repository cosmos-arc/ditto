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
                             │ 调用 Core Engine + DataHub
                             ▼
┌──────────────────────────────────────────────────────────────┐
│   Core Engines & DataHub                                     │
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
| **Engine Layer** | 因子、Regime、轮动、回测、风控等模型与算法 | `packages/ditto-core/` |
| **Data Layer** | 数据获取、存储、PIT 查询、复权计算 | `packages/ditto-data-hub/` |
| **Application Services** | 业务服务层（无框架依赖） | `apps/port/services/` |
| **Port Layer** | 统一入口层（API/CLI/Jobs） | `apps/port/api|cli|jobs/` |
| **Web UI Layer** | 前端展示与交互 | `apps/web/` |

### 3.2 目录结构

```
apps/
  port/                      # 统一入口层（API/CLI/Jobs）
    src/
      ditto_port/
        api/                 # HTTP API 入口
          routes/            # FastAPI 路由
        cli/                 # CLI 入口
          commands/          # 命令实现
          utils/             # CLI 工具
        jobs/                # 定时任务入口
          flows/             # Prefect Flow 定义
          tasks/             # Prefect Task 定义
        services/            # 业务服务层（无框架依赖）
          ingestion/         # 摄取服务
            coordinator.py   # 摄取协调器
            backfill.py      # 回补管理器
            config/          # 配置
        main.py              # FastAPI 启动入口

  web/
    src/
      app/                   # Next.js 页面路由
      components/            # UI 组件
      stores/                # Zustand 全局状态

packages/
  ditto-core/
    src/
      ditto_core/
        indicators/        # 技术指标 MA、EMA、RSI 等
        factor/            # 因子计算
        engine/            # Regime/Factor/Backtest/Risk 引擎
        strategy/          # 策略抽象 & ETF 行业轮动实现
        portfolio/         # 组合管理 & 多策略协调
        config/            # 配置模型

  ditto-data-hub/
    config/
      dq_rules.yaml        # DQ 规则配置（L1/L2/L3 统一）
    src/
      ditto_data_hub/
        hub.py             # DataHub Facade
        sources/           # 外部数据源适配（新）
          tushare/         #   Tushare 实现
          akshare/         #   AkShare 实现
        repositories/      # 业务聚合层
        stores/            # 数据存取层
        dq/                # 数据质量引擎（新）
          engine.py        #   统一 DQ 执行引擎
          checkers/        #   L1/L2/L3 检查器
        runtime/           # 运行时支持

  ditto-foundation/
    src/
      types/               # 前后端共享 schema
      contracts/           # Data Contract 定义
```

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
│Scheduler│     │  Flow   │     │ DataHub │     │ Storage │
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
User → BacktestSvc → FastBacktester → DataHub
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
| **可维护性** | 清晰分层；core 与 apps 分离；文档齐全 |
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

| 文档 | 内容 |
|------|------|
| `02_data_design.md` | 数据层详细设计 |
| `03_engine_design.md` | 引擎层详细设计 |
| `04_deployment_topology.md` | 部署拓扑 |
| `05_observability.md` | 可观测性方案 |
| `06_roadmap.md` | 路线图 |
| `07_research_playground.md` | 研究环境使用说明 |
| `08_risk_constitution.md` | 风险宪法 |
| `09_data_quality_design.md` | 数据质量设计 |
| `10_data_ingestion_scheduler_design.md` | 数据摄取任务设计 |

---

*本文档与其他设计文档共同构成 Ditto 的技术架构基础。*
