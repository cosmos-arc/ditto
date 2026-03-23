# 日频策略引擎完整设计

**日期**: 2026-03-20
**状态**: Draft
**范围**: `packages/core/src/ditto_core/strategy` / `packages/core/src/ditto_core/portfolio` / 策略运行控制面与 artifact-first 持久化契约
**背景文档**:
- `docs/plans/2026-03-19-daily-strategy-platform-gap-design.md`
- `packages/core/src/ditto_core/engine/README.md`
- `docs/design/unified-feature-factor-engine/main-design.md`

---

## 1. 目标与边界

本文档完成 Ditto 在“日频研究 / 回测 / 调仓建议”主线下的**策略引擎完整设计**。目标不是再写一套抽象 README，而是定义一组能直接落成 Core/Port/DataHub 分层实现的正式契约。

本次设计覆盖：

- `StrategySpec` 及其模板化建模
- `StrategyRun`、artifact、状态治理
- `Universe → Signal → Score → Regime → Filter → Select → Allocate → Risk → Execute → Output` 主链
- `SignalSnapshot / TargetPortfolio / RebalancePlan` 三类一等输出对象
- 与现有 `DerivedSpec`、research snapshot、artifact-first、`PUBLISHED` 治理的对接

明确不纳入当前实现主线：

- 实时信号在线服务
- Broker / OMS / 实盘订单回报
- 分钟级 `grain="1m"` 主路径
- 多策略资金预算优化器
- 通用二次规划/凸优化投资组合求解器

一句话总结：

> **Ditto 的策略引擎应采用“信号表达式优先 + 编排声明式优先 + Python 逃生舱保留 + artifact-first 治理”的混合范式，并以单策略日频闭环为 V1 主线。**

---

## 2. 业界调研结论与 Ditto 取舍

本次设计只采纳了一手资料中的稳定共识，而不是追逐零散博客结论。

### 2.1 业界共同模式

| 业界来源 | 稳定模式 | 对 Ditto 的启发 |
|---------|----------|----------------|
| QuantConnect Algorithm Framework | 把 Alpha / Portfolio Construction / Risk / Execution 拆为清晰阶段，以 `Insight` 作为一等信号对象，并强调只对 Universe 中资产发信号 | 策略引擎必须阶段化；信号对象必须带方向、置信度、权重/期限等元数据；Universe 不能硬编码在策略实现里 |
| QuantConnect Insight Manager | 活跃信号要有生命周期管理、取消、过期、跨部署恢复 | `SignalSnapshot` 不能只是临时 DataFrame，必须有 run 级身份、过期/覆盖语义、可追踪来源 |
| Qlib Strategy + Workflow + Recorder | 策略、回测、记录模板、实验跟踪放在统一工作流里；回测配置和策略配置结构化；运行产物标准化归档 | `StrategyRun` 必须是一等控制面对象；策略实验、回测结果、推荐结果必须按 run 归档，而不是散落脚本输出 |
| VectorBT | 研究路径强调“一个策略实例 = 一组列”，支持多参数、多资产、多窗口批量运行 | Ditto 的日频研究主链应优先选择 DataFrame/向量化风格，不把 Core 设计成面向对象逐 bar 回调系统 |
| Feast | version-controlled definitions、registry、materialize、offline truth、PIT dataset retrieval | `StrategySpec` 也要进入版本治理；策略运行必须冻结输入版本与 snapshot 引用 |
| dbt | artifact、manifest、run result、state-aware orchestration | `StrategyRun` 需要完整 artifact 清单、manifest/hash、状态感知重跑与差异比较基础 |
| WorldQuant / 101 Formulaic Alphas | 表达式化 alpha 便于组合、序列化、版本化；alpha 池低相关比“单一巨型策略”更重要 | Ditto 的 signal 层应最大化复用现有表达式引擎，但不要把整个策略平台退化为单条公式 |

### 2.2 设计决策

最终采用以下取舍：

1. **混合范式，而非纯表达式或纯过程式**
   - Signal 层表达式优先
   - Pipeline 层声明式优先
   - 每个阶段都保留 Callable 逃生舱

2. **DataFrame 作为计算语言，而不是对象爆炸**
   - Core 中间态以 Polars `DataFrame` 为主
   - 只有控制面对象和最终输出对象采用 dataclass

