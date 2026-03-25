# 策略引擎 Phase 2 实施计划 — 主计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完整回测闭环 — 日历步进 → 调仓触发 → 订单执行 → 成交模拟 → 统计输出

**Architecture:** Phase 2 是回测引擎实现阶段，产出 `execution/`（扩展）、`backtest/`（新增）两个 Core 子模块。`execution/` 扩展 Phase 0 的 Order/FillOutcome 为完整执行层；`backtest/` 作为编排层持有 Account 实例（state owner），依赖 strategy + execution + accounting。所有代码为纯计算，无 I/O，规则数据通过 dict 参数传入（不依赖 DataHub PIT 查询）。

**Tech Stack:** Python 3.13, dataclass(frozen=True), Protocol, pytest

**Design Doc:** `docs/plans/2026-03-21-strategy-engine-system-design-v3.md` §4-6, §8-9

**Prerequisite:** Phase 0 + Phase 1 已提交到 main

**Simplification Policy:**
- 简化版 ExecutionPlanner: 不含 T+1 冻结、涨跌停预检、100+1 手数，只做 pending-aware diff
- 简化版 Brokerage: 佣金 = max(5, amount × 0.03%)，滑点 = 固定 2bp，不区分 ETF/股票
- V1 PreTrade: 只检查 buying_power + lot_size（不含 concentration / turnover）
- V1 PostTrade: 空（Phase 4 才实现）
- DataHub: Phase 2 不消费 InstrumentRuleProvider，规则数据通过 dict/参数传入

---

## Phase 2 范围

```
输入: ParquetDataFeed (市场数据) + StrategyPipeline (Phase 1) + EngineConfig
  ↓
EngineLoop 编排:
  日历步进 → 调仓触发 → Pipeline → ExecutionPlanner (pending-aware)
  → PreTradeCheck (rolling, resize recheck) → Brokerage (模拟成交)
  → AuditCollector (NAV + Stats)
  ↓
输出: BacktestReport (NAV 曲线 + 交易明细 + PortfolioStatistics)
```

**包含：**
- Order / OrderEvent 模型 + TradeBuilder (FIFO)
- ExecutionPlanner 简化版（pending-aware diff, F2; locked_instruments, S1）
- BacktestBrokerage 简化版（线性佣金 + 固定滑点 + FillOutcome）
- CompositePreTradeCheck V1（buying_power + lot_size, resize recheck A1）
- PreTradeContext（逐单滚动, F1; 卖出递减 available_quantity, B3）
- EngineLoop（日历步进 + 调仓触发 + 状态编排）
- ParquetDataFeed（从 parquet 读取市场数据）
- ExecutionAuditCollector V1（NAV + PortfolioStatistics + order_log + fill_log）
- etf_rotation 回测集成测试（快照测试 + 不变量测试）

**不包含（后续 Phase）：**
- A 股完整交易规则（涨跌停/T+1/100+1/停牌）→ Phase 3
- 完整风控（PreTrade 6 规则 + PostTrade 4 规则 + RiskLock）→ Phase 4
- RunManifest + RuleRefs + 确定性回放 → Phase 4
- 多策略模板扩展 → Phase 5

---

## 子计划索引（按执行顺序）

| # | 子计划 | 范围 | 复杂度 | 依赖 |
|---|--------|------|--------|------|
| 01 | [order-trade-builder](2026-03-22-strategy-engine-phase2-01-order-trade-builder.md) | Order + OrderEvent + TradeBuilder (FIFO) | M | Phase 0 |
| 02 | [execution-planner](2026-03-22-strategy-engine-phase2-02-execution-planner.md) | ExecutionPlanner 简化版 (pending-aware, locked) | L | Part 01 |
| 03 | [backtest-brokerage](2026-03-22-strategy-engine-phase2-03-backtest-brokerage.md) | Brokerage Protocol + BacktestBrokerage + 简化 Reality Model | L | Part 01 |
| 04 | [pre-trade-v1](2026-03-22-strategy-engine-phase2-04-pre-trade-v1.md) | CompositePreTradeCheck V1 + PreTradeContext | L | Part 02 + 03 |
| 05 | [engine-loop](2026-03-22-strategy-engine-phase2-05-engine-loop.md) | EngineLoop 骨架 + 日历步进 + 状态编排 | L | Part 02 + 03 + 04 |
| 06 | [parquet-data-feed](2026-03-22-strategy-engine-phase2-06-parquet-data-feed.md) | ParquetDataFeed + DataFeed Protocol | M | Part 05 |
| 07 | [audit-collector-v1](2026-03-22-strategy-engine-phase2-07-audit-collector-v1.md) | ExecutionAuditCollector V1 + PortfolioStatistics | L | Part 05 |
| 08 | [backtest-integration](2026-03-22-strategy-engine-phase2-08-backtest-integration.md) | etf_rotation 回测快照测试 + 不变量测试 | M | Part 01-07 |

## 执行顺序

```
01 Order + TradeBuilder (M) ──── 无依赖，Phase 0 完成即可
02 ExecutionPlanner (L) ──────── 依赖 01（需要 Order）
03 BacktestBrokerage (L) ─────── 依赖 01（需要 Order + FillOutcome）
04 PreTrade V1 (L) ───────────── 依赖 02 + 03（需要 AccountView + rules）
05 EngineLoop 骨架 (L) ────────── 依赖 02 + 03 + 04（核心编排器）
06 ParquetDataFeed (M) ────────── 依赖 05（需要 DataFeed Protocol）
07 AuditCollector V1 (L) ──────── 依赖 05（需要 EngineLoop 调用 record）
08 回测集成测试 (M) ──────────── 依赖 01-07（全部就绪）
```

