# Ditto V1 版本设计：控制面 + 人工执行闭环

## Context

基于 2026-04-07 架构深度审计和业界对标，Ditto 当前基础设施和策略引擎回测已高度成熟（Phase 0-5 约 95% 完成），拥有业界领先的 A 股规则建模和完整的因子引擎。项目正处于从"回测系统"向"可交易系统"跨越的关键节点。

**V1 核心目标**：打通"研究结果 → 交易意图 → 人工执行 → 偏差复盘"完整闭环，面向 ETF 行业轮动/趋势、选股轮动/趋势方向。

**V1 不做**：实盘自动执行、实时因子/行情、ML/AI 训练。

**设计原则**：
- **控制面优先**：先打通人工执行闭环，再增强研究深度
- **架构债先行**：EngineLoop 拆分和 DecisionFrame schema 保护是所有后续工作的基础
- **渐进交付**：V1 交付可交易闭环，V1.1 增强研究能力（优化/归因）

---

## 版本路线

```
V1 交付线:
  Phase 0 (Foundation): EngineLoop 拆分 + DecisionFrame schema + RunManifest 丰富化
  Phase 1 (P0):         回测闭环 — 策略 API + 回测查询 + 基准数据 + Trade 查询服务
  Phase 2 (P0):         人工执行闭环 — 信号快照 + 交易意图 + 成交录入 + 实际持仓/P&L + 回测对比
  Phase 3 (P1):         Run Lineage / Replayability

V1.1 增强线:
  Phase 4 (P2):         组合优化 — MVO / Risk Parity / 约束
  Phase 5 (P2):         参数优化 — Optuna 编排 + Walk-Forward + 过拟合检测
  Phase 6 (P3):         Regime 扩展（决策时能力）
  Phase 7 (P3):         归因分析（事后能力）
```

**依赖关系**：
- Phase 0 → 1 → 2 → 3（V1 主线，严格顺序）
- Phase 3 → 4（优化依赖 Lineage 基础设施）
- Phase 4 → 5 → 7（参数优化依赖组合优化；归因依赖优化结果）
- Phase 6 与 4-5 可并行（但建议 Phase 4 后开始）

**工作量估算**：V1 ~5,500 行新代码；V1.1 ~4,500 行新代码

**新增依赖**：
- V1：无新依赖
- V1.1：`cvxpy >= 1.5,<2`（Phase 4）、`scipy >= 1.14,<2`（Phase 4 Risk Parity）、`optuna >= 4.0,<5`（Phase 5）

> **审批提醒**：新增依赖按项目规则属于"Ask first"事项，实施前需人工确认。Phase 2 的 SQLite schema 变更同样需要审批。

---

## Phase 0: Foundation Sprint

**目标**：解决架构审计 P0/P1 项，为所有后续 Phase 打下稳固基础

### 0.1 EngineLoop 拆分

**现状**：[engine.py](packages/engine/src/ditto_engine/backtest/engine.py) 631 行单体类，`_step()` 承担 7+ 项职责（数据组装、信号计算、PreTrade、风控、审计、TradeBuilder 生命周期）。

**拆分方案**：引入 `TradingStep` chain 模式

```
EngineLoop (瘦身后):
  run()     → 日历迭代 + StepChain 调度
  _step()   → 顺序调用 Steps，不再内嵌逻辑

TradingStep Protocol:
  execute(date, context) -> StepResult

Steps（严格保持当前行为顺序，见 engine.py:330-373）:
  DataFetchStep      — Slice 获取 + 账户快照 + lock 清除
  RiskScanStep       — PostTrade 风控扫描 + 锁管理（**前置**：影响当日 planning）
  StrategyStep       — Pipeline 调用 → TargetPortfolio（仅 rebalance day）
  PlanningStep       — ExecutionPlanner → ExecutionPlan
  PreTradeStep       — 校验循环 → 过滤/resize 订单
  ExecutionStep      — 提交订单 + 处理成交
  AuditStep          — per-step 审计记录（账户快照 + closed-trade drain）
  FinalizeStep       — run 结束时 flush 未平仓交易 + 构建 RunManifest

注意（行为细节）：
  - 逐日只做 closed-trade drain（已平仓交易的匹配记录）
  - 真正的 flush() 在 run() 结束时执行（engine.py:268）
  - 如果把最终 flush 错误地塞入每步 AuditStep，会导致行为变化

注意：当前 PostTrade 扫描在 Pipeline 前执行（engine.py:330），
通过 lock_instrument() 影响 StrategyContext，进而影响 Planning。
拆分时必须保持此前置顺序，不能简单后置。
```

