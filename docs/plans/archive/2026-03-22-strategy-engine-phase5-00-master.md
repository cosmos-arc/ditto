# 策略引擎 Phase 5: 多策略模板扩展

**Status:** Draft
**Design Doc:** `docs/plans/2026-03-21-strategy-engine-system-design-v3.md` §2.5, §7.3, §9.1
**Roadmap:** `docs/plans/2026-03-21-strategy-engine-phase2-5-roadmap.md`
**前置:** Phase 4 全部完成（Part 01 和 Part 02 至少）

---

## 概述

**Goal:** 4 个策略模板全部可用 + 选股类策略回测闭环

**里程碑:** 选股类策略（stock_selection_trend / stock_sector_rotation）回测闭环

**交付物:**
- `etf_trend_swing` 模板（趋势信号 + 追踪止损）
- `stock_selection_trend` 模板（多因子选股 + 趋势过滤）
- `stock_sector_rotation` 模板（行业配置 + 行业内选股）
- `inverse_vol` 权重分配器
- InstrumentDefinition 扩展（新股前 N 日 / 退市整理期）
- RiskLock 跨日 cooldown
- 每个模板的回测快照测试

---

## 关键设计决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 选股模板架构 | 复用 Pipeline 框架，选股结果作为 Universe 子集 | 最小化新基础设施 |
| 2 | stock_sector_rotation 拆分 | 先行业配置再行业内选股，两步 Pipeline | 清晰分层，可独立测试 |
| 3 | inverse_vol 实现 | `1/vol` 归一化权重 | 业界标准，简单有效 |
| 4 | 追踪止损 | Pipeline Constraint 阶段实现，非 PostTrade | 保持 Pipeline 纯函数语义 |
| 5 | 新股规则 | InstrumentDefinition 新增 `ipo_days` / `delisting_days` 字段 | 最小化 schema 变更 |

## v3 修订对应

| 修订 | Phase 5 落地 |
|------|-------------|
| S5 (cooldown 预留) | RiskLock 跨日 cooldown 实现 |
| §2.5 第四种模板 | stock_sector_rotation 模板 |
| §2.3 ParamConstraint | 模板参数约束声明 |

---

## 依赖关系

```
Part 01 (etf_trend_swing) ──→ 可与 Phase 4 并行
Part 02 (inverse_vol) ──→ 可与 Phase 4 并行
Part 03 (stock_selection_trend) ←── Phase 4 Part 01-02 完成
Part 04 (stock_sector_rotation) ←── Phase 4 Part 01-02 + Part 03
Part 05 (InstrumentDefinition 扩展) ←── Phase 3
Part 06 (RiskLock 跨日 cooldown) ←── Phase 4 Part 02
Part 07 (回测快照测试) ←── Part 01-04
```

**关键路径:** Phase 4 → Part 03 → Part 04 → Part 07
**并行机会:** Part 01、02、05、06 可与 Phase 4 并行开发。

---

## 子计划清单

### Part 01: etf_trend_swing 模板 `[L]` ✅ DONE

实现 ETF 趋势追踪策略模板。

**核心逻辑:**
1. Signal: 多周期动量信号（如 20 日动量 + 波动率调整）
2. Scoring: 趋势强度评分
3. Filter: 趋势方向过滤（只做多/只做空/双向）
4. Allocation: inverse_vol 权重（依赖 Part 02，V1 可先用 equal_weight）
5. Constraint: 追踪止损（持仓成本 × (1 - trailing_stop_pct)）

- [x] Task 1.1: 定义 `ETFTrendSwingConfig` + 参数 `[S]`
  - 文件: `strategy/templates/etf_trend_swing.py` (新建)
  - 实现: frozen dataclass，含 lookback_window/trend_threshold/trailing_stop_pct/max_positions/scoring_method/scoring_ascending/allocation_method/cash_target/signal_column

- [x] Task 1.2: 趋势信号 Stage `[M]`
  - 实现: 复用 SignalStage，读取 signal_column

- [x] Task 1.3: 趋势过滤 Stage `[M]`
  - 实现: 复用 TrendFilterStage，direction="long"