3. **artifact-first，而不是控制表塞大对象**
   - 大体量信号/持仓/交易明细落 Parquet/JSON artifact
   - SQLite/metadata 只保存可检索摘要与引用

4. **单策略闭环优先，多策略预算留口**
   - V1 先打通一条策略从研究到推荐的完整链
   - 多策略 Risk Budget 层在接口上预留，不抢当前主线

---

## 3. 顶层架构与层边界

### 3.1 分层定位

策略引擎的推荐边界如下：

```text
Port
  ├─ Strategy Definition / Run Application Service
  ├─ Strategy Input Assembler
  ├─ Strategy Artifact Persistence Service
  └─ Strategy API / Jobs / Web

Core.strategy
  ├─ StrategySpec / StrategyRun / Context / Protocols
  ├─ Pipeline Runner
  ├─ Universe / Signal / Score / Select builtins
  └─ 纯计算、纯规则、无 I/O

Core.portfolio
  ├─ Allocate / RiskSizer / Constraint / Rebalance / Cost builtins
  └─ 纯计算、纯规则、无 I/O

Core.backtest
  └─ 消费 TargetPortfolio / RebalancePlan 做日频回测

DataHub
  ├─ Strategy registry / run catalog / artifact metadata
  ├─ Strategy artifact persistence
  └─ 输入 snapshot / published derived version 查询
```

### 3.2 核心边界规则

1. `Core.strategy` / `Core.portfolio` 不直接读取 Store，不直接访问文件系统。
2. `Port` 负责拼装 `StrategyInputBundle`，把所有输入冻结后交给 Core。
3. `DataHub` 负责策略 spec/run/artifact 元数据与 artifact 落盘。
4. `Backtest` 是策略运行模式之一，但不反向污染 `StrategySpec` 语义。

这与现有 `DerivedSpec + materialize/publish + research snapshot` 模式保持一致，不额外制造第二套运行治理体系。

---

## 4. 核心设计原则

### 4.1 Strategy as Specification

策略不是脚本入口，而是版本化的正式规格。每次研究、回测、推荐都必须绑定：

- `strategy_id`
- `strategy_spec_version`
- 输入快照引用
- 参数覆写
- 产物引用

### 4.2 Signal First, Portfolio Second

策略引擎主链必须先明确：

```text
候选标的 -> 原始信号 -> 综合评分 -> 选入集合 -> 初始权重 -> 风险缩放 -> 目标仓位 -> 调仓计划
```

不要把“生成买卖列表”的过程写成一个黑箱函数。

### 4.3 DataFrame as Domain Language

Ditto 已明确采用 Polars 作为主数据语言，因此策略引擎中间态统一采用长表风格：

- `trade_date`
- `instrument_id`
- `signal_*`
- `composite_score`
- `selected`
- `target_weight`
- `reason_codes`

避免在 Core 里生成大量一次性 Python 对象树。

### 4.4 Explainability by Construction

每一个过滤、选择、缩放、削减动作都必须留下可解释痕迹，而不是事后靠日志猜测。

### 4.5 Draft-Friendly, Recommendation-Safe

- Lab/研究运行允许针对 `DRAFT` spec 做实验
- 调仓建议/调度运行默认只允许 `PUBLISHED` spec

这样既不牺牲研究效率，也不破坏推荐链路的治理纪律。

---

## 5. 统一语义对象

## 5.1 `StrategyTemplate`

`StrategyTemplate` 不是策略本身，而是可被 UI/API/脚手架消费的预配置蓝图。

推荐字段：

```python
@dataclass(frozen=True)
class StrategyTemplate:
    template_id: str
    name: str
    description: str
    asset_class: str
    required_params: tuple[str, ...]
    default_spec: "StrategySpec"
```

V1 模板：

- `etf_rotation`
- `etf_trend_swing`
- `stock_selection_trend`

模板输出的最终结果仍然必须是**具体化后的 `StrategySpec`**，真正进入版本治理的是 `StrategySpec`，而不是模板参数本身。

## 5.2 `StrategySpec`

`StrategySpec` 是策略定义的根对象。