### 0.2 DecisionFrame Schema 保护

**现状**：[protocols.py](packages/engine/src/ditto_engine/alpha/protocols.py) `type DecisionFrame = pl.DataFrame`，零运行时保护。

**增强方案**：

```python
# 列名常量
class FrameCol:
    INSTRUMENT_ID = "instrument_id"
    SIGNAL_VALUE = "signal_value"
    SCORE = "score"
    WEIGHT = "weight"
    REASON_CODES = "reason_codes"
    RANK = "rank"

# debug-mode schema validator
def validate_frame(frame: DecisionFrame, required: tuple[str, ...]) -> DecisionFrame:
    """在 __debug__ 模式下校验必需列，release 下 no-op。"""
    if __debug__:
        missing = set(required) - set(frame.columns)
        if missing:
            msg = f"DecisionFrame 缺少必需列: {missing}"
            raise ColumnNotFoundError(msg)
    return frame
```

### 0.3 StrategySpec.params Schema

**现状**：[specs.py](packages/engine/src/ditto_engine/alpha/specs.py) `params: dict[str, object]`，无类型约束。

**增强方案**：利用已有的 `ParamConstraint` 元数据，在 `validate_spec_params()` 中增加类型校验和范围约束。

### 0.4 RunManifest 丰富化

**现状**：[manifest.py](packages/engine/src/ditto_engine/backtest/manifest.py) `input_refs: tuple[InstrumentId, ...]`，只有 instrument ID，无数据指纹。

**增强方案**：

```python
@dataclass(frozen=True)
class InputRef:
    instrument_id: InstrumentId
    data_hash: str          # 数据快照 SHA-256 前 16 hex
    date_range: str         # "2024-01-01|2024-12-31"
    source: str             # 数据源标识

@dataclass(frozen=True)
class RunManifest:
    # ... existing fields ...
    input_refs: tuple[InputRef, ...] = ()        # InstrumentId → InputRef
    universe_hash: str = ""                       # universe 解析结果哈希
    benchmark_hash: str = ""                      # benchmark 解析结果哈希
    spec_hash: str = ""                           # StrategySpec 序列化哈希
    dependency_versions: str = ""                 # 关键依赖版本 JSON
    random_seed: int | None = None                # 随机种子（用于可复现性）
```

### 新增/修改文件

| 文件 | 用途 |
|------|------|
| `packages/engine/src/ditto_engine/backtest/steps.py` | TradingStep Protocol + 7 个 Step 实现 |
| `packages/engine/src/ditto_engine/alpha/frame.py` | FrameCol 常量 + validate_frame |
| `packages/engine/src/ditto_engine/backtest/manifest.py` | InputRef + RunManifest 增强 |
| `packages/engine/src/ditto_engine/alpha/specs.py` | params 校验增强 |
| `packages/engine/src/ditto_engine/backtest/engine.py` | 瘦身重构 |

### 验收标准
- `pixi run -e dev check` + `arch-check` 全通过
- EngineLoop `_step()` 仅编排 Steps，无内嵌业务逻辑
- `validate_frame` 在 debug 模式下捕获列名错误
- RunManifest 包含 InputRef 数据指纹
- 现有回测端到端结果不变（重构不改变行为）

---

## Phase 1: 回测闭环基础 (P0)

**目标**：策略生命周期管理 API + 回测结果查询 API + 基准数据注入 + **Trade 查询服务**

> **注意**：本 Phase 工作量高于初版评估。当前 Trade 明细是 parquet 文件产物（无结构化查询），Run 查询只支持按策略 ID（无统一 read model），审计只管 risk/pre-trade（缺成交和 trade log）。需要补齐这些缺口。

### 新增文件

| 文件 | 用途 |
|------|------|
| `interfaces/src/ditto_interfaces/api/routes/strategy.py` | 策略 CRUD API |
| `interfaces/src/ditto_interfaces/api/routes/backtest.py` | 回测结果查询 API |
| `interfaces/src/ditto_interfaces/models/strategy.py` | 请求/响应模型 |
| `packages/app/src/ditto_app/command/strategy.py` | 策略 Command Handler |
| `packages/app/src/ditto_app/query/backtest.py` | 回测 Query Facade |
| `packages/app/src/ditto_app/query/backtest_trade.py` | **回测成交查询**（读 parquet + 结构化返回） |
| `packages/app/src/ditto_app/query/run.py` | **统一 Run Read Model**（跨策略查询 + 状态过滤） |

### API 端点

