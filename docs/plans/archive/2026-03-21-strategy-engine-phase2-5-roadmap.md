# 策略引擎 Phase 2-5 路线图

**Status:** Phase 2 完成，Phase 3-5 详细计划已制定
**Design Doc:** `docs/plans/2026-03-21-strategy-engine-system-design-v3.md` §11

## 详细实施计划

| Phase | 计划文件 | 状态 | 子计划数 |
|-------|---------|------|---------|
| Phase 0 | `2026-03-21-strategy-engine-phase0-00-master.md` | 完成 | 5 |
| Phase 1 | `2026-03-21-strategy-engine-phase1-00-master.md` | 完成 | 4 |
| Phase 2 | `2026-03-22-strategy-engine-phase2-00-master.md` | **完成** | 8 |
| Phase 3 | `2026-03-22-strategy-engine-phase3-00-master.md` | Draft | 8 |
| Phase 4 | `2026-03-22-strategy-engine-phase4-00-master.md` | Draft | 8 |
| Phase 5 | `2026-03-22-strategy-engine-phase5-00-master.md` | Draft | 7 |

---

## 总览

```
Phase 0  ───→  Phase 1  ───→  Phase 2  ───→  Phase 3  ───→  Phase 4  ───→  Phase 5
 基础契约     Pipeline闭环    回测V1        Reality Model   风控+统计     多模板扩展
 (完成)       (完成)          (完成)        (A股完整)       (完善)        (扩展)
```

**关键路径**: Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
**并行机会**: Phase 4 和 Phase 5 可部分并行（Phase 5 的模板开发不依赖 Phase 4 的全部风控功能）

---

## Phase 2: 日频回测 V1（简化版）

**Goal:** 完整回测闭环 — 日历步进 → 调仓触发 → 订单执行 → 成交模拟 → 统计输出

**里程碑:** ETF 轮动策略 BACKTEST 闭环 + 基础统计报告（NAV 曲线 + 交易明细）

### 子计划（初步拆分）

| # | 子计划 | 范围 | 复杂度 |
|---|--------|------|--------|
| 01 | ExecutionPlanner (简化版) | pending-aware diff (F2)，不含 T+1/涨跌停 | L |
| 02 | BacktestBrokerage (简化版) | 线性佣金 + 固定滑点 + FillOutcome | L |
| 03 | EngineLoop | 日历步进 + 调仓触发 + rolling PreTrade (F1) | XL |
| 04 | PreTrade + PostTrade V1 | CompositePreTradeCheck (A1)，基础 PostTrade | L |
| 05 | ParquetDataFeed + AuditCollector V1 | 数据读取 + NAV/PortfolioStats + order_log/fill_log | L |
| 06 | 回测集成测试 | etf_rotation 3-5 日快照测试 + 不变量测试 | M |

### 关键设计决策

- **简化版 ExecutionPlanner**: 不处理 T+1 冻结、涨跌停预检、100+1 手数，只做简单的 pending-aware diff
- **简化版 Brokerage**: 佣金 = max(5, amount × 0.03%)，滑点 = 固定 2bp，不区分 ETF/股票
- **V1 PreTrade**: 只检查 buying_power + lot_size（不含 concentration / turnover）
- **V1 PostTrade**: 空（Phase 4 才实现）
- **Phase 0 Part 05 (DataHub)**: ExecutionPlanner 需要规则数据，但简化版可直接从参数传入，Part 05 可并行完成

### v3 修订对应

| 修订 | Phase 2 落地 |
|------|-------------|
| F1 (rolling PreTradeContext) | EngineLoop _build_pre_trade_context |
| F2 (pending-aware diff) | ExecutionPlanner._compute_pending_delta |
| A1 (resize recheck) | CompositePreTradeCheck |
| A2 (pre_trade audit) | ExecutionAuditCollector.record_pre_trade_decisions |
| B1 (resized_quantity 统一处理) | EngineLoop _step 内的 accept 路径 |
| B3 (卖出递减 available_quantity) | PreTradeContext.with_order_accepted |
| B4 (Slice.step_time) | EngineLoop 设置 Slice.step_time |

---

## Phase 3: Reality Model 完整化

**Goal:** 回测引擎对 A 股 ETF/股票交易规则完整建模（含规则版本化）

**里程碑:** 涨跌停/T+1/100+1/ST 场景的回测结果可信

### 子计划（初步拆分）