- [x] Task 1.4: 追踪止损 Stage `[M]`
  - 文件: `strategy/templates/etf_trend_swing.py`
  - 实现: TrailingStopStage (DecisionStage)，向量化的 polars join 实现 O(N)
  - 通过 StrategyContext.positions 获取持仓成本

- [x] Task 1.5: 组装 Pipeline `[M]`
  - 文件: `strategy/templates/etf_trend_swing.py`
  - 实现: `build_etf_trend_swing_pipeline(config)` 组装 Signal → TrendFilter → Score → RiskLockFilter → Select → Allocate → TrailingStop

- [x] Task 1.6: etf_trend_swing 单元测试 `[M]`
  - 文件: `tests/unit/strategy/test_etf_trend_swing_unit.py` (新建)
  - 实现: 17 个测试（Config 2 + TrailingStop 8 + Pipeline 7），全部通过

---

### Part 02: inverse_vol 权重分配器 `[M]` ✅ DONE

实现波动率倒数加权分配器。

- [x] Task 2.1: 实现 `InverseVolAllocator` `[M]`
  - 权重 = (1/vol_i) / Σ(1/vol_j) × (1 - cash_target)
  - 边界处理: 全零→等权、部分零→权重为0、空frame→空frame+weight列
  - 支持 cash_target 和自定义 vol_column
  - 文件: `portfolio/allocation.py`

- [x] Task 2.2: `InverseVolAllocator` 边界测试 `[S]`
  - 10 个测试: 正常分配、权重精确值、全零、部分零、单标的、单标的+cash_target、空frame、cash_target、自定义列名、frozen
  - 文件: `tests/unit/portfolio/test_allocation_unit.py`
  - 全部通过

---

### Part 03: stock_selection_trend 模板 `[XL]`

实现多因子选股 + 趋势过滤策略模板。**XL 必须拆分。**

**核心逻辑:**
1. Universe: 全市场股票（可按市值/流动性过滤）
2. Signal: 多因子信号（动量 + 基本面 + 质量）
3. Scoring: 多因子综合评分（加权或等权）
4. Filter: 趋势方向过滤
5. Select: Top K
6. Allocate: equal_weight / inverse_vol
7. Constraint: 集中度 + 换手率限制

- [ ] Task 3.1: 定义 `StockSelectionTrendSpec` + 参数约束 `[S]`
  - `universe_filter: str` (默认 "liquid", 允许 "all" / "large_cap")
  - `signal_factors: tuple[str, ...]` (默认 ("momentum_20d", "roe", "debt_ratio"))
  - `signal_weights: tuple[float, ...]` (与 factors 等长)
  - `trend_filter: bool` (默认 True)
  - `top_k: int` (默认 20)
  - `max_weight: float` (默认 0.1)
  - `rebalance_freq: str` (默认 "monthly")
  - 文件: `strategy/builtins/templates/stock_selection_trend.py` (新建)
  - 验收: Spec 定义，参数约束验证

- [ ] Task 3.2: 实现多因子信号 Stage `[L]`
  - 动量因子: 20 日/60 日收益率
  - 基本面因子: ROE / 负债率 / 营收增长（从 input_bundle 获取）
  - 质量因子: 波动率 / 换手率
  - 支持 custom factor 注册
  - 文件: `strategy/builtins/templates/stock_selection_trend.py`
  - 验收: 多因子信号计算正确

- [ ] Task 3.3: 实现多因子评分 Stage `[M]`
  - 加权平均: `score = Σ(w_i × factor_i_normalized)`
  - 因子标准化: rank-based 或 z-score
  - 文件: `strategy/builtins/templates/stock_selection_trend.py`
  - 验收: 评分排名一致

- [ ] Task 3.4: 实现趋势过滤 + 选股 + 分配 Pipeline `[M]`
  - 复用 TrendFilter (Part 01) + Select(top_k) + Allocate(equal_weight/inverse_vol)
  - 新增: MaxWeight constraint
  - 文件: `strategy/builtins/templates/stock_selection_trend.py`
  - 验收: Pipeline 端到端运行

