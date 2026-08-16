# Ditto: 量化投资系统

**版本**: v0.15.0 | **更新**: 2026-05-31 | **状态**: V2 架构整改完成

## 概要

面向 A 股 ETF 的全栈量化投资平台，对标 QuantConnect LEAN 架构。13 包模块化分层设计，追求长期稳定 Alpha。

## 核心功能

- **策略引擎** — Pipeline + Stage 架构，8 个内置 Stage + 4 个策略模板（etf_rotation / etf_trend_swing / stock_sector_rotation / stock_selection_trend）
- **回测引擎** — EngineLoop 日历步进，PreTrade 6 规则 + PostTrade 4 Guard
- **执行层** — ExecutionPlanner + BacktestBrokerage + TradeBuilder + Reality Model（佣金/滑点/结算）
- **组合构建** — WeightAllocator（等权/评分/波动率倒数）+ ConstraintChecker
- **Expression DSL** — Pratt Parser 编译器，44 算子，Polars 向量化执行
- **因子评估** — IC / ICIR / Fama-MacBeth / Regime IC / Performance Attribution（`ditto ops factor-ic` 诊断 CLI）
- **数据质量** — 多源校验、PIT 安全、L1-L4 检查器
- **衍生数据** — 物化编排 + 发布安全（Shadow Diff / Certification）
- **任务调度** — Prefect 3（摄取/回填/修补/物化/发布）
- **CLI** — Typer 命令行（ditto init db / ingest / backfill / query / strategy / ops）
- **策略 API** — FastAPI 路由（策略 CRUD + 发布 + 回测结果查询 + 成交审计）
- **人工执行闭环** — 信号快照 → 交易意图 → 成交录入 → 实际持仓/P&L → 回测vs实际对比
- **交易 API** — FastAPI 路由（意图查询/成交录入/持仓查询/P&L 汇总/信号查询/对比报告）
- **Regime 识别** — 市场状态识别（BULL/BEAR/NEUTRAL），多维复合 Regime Score + 仓位调节
- **因子增强回测** — FactorBridge 桥接 Analytics 表达式编译器到回测引擎，声明式因子配置
- **Universe 管理** — 预设 + 自定义 Universe CRUD + 成分股/ETF 管理 API
- **自定义费率** — CostConfig 支持佣金/印花税/滑点可配置，API 回测触发时注入
- **T+1 交收日历** — 交易日历注入 + settlement_date 自动计算 + 持仓冻结逻辑

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│  apps (ditto_apps)                                           │
│  FastAPI API / Typer CLI / Prefect Jobs / DI Composition Root│
└───────┬──────────────┬──────────────┬───────────────┬────────┘
        │              │              │               │
        v              v              v               v
┌──────────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────┐
│ ditto_       │ │ ditto_    │ │ ditto_    │ │ ditto_data   │
│ application  │ │ features  │ │ strategy  │ │ 数据访问层    │
│ CQRS 编排    │ │ 表达式编译 │ │ 策略/信号  │ │ CQRS + PIT   │
│ query/process│ │ 因子/物化  │ │           │ │ 13+ 域服务   │
│ command/     │ │           │ │           │ │ 质量引擎     │
│ builders     │ │           │ │           │ │             │
├──────────────┤ ├───────────┤ ├───────────┤ │             │
│              │ │ ditto_    │ │ ditto_    │ │             │
│              │ │ analysis  │ │ portfolio │ │             │
│              │ │ research  │ │ 组合构建   │ │             │
├──────────────┤ │           │ ├───────────┤ │             │
│              │ │           │ │ ditto_    │ │             │
│              │ │           │ │ risk      │ │             │
│              │ │           │ │ 风控      │ │             │
├──────────────┤ │           │ ├───────────┤ │             │
│              │ │           │ │ ditto_    │ │             │
│              │ │           │ │ execution │ │             │
│              │ │           │ │ 执行      │ │             │
├──────────────┤ │           │ ├───────────┤ │             │
│              │ │           │ │ ditto_    │ │             │
│              │ │           │ │ backtest  │ │             │
│              │ │           │ │ 回测引擎   │ │             │
└──────┬───────┘ └─────┬─────┘ └─────┬─────┘ └──────┬───────┘
       │               │             │               │
       v               v             v               v
   ┌───────────────────────────────────────────────────────┐
   │  ditto_kernel          │  ditto_platform                 │
   │  零依赖共享内核         │  基础设施（零业务逻辑）        │
   │  identity/enums/clock/ │  config/db/cache/concurrency/ │
   │  events/specs          │  observability/notification   │
   └────────────────────────┴──────────────────────────────┘
