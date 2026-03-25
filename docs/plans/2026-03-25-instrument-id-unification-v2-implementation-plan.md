# Instrument ID Semantics Unification v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一 `instrument_id` 在 DataHub / Core / Port 三层中的语义，将 Core 热路径从 source_ticker（str）切换为 canonical `InstrumentId`（int），建立可长期演进的单一身份模型。

**Architecture:** `InstrumentId = NewType("InstrumentId", int)` 已定义在 `ditto_kernel.identity`。Port 层 `MarketServiceDataFeed` 将 DataHub 的 `int` ID 直接作为 `InstrumentId` 传给 Core，不再做 `int → source_ticker` 转换。display map 独立维护供 artifact 使用。Core 层完全不可知展示信息。Port 层复用现有 `Instrument` 模型，不创建新的身份类型。

**Tech Stack:** Python 3.13, dataclasses, NewType, polars, sqlite, pytest, basedpyright, import-linter

**设计文档:** [shared-kernel-and-model-governance-design](2026-03-24-shared-kernel-and-model-governance-design.md)
**前置完成:** [kernel-package-creation](2026-03-24-kernel-package-creation.md) (Status: COMPLETED)

---

## 1. 身份概念模型

Ditto 系统中存在 4 种资产标识（不存在 symbol 概念）：

| 标识 | 类型 | 示例 | 职责 | 归属层 |
|------|------|------|------|--------|
| `InstrumentId` | `NewType("InstrumentId", int)` | `1000001` | 系统内部 canonical 主键，跨层唯一 | kernel |
| `ticker` | `str` | `000001` | 裸代码，无交易所信息 | DataHub metadata |
| `source_ticker` | `str` | `000001.SH` | 数据源供应商的资产代码（含 source 交易所后缀），1:N 关系 | DataHub mapping |
| `standard_ticker` | `str` | `000001.SSE` | Ditto 内部标准化展示代码（用自己的交易所标识拼接） | Port display |

**关键语义关系**：

```
InstrumentId (1) ──→ (N) source_ticker
                      ├── tushare: "000001.SH"
                      ├── wind:   "000001.SS"
                      └── eastmoney: "000001"

Instrument (1) ──→ ticker (1): "000001"
               ──→ standard_ticker (1): "000001.SSE" (computed: ticker + Ditto exchange code)
```

**source_ticker 解析是 DataHub 的职责**，不属于 Port 编排层。Port 通过 DataHub 的 `resolve_instrument_id()` 完成解析。

**不创建新的 Port 层身份类型**：Port 复用现有 `Instrument` Pydantic 模型（`ditto_port.models.metadata.Instrument`），从中提取 `InstrumentId` 传给 Core，按需取 `ticker` / `exchange` 构造 display map。

---

## 2. 当前问题

### 2.1 现状

| 层 | 当前主语义 | 证据 |
|---|---|---|
| DataHub 元数据/存储 | `instrument_id: int` | schema.sql, metadata.py |
| DataHub 规则表 | `instrument_id: TEXT`（存储 source_ticker） | trading_rule_reader.py, fee_schedule_reader.py |
| Port 策略适配层 | 从 `int` 转换到 `str(source_ticker)` 后喂给 Core | market_data_feed.py `_resolve_ticker_map()` |
| Core 全链路 | `instrument_id: str`（实际存储 source_ticker） | data_feed.py, market.py, position.py, rules.py 等 |

### 2.2 核心问题

1. **source_ticker 泄漏到 Core 热路径** — dict key、持仓 key、规则 key、审计日志 key 都默认把 source_ticker 当主键
2. **身份不稳定** — source_ticker 受 source、PIT 映射、换代码影响，Core 用它做状态 key 导致回放脆弱
3. **适配责任落在错误层次** — `MarketServiceDataFeed` 负责翻译，每个执行入口都重复定义
4. **规则子域不一致** — DataHub metadata 用 int，规则表用 TEXT，两套语义并存

---

## 3. 设计决策

| 决策 | 结论 | 理由 |
|------|------|------|
| `InstrumentId` 归属 | `ditto_kernel.identity` | 已完成（kernel 包已创建） |
| Port 身份类型 | 复用现有 `Instrument` 模型 | Instrument 已包含完整信息，无需新建类型 |
| Core 展示信息 | Core 纯 InstrumentId，Port 负责展示注入 | Core 不持有、不查询 symbol/ticker 映射 |
| 迁移策略 | Port + Core 同步一步到位 | 避免"语义已变但类型仍为 str"的中间态 |
| DataHub 规则表 | 直接改 schema，无历史数据迁移 | 开发阶段，无线上数据 |
| display map 来源 | DataHub `InstrumentReader` + `ticker + exchange` 拼接 | 复用现有查询能力 |
| `AssetClass` in DataFeed | 使用 kernel `AssetClass` | 替换当前 Literal 类型别名 |

