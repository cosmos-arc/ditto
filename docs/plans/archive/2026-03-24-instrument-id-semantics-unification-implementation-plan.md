# Instrument ID Semantics Unification Implementation Plan

> **⚠️ SUPERSEDED** — 该计划已被 [Instrument ID 全仓收口执行计划](2026-03-25-instrument-id-remediation-execution.md) 完全替代并实施。保留仅供历史参考。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一 `instrument_id` 在 DataHub / Core / Port 三层中的语义，消除当前 `DataHub int` 与 `Core/执行链 str(source ticker)` 的桥接状态，建立可长期演进的单一身份模型。

**Architecture:** 采用"内部 canonical ID + 外部显示/映射字段"方案。运行时主键统一为 `InstrumentId`（canonical、稳定、source-agnostic），`source_ticker` / `standard_ticker` 只在边界输入、展示与 artifact 中显式携带，不再承担 Core 热路径的主键职责。Core 层纯被动，只使用 `InstrumentId`，不持有、不查询 symbol/ticker 映射，所有展示层字段的注入由 Port 层在边界完成。迁移采用分阶段推进，先引入统一 identity model，再逐步收敛 DataFeed、RuleProvider、Account/Order 链路。

**Tech Stack:** Python 3.13, dataclasses, typing/NewType, polars, sqlite, pytest, basedpyright, import-linter

---

## 1. 问题说明

### 1.1 当前真实状态

当前仓库中的标识语义并不统一，而是存在三套并行语义：

| 层 | 当前主语义 | 证据 |
|---|---|---|
| DataHub 元数据/存储 | `instrument_id: int` 为主，`source_ticker: str` 为映射 | [schema.sql](/home/chevy/projects/ditto/packages/data/src/ditto_data/scripts/schema.sql), [metadata.py](/home/chevy/projects/ditto/packages/data/src/ditto_data/models/metadata.py), [instrument.py](/home/chevy/projects/ditto/packages/data/src/ditto_data/services/metadata/instrument.py) |
| Port 策略适配层 | 从 `int instrument_id` 解析到 `str source_ticker` 后再喂给 Core | [market_data_feed.py](/home/chevy/projects/ditto/apps/port/src/ditto_port/services/strategy/market_data_feed.py) |
| Core 回测/执行/账户 | `instrument_id: str` 被当成运行时主键（实际存储 source_ticker） | [data_feed.py](/home/chevy/projects/ditto/packages/core/src/ditto_core/backtest/data_feed.py), [market.py](/home/chevy/projects/ditto/packages/core/src/ditto_core/execution/reality/market.py), [position.py](/home/chevy/projects/ditto/packages/core/src/ditto_core/accounting/position.py), [rules.py](/home/chevy/projects/ditto/packages/core/src/ditto_core/execution/rules.py) |

更复杂的是，DataHub 内部也已经出现"执行子域提前切到字符串标识"的情况，例如 `trading_rule` 目前以 `TEXT instrument_id` 存储，见 [trading_rule_reader.py](/home/chevy/projects/ditto/packages/data/src/ditto_data/stores/metadata/trading_rule_reader.py)。这说明问题不是"哪边改成另一边那么简单"，而是系统缺少一套显式的身份语义模型。

#### 受影响的完整链路

除上述表中所列外，以下链路同样受 source_ticker 语义泄漏影响：

| 链路 | 文件 | 问题 |
|------|------|------|
| Benchmark 引用 | [engine.py](/home/chevy/projects/ditto/packages/core/src/ditto_core/backtest/engine.py) — `EngineConfig.benchmark_id: str` | benchmark 也用 source ticker 作为 key |
| 目标组合 | [targets.py](/home/chevy/projects/ditto/packages/core/src/ditto_core/execution/targets.py) — `TargetPortfolioLike.positions: dict[str, float]` | target portfolio 的 key 是 `str` |
| 策略输入传播 | [input_assembler.py](/home/chevy/projects/ditto/apps/port/src/ditto_port/services/strategy/input_assembler.py) — `instrument_ids = list(slice_.bars.keys())` | 直接传播了 `str` 语义到策略层 |
| 审计链 | [manifest.py](/home/chevy/projects/ditto/packages/core/src/ditto_core/backtest/manifest.py) — `RuleRef.instrument_id: str` | 审计记录中的 instrument 引用 |
| 序列化 | `BacktestReportSerializer` — SQLite 写入 | 序列化时的 instrument_id 字段语义 |