```

**依赖方向**（import-linter 强制检查）：

```
apps → agent → application → capability packages
apps → application → {strategy, portfolio, risk, execution, backtest} → kernel
apps → application → data → kernel, platform
apps → features → kernel
apps → data → kernel, platform
application → data, strategy, portfolio, risk, execution, backtest, features, kernel, platform
strategy → kernel
features → kernel, platform
data → kernel, platform
```

## 项目结构

```
ditto/
├── packages/
│   ├── apps/                    # 应用入口（API / CLI / Jobs + DI）
│   │   └── src/ditto_apps/
│   │       ├── api/                 # FastAPI 路由（routes/ + utils/）
│   │       ├── cli/                 # Typer CLI（commands/ + utils/）
│   │       ├── jobs/                # Prefect 任务编排（flows/ + tasks/）
│   │       ├── models/              # API 模型
│   │       ├── registry/            # Dishka DI 容器（contexts/ + infra/）
│   │       └── config/              # 接口层配置
│   ├── agent/                   # 治理型 Agent（runtime / tools / model / audit / eval）
│   │   └── src/ditto_agent/
│   ├── application/             # 应用编排层（CQRS）
│   │   └── src/ditto_application/
│   │       ├── queries/         # 查询编排（27 Facade）
│   │       ├── processes/       # 流程编排（execution/ingestion/materialization/quality）
│   │       ├── commands/        # 命令编排（9 Handler）
│   │       ├── builders/        # DI builders
│   │       ├── runtime/         # 运行时编排
│   │       ├── config.py        # 应用配置
│   │       ├── contracts.py     # 共享契约类型
│   │       ├── execution_dto.py # 执行层 DTO
│   │       ├── providers_builder.py   # Builder Provider
│   │       ├── providers_command.py   # Command Provider
│   │       ├── providers_market.py    # 行情 Provider
│   │       ├── providers_portfolio.py # 组合 Provider
│   │       ├── providers_process.py   # Process Provider
│   │       ├── providers_strategy.py  # 策略 Provider
│   │       ├── providers.py     # Provider 注册（基础）
│   │       ├── catalog_freshness.py  # 目录新鲜度
│   │       ├── catalog_maturity.py   # 目录成熟度
│   │       └── settings.py      # 交易配置
│   ├── strategy/                # 策略定义与信号生成
│   │   └── src/ditto_strategy/
│   │       ├── alpha/           # Alpha 信号（Pipeline + 8 Stage + 4 模板）
│   │       │   ├── builtins/        # 内置 Stage
│   │       │   └── templates/       # 策略模板
│   │       ├── audit/           # 策略审计
│   │       ├── di/              # DI 注册
│   │       ├── observability/   # 可观测性
│   │       ├── runs/            # 策略运行管理
│   │       ├── signals/         # 信号存储
│   │       ├── storage/         # 策略 artifact/run/spec 存储（sqlite/）
│   │       └── events.py
│   ├── portfolio/               # 组合构建与管理
│   │   └── src/ditto_portfolio/
│   │       ├── accounting/      # 会计核算（Account/BuyingPower/Cash/Position）
│   │       ├── holdings/        # 持仓管理
│   │       ├── observability/   # 可观测性
│   │       ├── positions/       # 持仓计算
│   │       ├── rebalancing/     # 调仓（Allocation/Constraints/Comparison）
│   │       ├── target_portfolios/ # 目标组合
│   │       └── projection.py    # 组合投影
│   ├── risk/                    # 风险管理
│   │   └── src/ditto_risk/
│   │       ├── constraints/     # 预交易约束
│   │       ├── drawdown/        # 回撤规则
│   │       ├── exposure/        # 暴露分析
│   │       ├── observability/   # 可观测性
│   │       ├── kill_switch.py   # 熔断开关
│   │       ├── post_trade.py    # 盘后风控
│   │       └── pre_trade.py     # 盘前风控
│   ├── execution/               # 交易执行
│   │   └── src/ditto_execution/
│   │       ├── audit/           # 执行审计
│   │       ├── broker/          # 券商网关（gateways/）
│   │       ├── di/              # DI 注册
│   │       ├── fills/           # 成交管理
│   │       ├── observability/   # 可观测性
│   │       ├── orders/          # 订单管理
│   │       ├── reality/         # 费用模型
│   │       ├── reconciliation/  # 对账
│   │       └── storage/         # 交易 SQLite 存储（sqlite/）
│   ├── backtest/                # 回测引擎
│   │   └── src/ditto_backtest/
│   │       ├── audit/           # 回测审计
│   │       ├── observability/   # 可观测性
│   │       ├── simulation/      # 模拟执行
│   │       ├── steps/           # EngineLoop Steps
│   │       └── engine.py        # EngineLoop + Audit
│   ├── features/                # 因子与表达式计算
│   │   └── src/ditto_features/
│   │       ├── config/          # 特征配置
│   │       ├── di/              # DI 注册
│   │       ├── evaluation/      # 因子评估（evaluator/ + metrics/）
│   │       ├── expression/      # Expression DSL（lexer/parser/ast/codegen/compiler）
│   │       ├── factors/         # 因子库（15 类因子）
│   │       ├── materialization/ # 物化编排
│   │       ├── models/          # Feature/Factor/Derived 模型
│   │       ├── observability/   # 可观测性
│   │       ├── services/        # 衍生数据服务（derived/）
│   │       ├── storage/         # 存储适配（parquet/ + runtime/ + sqlite/）
│   │       ├── compile_cache.py
│   │       └── derived_types.py
│   ├── analysis/                # research control-plane（非生产路径）
│   │   └── src/ditto_analysis/
│   │       ├── di/              # DI 注册
│   │       ├── research/        # 研究数据集控制面
│   │       └── storage/         # 研究 SQLite 存储（sqlite/）
│   ├── data/                    # 数据访问层
│   │   └── src/ditto_data/
│   │       ├── catalog/         # 数据目录契约
│   │       ├── config/          # 数据层配置
│   │       ├── di/              # DI 注册
│   │       ├── errors/          # 数据层错误类型
│   │       ├── helpers/         # 辅助工具（pit/ — PIT 安全）
│   │       ├── ingestion/       # 摄取服务（游标/冻结/晚到数据/质量记录）
│   │       ├── lineage/         # 数据血缘契约
│   │       ├── models/          # 数据模型（市场/元数据/宏观/摄入/存储）
│   │       ├── observability/   # 数据可观测性指标
│   │       ├── quality/         # 数据质量（L1-L4 checkers/ + golden specs）
│   │       ├── runtime/         # 运行时（SQL/Freeze/ID 分配）
│   │       ├── scripts/         # 数据脚本
│   │       ├── services/        # 域服务（market/metadata/fundamental/macro/capital/source）
│   │       ├── sources/         # 数据源（tushare/fred/tdx/ + schemas/）
│   │       ├── storage/         # 存储引擎（Reader/Writer CQRS，按域分目录）
│   │       │   ├── base/            # 存储基类
│   │       │   ├── capital/         # 资金存储
│   │       │   ├── fundamental/     # 基本面存储
│   │       │   ├── macro/           # 宏观存储
│   │       │   ├── market/          # 行情存储
│   │       │   ├── metadata/        # 元数据存储
│   │       │   ├── runtime/         # 运行时存储
│   │       │   └── schemas/         # 存储模式定义
│   │       └── utils/           # 数据工具函数
│   ├── kernel/                  # 共享内核（零依赖）
│   │   └── src/ditto_kernel/
│   │       ├── clock.py         # 时钟抽象
│   │       ├── events.py        # 事件类型
│   │       ├── exceptions.py    # 共享异常
│   │       ├── identity.py      # 标识类型（InstrumentId）
│   │       ├── instrument.py    # 工具注册参数
│   │       ├── market.py        # 市场数据类型
│   │       ├── math.py          # 数学工具函数
│   │       ├── order.py         # 订单类型
│   │       ├── runtime.py       # 运行时内核
│   │       ├── strategy.py      # 策略规格类型
│   │       ├── synchronizer.py  # 同步器
│   │       ├── time_context.py  # 时间上下文
│   │       ├── time_semantics.py # 时间语义
│   │       ├── tracing.py       # 追踪类型
│   │       └── trading.py       # 交易类型
│   └── platform/                # 基础设施
│       └── src/ditto_platform/
│           ├── foundation/      # 基础能力（cache/checksum/concurrency/config/db/observability/storage/util）
│           └── services/        # 服务（notification — Telegram/Email/Webhook）
├── config/                      # 环境配置
│   ├── default/
│   ├── development/
│   ├── testing/
│   └── production/
├── docs/                        # 项目文档
│   ├── adr/                     # 架构决策记录
│   ├── architecture/            # 架构规范文档
│   ├── design/                  # 设计文档
│   ├── plans/                   # 实施计划
│   ├── reviews/                 # 评审文档
│   ├── research/                # 研究文档
│   ├── sprints/                 # Sprint 计划
│   ├── openapi/                 # OpenAPI 规范
│   └── operations/              # 运维手册
├── scripts/                     # 工具脚本
└── (测试在各包内: packages/*/tests/)
```

## 快速开始

### 环境要求

- Python 3.13 | Pixi | Windows/Linux/macOS

### 安装

```bash
git clone <repository-url> && cd ditto
pixi install
```

### 配置

双层环境架构 — Pixi 环境选择 + `ENVIRONMENT` 运行时变量：

| 场景 | Pixi 环境 | ENVIRONMENT | 命令 |
|------|-----------|-------------|------|
| 本地开发 | `dev` | `development` | `pixi run -e dev ...` |
| 测试 | `dev` | `testing` | `pixi run -e dev test` |
| 生产 | `default` | `production` | `pixi run server` |

Tushare token 通过 keyring 配置：

```bash
pixi run -e dev python -c "
import keyring
keyring.set_password('ditto', 'tushare', 'your_token_here')
"
```

### 启动

```bash
pixi run -e dev ditto init db   # 初始化数据库
pixi run -e dev dev              # 开发模式（热重载）
pixi run server                  # 生产模式
```

### 开发命令

```bash
pixi run -e dev check            # lint + fmt + type + test --fast
pixi run -e dev test             # 单元测试（并行）
pixi run -e dev test --integration  # 集成测试
pixi run -e dev test --fast      # 快速测试
pixi run -e dev test --snapshot  # inline-snapshot
pixi run -e dev type             # basedpyright strict
pixi run -e dev lint             # ruff 检查
pixi run -e dev lint --fix       # 自动修复
pixi run -e dev fmt              # 格式化
pixi run -e dev ci               # 完整 CI
pixi run -e dev arch-check       # 分层依赖检查
```

## 开发路线图

- **Phase 0** — 环境与数据打底 (done)
- **Phase 0.5** — 数据质量验证 (done)
- **Phase 1** — 策略引擎：Pipeline + Stage + 4 模板 (done)
- **Phase 2** — 回测闭环：EngineLoop + PreTrade/PostTrade + Reality Model (done)
- **V1 Sprint Phase 0** — EngineLoop StepChain + DecisionFrame 保护 + RunManifest 丰富化 (done)
- **V1 Sprint Phase 1** — 策略/回测 API 闭环 (done)
- **V1 Sprint Phase 2** — 人工执行闭环 (done)
- **V1 Sprint 修复** — 8 项偏差修复: Position UPSERT/T+1 日历/基准 NAV/Comparison API/Signal API/分页/乐观锁/settlement_date (done)
- **V1 Sprint Enhancement** — Regime 识别 + 因子增强回测 + Universe 管理 + 自定义费率 + 回测 artifact + 可复现性验证 (done)
- **V1 Sprint Phase 3** — Run Lineage / Replayability (done)
- **Sprint 5** — 交易 API 分页 + 成交幂等 + 偏差报告 + CORS 配置 (done)
- **V1 RC Closeout** — 6 维度代码审查修复 (done)
- **Phase 3** — 实盘接入：BrokerAdapter / 纸面交易（规划中）
- **Phase 4** — App 层提取：CQRS 编排 + DI builders + engine 独立包 (done)
- **Phase 5** — ML 增强：因子权重学习 / 多策略组合（远期规划）

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.13 |
| 数据 | polars, duckdb, parquet, sqlite |
| API | fastapi, pydantic, orjson, granian |
| 任务 | prefect 3.4+ |
| DI | dishka |
| CLI | typer |
| 可观测 | loguru, opentelemetry |
| 工具 | cachebox, tenacity, limits |
| 包管理 | pixi |
| 测试 | pytest, hypothesis, inline-snapshot |
| 质量 | basedpyright, ruff |

## 相关文档

- [AGENTS.md](AGENTS.md) — 开发规范
- [packages/strategy/AGENTS.md](packages/strategy/AGENTS.md) — Strategy 层规范
- [packages/data/AGENTS.md](packages/data/AGENTS.md) — Data 层规范
- [packages/application/AGENTS.md](packages/application/AGENTS.md) — Application 层规范
- [packages/features/AGENTS.md](packages/features/AGENTS.md) — Features 层规范
- [packages/analysis/AGENTS.md](packages/analysis/AGENTS.md) — Analysis 层规范
- [packages/platform/AGENTS.md](packages/platform/AGENTS.md) — Platform 层规范
- [packages/kernel/AGENTS.md](packages/kernel/AGENTS.md) — Kernel 层规范
- [packages/apps/AGENTS.md](packages/apps/AGENTS.md) — Apps 层规范

## 变更记录

### v0.15.0 (2026-05-31)
**V2 架构整改 — 项目最大规模重构**

**V2 架构整改路线图 46/46 任务完成（2026-04 ~ 2026-05）**
- 全模块治理：932 生产文件 / 106K LOC / 721 测试文件 / 173K 测试 LOC
- 37 个 import-linter 架构合约全绿
- `# type: ignore` 清零（from 200+ → 0）
- BaseRuntimeKernel 统一运行时核心
- `data_store` API 清理（Reader/Writer CQRS 标准化）
- `@cache` 替换 mutable globals（thread-safety）
- 可维护性拆分：策略 runs/audit、组合 holdings/positions、风控 pre_trade/post_trade/kill_switch
- Application 层 CQRS 互斥矩阵（query↔process↔command 硬隔离）

**Batch 1-6 能力包治理**
- Catalog：数据目录契约（catalog/ 新增）
- PIT：Point-in-Time 安全机制强化
- Lineage：数据血缘契约（lineage/ 新增）
- Replay：可复现性验证框架
- Quality：L1-L4 检查器 + golden specs
- Observability：全包 observability/ 子目录新增

**PR#65 Batch 1 架构整改（173 files changed）**
- type:ignore 清零
- RiskGate daily_scan 类型修复
- regime 子包提取
- PaperBrokerGateway get_account snapshot

**PR#66 22 项 Review Fix**
- BaseRuntimeKernel 统一
- data_store API 清理
- @cache 替换 mutable globals
- 可维护性拆分
- 质量/规约/文档修复
- 7594 测试全绿

**其他**
- 质量评估 Skill 上线（6 维度并行评估）
- Batch 6 AI-Ready 基础：Hypothesis 桥接点、CompositeDecisionStage、Experience Memory

### v0.14.0 (2026-04-15)
**Sprint 5 交易 API 增强 + V1 RC Closeout**
- 交易 API 分页（limit/offset 统一下沉至 SQL 层）
- 成交幂等（trade_fill UNIQUE 约束 + INSERT OR IGNORE）
- 偏差报告 API（comparison query facade 增强）
- CORS 配置（可配置允许的 origins）
- 6 维度代码审查修复（25 files, +948/-418）
- 数据源调研文档（宏观/商品/舆情增量评估）
- 全量文档审计与同步

### v0.13.0 (2026-04-13)
**V1 Sprint Enhancement — 7 项关键能力补齐**
- R1 Regime: 市场状态识别（BULL/BEAR/NEUTRAL），多维复合 Regime Score + 仓位调节
- R2 FactorBridge: 因子增强回测路径，Analytics 表达式编译器桥接到回测引擎
- R3 回测触发: POST /backtests/runs 异步触发 + 状态轮询 + 取消/重试
- R5 Universe API: 完整 CRUD + 成分管理（预设 + 自定义双模式）
- R6 CostConfig: 自定义费率配置（佣金/印花税/滑点可注入回测）
- 回测 artifact 管理 + BacktestQueryFacade 增强
- 可复现性验证（ReplayValidator + LineageQueryFacade + ManifestDiff）
- 11 项审查问题修复 + 测试增强
- 5244 测试通过，0 类型错误

### v0.12.1 (2026-04-11)
**V1 Sprint 8 项偏差修复**
- F1: Position UPSERT — INSERT OR REPLACE 消除 UNIQUE 冲突
- F2: T+1 日历注入 — MetadataService 加载交易日历到 ManualTracker
- F3: 基准 NAV — BacktestQueryFacade 提取 benchmark_return + benchmark 端点
- F4: Comparison API — ComparisonQueryFacade + GET /trade/comparison（12 指标）
- F5: settlement_date — DTO 增加 settlement_date + RecordFillHandler 自动计算
- F6: Signal API — SignalQueryFacade + GET /trade/signals/latest + /trade/signals/{date}/intents
- F7: Run 分页 — limit/offset 下沉至 SQL 层，移除 Python 切片
- F8: 乐观锁 — UpdateStrategyHandler 版本校验防并发覆盖
- 架构: ComparisonMetrics 移至 query 层消除 R8 违规（23/24 contracts kept）
- 4353 测试通过，0 类型错误

### v0.12.0 (2026-04-11)
**V1 Sprint Phase 2 人工执行闭环完成**
- 信号快照 + 交易意图推导（SignalSnapshotProcess + generate_intents）
- 人工成交录入 + 状态管理（RecordFillHandler + UpdateIntentStatusHandler）
- 实际持仓聚合（ManualTracker — T+1 交收 + 加权平均成本 + 已实现/未实现 P&L）
- 回测 vs 实际对比（ComparisonMetrics — Sharpe/Return/成本/跟踪误差 12 指标）
- 交易 API 路由（/trade/intents, /trade/fills, /trade/positions, /trade/pnl）
- 共享 DTO 迁移至 ditto_application.types（解决 R8 互斥规则 query↔process 冲突）
- DI 注册 6 个新 Provider 方法（TradeService, ManualTracker, handlers, facades）
- 114 个新测试，4272 全通过

### v0.11.0 (2026-04-11)
**V1 Sprint Phase 1 回测闭环基础完成**
- 策略 CRUD API（CreateStrategyHandler + UpdateStrategyHandler + PublishStrategyHandler）
- 回测查询 API（BacktestQueryFacade + BacktestTradeQueryFacade + RunReadModel）
- 审计扩展（trade_fill record_type + ExecutionAuditService）

### v0.10.0 (2026-04-04)
**Phase 4 App 层提取完成**
- App 层独立为 `ditto_application` 包（CQRS: query/process/command + builders）
- Engine 独立为 capability packages（从 core 拆分 strategy/portfolio/execution/backtest/risk）
- Kernel 独立为 `ditto_kernel`（零依赖共享内核: instrument/order/market/strategy/identity/clock/events/quality/research/exceptions/math）
- 目录结构扁平化：`packages/apps/` 提升至根层级，移除旧 `apps/` 目录
- DI 泄漏修复 + engine 去冗余 + 测试迁移

### v0.9.0 (2026-03-24)
**文档与架构更新**
- README 全面更新反映代码库实际状态
- 架构图、项目结构、路线图、开发命令同步

### v0.8.0 (2026-03-23)
**Gap 补齐 + 质量加固**
- RegimeStage + validate_spec_params() + RebalancePlan
- DataHub 控制面: StrategyCatalogService + StrategyArtifactService
- 62 个新测试，3849 全通过，84.82% 覆盖率

*(更早版本见 git history)*

## 免责声明

本系统仅用于学习和研究目的，不构成投资建议。量化交易存在亏损风险，过去业绩不代表未来表现。使用者需充分理解风险、自行承担损失、遵守相关法律法规。
