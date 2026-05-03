---
date: 2026-03-31
topic: hybrid-plane-v2-refined
---


> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Hybrid 平面架构 v2 — 修订版需求文档

**源文档**: `docs/plans/2026-03-30-architecture-hybrid-plane-design.md`
**审查文档**: `docs/reviews/2026-03-31-hybrid-plane-v2-critical-review.md`
**参考文档**: `docs/plans/2026-03-31-ditto-future-architecture-design.md`（v3 提案）
**决策日期**: 2026-03-31

---

## Problem Frame

Ditto 架构重构设计 v2（Hybrid 平面架构）经批判性审查后，需要融合 v3 提案中的设计约束（Runtime Contract 体系、ACL 纪律、审计四分类、Query/Command/Process 互斥），补全运行时健壮性设计、里程碑验证策略、以及之前识别的 8 项补充建议，形成一份可直接进入 `/ce:plan` 的执行基线文档。

受影响方：全库架构，所有 Phase 0-5 的迁移实施。

---

## Requirements

### 架构融合决策

**R1.** 以 v2 的 5 包结构（kernel/infra/data/engine/analytics）为执行基线，不采纳 v3 的 8 包结构
**R2.** v3 的以下设计约束必须融入 v2 文档：唯一语义 owner、Runtime Contract 显式化、Query/Command/Process 互斥、审计证据四分类、Strangler 迁移优先
**R3.** `metadata` 和 `market` 统一在 `data/` 内部组织，不独立为顶层包，但用 importlinter 约束内部 owner 边界
**R4.** `apps/app/` 上升到 `packages/app/`，定位为业务包（Use Case 编排），不在 `apps/` 下
**R5.** 不独立 `integration/` 层，当前无 broker 对接需求支撑独立层的成本

> **ACL 边界说明**：不独立 integration 层时，data.sources/ 内部的 normalization 逻辑承担 ACL 职责。外部 provider 语义在 `data.sources.{tushare,fred,tdx}/normalization/` 中翻译为内部 canonical shape，不泄漏到 data.models 或更上层。

**最终模块结构**：

```text
packages/
  kernel/            # 跨层共享抽象（Clock, DataProvider, EventBus）— 14 符号
  infra/             # 基础设施（配置、日志、存储引擎、缓存、并发、通知）
  data/              # 数据平面（models + sources + storage + query + quality + ingestion）
  engine/            # 交易引擎（orchestrator + alpha + portfolio + execution + risk + accounting + backtest）
  analytics/         # 分析平面（expression + factors + evaluation + materialization + research）
  app/               # Use Case 编排（Query + Command + Process + registry）

apps/
  interfaces/        # 适配器（HTTP + CLI + Prefect Jobs）
  web/               # Web 前端（保持不变）
```

### 顶层依赖矩阵

**R6.** 依赖规则如下：

```text
interfaces → app
app         → data, engine, analytics
engine      → kernel
analytics   → kernel
data        → kernel
infra       → none
kernel      → none
```

**R7.** 禁止依赖规则：

```text
engine      -X-> data           # 通过 DataProvider Protocol 解耦
engine      -X-> app
analytics   -X-> data           # 数据由 app 层传入
analytics   -X-> app
analytics   -X-> engine
interfaces  -X-> data, engine, analytics  # 通过 app 解耦
data        -X-> engine, analytics
data.sources -X-> data.storage
data        -X-> engine, analytics
data.storage -X-> data.query
```

**R8.** `app` 内部互斥规则（可用 importlinter 强制）：

```text
Query    -X-> Command / Process    # 只读，不得触发写
Command  -X-> Query / Process      # 单次写，不得查询或编排
Process  ->  Query / Command        # 允许协调
builders -X-> query / write         # 只装配，不查询不写入
```

> **可执行性说明**：importlinter 检查模块级 import 依赖。为使 R8 可 enforce，app 必须采用 **module-per-role** 结构（如 `app/query/market.py`、`app/command/ingestion.py`、`app/process/backtest.py`），使角色边界与模块边界一致。函数调用级别的违规由代码审查保障。

### Kernel 约束

**R9.** Kernel 只保留真正跨层共享的协议：Clock、DataProvider、EventBus
**R10.** Pipeline/Stage/Context 已从 Kernel 移出，归属 Engine 和 Analytics 各自内部（强类型化）