- [ ] Task 3.5: 实现 `rebalance_freq` 调仓频率支持 `[M]`
  - `monthly`: 每月第一个交易日调仓
  - `weekly`: 每周一调仓
  - `daily`: 每日调仓
  - 在 `EngineLoop._is_rebalance_day` 中实现
  - 文件: `backtest/engine.py`, `strategy/specs.py`
  - 验收: 调仓频率正确

- [ ] Task 3.6: stock_selection_trend 单元测试 `[L]`
  - 多因子信号计算
  - 评分排名
  - 调仓频率
  - Pipeline 端到端
  - 文件: `tests/unit/strategy/test_stock_selection_trend_unit.py` (新建)
  - 验收: 全部测试通过

---

### Part 04: stock_sector_rotation 模板 `[XL]`

实现行业配置 + 行业内选股策略模板。**XL 必须拆分。**

**核心逻辑:**
1. Universe: 行业 ETF + 行业内股票
2. Signal: 行业动量信号
3. Allocation: 行业权重分配
4. Per-sector 选股: 每个行业内 Top K
5. Constraint: 行业集中度 + 个股权重限制

- [ ] Task 4.1: 定义 `StockSectorRotationSpec` + 参数约束 `[S]`
  - `sector_signal: str` (默认 "momentum_20d")
  - `top_sectors: int` (默认 3)
  - `stocks_per_sector: int` (默认 5)
  - `sector_weight_method: str` (默认 "equal")
  - `stock_weight_method: str` (默认 "equal")
  - `rebalance_freq: str` (默认 "monthly")
  - 文件: `strategy/builtins/templates/stock_sector_rotation.py` (新建)
  - 验收: Spec 定义，参数约束验证

- [ ] Task 4.2: 实现行业信号 Stage `[M]`
  - 计算每个行业的动量/趋势信号
  - 输入: market_data 按 sector 分组
  - 输出: DecisionFrame 含 `sector_signal_value` 列
  - 文件: `strategy/builtins/templates/stock_sector_rotation.py`
  - 验收: 行业信号计算正确

- [ ] Task 4.3: 实现行业选择 + 权重分配 Stage `[L]`
  - 选择 Top K 行业
  - 分配行业权重 (equal / score_weight / inverse_vol)
  - 输出: 每个行业的目标权重
  - 文件: `strategy/builtins/templates/stock_sector_rotation.py`
  - 验收: 行业选择和权重分配正确

- [ ] Task 4.4: 实现行业内选股 Stage `[L]`
  - 每个选中行业内按因子评分选 Top K 股票
  - 行业内 equal_weight 分配
  - 文件: `strategy/builtins/templates/stock_sector_rotation.py`
  - 验收: 行业内选股正确

- [ ] Task 4.5: 组装两层 Pipeline `[M]`
  - 第一层: Universe(sector ETFs) → Signal → Score → Select(top_sectors) → Allocate(sector_weight)
  - 第二层: 对每个选中行业 → Universe(stocks in sector) → Score → Select(top_k) → Allocate(equal)
  - 合并两层结果为统一 TargetPortfolio
  - 文件: `strategy/builtins/templates/stock_sector_rotation.py`
  - 验收: 两层 Pipeline 端到端运行

- [ ] Task 4.6: stock_sector_rotation 单元测试 `[L]`
  - 行业信号计算
  - 行业选择 + 权重分配
  - 行业内选股
  - 两层 Pipeline 端到端
  - 文件: `tests/unit/strategy/test_stock_sector_rotation_unit.py` (新建)
  - 验收: 全部测试通过

---

### Part 05: InstrumentDefinition 扩展 `[M]`

扩展 InstrumentDefinition 支持新股前 N 日和退市整理期。

- [ ] Task 5.1: `InstrumentDefinition` 新增字段 `[S]`
  - `ipo_date: str | None` — 上市日期
  - `delisting_date: str | None` — 退市日期
  - 不新增 `ipo_days` / `delisting_days` 字段，由 TradingRuleSet 的 price_limit_pct 变化体现
  - 文件: `execution/rules.py`
  - 验收: 新字段定义，backward compatible

