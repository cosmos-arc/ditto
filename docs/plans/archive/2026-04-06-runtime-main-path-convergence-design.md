# Runtime 主链路收口设计

**日期**: 2026-04-06
**状态**: 设计提案
**前置**: Hybrid Plane v2 结构迁移已完成（`2026-04-03-architecture-final-cleanup.md`）
**验证基线**: `pixi run -e dev check` 全部通过 + `pixi run -e dev arch-check` 全绿
**设计立场**: LEAN 三支柱模型 + Runtime Contract 显式化

---

## 1. 问题定性

Hybrid Plane v2 已完成"目录分层与静态依赖规则"的大框架迁移，但 **Runtime / Data access 主链路收口未完成**。

| 维度 | 状态 |
|------|------|
| 顶层包结构 | ✅ kernel / infra / data / engine / analytics / app / interfaces 已落地 |
| importlinter 主层级 | ✅ 20 条规则全绿 |
| app 层 CQRS | ✅ query / process / builders / command 已拆分，R8 互斥生效 |
| 引擎平面分离 | ✅ engine / analytics / data 从旧 core/datahub 分离 |
| 工程稳定性 | ✅ `pixi run -e dev check` 通过 |
| **DataFeed 主链路统一** | ❌ 双路径并存，主路径绕过 DataProvider |
| **TradingOrchestrator 编排** | ❌ 空壳 Protocol + alias，零生产消费者 |
| **data.query 对外边界** | ❌ 死代码，interfaces 直接依赖 data.services |
| **Clock / EventBus 接线** | ❌ Clock 零消费者；EventBus 未注入生产（且有时间戳 bug） |
| **data 内部 owner 边界** | ⚠️ importlinter 规则空转（storage→models 全豁免） |

**结论**：架构骨架已成型，核心链路仍处于"旧路径仍然工作、新路径尚未激活"的过渡态。

---

## 2. 设计原则

### 2.1 业界标杆：LEAN 三支柱模型

QuantConnect LEAN（项目自评 10/10 标杆）的引擎架构：

```
              ┌──────────────────────────────┐
              │       Engine（固定循环）        │
              │  for each time_step:           │
              │    slice = DataFeed.next()     │
              │    algorithm.on_data()          │
              │    transaction_handler()        │
              │    result_handler()             │
              └──────────┬────────────────────┘
                         │
            ┌────────────┼────────────┐
            │            │            │
      ┌─────▼─────┐ ┌───▼────┐ ┌────▼─────┐
      │ IDataFeed  │ │IBroker │ │IResult   │
      │（可插拔）   │ │（可插拔）│ │Handler   │
      └───────────┘ └────────┘ └──────────┘
```

**关键设计原则**：

1. **引擎循环是固定的具体类** — 日循环步骤有确定顺序，不需要多态
2. **多态在适配器层** — `IDataFeed`（历史/实时）、`IBrokerage`（模拟/实盘）、`IFillModel`/`ISlippageModel`（现实模型）是可插拔的
3. **没有"TradingOrchestrator"这种编排抽象** — LEAN 的 `Engine` 类就是最终方案

### 2.2 映射到 Ditto

| LEAN 概念 | Ditto 当前 | 应该是 |
|-----------|-----------|--------|
| Engine（固定循环） | EngineLoop | **保留为具体类，不抽象** |
| IDataFeed（可插拔） | DataFeed Protocol | **保留 Protocol，统一到 ProviderBackedDataFeed** |
| IBrokerage（可插拔） | Brokerage Protocol | 已有，保持 |
| IFillModel / ISlippageModel | FeeModel / FillModel | 已有，保持 |
| TradingOrchestrator | ❌ 不存在对应概念 | **删除空壳** |

### 2.3 项目自身设计文档的验证