### 1.2 为什么这是架构问题，而不是类型问题

当前桥接能跑，但会在以下场景持续放大复杂度：

1. **source 绑定泄漏到执行主链**
   - Core 热路径字典 key、持仓 key、规则 key、审计日志 key 都默认把 `source_ticker` 当主键。
   - 这让 Core 运行结果带上了供应商视角，而不是 Ditto 内部视角。

2. **同一证券的身份不再稳定**
   - canonical `instrument_id` 是稳定主键。
   - `source_ticker` 可能受 source、PIT 映射、换代码、退市重映射影响。
   - 如果 Core 用后者做状态 key，回放与跨 source 对齐会天然更脆弱。

3. **适配责任落在错误层次**
   - 当前 `MarketServiceDataFeed` 负责把 DataHub 世界翻译成 Core 世界。
   - 这会让每个执行入口都重复定义"哪个字符串才算 instrument identity"。

4. **artifact 与调试视图纠缠**
   - 运行时需要稳定 key。
   - 人类阅读需要可识别 symbol。
   - 现在两者被混成同一个字段，导致无法同时优化机器稳定性和人类可读性。

5. **多资产多交易所场景下问题加倍**
   - 同一证券在不同 source 可能有不同 ticker（如 tushare `600000.SH` vs wind `600000.SS`），Core 用 source_ticker 做 key 会导致跨源对齐失败。
   - 扩展到港股（`00700.HK`）、美股（`AAPL`）后，裸 ticker 的唯一性完全依赖 source 前缀，脆弱性倍增。

### 1.3 这个问题如果继续拖延，会出现什么后果

- Market service、rule provider、brokerage、audit、artifact 会继续扩散"临时字符串主键"假设。
- 将来补 API/job flow、comparison artifact、多 source 回放时，需要在更多边界重复做 `int ↔ str` 翻译。
- 一旦要支持换源、跨源一致性、symbol 变更回放，就会遇到"同一证券运行时被视为两个标的"的风险。

---

## 2. 目标与非目标

### 2.1 目标

1. 明确区分以下身份概念：
   - `InstrumentId`: Ditto 内部 canonical 主键（`int`）
   - `source_ticker`: source 视角代码（`str`，边界输入用）
   - `standard_ticker`: 标准化展示代码（`str`，展示用）

2. 将以下子链路统一到 canonical `InstrumentId`：
   - Core 数据入口层：`Slice.bars`、`MarketSnapshot`
   - Core 状态层：`Position`、`Order`、`CashBook`
   - Core 执行层：`ExecutionPlanner`、`InstrumentRuleProvider`、`TargetPortfolioLike`
   - Core 审计层：`RunManifest`、`PreTradeDecisionRecord`、`RiskScanRecord`
   - Core 输出层：`BacktestReport`（展示字段由 Port 层注入）
   - Port 适配层：`MarketServiceDataFeed`、`StrategyInputAssembler`、`ArtifactWriter`
   - Core / Port 引用层：`EngineConfig.benchmark_id`

3. 保留 artifact 和调试输出的人类可读性（由 Port 层负责展示字段注入）

4. 在迁移过程中保持回测主链、artifact 主链和 arch-check 不回退

### 2.2 非目标

- 本轮不规划 API / job flow 对外产品化入口
- 本轮不做多 source 统一行情引擎
- 本轮不重写全部 metadata schema，只处理执行主链相关关键表/接口
- 本轮不做历史 artifact 数据迁移（开发阶段，可直接清除）
- 本轮不做 PIT symbol 解析，display map 使用 start_date 快照（将来如需"回测报告中显示当时代码"再做 PIT symbol 查询）

---