```
POST   /api/v1/strategies                    # 创建策略 Spec
GET    /api/v1/strategies                    # 列出所有策略
GET    /api/v1/strategies/{id}               # 获取策略详情
PUT    /api/v1/strategies/{id}               # 更新策略
POST   /api/v1/strategies/{id}/publish       # 发布策略版本

GET    /api/v1/backtests/runs                # 列出回测运行记录（支持状态/策略/时间过滤）
GET    /api/v1/backtests/runs/{id}           # 获取运行详情
GET    /api/v1/backtests/runs/{id}/report    # 获取回测报告
GET    /api/v1/backtests/runs/{id}/trades    # 获取成交明细（从 parquet 结构化查询）
GET    /api/v1/backtests/runs/{id}/audit     # 获取审计日志（扩展至含成交记录）
```

### 复用组件
- `StrategyCatalogService` — save/get/list/publish（可用，80 行薄 facade）
- `StrategyRunService`（data 层）— run 生命周期管理（需扩展查询面）
- `BacktestService`（app 层）— 完整编排（352 行，核心复用）
- `StrategyServiceFactory` — 运行时组装（348 行，可用）
- `ExecutionAuditService` — 审计持久化（需扩展 record_type 支持成交记录）
- 现有 API 路由模式（参考 [market.py](interfaces/src/ditto_interfaces/api/routes/market.py)）

### 关键缺口与修复

| 缺口 | 现状 | 修复方案 |
|------|------|---------|
| Trade 明细查询 | `write_backtest_artifacts` 写 parquet，无查询服务 | 新增 `TradeQueryFacade`：读 parquet + 返回结构化 `list[TradeRecord]` |
| Run 统一查询 | `StrategyRunService.list_by_strategy()` 只支持按策略 | 新增 `RunReadModel`：跨策略列表 + 状态/时间范围过滤 |
| 审计覆盖 | `ExecutionAuditService` 只存 risk_log / pre_trade_log | 扩展 `record_type` 支持 `trade_fill` 类型 |
| 基准 NAV | `BacktestService.build_report` 已支持 `benchmark_navs` 参数 | 补"基准 NAV 组装与注入"读模型路径，不新开 provider |

### 修改文件
- `interfaces/.../api/routes/__init__.py` — 注册新路由
- `packages/app/src/ditto_app/providers.py` — DI 注册
- `packages/data/src/ditto_data/services/audit/execution_audit_service.py` — 扩展 record_type
- `packages/engine/src/ditto_engine/backtest/statistics.py` — 成交审计记录类型
- `pixi.toml` — （无新依赖）

### 验收标准
- `pixi run -e dev check` 全通过
- 策略 CRUD 完整可用
- 回测报告/成交/审计可通过 API 查询
- 基准 NAV 通过读模型路径自动获取并注入报告
- Run 列表支持跨策略、按状态/时间范围过滤

---

## Phase 2: 人工执行闭环 (P0)

**目标**：信号快照 → 交易意图 → 人工成交录入 → 实际持仓/P&L → 回测 vs 实际对比

> 打通"研究结果 → 交易意图 → 人工执行 → 偏差复盘"是 V1 的核心用户价值，将系统从"研究工具"升级为"交易辅助工具"。

### 核心领域对象

> **放置策略**：人工执行子域的对象按三层分离：
> - **app 层 DTO**（编排边界）：`TradeIntent`、`ManualExecutionFill`、`ActualPositionSnapshot`
> - **engine 层**：`FillEvent` 不变，app 层仅在需要复用统计/聚合逻辑时做适配转换
> - **data 层 Record**（纯存储）：`*Record` 对象，app 层做双向映射