```python
@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    version: int
    name: str
    template_id: str | None
    asset_class: str
    calendar: CalendarId = "cn_stock"
    grain: GrainId = "1d"
    universe: UniverseSpec
    signals: tuple[SignalSpec, ...]
    scorer: ScorerSpec
    regime_overlay: RegimeOverlaySpec | None = None
    filters: tuple[FilterSpec, ...] = ()
    selector: SelectorSpec = field(default_factory=SelectorSpec)
    weight_allocator: WeightAllocatorSpec = field(default_factory=WeightAllocatorSpec)
    risk_sizer: RiskSizerSpec = field(default_factory=RiskSizerSpec)
    constraints: tuple[ConstraintSpec, ...] = ()
    execution: ExecutionSpec = field(default_factory=ExecutionSpec)
    benchmark: str | None = None
    tags: tuple[str, ...] = ()
    description: str | None = None
```

关键决策：

1. `StrategySpec` 只描述“如何决策”，不描述 artifact 路径、运行日志等控制面信息。
2. `StrategySpec` 不直接持有 DataHub/Store 依赖。
3. `StrategySpec` 中允许声明式和命令式混用，但默认推荐内置方法名或可序列化引用。

## 5.3 `StrategyVersion`

策略规格本身也应有状态治理。

```python
class StrategyVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
```

规则：

- `DRAFT`: 允许 Lab / 手动 run
- `PUBLISHED`: 允许推荐任务、标准回测、模板复用
- `DEPRECATED`: 不允许新建默认 run，但保留历史查询
- `ARCHIVED`: 仅用于历史审计

## 5.4 `StrategyRun`

`StrategyRun` 是策略实验与执行控制面的根对象。

```python
class StrategyRunMode(StrEnum):
    RESEARCH = "research"
    BACKTEST = "backtest"
    RECOMMENDATION = "recommendation"


class StrategyRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class StrategyRun:
    run_id: str
    strategy_id: str
    strategy_version: int
    spec_status: StrategyVersionStatus
    mode: StrategyRunMode
    trigger: str
    start: str
    end: str
    asof: str
    benchmark_id: str | None
    baseline_run_id: str | None
    input_refs: tuple["StrategyInputRef", ...]
    parameter_overrides: dict[str, str | int | float | bool]
    metrics_summary: dict[str, float | str]
    status: StrategyRunStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None
```

关键字段解释：

- `spec_status`: 记录 run 使用的是 `DRAFT` 还是 `PUBLISHED` 版本，便于后续筛选
- `input_refs`: 冻结所有输入来源
- `baseline_run_id`: 支持 A/B 对比
- `parameter_overrides`: 允许对 spec 做 run 级局部覆写，但必须记录下来

## 5.5 输出对象

输出对象是策略域的三类一等结果：

- `SignalSnapshot`
- `TargetPortfolio`
- `RebalancePlan`

但为了与现有引擎一致，**持久化时采用“对象元数据 + artifact 内容”双层结构**。

### 5.5.1 `SignalSnapshot`

```python
@dataclass(frozen=True)
class SignalSnapshot:
    snapshot_id: str
    run_id: str
    strategy_id: str
    strategy_version: int
    trade_date: str
    row_count: int
    selected_count: int
    data_path: str
    manifest_hash: str
    created_at: str
```

artifact schema 推荐：

| 列 | 说明 |
|----|------|
| `trade_date` | 交易日 |
| `instrument_id` | 标的 |
| `signal_<name>` | 单信号原值 |
| `composite_score` | 综合评分 |
| `score_rank` | 排名 |
| `selected` | 是否入选 |
| `reason_codes` | 解释码列表 |

### 5.5.2 `TargetPortfolio`

```python
@dataclass(frozen=True)
class TargetPortfolio:
    target_id: str
    run_id: str
    strategy_id: str
    strategy_version: int
    trade_date: str
    gross_exposure: float
    net_exposure: float
    cash_target: float
    row_count: int
    data_path: str
    manifest_hash: str
    created_at: str
```

artifact schema 推荐：

| 列 | 说明 |
|----|------|
| `trade_date` | 交易日 |
| `instrument_id` | 标的 |
| `target_weight` | 目标权重 |
| `raw_weight` | 约束前权重 |
| `risk_scaled_weight` | 风险缩放后权重 |
| `selected` | 是否入选 |
| `constraint_actions` | 被约束调整的动作 |
| `reason_codes` | 目标仓位原因 |