## 3. 方案比较

### 方案 A：全仓统一为 `str source_ticker`

**优点**
- 对当前 Core 改动最小
- 调试输出友好

**缺点**
- 继续把外部 symbol 当内部主键
- 无法从语义上保证跨 source / PIT 稳定性
- DataHub 仍需长期维护 canonical int 与运行时 str 的双轨
- 多资产多 source 场景下，裸 ticker 的唯一性完全依赖 source 前缀

**结论**
- 不推荐，只是把当前桥接状态合法化

### 方案 B：全仓统一为 `int instrument_id`

**优点**
- 语义最纯，内部主键稳定
- 与 DataHub schema 自然对齐
- 存储紧凑

**缺点**
- 人类可读性退化
- 需要额外设计展示字段，否则 artifact / 日志可用性变差

**结论**
- 比方案 A 好，但如果没有"显示层字段"，会把调试体验做坏

### 方案 C：**推荐**，统一为 canonical `InstrumentId`，同时显式保留 symbol 视图

**核心思想**
- 运行时状态、规则查询、审计主键统一为 `InstrumentId`
- `source_ticker` / `standard_ticker` 不再充当状态 key，只作为边界输入与展示字段
- 需要可读输出时，由 Port 层显式注入展示字段

**为什么在多资产场景下仍选择单调 int 而非复合标识符（如 LEAN SecurityIdentifier）**

Ditto 的 `instrument_mapping` 表已支持 PIT 映射，`InstrumentIdAllocator` 按百万级范围分配保证唯一性。在 A 股为主、逐步扩展港股/美股的场景下，单调 int 的简洁性收益大于复合标识符的自描述性收益。复合标识符（编码 symbol + market + date）的序列化和比较开销在回测热路径中是不必要的。

**结论**
- 这是唯一同时满足"机器稳定性"和"人类可读性"的方案

---

## 4. 推荐设计

> **注意**：identity model（`InstrumentId` NewType + `InstrumentRef`）的归属位置待独立讨论。以下设计不预设其所在包，用 `ditto_*.models.identity` 占位。

### 4.1 统一身份模型

建议新增：

```python
InstrumentId = NewType("InstrumentId", int)

@dataclass(frozen=True)
class InstrumentRef:
    """Port 层编排工具 — 仅在 Port 层使用，Core 层不可见。"""
    instrument_id: InstrumentId
    source_ticker: str
    source: str
    standard_ticker: str | None = None
    exchange: str | None = None
    asset_class: str | None = None
```

**设计决策**：
- 只引入 `InstrumentId = NewType("InstrumentId", int)` 作为类型安全包装，`SourceTicker` / `StandardTicker` 不需要 NewType（运行时是 no-op，只在边界层使用，类型检查收益不足以覆盖复杂度）
- `InstrumentRef` 是 Port 层的编排工具，负责在边界组装时携带完整身份信息。Core 层只接收 `InstrumentId`，不需要知道 `source_ticker` 是什么

### 4.2 分层职责

| 层 | 统一职责 | 关键约束 |
|---|---|---|
| DataHub | canonical identity source of truth；负责 `identifier -> InstrumentId` 解析与 `InstrumentId -> symbol` 回查 | — |
| Port | 所有边界输入先解析到 `InstrumentId`；构造 `InstrumentRef` / display map；ArtifactWriter 在序列化时注入展示字段；不再把字符串 symbol 当运行时 key | **Port 是唯一负责 `InstrumentId → symbol` 映射的层** |
| Core | 账户、订单、行情、规则、审计、回测状态统一使用 `InstrumentId` | **Core 不持有、不查询 symbol/ticker 映射，不依赖 instrument_id 字符串格式** |

### 4.3 Core 中的具体语义

以下对象的 `instrument_id` 都应迁移为 canonical `InstrumentId`：

**数据入口层**
- `Slice.bars` — dict key
- `MarketSnapshot.instrument_id`

**状态层**
- `Position.instrument_id`
- `Order.instrument_id`
- `FillEvent.instrument_id`