```python
# ── app 层 DTO ──────────────────────────────────────────────
# ditto_app/process/execution/types.py

@dataclass(frozen=True)
class TradeIntent:
    """交易意图 — 策略 Pipeline 输出或人工创建."""
    intent_id: str
    run_id: str
    strategy_id: str
    instrument_id: InstrumentId
    direction: Literal["buy", "sell"]
    target_weight: float
    current_weight: float
    delta_weight: float
    intent_type: Literal["system", "manual"]
    signal_snapshot_id: str
    created_at: str

@dataclass(frozen=True)
class ManualExecutionFill:
    """人工成交记录 — 独立于 engine FillEvent 的人工作执行面对象."""
    fill_id: str
    intent_id: str
    instrument_id: InstrumentId
    direction: Literal["buy", "sell"]
    quantity: float
    price: float
    commission: float
    fill_time: str
    notes: str = ""

@dataclass(frozen=True)
class ActualPositionSnapshot:
    """实际持仓快照 — 查询层返回给 API 消费者."""
    snapshot_id: str
    as_of_date: str
    positions: tuple[PositionEntry, ...]
    cash: float
    total_value: float
    source: Literal["fill_aggregate", "manual_override"]

# ── engine 层不变 ──────────────────────────────────────────
# ditto_engine.accounting.fills.FillEvent 保持原样
# FillEvent 是 "Brokerage 产出的成交事实"，字段和语义偏回测/执行内核
# 不给人工作执行面字段（intent_id / notes）污染
# app 层 ManualExecutionFill -> FillEvent 适配仅在需要复用统计逻辑时发生

# ── data 层 Record ─────────────────────────────────────────
# ditto_data/models/trade.py

@dataclass(frozen=True)
class TradeIntentRecord: ...
@dataclass(frozen=True)
class ManualExecutionFillRecord: ...
@dataclass(frozen=True)
class ActualPositionSnapshotRecord: ...
# 纯存储模型，仅标准库类型 + kernel types（InstrumentId）
```

### 新增文件

| 文件 | 用途 |
|------|------|
| `packages/app/src/ditto_app/process/execution/types.py` | TradeIntent / ManualExecutionFill / ActualPositionSnapshot DTO |
| `packages/data/src/ditto_data/models/trade.py` | *Record 纯存储模型（TradeIntentRecord / ManualExecutionFillRecord / ActualPositionSnapshotRecord） |
| `packages/data/src/ditto_data/services/trade_service.py` | Intent/Fill/Position CRUD 服务（仅操作 `*Record` 对象） |
| `packages/app/src/ditto_app/command/trade.py` | 成交录入 Command Handler |
| `packages/app/src/ditto_app/query/portfolio_actual.py` | 实际持仓/P&L 查询 Facade（Phase 2 新增） |
| `packages/app/src/ditto_app/process/execution/signal_snapshot.py` | 信号快照生成 + 交易意图推导 |
| `packages/app/src/ditto_app/process/execution/manual_tracker.py` | Fill 聚合 → 实际持仓/P&L |
| `packages/app/src/ditto_app/process/execution/comparison.py` | 回测 vs 实际对比报告 |
| `packages/app/src/ditto_app/process/execution/ports.py` | 信号推送 Protocol（定义在 app process，实现在 interfaces） |
| `interfaces/src/ditto_interfaces/api/routes/trade.py` | 成交/持仓 API |
| `interfaces/src/ditto_interfaces/services/signal_delivery.py` | 信号推送实现（Telegram/Email/Webhook） |

### 核心流程

```
策略 Pipeline → TargetPortfolio:
  1. 生成 SignalSnapshot（当前持仓 + 目标组合）
  2. 对比 → 生成 TradeIntent 列表（delta_weight ≠ 0）
  3. 推送通知（via SignalDeliveryService，Protocol 定义在 app）

人工成交录入:
  POST /api/v1/trades → TradeExecutionCommandHandler:
    1. 验证 intent_id 有效
    2. 创建 ManualExecutionFill（app DTO）
    3. 映射为 ManualExecutionFillRecord → 持久化（data 层）
    4. 触发 ManualTracker 聚合

ManualTracker (App 层 Process):
  - 从所有 Fill 聚合 → ActualPositionSnapshot
  - 计算 ActualP&L（已实现/未实现）
  - 生成 ComparisonReport（回测 vs 实际：Sharpe/Return/成本/偏离度）
```

### API 端点

```
# 信号与意图
GET    /api/v1/signals/latest             # 最新信号快照
GET    /api/v1/signals/{id}/intents       # 信号对应的交易意图

# 成交记录
POST   /api/v1/trades                     # 记录手动成交
GET    /api/v1/trades                     # 查询成交记录
PUT    /api/v1/trades/{id}                # 修改成交
DELETE /api/v1/trades/{id}                # 删除成交

# 实际持仓与对比
GET    /api/v1/portfolio/actual           # 实际持仓快照
GET    /api/v1/portfolio/actual/pnl       # 实际 P&L
GET    /api/v1/portfolio/comparison       # 回测 vs 实际对比
```

### 复用组件
- `NotificationManager` — Telegram/Email/Webhook 推送
- `Account` / `Position` — 账户模型（复用 engine 层的 AccountView）
- `AShareSettlementModel` — T+1 交收规则

### 包依赖约束