---

## 4. 分层职责

| 层 | 职责 | 约束 |
|---|---|---|
| DataHub | canonical identity source of truth；负责 `identifier → InstrumentId` 解析与 `InstrumentId → ticker` 回查 | — |
| Port | 所有边界输入先解析到 `InstrumentId`；构建 display map；ArtifactWriter 注入展示字段 | **Port 是唯一负责 `InstrumentId → standard_ticker` 映射的层** |
| Core | 账户、订单、行情、规则、审计、回测状态统一使用 `InstrumentId` | **Core 不持有、不查询 symbol/ticker 映射** |

---

## 5. Phase 1：Port 边界 + Core 全链路同步切换 ✅ COMPLETED (2026-03-25)

### 依赖图

```
1A (Port 边界切换)
   │
   ├── 1B (Core 数据入口) ──→ 1C (Core 状态层) ──┐
   │                          │                   │
1D (Core 规则层, 可并行) ──────┤              ┌────┴────┐
                               │              │         │
                               │           1F (引用层)  │
                               │              │         │
                               └─────────→ 1E (执行层) ─┤
                                              │         │
                                           1G (引擎层) ←┘
                                              │
                                           1H (审计层)
```

> 1A 完成后 1B 和 1D 可并行启动。每步完成后必须 `pixi run -e dev check` + `pixi run -e dev arch-check` 全绿。

### 前置门禁：语义断裂扫描

Phase 1 开始前，必须 grep Core 层所有 `instrument_id` 上的字符串操作，确认无格式依赖：

```bash
grep -rn "instrument_id.*split\|instrument_id.*startswith\|instrument_id.*endswith\|instrument_id\[" packages/core/src/
```

如有发现，需先修复后才能继续。

---

### Step 1A：Port 层边界切换

**目标**
- `Instrument.instrument_id: int → InstrumentId`
- `MarketServiceDataFeed` 停止 int → source_ticker 转换，直接传 `InstrumentId`
- 构建 display map 供 artifact writer 使用
- `MarketServiceDataFeedConfig.benchmark_id` 类型调整

**Files**

| 文件 | 变更 |
|------|------|
| `apps/port/src/ditto_port/models/metadata.py` | `Instrument.instrument_id: int → InstrumentId` |
| `apps/port/src/ditto_port/services/strategy/market_data_feed.py` | 重写 `_resolve_ticker_map()` → `_build_display_map()`；`_build_bars_by_date()` key 从 `ticker_map[instrument_id]` 改为 `instrument_id`；替换 `AssetClass` Literal 别名为 kernel `AssetClass`；`MarketServiceDataFeedConfig.benchmark_id: str \| None → InstrumentId \| None` |
| `apps/port/src/ditto_port/services/strategy/artifact_writer.py` | 支持 display map 注入，artifact 输出双字段 |
| `apps/port/src/ditto_port/services/strategy/backtest_runtime_builder.py` | 适配 `InstrumentId` 类型的 benchmark_id |
| `apps/port/src/ditto_port/services/strategy/input_assembler.py` | 确认 instrument_ids 使用 `InstrumentId` |
| `apps/port/tests/unit/services/strategy/test_market_service_data_feed_unit.py` | 更新 fixture |
| `apps/port/tests/unit/services/strategy/test_artifact_writer_unit.py` | 更新 fixture |
| `apps/port/tests/unit/models/test_metadata_unit.py` | `instrument_id` fixture 改为 `InstrumentId` |

**关键动作**

1. `Instrument.instrument_id` 改为 `InstrumentId` 类型，`to_instrument()` 中 `row["instrument_id"]` 包装为 `InstrumentId(...)`
2. `MarketServiceDataFeed`：
   - 删除 `_resolve_ticker_map()` 方法
   - 新增 `_build_display_map()` → `dict[InstrumentId, str]`（从 Instrument records 的 `ticker + exchange` 拼接 standard_ticker）
   - `_build_bars_by_date()` 中 `MarketSnapshot.instrument_id` 直接使用 `InstrumentId`，不再做 str 转换
   - 内部 `_bars_by_date` 的 outer key 仍为 date（str），inner key 改为 `InstrumentId`
   - `get_slice()` 返回的 `Slice.bars` key 改为 `InstrumentId`