### 5.5.3 `RebalancePlan`

```python
@dataclass(frozen=True)
class RebalancePlan:
    plan_id: str
    run_id: str
    strategy_id: str
    strategy_version: int
    trade_date: str
    current_snapshot_ref: str | None
    target_snapshot_ref: str
    estimated_turnover: float
    estimated_cost: float
    trigger_reason: str
    row_count: int
    data_path: str
    manifest_hash: str
    created_at: str
```

artifact schema 推荐：

| 列 | 说明 |
|----|------|
| `trade_date` | 交易日 |
| `instrument_id` | 标的 |
| `current_weight` | 当前仓位 |
| `target_weight` | 目标仓位 |
| `delta_weight` | 调整幅度 |
| `action` | buy / sell / hold |
| `estimated_notional` | 预计交易额 |
| `estimated_cost` | 预计成本 |
| `reason_codes` | 调仓原因 |

---

## 6. 运行时输入与上下文契约

## 6.1 `StrategyInputRef`

为保证可复现，运行必须冻结输入来源：

```python
@dataclass(frozen=True)
class StrategyInputRef:
    ref_type: str         # derived_version / research_snapshot / positions_snapshot / universe_snapshot
    ref_id: str
    version: int | None
    role: str | None = None
```

## 6.2 `StrategyInputBundle`

`StrategyInputBundle` 由 Port 组装，Core 只消费。

```python
@dataclass(frozen=True)
class StrategyInputBundle:
    trade_calendar: pl.DataFrame
    base_universe: pl.DataFrame
    input_frames: dict[str, pl.DataFrame]
    positions_frame: pl.DataFrame | None
    benchmark_frame: pl.DataFrame | None
    metadata_frames: dict[str, pl.DataFrame] = field(default_factory=dict)
```

约束：

- `input_frames` 的 key 必须是稳定别名，供 `SignalSpec` / `FilterSpec` / `ScorerSpec` 引用
- 所有输入必须已完成 PIT 对齐
- Core 不负责“去哪儿读数据”，只负责“拿到数据后怎么决策”

## 6.3 `StrategyContext`

```python
@dataclass
class StrategyContext:
    run: StrategyRun
    spec: StrategySpec
    inputs: StrategyInputBundle
    parameters: dict[str, object]
    scratch: dict[str, object] = field(default_factory=dict)
```

`scratch` 只用于阶段间轻量传递，不得存放大 DataFrame 真相副本。大体量中间结果应显式作为 `DecisionFrame` 返回。

---

## 7. 统一计算载体：`DecisionFrame`

策略中间态统一使用一个长表风格 `DecisionFrame`。这是本文档最重要的实现决策之一。

### 7.1 基础结构

最小列集合：

| 列 | 说明 |
|----|------|
| `trade_date` | 交易日 |
| `instrument_id` | 标的 |
| `eligible` | 是否在候选集合内 |
| `selected` | 是否最终入选 |
| `composite_score` | 综合评分 |
| `raw_weight` | 分配阶段产出的初始权重 |
| `target_weight` | 风险/约束后最终权重 |
| `reason_codes` | 解释码 |

扩展列：

- `signal_*`
- `rank_*`
- `filter_*`
- `regime_state`
- `constraint_*`
- `estimated_cost_*`

### 7.2 好处

1. 与 Polars 高性能路径天然一致
2. 易于做参数扫描和批量运行
3. 每个阶段本质上只是“加列 / 过滤 / 排序 / 重赋值”
4. 非常适合测试与 artifact 化

### 7.3 不做的事

不在 Core 里构建一套复杂对象图，例如：

- `SignalCandidate`
- `SelectionCandidate`
- `PositionCandidate`
- `RiskAdjustedCandidate`

这些对象层次会显著增加实现与调试成本，不符合 Ditto 当前架构风格。

---

## 8. Pipeline 完整设计

## 8.1 主链

```text
Universe
  -> Signal
  -> Score
  -> Regime Overlay
  -> Filter
  -> Select
  -> Weight Allocate
  -> Risk Size
  -> Constraint Check
  -> Execute / Diff
  -> Output
```