- **策略引擎 v3 设计文档** (`2026-03-21-strategy-engine-system-design-v3.md`)：**不包含 TradingOrchestrator 概念**。编排由 Port 层服务（BacktestService / StrategyRunService）+ StrategyFacade 承担
- **未来架构设计** (`2026-03-31-ditto-future-architecture-design.md`)：提出 **Session Driver** 模式（BacktestSession / LiveSession），本质是应用层的 composition root，不是引擎层的编排抽象
- **确定性重放目标**：所有时间应来自 `Slice.step_time`，禁止 `datetime.now()`。当前 EventBus 的时间戳违反此约束

---

## 3. 分组与优先级

三组改动按依赖关系排序，前一组是后一组的前置：

```
Phase A（架构卫生）  ← 独立，低风险，可立即执行
  ├─ A1: 删除 data.query 死代码
  └─ A2: 删除 TradingOrchestrator 空壳

Phase B（DataFeed 统一）  ← 核心链路，依赖 A
  ├─ B1: PublishedBacktestRuntime.data_feed 类型改为 DataFeed Protocol
  ├─ B2: 主链路构造 ProviderBackedDataFeed
  ├─ B3: 抽取 InstrumentDisplayMap
  ├─ B4: 删除 MarketServiceDataFeed
  └─ B5: 更新受影响测试

Phase C（Clock/EventBus 接线）  ← 运行时支柱，依赖 B
  ├─ C1: EngineOptions 加入 Clock 参数
  ├─ C2: EngineLoop 每步调用 clock.advance_to()
  ├─ C3: 事件时间戳改为 clock.now()（修复 bug）
  ├─ C4: BacktestService 构造 SimulatedClock 并注入
  └─ C5: 修复测试中的时间戳断言

Phase D（已知问题记录）  ← 不改动代码
  └─ D1: importlinter data 内部边界空转
```

---

## 4. Phase A：架构卫生

### A1: 删除 data.query 死代码

**现状**：`ditto_data.query` 包含三个 Facade，全部零生产消费者。

| 符号 | 生产消费者 | 测试消费者 | 决策 |
|------|-----------|-----------|------|
| `MarketQuerist` | 0 | 仅 data 层单元测试 | 删除 |
| `MetadataQuerist` | 0 | 仅 data 层单元测试 | 删除 |
| `ServiceBackedDataProvider` | 0 | 仅 data 层单元测试 | **保留**（Phase B 中将成为主链路关键组件） |

**操作**：

1. 删除 `packages/data/src/ditto_data/query/market.py`
2. 删除 `packages/data/src/ditto_data/query/metadata.py`
3. 修改 `packages/data/src/ditto_data/query/__init__.py`：移除 `MarketQuerist`、`MetadataQuerist` 的 re-export
4. 删除对应测试文件 `packages/data/tests/unit/query/test_market_querist*.py`、`test_metadata_querist*.py`
5. 清理 `ditto_data.__init__` 中对已删符号的 re-export（如有）

**验收**：`grep -rn "MarketQuerist\|MetadataQuerist" packages/ --include="*.py"` 返回 0（除 `ServiceBackedDataProvider` 保留）

### A2: 删除 TradingOrchestrator 空壳

**现状**：`TradingOrchestrator` Protocol + `BacktestTradingOrchestrator = EngineLoop` alias 构成完全自引用的空壳模块。

**影响面**（全量）：

| 消费者 | 文件 | 性质 |
|--------|------|------|
| Protocol 定义 | `engine/orchestrator/protocol.py` | 源码 |
| Alias 定义 | `engine/backtest/engine.py:635` | 源码 |
| Re-export | `engine/orchestrator/__init__.py` | 源码 |
| Re-export | `engine/backtest/__init__.py` | 源码 |
| 单元测试 | `tests/unit/orchestrator/test_protocol_unit.py` | 测试 |
| 单元测试 | `tests/unit/orchestrator/test_backtest_orchestrator_unit.py` | 测试 |

**零生产消费者** — 没有任何非测试、非自身代码引用这两个符号。