**执行层**
- `InstrumentDefinition.instrument_id`
- `TradingRuleSet.instrument_id`
- `FeeSchedule.instrument_id`
- `TargetPortfolioLike.positions` — dict key
- `ExecutionPlanner` — 内部 dict key
- `InstrumentRuleProvider` — Protocol 接口签名（`list[InstrumentId]` → `dict[InstrumentId, InstrumentRules]`）

**审计层**
- `RunManifest.rule_refs` — `RuleRef.instrument_id`
- `PreTradeDecisionRecord.instrument_id`
- `RiskScanRecord.instrument_id`

**引用层**
- `EngineConfig.benchmark_id`
- `StrategyInputBundle` — instrument_ids 列表

### 4.4 Port 适配层的变化

`MarketServiceDataFeed` 不再把 bars key 映射成 `"510300.SH"` 这类 source ticker，而是：

1. Universe 查询返回 `list[InstrumentId]`
2. `Slice.bars` 以 `InstrumentId` 为 key
3. 单独维护 `display_symbol_by_id: dict[InstrumentId, str]`（在 `_ensure_loaded()` 时一次性构建，使用 start_date 快照）
4. artifact writer / audit serializer 在写出时补展示字段

**display map 生命周期**：
- 构建时机：`MarketServiceDataFeed._ensure_loaded()` 时
- 持有者：`MarketServiceDataFeed` 实例
- 消费者：`ArtifactWriter`、CLI logger（通过 Port 层服务传递）
- 复用：可复用 `InstrumentReader.get_instrument_id_ticker_map()` 和 `enrich_with_ticker()`

这样 Core 热路径不再依赖 symbol，而 CLI / artifact 仍然保留可读性。

### 4.5 DataHub 规则表的统一

当前 `trading_rule` 使用 `TEXT instrument_id`，这与 metadata 主 schema 的 canonical int 模型冲突。推荐统一为：

- `trading_rule.instrument_id INTEGER`
- `fee_schedule.instrument_id INTEGER`
- 任何 execution-facing PIT 规则表均以 canonical ID 为主键

同时需要同步修改：
- `InstrumentRuleProvider`（DataHub 侧）— `DefinitionRecord.instrument_id` 类型、`_definitions` dict key 类型、查询方法签名
- `TradingRuleReader` / `FeeScheduleReader` — 内部存储 key 类型

如果短期要兼容旧表，可以先做 reader 双读、writer 新写，最后完成 schema migration。

---

## 5. 迁移策略

### Phase 0：引入统一语义层，不改主链行为

**目标**
- 新增 `InstrumentId` NewType 和 `InstrumentRef`
- 不立即改 Core 主键类型

**Files**
- Create: `ditto_*.models.identity`（位置待定）
- Modify: 对应 `models/__init__.py`
- Create: 对应 unit tests

**验收标准**
- `from ditto_*.models.identity import InstrumentId, InstrumentRef` 可用
- `pixi run -e dev type` 通过

### Phase 1：Port 层切换输入语义，建立 display map

**前置门禁**：语义断裂扫描 — grep Core 层所有 `instrument_id` 上的字符串操作（`split(".")`、`startswith()`、`endswith()` 等），确认没有依赖 source_ticker 格式的代码。如有，需先修复。

**目标**
- Port 层 `MarketServiceDataFeed` 将 Core 输入从 `str(source_ticker)` 切换为 `str(canonical_id)`
- 构建 `display_symbol_by_id` 映射供 artifact writer 使用
- Core 层类型签名暂不变（仍为 `str`），但语义已变更

**Files**
- Modify: `apps/port/src/ditto_port/services/strategy/market_data_feed.py`
  - `_resolve_ticker_map()` → `_resolve_display_map()`（产 `dict[InstrumentId, str]`）
  - `_build_bars_by_date()` — key 从 `ticker_map[instrument_id]` 改为 `str(instrument_id)`