## 8.2 各阶段正式职责

### A. Universe

职责：决定策略在哪些标的上运行。

```python
@dataclass(frozen=True)
class UniverseSpec:
    base: str
    filters: tuple[FilterSpec, ...] = ()
    refresh_rule: str = "rebalance_aligned"
```

设计要点：

- `base` 是基础集合，如 `csi_etf_broad`
- `filters` 是叠加过滤链，不与后续硬门槛混淆
- `refresh_rule` 允许 Universe 更新频率与调仓频率不同

V1 内置：

- 静态 universe id
- 静态列表 universe
- 基于 metadata/流动性/上市天数的过滤

### B. Signal

职责：产出原始信号值，不做综合打分。

```python
@dataclass(frozen=True)
class SignalSpec:
    name: str
    source: str              # derived_ref:<id> / inline_expr:<expr> / callable:<name>
    dependencies: tuple[str, ...] = ()
```

V1 支持三类来源：

1. `derived_ref`
   - 首选，直接复用已 `PUBLISHED` 的 `DerivedSpec`
2. `inline_expr`
   - 使用现有 DSL 做策略局部信号表达
3. `callable`
   - 用于复杂 regime / 规则型逻辑

设计约束：

- `inline_expr` 只允许引用 `input_frames` 中已冻结的别名，不允许隐式发起数据查询
- 如果某个 `inline_expr` 被反复复用，应提升为正式 `DerivedSpec`

### C. Score

职责：把多个原始信号组合成综合评分。

```python
@dataclass(frozen=True)
class ScorerSpec:
    method: str
    params: dict[str, object] = field(default_factory=dict)
```

V1 内置：

- `equal_weight`
- `rank_then_combine`
- `ic_weighted`

推荐默认：`rank_then_combine`

原因：

- 兼容不同量纲
- 对极值更稳健
- 与 WorldQuant / 横截面排序策略习惯一致

### D. Regime Overlay

职责：对评分、总仓位、调仓触发做市场状态修饰，但不能绕过下游约束。

```python
@dataclass(frozen=True)
class RegimeOverlaySpec:
    method: str
    params: dict[str, object] = field(default_factory=dict)
```

V1 内置：

- `score_multiplier`
- `gross_exposure_scale`
- `rebalance_gate`

设计约束：

- `regime_overlay` 只能修改受控列，如 `score_multiplier` / `gross_exposure_multiplier`
- 不允许直接生成订单

### E. Filter

职责：执行硬门槛过滤。

```python
@dataclass(frozen=True)
class FilterSpec:
    name: str
    source: str
```

典型场景：

- 黑名单
- 停牌/ST/退市过滤
- 最小分数阈值
- 流动性阈值

Filter 与 Select 分离的原因：

- Filter 是二元“过/不过”
- Select 是排序“选谁/选几个”

### F. Select

职责：从通过过滤的候选中按规则选取。

```python
@dataclass(frozen=True)
class SelectorSpec:
    method: str = "top_k"
    params: dict[str, object] = field(default_factory=lambda: {"k": 5})
```

V1 内置：

- `top_k`
- `bottom_k`
- `threshold`

Deferred：

- `long_short`

原因：当前日频主线是 long-only 研究/推荐，不应让空头语义干扰 V1 主链。

### G. Weight Allocate

职责：在已选标的之间分配相对权重。

```python
@dataclass(frozen=True)
class WeightAllocatorSpec:
    method: str = "equal_weight"
    params: dict[str, object] = field(default_factory=dict)
```

V1 内置：

- `equal_weight`
- `score_weight`
- `inverse_vol`

P2 再加：

- `risk_parity`

### H. Risk Size

职责：对总风险和仓位暴露做整体缩放。

```python
@dataclass(frozen=True)
class RiskSizerSpec:
    method: str = "full_invest"
    params: dict[str, object] = field(default_factory=dict)
```

V1 内置：

- `full_invest`
- `vol_target`
- `drawdown_scale`
- `regime_scale`

### I. Constraint Check

职责：检查目标仓位是否违规，并执行确定性的修正动作。

```python
class ConstraintAction(StrEnum):
    REJECT = "reject"
    REDUCE = "reduce"
    WARN = "warn"


@dataclass(frozen=True)
class ConstraintSpec:
    type: str
    params: dict[str, object]
    action: ConstraintAction = ConstraintAction.REDUCE
```