**操作**：

1. 删除 `packages/engine/src/ditto_engine/orchestrator/` 整个目录
2. 删除 `engine.py` 中 `BacktestTradingOrchestrator = EngineLoop` alias（line 635-636）及 `__all__` 中的条目（line 70）
3. 编辑 `packages/engine/src/ditto_engine/__init__.py`：移除 orchestrator 相关 re-export
4. 删除 `packages/engine/tests/unit/orchestrator/` 测试目录
5. 验证 `packages/engine/src/ditto_engine/backtest/__init__.py` 中无 orchestrator 相关 re-export

**验收**：`grep -rn "TradingOrchestrator" packages/ --include="*.py"` 返回 0

---

## 5. Phase B：DataFeed 统一

### 5.1 现状：三条并存路径

```
路径 A（主链路 — 当前活跃）:
  BacktestRuntimeBuilder
    → new MarketServiceDataFeed(MetadataService, MarketService)
    → PublishedBacktestRuntime.data_feed: MarketServiceDataFeed（具体类型）
    → ServiceFactory 读取 runtime.data_feed.display_map
    → BacktestService._options.display_map
    → ArtifactWriter 用 display_map 丰富审计日志

路径 B（engine 测试）:
  conftest.py
    → new ProviderBackedDataFeed(mock DataProvider)
    → EngineLoop

路径 C（SliceBuilder 独立）:
  SliceBuilder.build()
    → new MarketServiceDataFeed(MetadataService, MarketService)
    → 只调用 trading_days() + get_slice()
```

### 5.2 目标：统一到 DataProvider → ProviderBackedDataFeed

```
目标链路:
  BacktestRuntimeBuilder
    → 接收 DataProvider（由 ServiceBackedDataProvider 实现）
    → new ProviderBackedDataFeed(DataProvider, tickers, id_map)
    → PublishedBacktestRuntime.data_feed: DataFeed（Protocol 类型）
    → InstrumentDisplayMap 单独注入（展示关注点分离）
```

### 5.3 `display_map` 分离方案

**`display_map` 的本质**：`InstrumentId → standard_ticker` 映射（如 `InstrumentId(2000001) → "510300.SH"`），是展示层关注点。

**当前耦合位置**：

| 文件 | 行号 | 用途 |
|------|------|------|
| `service_factory.py` | 288 | 从 `runtime.data_feed.display_map` 读取 |
| `backtest_service.py` | 116, 323 | `BacktestServiceOptions.display_map` 注入到 ArtifactWriter |
| `strategy_types.py` | 88-97 | `enrich_record_with_symbol()` 丰富审计记录 |
| `strategy_types.py` | 164-170 | 写审计文件时丰富记录 |
| `strategy_types.py` | 331-346 | `MarketServiceDataFeed.display_map` 属性定义 |
| `strategy_types.py` | 377-446 | `_build_display_map()` 实现 |

**分离方案**：

将 `display_map` 的构建逻辑从 `MarketServiceDataFeed` 中抽出，放到 app 层独立的 `InstrumentDisplayMap`：

```python
# 方案：在 strategy_types.py 或新文件中定义
def build_display_map(
    instrument_ids: list[InstrumentId],
    metadata_service: MetadataService,
) -> dict[InstrumentId, str]:
    """构建 InstrumentId → standard_ticker 映射。"""
    ...
```

这样 `ProviderBackedDataFeed` 不需要承担展示层职责，而 `display_map` 的消费者（ArtifactWriter）继续从 `BacktestServiceOptions` 获取。

### 5.4 具体改动

#### B1: `PublishedBacktestRuntime.data_feed` 类型改为 DataFeed Protocol

**文件**: `packages/app/src/ditto_app/builders/service_factory.py`

```python
# 改动前
@dataclass(frozen=True)
class PublishedBacktestRuntime:
    data_feed: MarketServiceDataFeed  # 具体类型
    ...

# 改动后
@dataclass(frozen=True)
class PublishedBacktestRuntime:
    data_feed: DataFeed  # Protocol 类型
    ...
```