> **注意**：当前 Pipeline/Stage/Context 在全库中零实际消费者（仅 kernel `__init__` re-export）。Phase 0.5 的实际操作是删除 kernel 中的未使用抽象，Phase 2d 在 engine 中按需重新定义强类型版本。
**R11.** Kernel 零实现约束：除 SimulatedClock、RealtimeClock、SimpleEventBus 外无业务实现
**R12.** DataProvider Protocol 返回 `AnyFrame = Any` 为已知类型安全 debt，标记在文档中，消除时机为 Phase 4 DI 容器落地后通过 runtime check 补偿

### Runtime Contract（精简为 5 个）

**R13.** Engine 侧定义 3 个顶层 Runtime Contract：

| Contract | 职责 | 定义位置 |
|----------|------|---------|
| `SessionContext` | 运行会话上下文（run_id, mode, clock, strategy_id, strategy_version, parameter_overrides） | `engine.orchestrator.context` |
| `MarketSlice` | 某时间步的市场切片（timestamp, trade_date, bars, benchmark） | `engine.orchestrator.context` |
| `AccountSnapshot` | 账户只读视图（cash, positions, frozen_quantities, pending_orders, buying_power） | `engine.accounting` |

**R14.** Research 侧定义 2 个顶层 Runtime Contract：

| Contract | 职责 | 定义位置 |
|----------|------|---------|
| `ResearchDataset` | 研究数据集（instruments, features, labels, benchmark, metadata_columns） | `analytics.research` |
| `EvaluationInput` | 评估输入（returns, benchmark_returns, exposures, grouping_metadata） | `analytics.evaluation` |

**R15.** 子模块内部定义的 contract 不上升为顶层 contract（如 AlphaOutput、PortfolioOutput、ExecutionSnapshot 由 engine 子模块内部定义）
**R16.** Runtime Contract 契约纪律：每个字段必须对应真实消费点，不允许"可能以后会用"的预埋字段

### Data 平面内部约束

**R17.** `data/` 保持统一包，但 `data/models/` 内部用 `metadata.py` + `market.py` + `common.py` 明确区分子域
**R18.** `data/query/` 作为数据平面唯一对外暴露层，内部可自由组合 metadata + market 查询
**R19.** `data.storage.*` 不直接 import `data.models.*` 的跨子域模型，通过 query 层中转（importlinter 约束）
**R20.** `data.sources` 和 `data.storage` 通过 `data.ingestion` 连接，不直接依赖

> **菱形依赖说明**：`data.ingestion` 同时依赖 `data.sources`（读原始数据）和 `data.storage`（写 canonical 数据），形成 sources → ingestion ← storage 的菱形。这是 **intentional** — ingestion 是 sources 和 storage 之间的唯一集成点。R20 禁止 sources→storage 直连是为了确保所有数据变换必须经过 ingestion 的校验和标准化管道。
**R21.** `data.ingestion = 领域关注点`（数据变换、校验、写入）；`app.ingestion = 过程关注点`（调度、重试）

### TradingOrchestrator 设计

**R22.** Engine 编排模型为 TradingOrchestrator（命令式），不是线性 Pipeline
**R23.** 每日循环流程（9 步）：获取数据切片 → 获取账户快照 → PostTrade 风控 → [调仓日] 策略 Stage 链 → ExecutionPlanner → PreTrade 校验 → place_order → process_pending → 审计记录
**R24.** Orchestrator 支持条件分支（PostTrade 可锁定标的、PreTrade 可阻断订单）、状态突变（Account 通过 Brokerage 变更）、非每日执行（调仓日判断）、反馈回路（成交影响下一交易日状态）
**R25.** 状态管理沿用 Brokerage owner 模式：Brokerage 拥有 Account，各 Stage 只拿 AccountView（frozen 只读快照）
**R26.** 策略 Stage 链（AlphaStage → PortfolioStage）内部可用 Engine 内部 Pipeline 纯函数组合

### 运行时健壮性

**R27.** TradingOrchestrator 异常策略：某 Stage 异常时 abort 当天循环、写入审计记录（记录异常 Stage + 时间步 + 错误信息）、下一交易日继续

> **正确性注意**：abort 当天意味着 Portfolio 不调整。审计记录（R33 Decision Evidence）必须区分"无需调仓"和"因错误跳过"。回测报告需在 Result Evidence 中标注跳过的交易日。
**R28.** EventBus handler 基础隔离：每个 handler 独立 try/except 包裹，异常只 log（loguru）不传播，确保一个 handler 失败不阻断后续 handler
**R29.** Brokerage.process_pending() 部分成交（partial fill）视为正常业务流程，不触发 abort