- Modify: `apps/port/src/ditto_port/services/strategy/backtest_runtime_builder.py`
- Modify: `apps/port/src/ditto_port/services/strategy/artifact_writer.py` — 支持 display map 注入
- Modify: `apps/port/tests/unit/services/strategy/test_market_service_data_feed_unit.py`
- Modify: `apps/port/tests/unit/services/strategy/test_artifact_writer_unit.py`

**关键动作**
1. DataFeed 组装阶段保留 canonical `InstrumentId`，`Slice.bars` key 改为 `str(canonical_id)`
2. 额外产出 `display_symbol_by_id` 映射
3. artifact writer 使用 display map 输出双字段
4. 删除 `_resolve_ticker_map()` 中的 `str(instrument_id)` fallback 逻辑

**验收标准**
- `MarketServiceDataFeed` 单测通过，`Slice.bars` 的 key 为 `str(canonical_id)` 格式
- `pixi run -e dev check` 通过

### Phase 2：Core 运行时主键切换到 canonical `InstrumentId`

**目标**
- 回测/执行/账户全链切到 `InstrumentId`
- 按依赖顺序分 8 个子步骤推进，每步可独立编译和测试

**依赖图与子步骤**

```
MarketSnapshot ←── Slice ←── DataFeed Protocol
      ↓                              ↑
Position / Order               EngineLoop
      ↓                              ↑
Account / OrderBook         ExecutionPlanner
      ↓                          ↗        ↖
  TargetPortfolio      Brokerage     InstrumentRuleProvider
```

| 子步骤 | 改动对象 | 依赖 | 关键文件 |
|--------|---------|------|---------|
| **2a** 数据入口 | `MarketSnapshot.instrument_id`、`Slice.bars`、`DataFeed` Protocol | 无 | `execution/reality/market.py`, `backtest/data_feed.py` |
| **2b** 状态层 | `Position`、`Order`、`FillEvent` | 2a | `accounting/position.py`, `accounting/order_book.py`, `execution/fills.py` |
| **2c** 账户层 | `Account`、`CashBook` | 2b | `accounting/account.py` |
| **2d** 规则层（可与 2a 并行） | `InstrumentRuleProvider` Protocol、`InMemoryRuleProvider`、`InstrumentDefinition`、`TradingRuleSet`、`FeeSchedule` | 无 | `execution/rules.py` |
| **2e** 执行层 | `ExecutionPlanner`、`Brokerage` | 2b + 2d | `execution/planner.py` |
| **2f** 引用层 | `TargetPortfolioLike`、`EngineConfig.benchmark_id` | 2b | `execution/targets.py`, `backtest/engine.py` |
| **2g** 引擎层 | `EngineLoop`、`EngineConfig` | 2a + 2e + 2f | `backtest/engine.py` |
| **2h** 审计层 | `RunManifest`、`RuleRef`、`PreTradeDecisionRecord`、`RiskScanRecord` | 2g | `backtest/manifest.py` |

**每步验收标准**
- `pixi run -e dev check` 通过
- 对应模块的单元测试通过
- `pixi run -e dev arch-check` 通过（确认无分层违规）

**全部完成后的集成验证**
```bash
pixi run -e dev pytest packages/core/tests/integration/backtest/test_reproducibility.py -v
```

### Phase 3：DataHub 规则子域 schema 收敛

**目标**
- 规则/费率等 execution-facing 表与 canonical ID 对齐
- DataHub 侧 `InstrumentRuleProvider` 同步迁移

**Files**
- Modify: `packages/data/src/ditto_data/stores/metadata/trading_rule_reader.py`
- Modify: `packages/data/src/ditto_data/stores/metadata/fee_schedule_reader.py`
- Modify: `packages/data/src/ditto_data/services/strategy/instrument_rule_provider.py` — `DefinitionRecord.instrument_id`、`_definitions` dict key、查询方法签名
- Modify: `packages/data/src/ditto_data/scripts/schema.sql`
- Modify: `packages/data/tests/unit/stores/metadata/...`
- Modify: `packages/data/tests/unit/services/strategy/test_strategy_run_service_unit.py`