需要从 `ditto_engine.backtest.data_feed` 导入 `DataFeed`。

#### B2: `BacktestRuntimeBuilder` 改为接收 `DataProvider`

**文件**: `packages/app/src/ditto_app/builders/service_factory.py`

```python
# 改动前
class BacktestRuntimeBuilder:
    def __init__(self, *, metadata_service, market_service): ...

    def build_published_runtime(self, ...):
        data_feed = MarketServiceDataFeed(metadata_service, market_service, config)

# 改动后
class BacktestRuntimeBuilder:
    def __init__(self, *, data_provider: DataProvider): ...

    def build_published_runtime(self, ...):
        data_feed = ProviderBackedDataFeed(data_provider, tickers, id_map)
```

**注意**：`ProviderBackedDataFeed` 需要 `tickers: tuple[str, ...]` 和 `id_map: dict[str, InstrumentId]` 参数。当前 `MarketServiceDataFeed` 在内部通过 `MetadataService` 获取这些信息。统一后，这部分逻辑需要在 builder 中显式完成。

#### B3: `SliceBuilder` 同步修改

**文件**: `packages/app/src/ditto_app/builders/slice_builder.py`

同样改为使用 `ProviderBackedDataFeed` + `DataProvider`。

#### B4: 抽取 `InstrumentDisplayMap`

**文件**: `packages/app/src/ditto_app/process/strategy_types.py`

将 `_build_display_map()` 方法从 `MarketServiceDataFeed` 中提取为独立函数。`BacktestRuntimeBuilder` 在构建 runtime 后单独调用，将结果注入 `BacktestServiceOptions`。

#### B5: 删除 `MarketServiceDataFeed` + `MarketServiceDataFeedConfig`

**文件**: `packages/app/src/ditto_app/process/strategy_types.py`

删除 `MarketServiceDataFeed` 类（line 314-446）和 `MarketServiceDataFeedConfig` 类（line 303-311）。

同步清理：
- `packages/app/src/ditto_app/process/__init__.py` — 移除 re-export
- `packages/app/src/ditto_app/process/strategy.py` — 移除 re-export
- `packages/app/src/ditto_app/builders/service_factory.py` — 移除 import

#### B6: 更新受影响测试

| 测试文件 | 改动 |
|---------|------|
| `test_backtest_runtime_builder_unit.py` | 改用 mock DataProvider 构造 |
| `test_market_service_data_feed_unit.py` | 删除（测试的类已不存在） |
| `test_strategy_service_factory_unit.py` | display_map 断言改为独立验证 |
| `test_strategy_provider_unit.py`（interfaces 层） | mock DataProvider |
| `test_artifact_writer_unit.py` | 不变（display_map 接口不变） |

### 5.5 验收标准

- `grep -rn "MarketServiceDataFeed" packages/ --include="*.py"` 返回 0
- `PublishedBacktestRuntime.data_feed` 类型为 `DataFeed` Protocol
- `pixi run -e dev test` 全部通过
- `pixi run -e dev arch-check` 全绿
- 回测端到端测试通过（确认功能不变）

---

## 6. Phase C：Clock/EventBus 接线

### 6.1 现状

**Clock**（`ditto_kernel.clock`）：
- `SimulatedClock` — 可推进的模拟时钟，用于回测
- `RealtimeClock` — 包装 `datetime.now()`，用于实盘
- **状态：零消费者。** 两个实现类在整个代码库中没有任何 import。

**EventBus**（`ditto_kernel.events`）：
- `EventBus` Protocol — `publish()` + `subscribe()`
- `SimpleEventBus` — 同步实现
- **状态：80% 接线但未注入生产。** `EngineOptions` 声明了 `event_bus: EventBus | None = None`，`EngineLoop` 有 `_publish_event()` 方法，但 `BacktestService` 从未构造和注入 EventBus。