3. `ArtifactWriter`：接收 `display_map: dict[InstrumentId, str]` 参数，序列化时在输出中注入 `instrument_symbol` 字段

**验收标准**
- `pixi run -e dev check` 通过
- `MarketServiceDataFeed` 单测：`Slice.bars` 的 key 为 `InstrumentId` 类型
- display map 正确构建

---

### Step 1B：Core 数据入口层

**目标**
- `MarketSnapshot.instrument_id: str → InstrumentId`
- `Slice.bars: dict[str, MarketSnapshot] → dict[InstrumentId, MarketSnapshot]`
- `DataFeed` Protocol 签名更新
- `ParquetDataFeed` 适配

**Files**

| 文件 | 变更 |
|------|------|
| `packages/core/src/ditto_core/execution/reality/market.py` | `MarketSnapshot.instrument_id: str → InstrumentId` |
| `packages/core/src/ditto_core/backtest/data_feed.py` | `Slice.bars: dict[str, ...] → dict[InstrumentId, ...]`；`DataFeed` Protocol 签名；`ParquetDataFeed.__init__(instrument_ids: list[str]) → list[InstrumentId]`；内部 dict key 全部 `str → InstrumentId` |
| `packages/core/tests/unit/backtest/test_data_feed_unit.py` | fixture 更新 |

**关键动作**

1. `MarketSnapshot` 的 `instrument_id` 改为 `InstrumentId`
2. `Slice` 的 `bars` dict key 改为 `InstrumentId`
3. `ParquetDataFeed` 的文件名仍为 `{ticker}.parquet`（物理文件名不受影响），但内存中的 dict key 统一为 `InstrumentId`
4. `DataFeed` Protocol 的 `get_slice()` 返回类型自动跟随 `Slice` 更新

**验收标准**
- `pixi run -e dev check` 通过
- `ParquetDataFeed` 单测通过，bars dict key 为 `InstrumentId`

---

### Step 1C：Core 状态层

**目标**
- `Position`、`Order`、`FillEvent` 的 `instrument_id: str → InstrumentId`
- `Account` 内部 dict key 更新

**Files**

| 文件 | 变更 |
|------|------|
| `packages/core/src/ditto_core/accounting/position.py` | `Position.instrument_id: str → InstrumentId` |
| `packages/core/src/ditto_core/accounting/order_book.py` | `Order.instrument_id: str → InstrumentId` |
| `packages/core/src/ditto_core/execution/fills.py` | `FillEvent.instrument_id: str → InstrumentId` |
| `packages/core/src/ditto_core/accounting/account.py` | `_positions: dict[str, Position] → dict[InstrumentId, Position]` |
| 对应测试文件 | fixture 更新 |

**验收标准**
- `pixi run -e dev check` 通过
- Core accounting + fills 单测全通过

---

### Step 1D：Core 规则层

**目标**
- `InstrumentDefinition`、`TradingRuleSet`、`FeeSchedule` 的 `instrument_id: str → InstrumentId`
- `InstrumentRuleProvider` Protocol 签名更新
- `InMemoryRuleProvider` dict key 更新
- `RulesGetter` 类型别名更新

**Files**

| 文件 | 变更 |
|------|------|
| `packages/core/src/ditto_core/execution/rules.py` | 所有 `instrument_id: str → InstrumentId`；`RulesGetter` 签名；Protocol 方法签名；`InMemoryRuleProvider` 内部 dict key |
| `packages/core/tests/unit/execution/test_rules_unit.py` | fixture 更新 |

**关键动作**

1. `InstrumentDefinition.instrument_id: InstrumentId`
2. `TradingRuleSet.instrument_id: InstrumentId`
3. `FeeSchedule.instrument_id: InstrumentId`
4. `InstrumentRuleProvider` Protocol 方法签名全部 `str → InstrumentId`：
   - `get_definition(instrument_id: InstrumentId)`
   - `get_trading_rule(instrument_id: InstrumentId, as_of_date: str)`
   - `get_fee_schedule(instrument_id: InstrumentId, as_of_date: str)`
   - `get_rules(as_of_date: str, instrument_ids: list[InstrumentId])`
5. `RulesGetter = Callable[[InstrumentId, str], InstrumentRules]`
6. `InMemoryRuleProvider` 内部 `_definitions`、`_trading_rules`、`_fee_schedules` dict key 全部 `str → InstrumentId`