V1 内置：

- `max_weight_per_instrument`
- `max_turnover`
- `min_holdings`
- `cash_floor`

P2 内置：

- `max_sector_exposure`
- `style_neutrality`
- `beta_band`

关键决策：

> V1 不引入通用优化器，优先使用“后置检查 + 确定性削减”模式。

理由：

- ETF 轮动和日频长仓模板规模小
- 解释性更强
- 测试与问题定位更简单

### J. Execute / Diff

职责：将目标仓位与当前持仓做 diff，生成调仓计划和成本估算。

```python
@dataclass(frozen=True)
class TriggerSpec:
    method: str = "calendar"
    params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CostModelSpec:
    commission_rate: float = 0.0003
    slippage_bps: float = 5.0
    impact_model: str = "linear"


@dataclass(frozen=True)
class ExecutionSpec:
    trigger: TriggerSpec = field(default_factory=TriggerSpec)
    cost_model: CostModelSpec = field(default_factory=CostModelSpec)
```

V1 触发规则：

- `calendar`
- `signal_change_pct`
- `composite`

V1 成本模型：

- 线性佣金
- 固定 bp 滑点
- 可选线性冲击

P2 再加：

- `square_root` 冲击模型
- 分批执行语义

---

## 9. Protocol 与 Callable 扩展点

为了兼顾声明式与灵活性，所有阶段都走“内置方法名 + Callable Protocol”双轨。

推荐协议：

```python
class DecisionStage(Protocol):
    def execute(self, ctx: StrategyContext, frame: pl.DataFrame) -> pl.DataFrame: ...
```

更细粒度的阶段协议可以在实现时再拆，但原则不变：

- 输入输出都围绕 `DecisionFrame`
- Core 只接受纯计算 Callable
- Callable 不应隐式发起 I/O

### 9.1 允许的扩展

- `CallableSignal`
- `CallableScorer`
- `CallableSelector`
- `CallableAllocator`
- `CallableSizer`
- `CallableConstraint`
- `CallableTrigger`

### 9.2 沉淀路径

遵循业界常见 80/20 模式：

1. 先用 Callable 快速验证
2. 复用频率高后提炼为内置方法
3. 最终必要时提升为正式 `DerivedSpec` / 模板能力

这样既不把 `StrategySpec` 变成牢笼，也不让整个策略平台滑回“随便写 Python 类”的失控状态。

---

## 10. 与 `DerivedSpec` / 研究快照 / 发布治理的对接

这是 Ditto 相比多数开源回测框架最值得利用的既有优势。

### 10.1 对接原则

1. 策略引擎**优先消费已发布的 derived artifacts**
2. `StrategyRun` 必须记录所有 `derived_id + version` 引用
3. 回测/研究 run 若使用研究数据集，应记录 `dataset_snapshot_id`
4. 标准推荐任务只允许使用 `PUBLISHED` derived inputs

### 10.2 为什么不把策略直接做成 `DerivedSpec.role=SIGNAL`

当前不建议在 V1 直接把整个策略语义硬塞进 `DerivedSpec`，原因是：

- `DerivedSpec` 当前强项是单实体派生计算与版本治理
- 策略主链还包含筛选、权重、约束、持仓 diff、成本估算
- 这些语义远超“一个派生值”的边界

正确做法是：

- `DerivedSpec` 负责特征/因子/局部信号真相层
- `StrategySpec` 负责决策编排
- `StrategyRun` 负责运行控制面

### 10.3 研究与推荐的版本纪律

推荐规则：

- `RESEARCH` run：可绑定 `DRAFT` strategy version，但必须显式记录
- `BACKTEST` run：允许 `DRAFT` 或 `PUBLISHED`
- `RECOMMENDATION` run：默认必须 `PUBLISHED`

这与当前 derived engine 中“research 绑定 `PUBLISHED` 版本”的治理方向一致，只是在策略层保留了研究灵活性。

---

## 11. Artifact 与控制面设计

## 11.1 artifact-first 路径

推荐目录语义：