**时间戳 bug**：

```python
# engine.py — 事件时间戳使用 datetime.now(UTC)
# 在 2026 年跑 2024 年的回测，所有事件时间戳 = 2026-04-06，不是 2024-xx-xx
# 违反设计文档的"确定性重放"核心目标
```

| 位置 | 当前代码 | 问题 |
|------|---------|------|
| `engine.py:366` | `timestamp=datetime.now(UTC)` | RiskGuardTriggered 事件 |
| `engine.py:421` | `timestamp=datetime.now(UTC)` | OrderFilled 事件 |
| `engine.py:506` | `timestamp=datetime.now(UTC)` | OrderSubmitted 事件 |
| `engine.py` Manifest | `datetime.now(UTC).strftime(...)` | 可接受（元数据时间戳） |

### 6.2 目标

让 Clock 和 EventBus 成为运行时事实而非文档概念：

```
回测路径:
  SimulatedClock(initial=start_datetime)
    → EngineLoop 每步调用 clock.advance_to(slice.step_time)
    → 事件时间戳使用 clock.now()
  SimpleEventBus()
    → 注入到 EngineOptions.event_bus
    → 事件真正被发布和消费
```

### 6.3 具体改动

#### C1: `EngineOptions` 加入 `clock` 参数

**文件**: `packages/engine/src/ditto_engine/backtest/engine.py`

```python
# 改动前
@dataclass
class EngineOptions:
    fee_model: FeeModel | None = None
    rule_provider: InstrumentRuleProvider | None = None
    post_trade_guard: PostTradeRiskGuard | None = None
    audit_collector: ExecutionAuditCollector | None = None
    event_bus: EventBus | None = None

# 改动后
@dataclass
class EngineOptions:
    clock: Clock  # 必需参数，不再可选
    fee_model: FeeModel | None = None
    rule_provider: InstrumentRuleProvider | None = None
    post_trade_guard: PostTradeRiskGuard | None = None
    audit_collector: ExecutionAuditCollector | None = None
    event_bus: EventBus | None = None
```

需要从 `ditto_kernel.clock` 导入 `Clock`。

**注意**：`clock` 作为必需参数意味着所有现有构造点都需要更新。需要评估对测试的影响。

#### C2: `EngineLoop._step()` 每步调用 `clock.advance_to()`

**文件**: `packages/engine/src/ditto_engine/backtest/engine.py`

```python
def _step(self, date: str) -> None:
    slice = self._data_feed.get_slice(date)
    self._clock.advance_to(slice.step_time)  # 新增：推进时钟
    ...
```

#### C3: 事件时间戳改为 `clock.now()`

**文件**: `packages/engine/src/ditto_engine/backtest/engine.py`

```python
# 改动前（3 处）
timestamp=datetime.now(UTC)

# 改动后
timestamp=self._clock.now()
```

#### C4: `BacktestService` 构造 `SimulatedClock` 并注入

**文件**: `packages/app/src/ditto_app/process/backtest_service.py`

```python
from ditto_kernel.clock import SimulatedClock

def _execute_backtest(self, ...):
    clock = SimulatedClock(
        initial=datetime.strptime(config.start_date, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, tzinfo=UTC
        )
    )
    event_bus = SimpleEventBus()  # 可选：是否在 Phase C 就注入
    options = EngineOptions(
        clock=clock,
        event_bus=event_bus,  # 可选
        fee_model=...,
        ...
    )
```

#### C5: 修复测试中的时间戳断言

所有测试中如果硬编码了 `datetime.now()` 相关的断言，需要改为验证事件时间戳处于回测时间范围内。

### 6.4 `EngineOptions.clock` 必需 vs 可选的权衡