推荐路径：**01 → 02 → 03 → 04 → 05 → 06 → 07 → 08**

02 和 03 可并行加速。06 和 07 可并行加速。

## Phase 2 交付物清单

### Core 层新增/扩展模块

```
ditto_core/
├── execution/                    # [Phase 0 已有] 扩展
│   ├── __init__.py               # 扩展导出
│   ├── orders.py                 # [Part 1] Order / OrderEvent / OrderType / OrderDirection
│   ├── planner.py                # [Part 2] ExecutionPlanner + ExecutionPlan + BlockedOrder
│   ├── brokerage.py              # [Part 3] Brokerage Protocol + BacktestBrokerage
│   ├── trade_builder.py          # [Part 1] TradeBuilder / FifoTradeBuilder / TradeRecord
│   └── reality/                  # [Part 3] 简化 Reality Model
│       ├── __init__.py
│       ├── fill.py               #     SimpleFillModel
│       ├── slippage.py           #     FixedBpsSlippage
│       ├── fee.py                #     SimpleFeeModel
│       └── settlement.py         #     SimpleSettlementModel
│
└── backtest/                     # [Phase 2 新增] 回测引擎编排层
    ├── __init__.py
    ├── engine.py                 # [Part 5] EngineLoop / EngineConfig / EngineResult / PreTradeContext
    ├── data_feed.py              # [Part 6] DataFeed Protocol / ParquetDataFeed / Slice / MarketSnapshot
    └── audit/                    # [Part 7] 统计与审计层
        ├── __init__.py
        ├── collector.py          #     ExecutionAuditCollector
        ├── models.py             #     RiskScanRecord / PreTradeDecisionRecord
        ├── portfolio.py          #     PortfolioStatistics
        └── trade.py              #     TradeStatistics
```

### 测试

```
packages/core/tests/
├── unit/execution/
│   ├── test_orders_unit.py           # [Part 1] Order + OrderEvent
│   ├── test_trade_builder_unit.py    # [Part 1] FIFO trade matching
│   ├── test_planner_unit.py          # [Part 2] ExecutionPlanner
│   ├── test_brokerage_unit.py        # [Part 3] BacktestBrokerage
│   ├── test_fill_model_unit.py       # [Part 3] SimpleFillModel
│   ├── test_fee_model_unit.py        # [Part 3] SimpleFeeModel
│   └── test_slippage_unit.py         # [Part 3] FixedBpsSlippage
│
├── unit/backtest/
│   ├── test_pre_trade_unit.py        # [Part 4] PreTradeCheck + PreTradeContext
│   ├── test_engine_loop_unit.py      # [Part 5] EngineLoop
│   ├── test_data_feed_unit.py        # [Part 6] ParquetDataFeed
│   ├── test_audit_collector_unit.py  # [Part 7] AuditCollector
│   └── test_portfolio_stats_unit.py  # [Part 7] PortfolioStatistics
│
└── integration/backtest/
    ├── test_backtest_snapshot.py     # [Part 8] 快照测试
    └── test_backtest_invariants.py   # [Part 8] 不变量测试
```

## 质量门禁

每个子计划完成后执行：

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
```

Phase 2 全部完成后执行：

```bash
pixi run -e dev ci             # CI 完整检查
```

## 里程碑

**Phase 2 完成标志：** ETF 轮动策略 BACKTEST 闭环 — 给定 parquet 市场数据 + 策略配置，EngineLoop 输出合法的 BacktestReport，含 NAV 曲线 + 交易明细 + PortfolioStatistics，且快照测试 + 不变量测试全部通过。

**Phase 2 状态：✅ 已完成（2026-03-22）**
- Part 01-07 全部完成，Part 08 集成测试通过
- 3260 个测试全部通过（含 28 planner 单元测试 + 55 集成测试）
- lint / format / type 检查通过

## v3 修订落地图

| 修订 | Phase 2 落地位置 |
|------|----------------|
| F1 (rolling PreTradeContext) | Part 04 PreTradeContext + Part 05 EngineLoop._build_pre_trade_context |
| F2 (pending-aware diff) | Part 02 ExecutionPlanner._compute_pending_delta |
| A1 (resize recheck) | Part 04 CompositePreTradeCheck |
| B1 (resized_quantity 统一处理) | Part 05 EngineLoop._step accept 路径 |
| B2 (NoFill can_retry=False → INVALID) | Part 03 BacktestBrokerage.process_pending |
| B3 (卖出递减 available_quantity) | Part 04 PreTradeContext.with_order_accepted |
| B4 (Slice.step_time) | Part 05 EngineLoop + Part 06 DataFeed |
| S1 (Planner lock) | Part 02 ExecutionPlanner locked_instruments |

## 注意事项

1. **纯计算**：所有 Phase 2 代码无 I/O，无网络，无文件系统访问（DataFeed 通过 Protocol 注入）
2. **简化版规则**：Phase 2 不处理 A 股完整交易规则（涨跌停/T+1/100+1/停牌），Phase 3 替换
3. **规则数据 dict 传入**：不依赖 DataHub PIT 查询，规则通过参数 dict 传入
4. **frozen dataclass**：新增数据结构遵循 Phase 0 约定
5. **PostTrade V1 为空**：Phase 4 才实现 PostTradeRiskGuard
6. **PreTrade V1 仅 2 条规则**：buying_power + lot_size，Phase 4 扩展到 6 条