| 组件 | 所在层 | 原因 |
|------|--------|------|
| `SignalDeliveryProtocol` | `ditto_app.process.execution.ports` | 接口定义在 app process，IO 实现注入 |
| `SignalDeliveryService` | `ditto_interfaces.services` | IO 操作（发通知）在 interfaces |
| `TradeIntent` | `ditto_app.process.execution.types` | 编排边界 DTO，和 `strategy_types.py` 同级 |
| `ManualExecutionFill` | `ditto_app.process.execution.types` | 人工执行面对象，独立于 engine FillEvent |
| `ActualPositionSnapshot` | `ditto_app.process.execution.types` | 查询层 DTO，由 data Record 映射而来 |
| `FillEvent`（不变） | `ditto_engine.accounting.fills` | 回测执行内核语义，不添加人工作执行面字段 |
| `*Record` 对象 | `ditto_data.models.trade` | 纯存储模型，仅 kernel types |
| `ManualTracker` | `ditto_app.process` | 编排逻辑在 app |
| `ComparisonReport` | `ditto_app.process` | 编排逻辑在 app |

### 跨层对象映射策略（关键）

> **问题**：data 层 `trade_service.py` 不能直接操作 `TradeIntent`（app 层）或 `ManualExecutionFill`（app 层），因为 `.importlinter` 禁止 `data → app`（line 76）。

**解决方案**：data 层定义纯存储 record，app 层做双向映射：

```
ditto_data.models.trade:
  TradeIntentRecord            — 纯存储模型（仅标准库类型 + kernel types）
  ManualExecutionFillRecord    — 纯存储模型
  ActualPositionSnapshotRecord — 纯存储模型

ditto_data.services.trade_service:
  CRUD 操作仅接受/返回 *Record 对象（零 app/engine 依赖）

ditto_app.command.trade (CommandHandler):
  app TradeIntent → data TradeIntentRecord（写入映射）
  app ManualExecutionFill → data ManualExecutionFillRecord（写入映射）

ditto_app.query.portfolio_actual (QueryFacade):
  data ActualPositionSnapshotRecord → app ActualPositionSnapshot（读取映射）
```

**映射规则**：
- data 层永远只看到自己的 `*Record` 对象 + `InstrumentId`（kernel 类型）
- 所有跨层映射（app↔data, engine↔data）都在 **app 层**完成
- data 层不 import 任何 app/engine 模块

### 验收标准
- 信号推送可发送到至少一个渠道（Telegram）
- TradeIntent 从 Pipeline 输出自动生成
- 成交记录 CRUD 完整可用
- 实际持仓正确计算（含 T+1 交收）
- 回测 vs 实际对比报告含 Sharpe/Return/成本/偏离度差异
- `pixi run -e dev check` + `arch-check` 全通过

### 审批 Gate
- [ ] SQLite schema 变更（`trade_intents` / `execution_fills` / `actual_positions` 表设计）需人工审批
- [ ] 新增 API 端点设计（信号/成交/持仓）确认后开始实施

## Phase 3: Run Lineage / Replayability (P1)

**目标**：实验级复现能力 —— 相同 manifest + 相同输入 → 完全一致的 nav_series

> 不同于原"RunManifest 回放"，Phase 0 已增强 RunManifest（InputRef + universe_hash + spec_hash + random_seed），本 Phase 聚焦验证和回放机制。

### 新增文件

| 文件 | 用途 |
|------|------|
| `packages/engine/src/ditto_engine/backtest/replay.py` | 回放器 + 验证 |

### 修改文件
- `interfaces/.../api/routes/backtest.py` — 新增回放端点

### 核心设计

```python
@dataclass(frozen=True)
class ReplayValidationResult:
    is_reproducible: bool
    nav_correlation: float          # 1.0 = 完全一致
    max_nav_diff_bps: float         # 最大偏差（基点）
    manifest_diff: ManifestDiff     # 哪些字段不同
    input_data_match: bool          # 数据指纹是否一致

class ReplayValidator:
    def validate(original: RunManifest, replayed: RunManifest) -> ReplayValidationResult
    def replay(manifest: RunManifest, data_provider) -> EngineResult
```

### API 端点

```
POST   /api/v1/backtests/runs/{id}/replay     # 基于原始 manifest 重放
GET    /api/v1/backtests/runs/{id}/lineage     # 查询运行血统
```

### 验收标准
- 两次相同输入回测，nav_series 完全一致
- manifest 差异可被检测并分类报告（数据/配置/版本/随机种子）
- Lineage API 返回完整的运行血统链

---

## Phase 4: 组合优化增强 — V1.1 (P2)