### DomainEvent 设计

**R30.** 事件定义归属：kernel（DomainEvent 基类 + EventBus Protocol + SimpleEventBus）、engine（OrderSubmitted, OrderFilled, OrderCanceled, PositionChanged, RiskGuardTriggered）、data（DataIngested, QualityCheckCompleted）
**R31.** 当前不做异步事件分发、不持久化事件、不跨进程、不引入消息队列
**R32.** 实时流扩展策略：不改现有协议，通过 Protocol 继承 + 实现扩展演进（Phase 5 后按需）

### 审计四分类

**R33.** 每次回测至少可重建 4 类审计证据：
- **Input Evidence**：数据集版本、规则版本、参数覆盖、session 配置
- **Decision Evidence**：信号输出、目标头寸、风控调整、订单规划
- **Execution Evidence**：委托、成交、费用、账户变化
- **Result Evidence**：report、attribution、artifact URI、run manifest hash

### Analytics 平面约束

**R34.** analytics 是纯计算包，不依赖 DataProvider，所有数据由调用方（app 层）传入
**R35.** `analytics/expression/` 和 `analytics/evaluation/` 内部纯函数，零 I/O
**R36.** `analytics/compile_cache.py` 是唯一引入 I/O 的模块（SQLite + cachebox），作为编译器的可选外层（decorator 模式），expression 核心编译链不直接依赖

---

## Success Criteria

- [ ] v2 文档融合 v3 设计约束 + 8 项补充建议 + 运行时健壮性 + 里程碑验证策略
- [ ] 所有 Runtime Contract 有明确归属（位置 + 消费点）
- [ ] 每个 Phase 有功能级回归验证方案（不仅仅是 `pixi check`）
- [ ] 类型安全 debt（AnyFrame）有消除时机和方案
- [x] datahub 迁移前有逐子目录归属标记
- [ ] importlinter 规则覆盖所有新增约束（app 互斥、data 内部 owner 边界）

---

## Scope Boundaries

- **不纳入**：v3 的 8 包结构（metadata/market 独立、integration 独立）
- **不纳入**：三级缓存 L1/L2/L3（当前只有 compile_cache 需要缓存）
- **不纳入**：异步事件分发、Event Sourcing、消息队列
- **不纳入**：微服务化
- **延迟到 Phase 3-4**：data/ 是否拆分为 metadata + market（视纠缠程度决定）
- **延迟到 broker 对接需求出现**：独立 integration 层、LiveOrchestrator

---

## Key Decisions

