# B8/B9/B10 延后项决策设计

> 创建：2026-05-10
> 基线：`docs/plans/2026-05-10-b8-b9-b10-remediation-plan.md` 延后项清单
> 状态：已确认
> 方法：源码分析 + 业界对标（LEAN / NautilusTrader / vnpy）→ 决策

---

## 决策总览

延后 8 项代码级 + 9 项架构级，经源码调研和业界对标后决策如下：

| 类别 | 执行 | 接受现状 |
|------|------|---------|
| 代码级 | 4 项（含大文件拆分 7 文件） | 4 项 |
| 架构级 | 3 Phase 依赖链 | — |

---

## 一、代码级延后项决策

### 1. B9-K.2 `DEFAULT_COMMISSION_RATE` 归属 → 接受 kernel + 清理附带问题

**调研结论**：`DEFAULT_COMMISSION_RATE` 已在正确位置。

kernel 满足全部 5 条准入规则：
1. 跨层使用（execution/risk/backtest/strategy/application 5 包消费）✅
2. 零业务行为（纯 `float` 常量）✅
3. 高稳定性（佣金费率是领域常量）✅
4. 无外部依赖 ✅
5. 纯值语义 ✅

移入任何单一包都会违反架构禁令（如 strategy↛execution）。kernel 是唯一公共祖先。

**附带问题修复**：
- `default_price_limit_pct()`：零生产消费者（仅 execution 测试引用），删除或标注 reserved
- apps 副本 `_DEFAULT_COMMISSION_RATE = 0.0003`：Pydantic + `from __future__ import annotations` 的 linter workaround，添加 sync guard 注释或提取为常量引用

### 2. B9-K.6 DecisionFrame → 删除 kernel 死 Protocol

**调研结论**：存在两个互相矛盾的定义。

| 定义 | 位置 | 类型 | 消费者 |
|------|------|------|--------|
| kernel `DecisionFrame(Protocol)` | `kernel/strategy.py` | 3 property: `instruments`/`signals`/`scores` | **零** |
| strategy `type DecisionFrame = pl.DataFrame` | `strategy/alpha/protocols.py` | 类型别名 | 全部 stage/pipeline |

两者结构不兼容（`pl.DataFrame` 没有 `instruments`/`signals`/`scores` 属性）。kernel Protocol 从未被使用。

strategy 层已有 `validate_frame()`（`alpha/frame.py`），在 pipeline 各 stage 入口做列名存在性检查，是实际契约。

**决策**：删除 kernel 死 Protocol，strategy 的 `pl.DataFrame` + `validate_frame()` 是实际契约。

### 3. B9-EX.4 compute_diff → 引入 DiffContext

**调研结论**：10 个参数，1 个调用点（`SimpleExecutionPlanner.plan()`），已有 `# noqa: PLR0913`。

参数自然分组：

```python
@dataclass(frozen=True, slots=True)
class DiffContext:
    # Portfolio state
    target: TargetPortfolioLike
    account_view: AccountView
    pending_delta: dict[InstrumentId, int]

    # Scope + Market data
    all_instruments: set[InstrumentId]
    instrument_rules: dict[InstrumentId, InstrumentRules]
    market_snapshots: dict[InstrumentId, MarketSnapshot]
    default_lot_size: int

    # Policy
    locked_instruments: set[InstrumentId]
    pre_check_fn: Callable[
        [InstrumentId, int, dict[InstrumentId, MarketSnapshot]],
        BlockedOrder | None,
    ]
```

`compute_diff` 签名从 10 参数降至 3：`(ctx: DiffContext, make_order: MakeOrderFn)` → `tuple[list[Order], list[BlockedOrder]]`。

`make_order` 保持独立参数（factory/callback，不属于 frozen dataclass）。

### 4. B9-DATA.4 + B9-APP.5 大文件拆分 → Facade 模式

**调研结论**：7 个文件 > 600 LOC，全部有清晰自然分段。

**策略**：Facade 模式（项目已有先例——B9-DATA.2 `errors.py` 606 LOC → 4 域文件 + facade）。

优势：
- 公共 API 零破坏（消费端 import 路径不变）
- `arch-check` 不受影响
- 每个文件独立拆分、独立验证

**执行顺序（按难度递增）**：

| 序号 | 文件 | LOC | 难度 | 拆分方案 |
|------|------|-----|------|---------|
| 1 | config.py | 615 | 低 | INGESTION_SPECS（纯数据）→ `config/specs.py`，helpers → `config/queries.py` |
| 2 | research.py | 603 | 低 | 底部 154 LOC 纯函数 → `research_helpers.py`，snapshot builders 各保留 |
| 3 | capital.py | 725 | 低 | 按子域分组：valuation/dividend/margin/pledge → capital_market.py，index → index_data.py，corporate → corporate_events.py |
| 4 | runtime_builder.py | 627 | 中 | 反序列化段(174 LOC) → `deserialization.py`，模板配置段(150 LOC) → `template_builders.py` |
| 5 | tushare_source.py | 777 | 中 | 按资产域：stock/etf/index/fundamental/capital/macro/fx 各段委托清晰 |
| 6 | market_service.py | 752 | 中高 | query types → `queries.py`，core engine → `engine.py`，adjustment → `adjustment.py`，convenience API 保留 |
| 7 | coordinator.py | 763 | 高 | instrument-level 路径(180 LOC) → `instrument_ingestion.py`，side effects → `post_ingest.py`。需行为快照测试先行 |