| 方案 | 优点 | 缺点 |
|------|------|------|
| `clock: Clock`（必需） | 强制所有路径正确处理时间，编译期保证 | 需要更新所有测试的 fixture |
| `clock: Clock \| None = None`（可选） | 向后兼容，改动小 | 不注入时 `clock.now()` 会 crash，违背设计意图 |
| `clock: Clock = field(default_factory=RealtimeClock)` | 有默认值，不破坏现有代码 | 掩盖了未正确注入的问题 |

**建议**：选择方案 1（必需参数）。理由：
- 回测路径必须用 SimulatedClock（确定性重放是核心目标）
- 实时路径必须用 RealtimeClock
- 不存在"不需要时钟"的合理场景

### 6.5 验收标准

- `grep -rn "datetime.now(UTC)" packages/engine/src/ --include="*.py"` 返回 0（engine 层不再使用 wall-clock time）
- `SimulatedClock` 被至少 `BacktestService` 和 `EngineLoop` 使用
- 回测事件时间戳处于回测时间范围内（非 wall-clock time）
- `pixi run -e dev test` 全部通过
- `pixi run -e dev arch-check` 全绿

---

## 7. Phase D：已知问题记录

### D1: importlinter data 内部边界空转

**现状**：

`data-storage-no-model-import` 规则声称禁止 `ditto_data.storage → ditto_data.models`，但 7 个 models 子模块全部豁免（line 279-286），规则形同虚设。

**决策**：接受现状。理由：
- data 内部模块数量有限，owner 边界的维护成本高于收益
- storage → models 的耦合是 CQRS Writer/Reader 需要模型类型定义，属于自然耦合
- 等模块增长到需要更严格边界时再收紧

**操作**：更新规则注释，使描述更诚实。

---

## 8. 风险评估

| Phase | 风险级别 | 主要风险 | 缓解措施 |
|-------|---------|---------|---------|
| A | 低 | 删除代码可能有遗漏的消费者 | Grep 全量搜索验证 |
| B | 中 | DataFeed 切换可能引入行为差异 | 端到端回测对比测试 |
| B | 中 | `ProviderBackedDataFeed` 缺少 `display_map` 需要拆分 | 提取到独立函数 |
| C | 中 | `Clock` 必需参数导致大量测试 fixture 需更新 | 分步推进，先加可选参数再改必需 |
| C | 低 | 事件时间戳从 wall-clock 改为 simulated 可能破坏测试 | 更新断言为范围检查 |

---

## 9. 不做的事

以下内容**明确不在本次设计范围内**：

1. **实盘交易 Session Driver** — Phase B/C 的改动为实盘铺路，但 LiveSession 本身不在本次范围
2. **Decision Pipeline 重构** — 策略决策层的 Stage 链（Universe → Signal → Score → ...）运行良好，不需要改动
3. **data 内部 owner 边界收紧** — 模块数量有限，成本/收益不合理
4. **异步 EventBus** — 当前 SimpleEventBus 足够，异步需求等实盘路径再引入
5. **EngineLoop 拆分为可组合 Stage** — 日循环的 8 步是固定顺序，不需要可组合（LEAN 也是固定循环）

---

## 10. 与未来架构的对齐

本设计的改动为 `2026-03-31-ditto-future-architecture-design.md` 描述的未来架构铺路：

| 未来架构概念 | 本次改动 | 对齐方式 |
|-------------|---------|---------|
| Session Driver（BacktestSession / LiveSession） | EngineLoop 保持具体类 + 可插拔适配器 | Session = composition root，组装正确的 DataFeed + Clock + Brokerage |
| Runtime Contract（SessionContext, MarketSlice） | DataFeed Protocol + Clock Protocol | 这些 Protocol 就是 Runtime Contract 的基础 |
| ACL 隔离 | DataProvider Protocol 隔离 data 层细节 | Engine 不依赖 data.services，只依赖 DataProvider Protocol |
| 确定性重放 | Clock 接线 + 事件时间戳修复 | 消除 wall-clock 依赖，所有时间来自 SimulatedClock |