**验收标准**
- `pixi run -e dev check` 通过
- Core rules 单测全通过

---

### Step 1E：Core 执行层

**目标**
- `ExecutionPlanner` 内部 dict key 更新
- `BlockedOrder.instrument_id: str → InstrumentId`

**Files**

| 文件 | 变更 |
|------|------|
| `packages/core/src/ditto_core/execution/planner.py` | `BlockedOrder.instrument_id: InstrumentId`；`SimpleExecutionPlanner` 内部 dict key |
| `packages/core/tests/unit/execution/test_planner_unit.py` | fixture 更新 |

**前置依赖**：1C + 1D

**验收标准**
- `pixi run -e dev check` 通过

---

### Step 1F：Core 引用层

**目标**
- `TargetPortfolioLike.positions: dict[str, float] → dict[InstrumentId, float]`
- `EngineConfig.benchmark_id: str | None → InstrumentId | None`

**Files**

| 文件 | 变更 |
|------|------|
| `packages/core/src/ditto_core/execution/targets.py` | `TargetPortfolioLike.positions` 返回类型 |
| `packages/core/src/ditto_core/backtest/engine.py` | `EngineConfig.benchmark_id: InstrumentId | None` |
| 对应测试文件 | fixture 更新 |

**前置依赖**：1C

**验收标准**
- `pixi run -e dev check` 通过

---

### Step 1G：Core 引擎层

**目标**
- `EngineLoop` 内部调整，适配 `InstrumentId` 语义

**Files**

| 文件 | 变更 |
|------|------|
| `packages/core/src/ditto_core/backtest/engine.py` | `EngineLoop` 内部 dict key、方法参数 |
| `packages/core/tests/unit/backtest/test_engine_unit.py` | fixture 更新 |

**前置依赖**：1E + 1F

**验收标准**
- `pixi run -e dev check` 通过

---

### Step 1H：Core 审计层

**目标**
- `RuleRef.instrument_id: str → InstrumentId`
- `PreTradeDecisionRecord.instrument_id: InstrumentId`
- `RiskScanRecord.instrument_id: InstrumentId`

**Files**

| 文件 | 变更 |
|------|------|
| `packages/core/src/ditto_core/backtest/manifest.py` | `RuleRef.instrument_id: InstrumentId`；`RuleRefCollector` dict key |
| `packages/core/tests/unit/backtest/test_manifest_unit.py` | fixture 更新 |

**前置依赖**：1G

**验收标准**
- `pixi run -e dev check` 通过

---

### Phase 1 集成验证

```bash
# Core 全量测试
pixi run -e dev pytest packages/core/tests/unit/ -v
pixi run -e dev pytest packages/core/tests/integration/backtest/test_reproducibility.py -v

# Port 全量测试
pixi run -e dev pytest apps/port/tests/unit/ -v

# 架构检查
pixi run -e dev arch-check
```

---

## 6. Phase 2：DataHub 规则域收敛 + 清理 ✅ COMPLETED (2026-03-25)

### Step 2A：DataHub 规则表 schema 收敛

**目标**
- `trading_rule` 和 `fee_schedule` 的 `instrument_id` 从 `TEXT` 改为 `INTEGER`
- Reader/Writer 同步更新

**Files**

| 文件 | 变更 |
|------|------|
| `packages/datahub/src/ditto_datahub/stores/metadata/trading_rule_reader.py` | `_CREATE_TABLE` schema：`instrument_id TEXT → INTEGER`；`TradingRuleRecord.instrument_id: InstrumentId`；内部 dict key；PIT query 参数 |
| `packages/datahub/src/ditto_datahub/stores/metadata/trading_rule_writer.py` | `_CREATE_TABLE` schema：`instrument_id TEXT → INTEGER`；写入方法参数类型 |
| `packages/datahub/src/ditto_datahub/stores/metadata/fee_schedule_reader.py` | 同上 |
| `packages/datahub/src/ditto_datahub/stores/metadata/fee_schedule_writer.py` | 同上 |
| `packages/datahub/src/ditto_datahub/services/strategy/instrument_rule_provider.py` | `DefinitionRecord.instrument_id: InstrumentId`；`get_definition()` / `get_rules()` 方法签名 |
| `packages/datahub/src/ditto_datahub/services/audit/execution_audit_service.py` | 审计表 `instrument_id TEXT → INTEGER`（如需） |
| 对应测试文件 | fixture 更新 |

**注意**：`trading_rule` 和 `fee_schedule` 表定义在各自的 reader/writer 文件的 `_CREATE_TABLE` 常量中，不在 `schema.sql`。无需修改 `schema.sql`。