**关键动作**
1. 将 `TEXT instrument_id` 收敛为 canonical integer
2. `InstrumentRuleProvider` 的 dict key 和方法签名同步改为 `InstrumentId`
3. 如需迁移，先做 reader dual-read，再做 writer cutover

**验收标准**
- 规则表 reader 单测通过
- `InstrumentRuleProvider` 的 DataHub 实现和 Core `InMemoryRuleProvider` 都能正确对接
- `pixi run -e dev check` 通过

### Phase 4：清理桥接与语义债务

**目标**
- 删除"source_ticker 当主键"的残留逻辑
- 清理测试中的 hardcode source ticker fixture
- 文档全部更新

**Files**
- Modify: `apps/port/src/ditto_port/services/strategy/market_data_feed.py` — 清理 ticker_map 残留
- Modify: `apps/port/src/ditto_port/services/strategy/input_assembler.py` — 确认 instrument_ids 传播使用 `InstrumentId`
- Modify: `packages/core/src/ditto_core/portfolio/report_views.py` — 如有 instrument_id 引用则迁移
- Modify: `docs/plans/2026-03-21-strategy-engine-system-design-v3.md`
- Modify: `packages/core/src/ditto_core/strategy/README.md`
- Modify: `packages/core/src/ditto_core/portfolio/README.md`
- Modify: 所有测试文件中 hardcode 的 source ticker fixture

**验收标准**
- `pixi run -e dev check` + `pixi run -e dev arch-check` 全绿
- grep 确认 Core 层无 source_ticker 引用

---

## 6. 测试与验证策略

### 6.1 前置测试（Phase 1 之前）

| 测试 | 目的 |
|------|------|
| **语义断裂扫描** | grep Core 层所有 `instrument_id` 上的字符串操作（`split(".")`、`startswith()`、`endswith()`、`in` 等），确认无格式依赖 |
| `identifier → InstrumentId → symbol` 双向解析回归测试 | DataHub 层已有能力（`resolve_instrument_id` + `get_source_ticker`），回归验证 |

### 6.2 Phase 级测试

| Phase | 必须通过的测试 |
|-------|--------------|
| Phase 0 | `InstrumentId` NewType 类型检查通过 |
| Phase 1 | `MarketServiceDataFeed` 以 canonical ID 组装 `Slice` 的单测；display map 构建正确性测试（含边界：映射缺失 fallback） |
| Phase 2 | 每个子步骤对应的模块单元测试；`ExecutionPlanner / Brokerage / Account` 在 `InstrumentId` 语义下的回归测试；`InstrumentRuleProvider` Protocol 契约变更后的集成测试（DataHub 实现 + Core `InMemoryRuleProvider` 对接） |
| Phase 3 | `RuleProvider` 按 canonical ID 查询规则的 PIT 测试；benchmark_id 迁移后 `benchmark_close_by_date` 正确性测试 |
| Phase 4 | 全量回归：`pixi run -e dev check` + `pixi run -e dev arch-check` |

### 6.3 必须通过的验证命令

```bash
# 每个子步骤完成后
pixi run -e dev check

# Phase 2 全部完成后
pixi run -e dev pytest packages/core/tests/unit/execution -v
pixi run -e dev pytest packages/core/tests/integration/backtest/test_reproducibility.py -v

# Phase 3 完成后
pixi run -e dev pytest packages/data/tests/unit/services/strategy/test_strategy_run_service_unit.py -v

# 最终验收
pixi run -e dev check
pixi run -e dev arch-check
```

---

## 7. 风险与控制

### 风险 1：人类可读性退化

**表现**
- artifact、日志、调试输出只剩数字 ID

**控制**
- 所有对外输出统一双字段：`instrument_id` + `instrument_symbol`
- Port 层 `ArtifactWriter` 在序列化时注入展示字段
- CLI 日志通过 Port 层的格式化函数输出，开发阶段接受部分日志可读性下降

### 风险 2：Phase 2 一次性大迁移范围过大

**表现**
- Core 热路径类型变更过多，回归面过宽