- **v2 为执行基线**：5 包结构对应当前体量，不过度模块化。v3 的设计约束作为纪律文档融入。
- **data 统一不拆**：metadata/market 的纠缠是实现层面交叉访问，不是概念混淆。用 importlinter 内部约束 + query 统一对外暴露解决。
- **app 上升到 packages/**：app 是业务包（有依赖、有 DI、有业务逻辑），不是部署入口。部署入口是 interfaces/。
- **Runtime Contract 精简为 5 个**：engine 侧 3 个（SessionContext, MarketSlice, AccountSnapshot）+ research 侧 2 个（ResearchDataset, EvaluationInput）。子模块内部 contract 不上升。
- **Orchestrator 异常 = abort + 审计**：简单可靠，适合当前回测场景。未来实盘可演进为可配置策略。
- **EventBus 基础隔离**：成本极低（try/except + log），防止级联故障。
- **类型安全 debt 显式管理**：DataProvider 返回 AnyFrame 是已知 debt，消除时机为 Phase 4。

---

## Datahub 子域归属审计表

> 以下为 2026-03-31 完成的 datahub 逐子目录归属标记，作为 Phase 2+ 迁移的输入。

### 明确归属 data 的模块（~150 文件）

| 模块 | 目标位置 | 说明 |
|------|---------|------|
| `models/common.py, metadata.py, market.py, macro.py, source_codes.py, enums.py, storage.py, ingestion.py` | `data.models/` | 数据模型（不变） |
| `config/` | `data.config/` | 数据层配置 |
| `stores/base/` | `data.storage.base/` | 基础存储抽象 |
| `stores/market/` | `data.storage.market/` | 行情存储 |
| `stores/metadata/` | `data.storage.metadata/` | 元数据存储 |
| `stores/fundamental/` | `data.storage.fundamental/` | 基本面存储 |
| `stores/capital/` | `data.storage.capital/` | 资金数据存储 |
| `stores/macro/` | `data.storage.macro/` | 宏观数据存储 |
| `stores/schemas/` | `data.storage.schemas/` | 存储 Schema |
| `stores/sqlite_client.py` | `data.storage/` | SQLite 客户端 |
| `sources/` | `data.sources/` | 外部数据源适配器 |
| `services/{market,metadata,fundamental,capital,macro}_service.py` | `data.services/` | 数据服务 |
| `services/metadata/` | `data.services.metadata/` | 元数据子服务 |
| `services/{ingestion_log,cursor,quality_record,freeze,late_arrival,source}.py` | `data.services/` | 数据管道服务 |
| `query/` | `data.query/` | 查询层（不变） |
| `runtime/freeze_manager.py` | `data.storage/` | 数据版本管理 |
| `runtime/instrument_id_allocator.py` | `data.storage/` | ID 分配 |
| `stores/runtime/quality/` | `data.quality/` | 质量追踪 |
| `stores/runtime/ingestion/` | `data.ingestion/` | 摄取状态 |

### 迁移到 engine 的模块（~55 文件）

| 模块 | 目标位置 | 说明 |
|------|---------|------|
| `models/strategy.py, strategy_run.py, strategy_audit.py` | `engine.alpha/` | 策略域模型 |
| `models/portfolio.py, trading.py` | `engine.portfolio/` / `engine.accounting/` | 执行域模型 |
| `models/derived.py, publication_safety.py` | `engine.materialization/` | 衍生计算模型 |
| `services/strategy/` (4 files) | `app.backtest/` | 策略编排服务（Process 层） |
| `services/audit/execution_audit_service.py` | `engine.backtest.audit/` | 执行审计 |
| `services/derived/` (10 files) | `app.materialization/` | 衍生物化编排（Process 层） |
| `services/derived_catalog_service.py` | `app.materialization/` | 衍生目录服务 |
| `services/derived_shadow_slot_service.py` | `app.materialization/` | 发布安全服务 |
| `runtime/sql_engine.py` | `data.query/` 或保留 `data.runtime/` | SQL 查询引擎（依赖 data 存储，R7 约束下不能进 engine） |
| `helpers/adjustment.py` | `data.helpers/` | 复权计算（依赖 data 存储） |
| `helpers/pit/dataframe.py, sql.py` | `data.helpers/` | PIT 工具（依赖 data 存储） |
| `stores/runtime/derived_sqlite/` | `data.storage.runtime/` | 衍生 SQLite 存储 |
| `stores/runtime/research_sqlite/` | `data.storage.runtime/` | 研究 SQLite 存储 |
| `stores/runtime/publication_shadow_sqlite/` | `data.storage.runtime/` | 发布安全 SQLite 存储 |
| `stores/runtime/publication_safety/` | `data.storage.runtime/` | 发布安全存储 |
| `stores/runtime/derived_artifact_writer.py` | `data.storage.runtime/` | 衍生产物写入 |

> **关键约束**：`runtime/sql_engine.py`、`helpers/`、`stores/runtime/` 中的模块依赖 data 存储基础设施。R7 禁止 engine→data，因此这些模块不能进入 engine 包。保留在 `data/` 内部，作为 data 平面的计算基础设施。

### 迁移到 analytics 的模块（~15 文件）

| 模块 | 目标位置 | 说明 |
|------|---------|------|
| `models/factors.py, features.py` | `analytics.factors/` | 因子/指标元数据 |
| `stores/factors/` | `data.storage.factors/` | 因子存储（依赖 data 存储，保留 data） |
| `stores/features/` | `data.storage.features/` | 指标存储（依赖 data 存储，保留 data） |
| `models/research.py` | `analytics.research/` | 研究元数据 |
| `services/research_artifact_service.py` | `analytics.research/` | 研究产物 I/O |
| `services/research_catalog_service.py` | `analytics.research/` | 研究目录服务 |
| `services/forward_return_service.py` | `analytics.evaluation/` | 前收计算 |

> **关键约束**：`stores/factors/` 和 `stores/features/` 依赖 data 存储基础设施，保留在 data.storage 下。analytics 包通过 DataProvider / app 层获取因子数据，不直接依赖存储实现。

### 迁移到 kernel 的模块（1 文件）

| 模块 | 目标位置 | 说明 |
|------|---------|------|
| `helpers/pit/policy.py` | `kernel.pit` | PIT 安全常量（跨平台契约） |

### 迁移到 infra 的模块（~5 文件）

| 模块 | 目标位置 | 说明 |
|------|---------|------|
| `stores/runtime/unit_of_work.py` | `infra.transaction` | 通用事务模式 |
| `services/hot_layer/` | `infra` | 热层协议（Phase 5+） |
| `utils/` | `infra` | 时区等通用工具 |

### 迁移到 app 的模块

| 模块 | 目标位置 | 说明 |
|------|---------|------|
| `scripts/` | `app` | 运维脚本 |

---

## Dependencies / Assumptions

- Phase 0/1 已完成（Kernel 扩展 + Data 平面 query 层收拢），但 Phase 1 有未完成项（DataFeed 旧路径未清理、Golden test 缺失）
- Phase 0.5（Pipeline 移出 + Provider 合并）尚未开始
- datahub 子域归属审计已完成（见上方归属表），迁移文件分布：data ~150, engine ~55（其中 ~40 因 R7 约束保留在 data 内部）, analytics ~15, kernel 1, infra ~5

---

## Outstanding Questions

### Deferred to Planning

- [R12][Technical] DataProvider AnyFrame 消除方案：Phase 4 DI 容器落地后，是否可用 runtime type check（如 beartype）补偿？还是需要 Provider 也移出 Kernel？倾向方案：beartype 的 `@beartype` decorator 可以在运行时校验 Protocol 返回值是否为 `pl.DataFrame`，但 Python Protocol 的 structural subtyping 不保证 runtime contract。更可靠的路径是 Phase 4 后将 DataProvider Protocol 本身也移至 data/（消费者都在 data 层），Kernel 只留 Clock + EventBus。
- [R17-R19][Technical] data/ 内部 importlinter 约束的具体规则设计：哪些模块可以跨 metadata/market 子域访问？
- [R36][Technical] compile_cache 与 expression 核心的解耦方式：decorator 注入 vs 显式可选参数？
- [Needs research] Phase 2 Pipeline 移入 engine 时 polars 依赖的影响范围评估

### Deferred to Later Phases

- [R3][Technical] data/ 是否拆分为 metadata + market — Phase 3-4 视纠缠程度决定
- [R5/ACL][Technical] 无独立 integration 层时，data.sources/ 的 ACL 边界如何 enforce — 当前由 data.sources 内部 normalization 逻辑承担
- [R27][Technical] Orchestrator 可配置异常策略 — 实盘需求出现时
- [Migration][Technical] datahub `stores/` → `data.storage/` 重命名何时执行、影响范围评估
- [Migration][Technical] datahub→data 整体包名重命名在哪个 Phase 执行

---

## 里程碑验证策略

### Phase 0.5（Pipeline 移出 + Provider 合并，3 PR）

| 验证项 | 方法 | 通过标准 |
|--------|------|---------|
| Kernel 导出正确 | `pixi run -e dev type --all` | Pipeline/Stage/Context 从 `ditto_kernel/__init__.py` `__all__` 移除，`pipeline.py` 删除，对应测试删除或迁移到 engine/analytics |
| Provider 合并正确 | `pixi run -e dev test` | 原有 BacktestProvider/LiveProvider 测试全部迁移到 DataProviderAdapter |
| 无破坏性变更 | `pixi run -e dev check` | lint + type + test 全通过 |
| Kernel 依赖不变 | `pixi run -e dev arch-check` | importlinter kernel-zero-dep 通过（移出后 kernel 仍无外部依赖） |

### Phase 1 补完（2-3 PR）

| 验证项 | 方法 | 通过标准 |
|--------|------|---------|
| DataFeed 统一 | grep `ParquetDataFeed` 返回 0 结果 | 旧路径完全清理 |
| Core 依赖收敛 | `pixi run -e dev arch-check` | importlinter core-must-not-depend-on-datahub 通过 |
| 回测行为不变 | golden test（回测 1 年 ETF 等权重策略） | 输出指标（年化收益、最大回撤、夏普）与基线一致 |
| 中间态架构约束 | `pixi run -e dev arch-check` | DataFeed 清理后 core 对 datahub 依赖仅剩 query/（Phase 2 迁移前允许） |

### Phase 2（Engine 平面成型，~8 PR）

| 验证项 | 方法 | 通过标准 |
|--------|------|---------|
| 子域迁出正确 | `pixi run -e dev check` | 每个 PR 都全通过 |
| import 迁移完整 | `grep -r "ditto_kernel.engine" packages/ apps/` | 返回 0 结果（Phase 2b 完成后） |
| 包名重命名正确 | `grep -r "ditto_kernel" packages/ apps/ --include="*.py"` | 返回 0 结果（Phase 2c 完成后） |
| 功能完整 | 集成测试：回测 + 策略 + 因子计算 + 评估 | 全部通过 |
| 类型安全 | `pixi run -e dev type --all` | 新的 engine.orchestrator 强类型 Stage 契约无 Any |
| EventBus 隔离 | 单元测试：handler 异常不阻断后续 handler | SimpleEventBus handler try/except 隔离生效 |
| Orchestrator 异常处理 | 单元测试：Stage 异常 → abort + 审计记录 | abort 行为 + 审计记录写入 |
| 中间态架构约束 | `pixi run -e dev arch-check` | 中间态 importlinter 通过（R7 禁止依赖 + R8 互斥规则） |

### Phase 3（Analytics 平面收尾 + datahub engine 域模块迁出，~5 PR）

> Phase 3 是 datahub→data 迁移的核心阶段，处理归属表中标注为 engine/analytics 的模块。

| 验证项 | 方法 | 通过标准 |
|--------|------|---------|
| analytics 包自包含 | `pixi run -e dev type --all` | analytics 内部无 datahub import |
| engine 域模型迁出 | `grep -r "ditto_data.models.strategy\|ditto_data.models.portfolio\|ditto_data.models.trading" packages/ apps/` | 返回 0 结果 |
| strategy 服务迁出 | `grep -r "ditto_data.services.strategy" packages/ apps/` | 返回 0 结果 |
| 因子/研究模块迁出 | `grep -r "ditto_data.models.factors\|ditto_data.models.research\|ditto_data.models.features" packages/ apps/` | 返回 0 结果（stores/factors 保留在 data） |
| 功能完整 | 因子计算 + 评估 + 衍生物化集成测试 | 全部通过 |
| 架构约束 | `pixi run -e dev arch-check` | engine -X-> data 规则通过（中间态 importlinter） |

### Phase 4（Application 层提炼，~7 PR）

| 验证项 | 方法 | 通过标准 |
|--------|------|---------|
| DI 容器正确 | 启动应用 + 全部 HTTP 端点 smoke test | 无 DI 解析错误 |
| 功能不变 | 全量 CLI 命令 + HTTP 端点 + Prefect Jobs | 与迁移前行为一致 |
| 旧路径清理 | `grep -r "ditto_interfaces" packages/ apps/ --include="*.py"` | 返回 0 结果 |

### Phase 5（固化，~4 PR）

| 验证项 | 方法 | 通过标准 |
|--------|------|---------|
| 架构规则 | `pixi run -e dev arch-check` | importlinter 全部通过（含新增规则） |
| 完整 CI | `pixi run -e dev ci` | 全通过 |
| 文档同步 | 人工检查所有 CLAUDE.md | 反映最终架构 |

---

## 补充建议清单（已融入本文档）

| # | 建议内容 | 融入位置 | 状态 |
|---|---------|---------|------|
| S1 | DataProvider AnyFrame 类型安全 debt 显式管理 | R12 | ✅ |
| S2 | datahub 迁移前逐子目录归属标记 | Datahub 子域归属审计表 | ✅ |
| S3 | Phase 0.5 Pipeline 移入 core 时 polars 依赖影响 | Outstanding Questions | ✅ |
| S4 | compile_cache 归属为 analytics 内部基础设施 | R36 | ✅ |
| S5 | TradingOrchestrator 异常处理策略 | R27 | ✅ |
| S6 | EventBus handler 基础隔离 | R28 | ✅ |
| S7 | 每个 Phase 的回归测试策略 | 里程碑验证策略 | ✅ |
| S8 | v2/v3 关系明确定位 | Key Decisions | ✅ |

---

## Next Steps

→ `/ce:plan` for structured implementation planning（Phase 0.5 开始）