- [ ] Task 5.2: 新股涨跌停规则 `[M]`
  - 主板新股上市首日无涨跌停限制（price_limit_pct = None）
  - 创业板/科创板前 5 日无涨跌停限制
  - 第 N 日后恢复正常涨跌停
  - 通过 `TradingRuleSet` 版本化体现（上市日期 → 规则变更日期）
  - 文件: `execution/rules.py`
  - 验收: 新股涨跌停规则正确

- [ ] Task 5.3: 退市整理期规则 `[S]`
  - 退市整理期涨跌幅限制 10%（无 ST 额外限制）
  - `lifecycle_state = "delisting"` 时特殊处理
  - 文件: `execution/rules.py`
  - 验收: 退市整理期规则正确

- [ ] Task 5.4: 扩展测试 `[S]`
  - 新股首日无涨跌停
  - 新股第 N+1 日恢复涨跌停
  - 退市整理期 10% 涨跌幅
  - 文件: `tests/unit/execution/test_rules_unit.py`
  - 验收: 扩展规则测试通过

---

### Part 06: RiskLock 跨日 cooldown `[M]`

实现 S5 RiskLock 跨日冷却机制。

- [ ] Task 6.1: `RiskAction.cooldown_until_date` 实现 `[M]`
  - PostTrade 规则可设置 `cooldown_until` 字段
  - `_execute_risk_actions` 中当 action 包含 cooldown_until 时，设置跨日锁定
  - `clear_locks()` 只清除 `cooldown_until <= today` 的锁定
  - 文件: `backtest/risk/post_trade.py`, `backtest/engine.py`
  - 验收: cooldown 锁定跨日生效，到期自动清除

- [ ] Task 6.2: cooldown 测试 `[S]`
  - 设置 cooldown → 次日仍锁定 → 到期日清除
  - 与当日锁定共存
  - 文件: `tests/unit/backtest/test_post_trade_unit.py`
  - 验收: cooldown 生命周期测试通过

---

### Part 07: 每个模板的回测快照测试 `[L]`

为所有 4 个模板创建回测快照测试 + 不变量测试。

- [ ] Task 7.1: etf_trend_swing 快照测试 `[M]`
  - 5 日快照，含追踪止损触发场景
  - NAV 序列确定性
  - 文件: `tests/integration/strategy/test_etf_trend_swing_snapshot.py` (新建)
  - 验收: 快照测试通过

- [ ] Task 7.2: stock_selection_trend 快照测试 `[M]`
  - 10 日快照，含多因子评分 + 调仓频率验证
  - NAV 序列确定性
  - 文件: `tests/integration/strategy/test_stock_selection_trend_snapshot.py` (新建)
  - 验收: 快照测试通过

- [ ] Task 7.3: stock_sector_rotation 快照测试 `[M]`
  - 10 日快照，含两层 Pipeline + 行业切换
  - NAV 序列确定性
  - 文件: `tests/integration/strategy/test_stock_sector_rotation_snapshot.py` (新建)
  - 验收: 快照测试通过

- [ ] Task 7.4: 模板通用不变量测试 `[S]`
  - 所有模板: 不超卖、现金守恒、权重和 <= 1.0
  - 追踪止损: 触发后权重为 0
  - 调仓频率: 非调仓日无新订单
  - 文件: `tests/integration/strategy/conftest.py` (新建共享 fixtures)
  - 验收: 不变量测试通过

---

## 风险点

| 风险 | 影响 | 缓解 |
|------|------|------|
| stock_selection_trend XL | 实现复杂度高 | 拆分为 6 个独立 Task，逐个 TDD |
| stock_sector_rotation XL | 两层 Pipeline 编排复杂 | 先单层验证，再组合 |
| 追踪止损需要持仓信息 | Pipeline 无状态设计 | 通过 StrategyContext external_data 传入 |
| 多因子数据依赖 | ROE/负债率等需要额外数据源 | V1 使用 input_bundle 传入 mock 数据 |
| 调仓频率需要交易日历 | _is_rebalance_day 需要交易日历 | DataFeed.trading_days() 已提供 |