```text
strategy/specs/{strategy_id}/v{version}/spec.json
strategy/runs/{strategy_id}/v{version}/{run_id}/
  manifest.json
  decision_frame.parquet
  signal_snapshot.parquet
  target_portfolio.parquet
  rebalance_plan.parquet
  backtest_nav.parquet
  backtest_metrics.json
  diagnostics.json
```

其中：

- `decision_frame.parquet` 是完整中间态，供调试与 drilldown
- 三类业务输出 artifact 是面向产品与回放的正式对象
- `manifest.json` 记录输入引用、schema、hash、builder version

## 11.2 最小控制面表

建议最小化为四类记录：

1. `strategy_version`
2. `strategy_run`
3. `strategy_artifact`
4. `strategy_state`

不要一开始为每个输出对象再单独铺一套表。

### 11.2.1 `strategy_artifact`

推荐字段：

- `artifact_id`
- `run_id`
- `artifact_kind`
- `trade_date`
- `path`
- `manifest_hash`
- `row_count`
- `summary_json`
- `created_at`

`artifact_kind` 取值：

- `decision_frame`
- `signal_snapshot`
- `target_portfolio`
- `rebalance_plan`
- `backtest_nav`
- `backtest_metrics`
- `diagnostics`

### 11.2.2 `strategy_state`

推荐字段：

- `strategy_id`
- `active_version`
- `latest_run_id`
- `latest_backtest_run_id`
- `latest_recommendation_run_id`
- `latest_target_artifact_id`
- `latest_rebalance_artifact_id`
- `updated_at`

用途：

- 最新推荐查询
- 工作台首页展示
- 运行状态追踪

---

## 12. 回测与推荐的统一主链

### 12.1 核心判断

回测不是另一套策略模型，而是 `StrategyRunMode.BACKTEST`。

### 12.2 统一链路

```text
StrategySpec
  -> StrategyInputBundle
  -> DecisionFrame
  -> SignalSnapshot
  -> TargetPortfolio
  -> RebalancePlan
  -> Backtest NAV / Metrics / Reports
```

### 12.3 各模式差异

| 模式 | 主要输出 | 说明 |
|------|---------|------|
| `RESEARCH` | `decision_frame` / `signal_snapshot` / diagnostics | 用于因子拆解、参数扫描、敏感性分析 |
| `BACKTEST` | 上述全部 + NAV / metrics | 用于历史评估 |
| `RECOMMENDATION` | 最新 `target_portfolio` + `rebalance_plan` | 用于调仓建议 |

设计约束：

- 三种模式共用同一套 `StrategySpec`
- 不允许 recommendation 走一套特例逻辑
- 不允许 backtest 自己重新定义一套持仓对象

---

## 13. 多策略资金分配的边界

多策略资金分配是下一层 `Risk Budget` 问题，不进入 V1 主实现。

### 13.1 为什么先不做

1. 当前主线优先验证 ETF 轮动 / 趋势 / 选股模板闭环
2. 多策略预算需要处理相关性、组合层级目标、冲突信号
3. 一旦过早引入，会放大当前系统复杂度

### 13.2 但必须留口

推荐保留一个非常窄的扩展点：

```python
class CapitalAllocator(Protocol):
    def allocate(self, runs: list[TargetPortfolio]) -> list[TargetPortfolio]: ...
```

V1 默认实现：

- `single_strategy_full_budget`

P2 才引入：

- `fixed_mix_budget`
- `vol_target_mix_budget`
- `correlation_aware_budget`

---

## 14. 推荐模块布局

## 14.1 Core.strategy

```text
packages/core/src/ditto_core/strategy/
  __init__.py
  specs.py
  context.py
  models.py
  protocols.py
  runner.py
  validation.py
  builtins/
    universe.py
    signal.py
    scoring.py
    regime.py
    filtering.py
    selection.py
  templates/
    etf_rotation.py
    etf_trend_swing.py
    stock_selection_trend.py
```

## 14.2 Core.portfolio

```text
packages/core/src/ditto_core/portfolio/
  __init__.py
  models.py
  allocation.py
  sizing.py
  constraints.py
  rebalance.py
  cost.py
```

## 14.3 Port / DataHub

Port 推荐新增：

- `strategy_definition_service.py`
- `strategy_run_service.py`
- `strategy_input_assembler.py`
- `strategy_artifact_persistence_service.py`