**目标**：MVO + Risk Parity + 行业/因子暴露约束

**新增依赖**：`cvxpy >= 1.5,<2`、`scipy >= 1.14,<2`

### 技术选型收口

| 优化器 | 求解器 | 理由 |
|--------|--------|------|
| MVO | CVXPY | 官方聚焦凸优化/二次规划，完全匹配 |
| Risk Parity | SciPy `minimize` | 序贯二次规划，不强制绑 CVXPY，避免过度依赖 |
| 约束检查 | CVXPY constraints | 统一约束表达框架 |

### 新增文件

| 文件 | 用途 |
|------|------|
| `packages/engine/src/ditto_engine/portfolio/optimizers/__init__.py` | 模块导出 |
| `packages/engine/src/ditto_engine/portfolio/optimizers/protocols.py` | PortfolioOptimizer Protocol |
| `packages/engine/src/ditto_engine/portfolio/optimizers/mvo.py` | MVO 优化器（CVXPY） |
| `packages/engine/src/ditto_engine/portfolio/optimizers/risk_parity.py` | Risk Parity 优化器（SciPy） |
| `packages/engine/src/ditto_engine/portfolio/optimizers/constraints.py` | 行业/因子/换手约束 |
| `packages/engine/src/ditto_engine/portfolio/optimization_stage.py` | DecisionStage 适配器 |

### 包依赖约束
- 优化**算法**在 `ditto_engine.portfolio.optimizers`（纯计算）
- 优化**编排和运行**在 `ditto_app.process`（App 层注入配置）
- `cvxpy` / `scipy` 是第三方计算库，不违反 engine → 无 data/infra 依赖的约束

### 验收标准
- MVO 对 3+ 标的产生有效权重（sum=1, all≥0）
- Risk Parity 对等波动标的产生近似等权
- 行业/因子约束有效限制
- 无解时 graceful 退化
- `pixi run -e dev check` + `arch-check` 通过

---

## Phase 5: 参数优化编排 — V1.1 (P2)

**目标**：网格搜索 + 贝叶斯优化 + Walk-Forward + 过拟合检测

**新增依赖**：`optuna >= 4.0,<5`

### 技术选型收口

| 组件 | 所在层 | 说明 |
|------|--------|------|
| 算法（Grid/Bayesian） | `ditto_engine.optimization` | 纯计算封装 |
| 过拟合检测 | `ditto_engine.optimization` | 统计检验 |
| Study 持久化配置 | `ditto_app` | Optuna storage 由 app 层注入 |
| Walk-Forward 编排 | `ditto_app.process` | 长任务编排，Prefect 调度 |
| Pruner 配置 | `ditto_app` | 早停策略由 app 层注入 |

### 新增文件

| 文件 | 用途 |
|------|------|
| `packages/engine/src/ditto_engine/optimization/__init__.py` | 模块导出 |
| `packages/engine/src/ditto_engine/optimization/protocols.py` | ParamOptimizer, ObjectiveFunction Protocol |
| `packages/engine/src/ditto_engine/optimization/result.py` | OptimizationResult, TrialRecord |
| `packages/engine/src/ditto_engine/optimization/grid_search.py` | 网格搜索 |
| `packages/engine/src/ditto_engine/optimization/bayesian_search.py` | 贝叶斯优化（optuna TPE） |
| `packages/engine/src/ditto_engine/optimization/overfit_detector.py` | IS/OOS 衰减比 + Deflated Sharpe |
| `packages/app/src/ditto_app/process/optimization/walk_forward.py` | Walk-Forward 编排 |
| `packages/app/src/ditto_app/builders/optimization_factory.py` | Optuna storage/pruner 注入 |
| `interfaces/src/ditto_interfaces/api/routes/optimization.py` | 优化 API |

### 验收标准
- 网格搜索对 2x3 参数网格返回 6 个 trial
- 贝叶斯优化 50 次试验收敛
- Walk-Forward 正确划分 IS/OOS 窗口
- 过拟合检测在明显过拟合场景返回 "overfit"
- Optuna Study 持久化到 SQLite，中断后可恢复

---

## Phase 6: Regime 扩展 — V1.1 (P3)

**目标**：宏观 Regime + 市场宽度 — **决策时能力**（影响仓位/策略选择/风控阈值）

> Regime 和 Attribution 拆分为独立 Phase：Regime 是决策时能力，Attribution 是事后分析能力，生命周期和使用者不同。

### 修改文件

| 文件 | 用途 |
|------|------|
| `packages/engine/src/ditto_engine/alpha/builtins/regime.py` | 扩展多维度 |