| # | 子计划 | 范围 | 复杂度 |
|---|--------|------|--------|
| 01 | AShareFillModel | 涨跌停/停牌/LIMIT/集合竞价 → FillOutcome | L |
| 02 | AShareFeeModel | 最低 5 元/印花税/过户费 | M |
| 03 | AShareSettlementModel | T+0/T+1 交收规则 | M |
| 04 | SlippageModel | FixedBps + VolumeShare | M |
| 05 | ExecutionPlanner 完整化 | T+1/涨跌停/停牌/100+1 规则 | L |
| 06 | 规则版本化接入 | trading_rule_store + fee_schedule_store PIT 查询 | L |
| 07 | InstrumentLifecycle | ST/*ST → price_limit_pct | M |
| 08 | 快照测试升级 | 涨跌停/ST 场景的回测快照测试 | M |

### 关键设计决策

- **规则版本化**: 复用 Phase 0 Part 05 的 PIT 基础设施（TradingRuleStore + FeeScheduleStore）
- **100+1 规则**: 买入最低 100 份起可 1 份递增；零股必须一次性卖出
- **集合竞价**: ClosingAuctionFillModel 单独实现

### v3 修订对应

| 修订 | Phase 3 落地 |
|------|-------------|
| R1 (100+1 政策溯源) | 数量取整规则 |
| R6 (三层分离签名) | 所有 Reality Model 方法签名 |
| R8 (FillOutcome 集成) | FillModel 返回 FillOutcome |

---

## Phase 4: 风控 + 统计完善

**Goal:** 三层风控 + 完整统计 + 审计日志 + 确定性回放

**里程碑:** 回测报告可直接用于策略决策

### 子计划（初步拆分）

| # | 子计划 | 范围 | 复杂度 |
|---|--------|------|--------|
| 01 | PreTradeRiskCheck 完整版 | 6 条内置规则 (buying_power/no_short/price_valid/lot_size/concentration/turnover) | L |
| 02 | PostTradeRiskGuard | 4 条内置规则 + RiskLock (R4) | L |
| 03 | RuleRefs + RunManifest | F3 全量冻结 + manifest 序列化 (P2) | M |
| 04 | TradeStatistics + AlphaStats | 交易统计 + Alpha 分析 | L |
| 05 | risk_log + pre_trade_log | R12/A2 审计 artifact | M |
| 06 | StrategyComparisonReport | 策略对比报告 | M |
| 07 | 确定性回放测试 | S4 两层测试 + P2/P4/P5 证明型测试 | L |
| 08 | 风控集成测试 | PostTrade 触发 + RiskLock + 审计日志 | M |

### v3 修订对应

| 修订 | Phase 4 落地 |
|------|-------------|
| R4 (PostTrade RiskLock) | PostTradeRiskGuard |
| F3 (RuleRefs 全量冻结) | RunManifest.rule_refs |
| R12 (risk_log) | ExecutionAuditCollector.record_risk_scan |
| S4 (确定性测试拆两层) | test_reproducible + test_version_change_diff |
| S5 (cooldown 预留) | RiskAction.cooldown_until 字段 |

---

## Phase 5: 多策略模板扩展

**Goal:** 4 个策略模板全部可用 + 选股类策略回测闭环

**里程碑:** 选股类策略（stock_selection_trend / stock_sector_rotation）回测闭环

### 子计划（初步拆分）

| # | 子计划 | 范围 | 复杂度 |
|---|--------|------|--------|
| 01 | etf_trend_swing 模板 | 趋势信号 + 追踪止损 | L |
| 02 | stock_selection_trend 模板 | 多因子选股 + 趋势过滤 | XL |
| 03 | stock_sector_rotation 模板 | 行业配置 + 行业内选股 | XL |
| 04 | inverse_vol allocator | 波动率倒数加权 | M |
| 05 | InstrumentDefinition 扩展 | 新股前 N 日 / 退市整理期 | M |
| 06 | RiskLock 跨日 cooldown | S5 实现跨日冷却 | M |
| 07 | 每个模板的回测快照测试 | 快照 + 不变量 | L |

### 与 Phase 4 的并行

Phase 5 的 Part 01 (etf_trend_swing) 和 Part 04 (inverse_vol) 不依赖 Phase 4 的风控功能，可与 Phase 4 并行开发。Part 02-03 (选股模板) 依赖 Phase 4 的完整风控。

---

## 跨 Phase 关注点

### Phase 0 Part 05 (DataHub) 补完

| 时间 | 内容 |
|------|------|
| Phase 1 期间 | 可并行完成，不阻塞 Phase 1 |
| Phase 2 开始前 | 必须完成（ExecutionPlanner 需要规则数据） |

### 新增 Core 模块

| Phase | 新增模块 |
|-------|---------|
| 1 | `portfolio/` |
| 2 | `execution/planner.py`, `execution/brokerage.py`, `execution/trade_builder.py` |
| 3 | `execution/reality/fill.py`, `execution/reality/fee.py`, `execution/reality/settlement.py`, `execution/reality/slippage.py` |
| 4 | `backtest/engine.py`, `backtest/data_feed.py`, `backtest/risk/pre_trade.py`, `backtest/risk/post_trade.py`, `backtest/audit/` |
| 5 | `strategy/builtins/templates/` 扩展 |

### 新增 DataHub 模块

| Phase | 新增模块 |
|-------|---------|
| 0 Part 5 | `stores/metadata/trading_rule_*`, `services/strategy/instrument_rule_provider` |
| 2 | `services/audit/execution_audit_service.py` |
| 4 | `services/strategy/strategy_artifact_service.py` |

### 新增 Port 模块

| Phase | 新增模块 |
|-------|---------|
| 4 | `services/strategy/strategy_run_service.py`, `services/strategy/backtest_service.py` |