**控制**
- 按 §5.2 依赖图拆为 8 个子步骤（2a-2h），每步有独立验收标准
- 2a 和 2d 可并行执行（无依赖关系）
- 每步完成后必须 `pixi run -e dev check` + `pixi run -e dev arch-check` 全绿

### 风险 3：DataHub 内部子域继续各自演化

**表现**
- metadata 是 int，rules 是 str，artifact 又回到 symbol

**控制**
- 明确 canonical ID 是唯一内部主键，任何偏离都必须写成 display field，而不是主键
- 代码审查清单：新增涉及 instrument 标识的代码时，必须使用 canonical ID，source ticker 只能出现在 display/output 上下文

### 风险 4：Phase 1 隐式语义变更导致测试假通过

**表现**
- Core 输入从 `source_ticker` 改成 `str(canonical_id)`，但类型签名仍为 `str`，测试可能假通过
- dict key 的哈希分布变化可能暴露隐性 bug

**控制**
- Phase 1 前置门禁：语义断裂扫描，确认 Core 层无 `instrument_id` 字符串格式依赖
- Phase 1 后立即跑 Core 全量测试，关注是否有因 key 语义变化导致的意外行为

### 风险 5：display map 在长区间的一致性

**表现**
- 证券经历换代码（ETF 合并、更名）时，start_date 快照的 ticker 与后续日期不同

**控制**
- 已在非目标中声明：本轮 display map 使用 start_date 快照，不做 PIT symbol 解析
- 将来需要时再引入 PIT symbol 查询能力

---

## 8. 结论

这个问题的本质不是"把一个字段从 `str` 改成 `int`"，而是 Ditto 目前缺少一套显式的证券身份语义模型。推荐方案是：

1. `InstrumentId` 成为运行时唯一 canonical 主键
2. `source_ticker` / `standard_ticker` 从"状态主键"降级为"边界输入 + 展示字段"
3. Port 负责解析与显示映射，Core 负责稳定状态与可回放行为
4. **Core 层只使用 `InstrumentId`，不持有、不查询 symbol/ticker 映射，所有展示层字段的注入由 Port 层在边界完成**

只有这样，后续 comparison artifact、多 source、API/job flow、策略回放与 audit 才不会继续建立在临时桥接之上。

---

## 9. 完成记录

> **COMPLETED (2026-03-25)**

### Phase 0 — COMPLETED
- `InstrumentId = NewType("InstrumentId", int)` 定义于 `packages/kernel/src/ditto_kernel/identity.py`
- 实施范围超越原计划，已深度集成到 Core/DataHub/Port 三层（~29 个业务文件）
- `InstrumentRef` 未实现（YAGNI — 当前 `dict[InstrumentId, str]` display_map 已满足需求）

### Phase 1 — COMPLETED
- `MarketServiceDataFeed` 已构建 `display_map` 属性（`dict[InstrumentId, str]`）
- `Slice.bars` key 已切换为 `InstrumentId`
- `ArtifactWriter` 已支持 `display_map` 参数，审计日志输出注入 `instrument_symbol` 展示字段
- `BacktestServiceOptions.display_map` 已添加，`BacktestService._persist_artifact()` 已传递

### Phase 2 — COMPLETED (10/10)
- 数据入口：`MarketSnapshot.instrument_id`、`Slice.bars` key
- 状态层：`Position`、`Order`、`FillEvent`
- 执行层：`ExecutionPlanner`、`InstrumentRuleProvider`、`InMemoryRuleProvider`
- 引用层：`TargetPortfolioLike.positions`、`EngineConfig.benchmark_id`
- 审计层：`RuleRef.instrument_id`、`RunManifest.input_refs`

### Phase 3 — COMPLETED (3/3)
- `TradingRuleRecord`、`FeeScheduleRecord`、`DefinitionRecord` 均为 `InstrumentId`
- SQL schema 统一 `INTEGER`，映射转换正确

### Phase 4 — COMPLETED
- `input_assembler.py` 传播链路正确
- Core 层 `source_ticker` 残留仅 quality 子域（合法业务属性）
- DataHub 层 `source_ticker` 属于数据摄入管道基础设施（合法）
- 文档已更新