DataHub 推荐新增：

- `strategy_catalog_service.py`
- `strategy_artifact_service.py`

注意：

- 控制面与 artifact I/O 必须都下沉到 DataHub
- Port 只负责编排，不直接操作文件

---

## 15. 测试与验证策略

### 15.1 Core 单元测试

必须覆盖：

- 每个内置 stage 方法
- `DecisionFrame` schema 约束
- 约束削减逻辑
- 成本估算逻辑
- run mode 分歧逻辑

### 15.2 契约测试

必须新增：

- `StrategySpec` / `StrategyRun` / artifact manifest 序列化测试
- `DRAFT` / `PUBLISHED` 运行权限测试
- 输入引用冻结与 replay 一致性测试

### 15.3 模板级测试

V1 至少保证：

- `etf_rotation` 单元测试
- `etf_trend_swing` 单元测试
- 一个推荐链路集成测试
- 一个回测链路集成测试

### 15.4 端到端验证

最终验收仍应沿用项目标准：

```bash
pixi run -e dev check
pixi run -e dev arch-check
```

---

## 16. Phase 切分建议

## Phase 0：语义与控制面

- `StrategySpec` / `StrategyRun` / artifact models
- `DecisionFrame` schema
- DataHub 控制面表与 artifact service

## Phase 1：ETF 轮动主链

- Universe / Signal / Score / Select
- `equal_weight` / `score_weight`
- `max_turnover` / `cash_floor`
- `RECOMMENDATION` 闭环

## Phase 2：日频回测闭环

- `BACKTEST` 模式
- NAV / metrics / report artifact
- baseline 对比

## Phase 3：趋势与股票模板

- regime overlay
- 股票过滤链
- `vol_target` / `drawdown_scale`

## Deferred

- 多策略预算
- long-short
- 分钟级
- broker/execution adapter
- 通用优化器

---

## 17. 明确反模式

以下做法明确禁止：

1. 把整个策略写成单个 Python 类，在里面自己读数据、算分、下订单
2. 把大体量持仓/交易明细直接塞进控制表字段
3. recommendation 路径绕过 `StrategyRun`
4. 在 Core 阶段函数里直接访问 DataHub/Store
5. 把策略治理和 `DerivedSpec` 治理做成两套完全无关的版本体系
6. 为了“灵活”而默认走 Callable，导致 spec 不可序列化、不可 diff

---

## 18. 最终结论

Ditto 的策略引擎应该稳定为以下形态：

1. **策略定义层**
   - `StrategyTemplate` + `StrategySpec` + `StrategyVersion`

2. **策略运行层**
   - `StrategyRun` + `StrategyInputBundle` + `DecisionFrame`

3. **组合输出层**
   - `SignalSnapshot` + `TargetPortfolio` + `RebalancePlan`

4. **治理层**
   - artifact-first
   - run-level lineage
   - `DRAFT/PUBLISHED` 分流
   - 与 published derived inputs 对齐

5. **扩展层**
   - 每阶段声明式优先
   - Callable escape hatch 保留
   - 多策略预算与实时执行仅留接口

这套设计的核心价值，不是“抽象优雅”，而是它能同时满足：

- 日频研究速度
- 回测与推荐对象统一
- 已有 derived engine 治理复用
- 后续 API/Web 产品化可追踪
- 长期演进到多策略与执行层时不推倒重来

---

## 19. 外部参考

- QuantConnect Algorithm Framework Alpha Creation: https://www.quantconnect.com/docs/v1/algorithm-framework/alpha-creation
- QuantConnect Insight Manager: https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/insight-manager
- Qlib Workflow: https://qlib.readthedocs.io/en/stable/component/workflow.html
- Qlib Strategy / Backtest: https://qlib.readthedocs.io/en/v0.6.2/component/backtest.html
- VectorBT Getting Started: https://vectorbt.dev/
- Feast Components Overview: https://docs.feast.dev/getting-started/components/overview
- dbt State-aware Orchestration: https://docs.getdbt.com/docs/deploy/state-aware-about
- 101 Formulaic Alphas: https://arxiv.org/abs/1601.00991
- WorldQuant Learn2Quant: https://www.worldquant.com/learn2quant/