### Regime 扩展

```
现有: MA_CROSS, VOLATILITY_THRESHOLD
新增:
  - MACRO_INDICATOR: 利率方向(LPR/MLF) + M2 同比 + CPI/PPI 剪刀差 + PMI 荣枯线
  - MARKET_BREADTH: 涨跌家数比 (A/D Ratio)

综合 Regime = f(趋势, 波动率, 宏观, 宽度)
→ {BULL, BEAR, SIDEWAY, CRISIS} × 置信度
→ 影响: 仓位比例、策略选择、风控阈值
```

### 包依赖约束

Regime 数据获取遵循 Port 注入模式：
- `MacroService`（data 层）通过 Protocol 注入到 `RegimeStage`（engine 层）
- engine 层不直接依赖 data 层
- `MacroDataProvider` Protocol 定义在 **`ditto_kernel`**（不能放 engine：`.importlinter` 禁止 data → engine）

**签名限制**：kernel Protocol 准入标准要求零外部依赖（见 kernel CLAUDE.md）。因此 `MacroDataProvider` 方法签名不能返回 `pl.DataFrame`，只能用标准库类型或 kernel 内置类型（如 `dict[str, float]`、`tuple[float, ...]`）。polars DataFrame 的组装由 Protocol 实现方（data 层）或消费方（engine 层 wrapper）负责。

### 验收标准
- 宏观 Regime 检测正确识别经济周期状态
- 市场宽度指标正确计算
- 综合信号可影响仓位比例和策略选择

---

## Phase 7: 归因分析 — V1.1 (P3)

**目标**：Brinson + 因子归因 + 交易成本归因 — **事后分析能力**

### 新增文件

| 文件 | 用途 |
|------|------|
| `packages/analytics/src/ditto_analytics/attribution/__init__.py` | 模块导出 |
| `packages/analytics/src/ditto_analytics/attribution/brinson.py` | Brinson 归因 |
| `packages/analytics/src/ditto_analytics/attribution/factor_attribution.py` | Barra 风格因子归因 |
| `packages/analytics/src/ditto_analytics/attribution/cost_attribution.py` | Implementation Shortfall |

### 归因分析

```
Brinson: allocation + selection + interaction = active_return
Factor (Barra): 因子收益贡献 + 特质收益 + R²
Cost: commission + slippage + timing = total cost (bps)
```

### 包依赖约束

- analytics 层**纯计算、零 IO**（`.importlinter` 约束）
- `MacroService`、`AShareFeeModel` 等数据获取通过 **Protocol 注入**，不直接依赖 data 层
- 归因的**编排**在 app 层，analytics 只做计算
- Protocol 定义在 **`ditto_kernel`**（不能放 app：`.importlinter` 禁止 analytics → app）

### 复用组件
- `FactorEvaluator` / `Fama-MacBeth` — 因子评估基础
- `AShareFeeModel` + `VolumeShareSlippage` — 成本计算（通过 Protocol 注入）

### 验收标准
- Brinson 归因分解数值正确（allocation + selection + interaction = active_return）
- 因子归因 R² 在合理范围
- 交易成本归因各项分解正确

---

## 跨 Phase 关注点

### importlinter 检查
- 所有新文件必须通过 `pixi run -e dev arch-check`
- Engine 层新模块不引入 data/infra 依赖（cvxpy/optuna/scipy 是第三方计算库，不违规）
- Analytics 归因模块仅依赖 kernel，数据通过 Protocol 注入
- App 层不引入 interfaces
- Signal 推送 Protocol 定义在 app process，实现在 interfaces

### DI 容器变更

| Phase | Provider | 新增 |
|-------|---------|------|
| 0 | — | EngineOptions 注入 TradingStep chain |
| 1 | AppCommandProvider | StrategyCommandHandler |
| 1 | AppQueryProvider | BacktestQueryFacade, BacktestTradeQueryFacade, RunReadModel |
| 2 | AppCommandProvider | TradeExecutionCommandHandler |
| 2 | AppQueryProvider | PortfolioActualQueryFacade |
| 2 | AppProcessProvider | SignalSnapshotProcess, ManualTracker |
| 4 | AppProcessProvider | WalkForwardOrchestrator |
| 5 | AppBuilderFactory | OptimizationFactory（Optuna storage/pruner 注入）|

### 模块名 / 类名对应关系