**验收标准**
- `pixi run -e dev check` 通过
- 规则表 reader/writer 单测通过

---

### Step 2B：Port 层清理

**目标**
- 删除残留的 source_ticker 桥接逻辑
- 确认所有 instrument_ids 传播使用 `InstrumentId`

**Files**

| 文件 | 变更 |
|------|------|
| `apps/port/src/ditto_port/services/strategy/market_data_feed.py` | 确认无 ticker_map 残留 |
| `apps/port/src/ditto_port/services/strategy/input_assembler.py` | 确认 `instrument_ids = list(slice_.bars.keys())` 返回 `list[InstrumentId]` |
| `apps/port/src/ditto_port/services/strategy/artifact_writer.py` | 确认 display map 注入完成 |

**验收标准**
- `pixi run -e dev check` 通过

---

### Step 2C：测试 fixture 更新

**目标**
- 所有 hardcode 的 source ticker fixture 改为 `InstrumentId`
- 回测可重现性测试确认 hash 计算基于 `InstrumentId` 仍正确

**范围**
- 所有 Core 测试文件中 `"510300.SH"` 等 fixture
- 所有 Port 测试文件中对应的 fixture
- `test_reproducibility.py` 集成测试

**验收标准**
- grep 确认 Core 层无 source_ticker 引用：
```bash
grep -rn "510300\|159915\|\.SH\|\.SZ\|\.SSE\|\.XSHE\|\.XSHG" packages/core/src/
```

---

### Step 2D：文档更新

**Files**

| 文件 | 变更 |
|------|------|
| `docs/plans/2026-03-21-strategy-engine-system-design-v3.md` | 反映 InstrumentId 统一决策 |
| `packages/core/src/ditto_core/strategy/README.md` | identity model 说明 |
| `packages/core/src/ditto_core/portfolio/README.md` | instrument_id 语义说明 |

---

### Phase 2 最终验收

```bash
# 完整检查
pixi run -e dev check

# 架构检查
pixi run -e dev arch-check

# Core 集成测试
pixi run -e dev pytest packages/core/tests/integration/backtest/test_reproducibility.py -v

# 全量回归
pixi run -e dev ci
```

---

## 7. 测试策略

### 7.1 前置测试（Phase 1 之前）

| 测试 | 目的 |
|------|------|
| **语义断裂扫描** | grep Core 层 `instrument_id` 字符串操作，确认无格式依赖 |
| **identity 解析回归** | DataHub `resolve_instrument_id()` + `get_source_ticker()` 回归验证 |

### 7.2 Phase 级测试

| Step | 必须通过的测试 |
|------|--------------|
| 1A | `MarketServiceDataFeed` 以 `InstrumentId` 组装 `Slice`；display map 构建正确性（含边界：映射缺失 fallback） |
| 1B-1H | 每步对应的模块单元测试 |
| Phase 1 完成 | Core 全量测试 + Port 全量测试 + 回测可重现性集成测试 |
| 2A | 规则表 reader/writer 单测 |
| Phase 2 完成 | 全量回归 `pixi run -e dev ci` |

---

## 8. 风险与控制

| 风险 | 控制 |
|------|------|
| dict key 哈希分布变化（str→int） | 前置语义断裂扫描 + 每步全量测试 |
| artifact 可读性退化 | ArtifactWriter 输出双字段（`instrument_id` + `instrument_symbol`） |
| display map 在长区间不一致（换代码场景） | 本轮使用 start_date 快照，非目标：PIT symbol |
| Phase 1 范围过大 | 按 8 个子步骤拆分，每步独立验收 |
| DataHub 规则表 schema 变更 | 开发阶段无历史数据，直接改 |
| Core 仍有对 datahub.models 的导入 | arch-check 每步验证 |

---

## 9. 结论

本计划是 [instrument-id-semantics-unification](2026-03-24-instrument-id-semantics-unification-implementation-plan.md) 的 v2 更新，主要变化：

1. **Phase 0 已完成** — `ditto_kernel` 已创建，`InstrumentId` 已定义
2. **不创建 Port 层身份类型** — 复用现有 `Instrument` 模型
3. **一步到位** — Port + Core 同步切换，无中间态
4. **source_ticker 解析归属 DataHub** — 不属于 Port 编排层
5. **Core 纯 InstrumentId** — 不持有、不查询任何展示信息
6. **DataHub 规则表直接收敛** — 无历史数据迁移负担