每个拆分后原文件保留为 facade（re-export），确保公共 API 不变。

### 5. 接受现状的项

| 项 | 决策 | 理由 |
|----|------|------|
| B9-PF.5 Constraint priority 移除 | 延后 | P2，待触发动机（如新增 check 时） |
| B9-RK.2 checks.py 拆分 | 延后 | 319 LOC 内聚性高，每个 check 25-45 行，拆分收益有限 |
| B9-DATA.3 apps DI 注入 | 接受 | registry/contexts 是 Composition Root，直接引用具体服务类是标准做法（Mark Seemann DI 模式） |

---

## 二、架构级延后项：3 Phase 依赖链

基于业界对标（LEAN / NautilusTrader / vnpy），确认依赖链和设计方向：

### Phase 1: Runtime Spine

**业界核心洞察**：LEAN 的 backtest/live parity 秘密是**一个接口**：

```
ISynchronizer.StreamData() → IEnumerable<TimeSlice>
```

主循环 `AlgorithmManager.Run()` 永远不知道自己的模式——回测/实盘切换是 Synchronizer 级别的一行代码。

**Ditto 落地方向**：

| 组件 | 行业对标 | Ditto 当前 | 差距 |
|------|---------|-----------|------|
| 时间同步 | LEAN `ISynchronizer` | `Clock`/`SimulatedClock` | 缺数据流前沿驱动的时间抽象 |
| 主循环 | LEAN `AlgorithmManager` | `TradingLoop` Protocol（已定义） | 缺单线程确定性执行保证 |
| 类型化事件 | LEAN `OrderEvent`/`PortfolioEvent` | `DomainEvent` = `str` + `dict` | 需类型化 dataclass + 事件名目录 |
| TimeContext | LEAN `algorithm.UtcTime` | PIT 术语散布各包 | 需共享值对象统一 knowledge_date/as_of 等 |

**启动条件**：B8-B10 代码级修复完成后

### Phase 2: OMS Lite（紧随 Phase 1）

**业界共识**：Order FSM + Append-Only Journal，与执行引擎共置。

```
Order 创建后不可变 → OrderEvent journal 是 source of truth → 状态机确定性
```

**Ditto 落地方向**：
- `ClientOrderId`/`BrokerOrderId`/`OrderState`/`OrderTicket` → execution 包内先设计
- `OrderEvent` append-only journal（Python list / SQLite，不需要 Kafka）
- 状态转换表是数据结构（不是 if-else）
- Backtest/Paper 共享 seam 利用 Phase 1 的 Synchronizer 抽象

**为何紧随 Phase 1**：portfolio 状态重建依赖 execution journal，是 Phase 3 的前置。

### Phase 3: Consumer-Owned Ports 深化

**业界共识**（NautilusTrader 最纯粹）：每个有界上下文定义自己的 Port，ISP 是关键。

**Ditto 现状**：109 个 Protocol，已行业领先。

**演化方向**：
- `ditto_data.provider.DataProvider` → 消费端各自定义窄 Port
- application 层窄编排 Port（`ResearchCatalogPort`/`ResearchArtifactPort`/`IngestionSourcePort`）
- DataCatalog Runtime Store
- Dataset enum 降权为 DataCatalog 元数据

---

## 三、B10 遗留项

| 项 | 触发条件 |
|----|---------|
| B10.1 Platform 死代码清理 | 随代码级修复同步 |
| B10.2 barrel/`__all__` 统一 | 随代码级修复同步 |
| B10.3 CLAUDE.md 同步 | 随代码级修复同步 |
| B10.4 Golden E2E | Phase 1 完成后作为验收手段 |
| B10.5 Data errors facade 验证 | B9-DATA.4 拆分时同步 |
| B10.6 Data services DI 验证 | 接受现状，无需单独验证 |

---

## 四、业界对标参考

| 来源 | 关键参考 |
|------|---------|
| LEAN Engine.cs | 配置驱动 Handler 工厂方法 |
| LEAN AlgorithmManager.cs | 确定性单线程主循环 |
| LEAN ISynchronizer.cs | 回测/实盘时间抽象 |
| NautilusTrader | Actor 模型 + 纯六边形架构 |
| vnpy EventEngine | 反应器模式（120 LOC） |
| Martin Fowler Event Sourcing | 交易系统轻量级事件溯源 |