| 文件 | 类名 | Phase |
|------|------|-------|
| `query/backtest_trade.py` | `BacktestTradeQueryFacade` | 1 |
| `query/portfolio_actual.py` | `PortfolioActualQueryFacade` | 2 |
| `query/run.py` | `RunReadModel` | 1 |
| `query/backtest.py` | `BacktestQueryFacade` | 1 |
| `command/trade.py` | `TradeExecutionCommandHandler` | 2 |
| `process/execution/manual_tracker.py` | `ManualTracker` | 2 |
| `process/execution/ports.py` | `SignalDeliveryProtocol` | 2 |

### 测试要求
- 每个模块分支覆盖率 ≥ 80%
- 遵循 TDD（RED → GREEN → REFACTOR）
- `pixi run -e dev check` 全通过
- Phase 0 重构后：现有回测端到端测试必须通过（行为不变）

### 文件统计

| 版本 | 新增文件 | 修改文件 | 新代码 |
|------|---------|---------|--------|
| V1 (Phase 0-3) | ~22 | ~12 | ~5,500 行 |
| V1.1 (Phase 4-7) | ~20 | ~8 | ~4,500 行 |

---

## 关键文件索引

| 文件 | 重要性 | 说明 |
|------|--------|------|
| `packages/engine/src/ditto_engine/backtest/engine.py` | 核心重构 | EngineLoop 631 行单体，Phase 0 拆分目标 |
| `packages/engine/src/ditto_engine/alpha/protocols.py` | 核心重构 | DecisionFrame 零保护，Phase 0 schema 目标 |
| `packages/engine/src/ditto_engine/backtest/manifest.py` | 核心增强 | RunManifest 257 行，Phase 0/3 丰富化目标 |
| `packages/engine/src/ditto_engine/alpha/specs.py` | 核心增强 | StrategySpec params 校验，Phase 0 目标 |
| `packages/app/src/ditto_app/process/execution/backtest_process.py` | 回测编排 | BacktestService 352 行，Phase 1 复用核心 |
| `packages/app/src/ditto_app/builders/service_factory.py` | DI 组装 | StrategyServiceFactory 348 行，Phase 1 复用 |
| `packages/data/src/ditto_data/services/audit/execution_audit_service.py` | 审计扩展 | Phase 1 扩展 record_type |
| `packages/engine/src/ditto_engine/portfolio/allocation.py` | 优化适配 | Allocator Protocol，Phase 4 复用 |
| `packages/engine/src/ditto_engine/alpha/builtins/regime.py` | Regime 基础 | Phase 6 扩展目标 |
| `.importlinter` | 架构约束 | 所有 Phase 必须通过 |

## 验证方式

每个 Phase 完成后：
1. `pixi run -e dev check` — lint + type + test
2. `pixi run -e dev arch-check` — 架构约束
3. 策略模板回测端到端验证
4. 新增 API 端点通过 httpie/curl 测试
5. Phase 0 额外：现有回测结果对比（行为不变性）

## 设计决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| Phase 排序 | A: 研究优先 / B: 架构优先 / C: 闭环优先 | C | 平衡用户价值和技术债，先打通交易闭环 |
| 人工执行对象模型 | 四类 / 三类 | 三类 | ManualOrder 合并入 TradeIntent，够用不冗余 |
| Risk Parity 求解器 | CVXPY / SciPy | SciPy | 序贯二次规划足够，避免对 CVXPY 过度依赖 |
| 基准 NAV 获取 | 新建 Provider / 读模型注入 | 读模型注入 | build_report 已支持 benchmark_navs，不造轮子 |
| Optuna 集成深度 | engine 自管 / app 注入 | app 注入 | Study 持久化/Pruner 是编排关注点，不是算法 |
| analytics 数据获取 | 直接依赖 data / Protocol 注入 | Protocol 注入 | 保持 analytics 纯计算隔离 |
| DecisionFrame 保护 | 运行时校验 / debug-mode | debug-mode | 零生产开销，开发时捕获错误 |
| Signal Delivery Protocol 位置 | providers/ / ports/ / process | process/execution/ports.py | 避免 providers.py 同名冲突，与 strategy_types.py 同级 |
| 跨层 Protocol 放置 | engine / app / kernel | **统一 kernel** | importlinter 禁止 data→engine、analytics→app，只有 kernel 所有层可依赖 |
| 交易子域对象位置 | 全放 kernel / 按职责分散 | 按职责分散 | V1 期频繁调整的模型不符合 kernel"稳定性高"准入标准 |
| PostTrade 执行时机 | 后置（原始设计）/ 前置（现状） | **前置 RiskScanStep** | engine.py:330 明确在 Pipeline 前执行，影响当日 planning |
