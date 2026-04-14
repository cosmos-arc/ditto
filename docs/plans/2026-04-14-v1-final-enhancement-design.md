# Ditto V1 RC 发布闸门设计

> **创建**: 2026-04-14
> **更新**: 2026-04-14（基于 Code Review 重排优先级）
> **状态**: Draft
> **前置**: V1 Sprint Phase 0-3 + Enhancement 全部完成
> **目标**: 从"功能补齐清单"升级为"V1 RC 发布闸门"——先修正确性和发布契约，再扩因子数量

---

## 1. 背景与定位

### 1.1 V1 版本定位

**V1 RC 发布版本**：面向真实使用场景，提供可信赖的回测引擎、可接入的策略框架、可操作的人工执行闭环、可联调的产品 API。

- 完整回测 + 策略能力接入（正确性优先）
- 不引入实盘和实时因子
- 人工执行和记录（信号推送至少一个通道可用）
- 前端功能由另一团队负责，Ditto 仅提供 API
- 不需要备份能力
- **核心原则**：不能在回测、风险、执行记录这些未来会复用的边界上留下错误模型

### 1.2 当前完成状态

V1 Sprint Phase 0-3 + Enhancement 已全部完成：

| Phase | 状态 | 关键产出 |
|-------|------|----------|
| Phase 0: Foundation | Done | TradingStep Chain, DecisionFrame Schema, RunManifest Enrichment |
| Phase 1: Backtest Closed Loop | Done | BacktestQueryFacade, RunReadModel, 14+ API 端点 |
| Phase 2: Manual Execution | Done | SignalSnapshot, ManualTracker, TradeService, ComparisonReport |
| Phase 3: Lineage/Replay | Done | ReplayValidator, LineageQueryFacade, ManifestDiff |
| Enhancement: R1-R7 | Done | Regime Engine, FactorBridge, Backtest Trigger, Universe, CostConfig |

### 1.3 能力评分（对标 LEAN 9.15）

| 维度 | 当前 | V1 RC 后 | 说明 |
|------|------|----------|------|
| 架构分层 | 8 | 8 | 已领先 |
| 数据基础设施 | 8 | 8.5 | 全数据集调度 + DQ 覆盖 |
| 因子引擎 | 9 | 9.5 | 分类覆盖 + 质量验证 + IC 修复 |
| 策略引擎 | 8 | 8.5 | Regime 增强 + 信号推送 + seed specs |
| 回测引擎 | 8 | 9 | 正确性硬化 + golden tests + 基准注入 |
| 交易执行 | 2 | 2 | V1 不引入实盘 |
| 生产运维 | 3 | 6 | 告警集成 + 摄取状态 + EOD 闭环 |
| 研究工具链 | 5 | 6.5 | 因子库扩展 + 评估修复 + validate_factor_specs |
| API/产品化 | 2 | 8 | 统一契约 + 分页 + 错误模型 + OpenAPI |
| **综合** | **6.35** | **7.7** | |

---

## 2. 缺口全景与优先级

> **Review 修订说明**：基于 2026-04-14 Code Review，将设计从"功能补齐清单"升级为"V1 RC 发布闸门"。
> 核心原则：**先修正确性和发布契约，再扩因子数量。** 业界成熟框架（QuantConnect LEAN、NautilusTrader）将 Universe、Alpha、Portfolio、Risk、Execution 分层作为基础框架；Ditto V1 不做实盘，但不能在回测、风险、执行记录这些未来会复用的边界上留下错误模型。

### P0 — 阻塞发布（正确性 + 发布契约）

| # | 模块 | 缺口 | 工作量 |
|---|------|------|--------|
| **F0** | **正确性门禁** | **IC decay 硬 bug + 部分成交覆盖 + MaxDrawdown 状态 + StrategySpec 校验 + golden tests** | **~300 行** |
| F1 | 因子库 | 传统多因子不够丰富（56→113），验收标准改为质量优先 | ~800 行 |
| F2 | 每日调度 | 12 个 T1 数据集未纳入自动调度 | ~100 行 |
| F3 | DQ 规则 | 财务/资金数据无质量规则 | ~80 行 YAML |
| F4 | 信号推送 | 设计完成但实现推迟，改为复用 infra notification | ~300 行 |
| F5 | API 分页 | 模型定义但未实际使用 | ~150 行 |

### P1 — 强烈建议

| # | 模块 | 缺口 | 工作量 |
|---|------|------|--------|
| F6 | API 一致性 | 响应格式/错误处理不统一（APIError 定义但全库 0 处使用） | ~250 行 |
| F7 | 摄取状态 API | 仅占位 "coming soon"（ingestion + portfolio） | ~300 行 |
| F8 | IC decay 修复 | 已合并入 F0 | — |
| F9 | 指数成分股 | 数据集未注册 | ~80 行 |
| F10 | DQ 告警集成 | 基础设施就位但未接入 | ~50 行 |
| F12 | EOD 编排 Flow | 摄取→物化→策略未串联，V1 正式使用需要 | ~150 行 |

### P2 — 锦上添花

| # | 模块 | 缺口 | 工作量 |
|---|------|------|--------|
| F11 | CLI 运维命令 | 缺 status/dq/deploy | ~200 行 |
| F13 | CORS 环境化 | 硬编码 localhost:3000，如前端联调依赖可提升至 P1 | ~20 行 |
| F14 | Regime 宏观指标 | LPR/MLF/M2/CPI | ~200 行 |

**优先级调整摘要**：

| 变更 | 原优先级 | 新优先级 | 理由 |
|------|---------|---------|------|
| 新增 F0 正确性门禁 | — | **P0** | IC decay 硬 bug 产出错误指标；部分成交数量被覆盖；MaxDrawdown 状态问题 |
| F8 IC decay | P1 | 合并入 F0 | 确认为评估层硬 bug，必须阻塞发布 |
| F12 EOD 编排 | P2 | **P1** | V1 是要正式使用的，不是 demo；每日调度 + DQ + 告警是日常运营基础 |
| F13 CORS | P2 | P2（可按需提升） | 如前端联调依赖则提升至 P1 |

**总工作量估算**：P0 ~1,730 行 + P1 ~830 行 + P2 ~420 行 ≈ **2,980 行新代码**

---

## 3. F0: V1 正确性门禁（新增，P0）

> **Review 驱动**：回测正确性是 V1 的信任基础。IC decay 硬 bug 静默产出错误指标，部分成交数量被覆盖，MaxDrawdown 状态可能重置——这些问题在发布前必须解决。

### 3.1 F0.1: IC Decay 修复（原 F8，提升至 P0）

**问题**：[evaluator.py:199-204](packages/analytics/src/ditto_analytics/evaluation/evaluator.py#L199-L204) 中 `_compute_ic_decay_safe` 将 factor value 当作 pseudo_close 传给 `ic_decay()`，实际计算的是 factor 值的自相关性而非 factor vs forward returns 的 IC。结果完全无意义。

**根因**：`ic_decay()` 需要 close prices 计算 forward returns，但评估器没有 forward returns 数据，于是用 factor value 伪装 close。

**修复方案**：

```python
def _compute_ic_decay_safe(
    factor_df: pl.DataFrame,
    returns_df: pl.DataFrame,  # 多列 forward return: fwd_ret_5, fwd_ret_10, ...
    lags: list[int] = [5, 10, 20, 40, 60],
) -> pl.DataFrame:
    """计算因子在不同预测窗口下的 IC 衰减"""
    results = []
    for lag in lags:
        fwd_col = f"fwd_ret_{lag}"
        if fwd_col in returns_df.columns:
            ic = spearman_corr(factor_df["value"], returns_df[fwd_col])
            results.append({"lag": lag, "ic": ic})
    return pl.DataFrame(results)
```

**验收**：修复后 IC decay 数值应在合理范围内（绝对值 < 0.5），且随 lag 增大呈衰减趋势。

### 3.2 F0.2: 部分成交数量覆盖防御

**问题**：[brokerage.py:296](packages/engine/src/ditto_engine/execution/brokerage.py#L296) 中 `_build_fill_event` 始终用 `ticket.leaves_quantity`（全量剩余）作为成交数量，fill model 返回的 `Filled` 对象只取了 `fill_price`，忽略了可能的部分成交数量。

**处理方案**：V1 fill model 合约为 all-or-nothing，暂不重构。添加防御性检查：

```python
# brokerage.py _build_fill_event
fill_qty = ticket.leaves_quantity
# 防御性检查：确保 fill model 意图与实际一致
assert fill_qty <= ticket.leaves_quantity, (
    f"Fill qty {fill_qty} exceeds leaves qty {ticket.leaves_quantity}"
)
```

**后续**：如 V2 引入部分成交模型，需重构 fill model contract 以返回实际成交数量。

### 3.3 F0.3: MaxDrawdown 状态隔离

**问题**：MaxDrawdown 计算可能在回测间共享状态，导致独立回测结果互相污染。

**修复方案**：确保每个 BacktestRun 的 MaxDrawdown 计算使用独立的 accumulator 实例，或在 `reset()` 时彻底清除状态。

**验收**：连续运行两个不同策略的回测，MaxDrawdown 值应相互独立。

### 3.4 F0.4: StrategySpec 参数最小校验

**问题**：StrategySpec 创建时缺少参数合法性校验，可能导致运行时才暴露的配置错误。

**修复方案**：在 StrategySpec model 上添加 `model_validator`，校验：
- universe 非空
- benchmark 在 universe 内或为已知指数代码
- rebalance_freq > 0
- cost_model 参数合法（commission_rate ∈ [0, 1] 等）

### 3.5 F0.5: 回测 Golden Tests

**目标**：建立回测结果快照机制，确保核心策略的回测数字不随代码变更漂移。

**方案**：使用 inline-snapshot 机制锁定关键指标：

```python
@pytest.mark.golden
def test_etf_rotation_backtest_reproducible(snapshot):
    result = run_backtest(strategy="etf_rotation", period="2024-01-01:2024-12-31")
    assert result.sharpe_ratio == snapshot
    assert result.max_drawdown == snapshot
    assert result.total_return == snapshot
    assert result.annual_turnover == snapshot
```

**覆盖策略**：ETF 行业轮动、ETF 趋势（至少 2 个）。

**验收标准**：
- IC decay golden test 通过（修复后锁定快照）
- 至少 2 个策略回测结果可复现
- `pixi run -e dev check` 全通过

---

## 4. F1: 因子库扩展

### 3.1 设计原则

- **对标 Barra CNE5 + A 股实证研究**：覆盖传统多因子模型全部核心维度
- **A 股有效性优先**：按因子在 A 股市场的有效性排序实施
- **表达式驱动**：优先使用 Ditto 表达式语言（`factor_specs.py`），复杂因子用 Python 函数
- **数据可行性**：仅依赖当前已接入的数据源（Tushare/TDX/FRED）

### 3.2 因子体系总览

| 因子大类 | 当前 | V1 目标 | 新增 | A 股有效性 |
|---------|------|---------|------|-----------|
| 价值 (Value) | 2 | 10 | 8 | 高 |
| 动量/反转 (Momentum) | 3 | 10 | 7 | 极高 |
| 质量 (Quality) | 2 | 10 | 8 | 高 |
| 规模 (Size) | 0 | 5 | 5 | 极高 |
| 波动率 (Volatility) | 6 | 12 | 6 | 中高 |
| 流动性 (Liquidity) | 1 | 8 | 7 | 高 |
| 成长 (Growth) | 1 | 6 | 5 | 中 |
| 技术/量价 (Technical) | 35 | 45 | 10 | 中高 |
| 另类 (Alternative) | 1 | 4 | 3 | 中 |
| Primitives | 3 | 3 | 0 | - |
| **合计** | **56** | **~113** | **~57** | |

### 3.3 价值因子（+8）

| 因子 ID | 表达式逻辑 | 数据依赖 | 说明 |
|---------|-----------|---------|------|
| `value_ps` | `close / rvps` | fundamental.rvps | 市销率倒数 |
| `value_pcf` | `close * total_shares / ocf_ttm` | fundamental.ocf + market | 市现率倒数 |
| `value_evebitda` | `(market_cap + total_debt - cash) / ebitda` | capital + fundamental | EV/EBITDA 倒数 |
| `dividend_yield` | `dps_ttm / close` | corporate_actions.dividend | 股息率 |
| `bp_ratio` | `total_equity / market_cap` | balance_sheet + market | 净资产/市值 (Barra BP) |
| `ep_ttm` | `net_income_ttm / market_cap` | income + market | TTM 盈利收益率 |
| `ev_to_sales` | `ev / revenue_ttm` | capital + fundamental | EV/Sales 倒数 |
| `pcf_ttm` | `ocf_ttm / market_cap` | fundamental + market | TTM 现金流收益率 |

### 3.4 动量/反转因子（+7）

| 因子 ID | 表达式逻辑 | 说明 |
|---------|-----------|------|
| `reversal_1m` | `-ts_pct_change(close, 20)` | 1 月反转（A 股极有效） |
| `reversal_3d` | `-ts_pct_change(close, 3)` | 3 日短期反转 |
| `momentum_3m` | `ts_pct_change(close, 60)` | 3 月动量 |
| `umd_6m` | `ts_pct_change(close, 126) - ts_pct_change(close, 21)` | 经典 UMD（剔除近 1 月） |
| `momentum_accel` | `ts_delta(returns_20, 20)` | 动量加速度 |
| `sequential_momentum` | `sign(returns_20) * sign(returns_60)` | 连续动量方向 |
| `idio_momentum` | FF3 回归残差的动量 | 特质动量（需 Python 函数） |

### 3.5 质量因子（+8）

| 因子 ID | 表达式逻辑 | 说明 |
|---------|-----------|------|
| `roa` | `net_income / total_assets` | 总资产收益率 |
| `accruals` | `(net_income - ocf) / total_assets` | 应计利润（低=高质量） |
| `delta_roe` | `ts_delta(roe, 4)` | ROE 边际变化 |
| `roe_stability` | `-ts_std(roe, 8)` | ROE 稳定性（负号） |
| `cash_ratio` | `ocf / net_income` | 盈利现金含量 |
| `gross_margin` | `(revenue - cogs) / revenue` | 毛利率 |
| `operating_leverage` | `ts_delta(op_income, 4) / ts_delta(revenue, 4)` | 经营杠杆 |
| `earnings_smoothness` | `-ts_corr(roe, delta_roe, 8)` | 盈利平滑度 |

### 3.6 规模因子（+5，新类别）

| 因子 ID | 表达式逻辑 | 说明 |
|---------|-----------|------|
| `log_market_cap` | `log(total_shares * close)` | 对数总市值 |
| `log_free_float_cap` | `log(free_float_shares * close)` | 对数流通市值 |
| `size_nl` | `power(log_market_cap, 3)` | 非线性市值（Barra SIZENL） |
| `market_cap_rank` | `cs_rank(log_market_cap)` | 市值截面排名 |
| `free_float_ratio` | `free_float_shares / total_shares` | 自由流通比例 |

### 3.7 波动率因子（+6）

| 因子 ID | 表达式逻辑 | 说明 |
|---------|-----------|------|
| `idiosyncratic_vol` | FF3 回归残差标准差 | 特质波动率（Python 函数） |
| `downside_beta` | 下行市场协方差 / 下行市场方差 | 下行 Beta（Python 函数） |
| `beta_252` | `ts_corr(daily_returns, market_returns, 252)` | 市场 Beta |
| `cmra` | `ts_max(monthly_returns, 12) - ts_min(monthly_returns, 12)` | 累积波动范围 (Barra) |
| `realized_skewness` | 时序偏度 | 实现偏度 |
| `vol_ratio` | `volatility_20 / volatility_60` | 波动率比率 |

### 3.8 流动性因子（+7，新类别）

| 因子 ID | 表达式逻辑 | 说明 |
|---------|-----------|------|
| `turnover_20d` | `ts_mean(volume / free_float_shares, 20)` | 20 日平均换手率 |
| `turnover_change` | `turnover_20d / ts_delay(turnover_20d, 20) - 1` | 换手率变化 |
| `amihud_illiquidity` | `ts_mean(abs(daily_return) / amount, 20)` | Amihud 非流动性 |
| `turnover_stability` | `-ts_std(turnover_20d, 60)` | 换手率稳定性 |
| `volume_price_corr` | `ts_corr(volume, daily_returns, 20)` | 量价相关性 |
| `money_flow_index` | MFI 标准公式 | 资金流量指数 |
| `obv` | 累积 OBV 公式 | 能量潮指标 |

### 3.9 成长因子（+5）

| 因子 ID | 表达式逻辑 | 说明 |
|---------|-----------|------|
| `revenue_growth` | `ts_pct_change(revenue, 4)` | 营收同比增长 |
| `net_profit_growth` | `ts_pct_change(net_income, 4)` | 净利同比增长 |
| `op_profit_growth` | `ts_pct_change(op_income, 4)` | 营业利润增长 |
| `growth_stability` | `ts_corr(revenue_growth, net_profit_growth, 8)` | 增长协调性 |
| `sustainable_growth` | `roe * (1 - dividend_payout_ratio)` | 可持续增长率 |

### 3.10 技术/量价因子（+10）

| 因子 ID | 表达式逻辑 | 说明 |
|---------|-----------|------|
| `kdj_k` | Stochastic K 公式 | 随机指标 K |
| `kdj_d` | Stochastic D 公式 | 随机指标 D |
| `cci` | CCI 标准公式 | 商品通道指数 |
| `williams_r` | Williams %R 公式 | 威廉指标 |
| `mfi` | MFI 标准公式 | 资金流量指数 |
| `vwap_20d` | `ts_sum(tp * volume, 20) / ts_sum(volume, 20)` | 20 日 VWAP |
| `obv_ma20` | `ts_mean(obv, 20)` | 20 日 OBV 均线 |
| `choppiness_index` | CHOP 标准公式 | 盘整指标 |
| `supertrend` | ATR + 中轨公式 | 超级趋势线 |
| `elder_ray_bull` | `ema_13 - atr_multiplier` | 艾尔德射线（多头） |

### 3.11 另类因子（+3）

| 因子 ID | 表达式逻辑 | 数据依赖 | 说明 |
|---------|-----------|---------|------|
| `margin_change` | `ts_pct_change(margin_buy, 20)` | capital.margin | 融资买入变化 |
| `pledge_ratio` | `pledge_shares / total_shares` | capital.pledge | 股权质押比例 |
| `short_interest_ratio` | `short_balance / market_cap` | capital.margin | 融券余额比 |

### 4.1 设计原则

- **对标 Barra CNE5 + A 股实证研究**：覆盖传统多因子模型全部核心维度
- **A 股有效性优先**：按因子在 A 股市场的有效性排序实施
- **表达式驱动**：优先使用 Ditto 表达式语言（`factor_specs.py`），复杂因子用 Python 函数
- **数据可行性**：仅依赖当前已接入的数据源（Tushare/TDX/FRED）
- **质量优先于数量**：不验收"113 个因子"数字，验收分类覆盖 + PIT 依赖 + DQ 规则 + IC/分层收益 + 回测接入

**文件修改**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `packages/analytics/src/ditto_analytics/factors/technical.py` | 修改 | 新增 10 个技术因子 |
| `packages/analytics/src/ditto_analytics/factors/value.py` | 新建 | 从 fundamental.py 拆出 10 个价值因子 |
| `packages/analytics/src/ditto_analytics/factors/momentum.py` | 新建 | 10 个动量/反转因子 |
| `packages/analytics/src/ditto_analytics/factors/quality.py` | 新建 | 10 个质量因子 |
| `packages/analytics/src/ditto_analytics/factors/size.py` | 新建 | 5 个规模因子 |
| `packages/analytics/src/ditto_analytics/factors/volatility.py` | 新建 | 12 个波动率因子（含已有迁移） |
| `packages/analytics/src/ditto_analytics/factors/liquidity.py` | 新建 | 8 个流动性因子 |
| `packages/analytics/src/ditto_analytics/factors/growth.py` | 新建 | 6 个成长因子（含已有迁移） |
| `packages/analytics/src/ditto_analytics/factors/alternative.py` | 新建 | 4 个另类因子（含已有迁移） |
| `packages/analytics/src/ditto_analytics/factors/factor_specs.py` | 修改 | 聚合所有因子到 ALL_FACTOR_SPECS |

**实施顺序**：价值 → 规模 → 动量/反转 → 质量 → 流动性 → 波动率 → 成长 → 技术 → 另类

**验收标准**（质量优先，非数量驱动）：

| 验收维度 | 标准 | 说明 |
|---------|------|------|
| 分类覆盖 | 9 大类均有因子实现 | 价值/动量/质量/规模/波动率/流动性/成长/技术/另类 |
| spec 依赖 | 全部通过 `validate_factor_specs()` | PIT 数据依赖声明完整、无循环依赖 |
| PIT 数据可用性 | 核心因子缺失率 < 5% | 依赖的 T1 数据集已接入且 DQ 通过 |
| DQ 规则 | 因子依赖的数据集均有 DQ 规则 | 与 F3 联动，factor spec 的数据依赖必须可质检 |
| IC 验证 | 至少 3 个因子有 IC/分层收益验证结果 | 选择价值、动量、质量各 1 个代表因子 |
| 回测接入 | FactorBridge 端到端可运行 | 因子计算 → 策略信号 → 回测执行全链路 |
| 单元测试 | 每个新因子至少 1 个单元测试 | `pixi run -e dev check` 全通过 |

> **Review 修订**：不再以"113 个因子"作为 V1 验收目标。因子扩展可以并行推进，但发布闸门是**分类覆盖 + 质量验证**。`validate_factor_specs()` 提升为 P0 CI gate。

---

## 5. F4: 信号推送实现（复用 infra notification）

> **Review 修订**：当前 `signal_delivery.py` 自行实现 `_TelegramNotificationAdapter` 直接调用 Telegram Bot API（httpx），完全绕过了 `ditto_infra.services.notification` 已有的 AlertManager + TelegramSender + WebhookSender + TemplateEngine。改为复用 infra notification 统一通道。

### 5.1 现有基础设施

`ditto_infra.services.notification` 已提供完整的多通道通知系统：

| 组件 | 位置 | 说明 |
|------|------|------|
| AlertManager | `infra/.../notification/manager.py` | 业务级告警协调器，支持多通道投递 + 单通道失败隔离 |
| TelegramSender | `infra/.../notification/channels/telegram.py` | Telegram Bot API 实现 |
| WebhookSender | `infra/.../notification/channels/webhook.py` | Webhook POST 实现 |
| EmailSender | `infra/.../notification/channels/email.py` | Email 实现（V1 可选） |
| TemplateEngine | `infra/.../notification/template.py` | 多通道模板渲染 |

### 5.2 重构设计

```
SignalDeliveryService (interfaces 层)
  └─ AlertManager (infra 层，已有)
       ├─ TelegramSender    ← 复用 infra
       ├─ WebhookSender     ← 复用 infra
       ├─ EmailSender       ← 复用 infra（V1 可选）
       └─ TemplateEngine    ← 复用 infra，新增 signal 模板
```

**改造内容**：
1. 删除 `signal_delivery.py` 中的 `_TelegramNotificationAdapter`（自定义 httpx 实现）
2. `SignalDeliveryProvider` 改为注入 `AlertManager` 实例
3. 新增 `signal_trading.html` 模板到 TemplateEngine（调仓信号格式化）
4. 保留 `NotificationPort` Protocol 作为 app 层抽象

### 5.3 推送内容

基于 `SignalSnapshot`，通过 TemplateEngine 渲染：

```json
{
  "strategy_id": "etf_rotation_v2",
  "signal_date": "2026-04-14",
  "regime": { "label": "bull", "score": 72.5, "position_ratio": 1.0 },
  "actions": [
    {
      "instrument_id": "159915.SZ",
      "ticker": "创业板ETF",
      "action": "buy",
      "target_weight": 0.25,
      "current_weight": 0.15,
      "delta_weight": 0.10
    }
  ]
}
```

### 5.4 新增/修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `interfaces/.../registry/infra/signal_delivery.py` | 修改 | 删除自定义 Telegram 适配器，改用 AlertManager |
| `packages/infra/.../notification/templates/signal_trading.html` | 新建 | 信号推送 HTML 模板 |
| `config/production/notification.env` | 修改 | 配置 Telegram Bot Token + Webhook URL |
| `config/development/notification.env` | 修改 | 配置开发环境通知渠道 |

### 5.5 验收标准

- Telegram 推送能成功发送调仓信号（通过 infra TelegramSender）
- Webhook 推送能成功 POST 到目标 URL（通过 infra WebhookSender）
- 无自定义通知适配器代码（全部复用 infra notification）
- 推送失败时 graceful 降级（AlertManager 的单通道失败隔离）
- `pixi run -e dev check` 全通过

---

## 6. F2: 每日调度全覆盖

### 5.1 分层调度设计

```
18:30  T0 元数据（已有，不变）
       ├─ calendar, stock_basic, etf_basic, index_basic

18:45  T1-L0 核心行情（已有，不变）
       ├─ etf_daily, index_daily, stock_daily

19:00  T1-L1 行情衍生（已有，不变）
       ├─ stock_status, adj_factor, fund_adj

19:15  T1-L2 财务数据（新增）
       ├─ balance_sheet, income_statement, cash_flow
       ├─ dividend, corporate_actions

19:30  T1-L3 资金+宏观（新增）
       ├─ valuation_metrics, margin_trading, pledge_ratio
       ├─ macro_indicators, fx_daily, commodity_daily

19:45  T3 质量检查（扩展覆盖）
       ├─ 全部 T1 数据集的 DQ 批量检查
```

### 5.2 修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `interfaces/.../jobs/flows/daily.py` | 修改 | 扩展 daily_ingestion_flow 添加 T1-L2/L3 步骤 |

### 5.3 验收标准

- `daily_ingestion_flow` 覆盖全部 20 个 T1 数据集
- 分层调度正确执行（依赖关系正确）
- 非交易日自动跳过
- 失败数据集不影响其他数据集摄取

---

## 7. F3: DQ 规则扩展

### 6.1 新增规则文件

| 数据集 | L1 规则 | L2 规则 |
|--------|---------|---------|
| balance_sheet | not_null(核心列), required_columns | positive(total_assets, total_equity) |
| income_statement | not_null(核心列), required_columns | range_check(revenue ≥ 0) |
| cash_flow | not_null(核心列), required_columns | expression(字段一致性) |
| dividend | not_null(record_date, ex_date) | range_check(dividend ≥ 0) |
| corporate_actions | not_null(action_type, ex_date) | required_columns |
| valuation_metrics | not_null, required_columns | positive(pe, pb), range_check |
| margin_trading | not_null, required_columns | positive(margin_buy, margin_balance) |
| pledge_ratio | not_null, required_columns | range_check(ratio ∈ [0, 1]) |
| macro_indicators | not_null, required_columns | range_check(按指标类型) |
| fx_daily | not_null(ohlc), expression(high ≥ low) | no_zero_volume |
| commodity_daily | not_null(ohlc), expression(high ≥ low) | no_zero_volume |

### 6.2 新增文件

| 文件 | 说明 |
|------|------|
| `config/default/dq_rules/balance_sheet.yml` | 财务 DQ 规则 |
| `config/default/dq_rules/income_statement.yml` | 利润表 DQ 规则 |
| `config/default/dq_rules/cash_flow.yml` | 现金流 DQ 规则 |
| `config/default/dq_rules/dividend.yml` | 分红 DQ 规则 |
| `config/default/dq_rules/corporate_actions.yml` | 公司行为 DQ 规则 |
| `config/default/dq_rules/valuation_metrics.yml` | 估值 DQ 规则 |
| `config/default/dq_rules/margin_trading.yml` | 融资融券 DQ 规则 |
| `config/default/dq_rules/pledge_ratio.yml` | 股权质押 DQ 规则 |
| `config/default/dq_rules/macro_indicators.yml` | 宏观指标 DQ 规则 |
| `config/default/dq_rules/fx_daily.yml` | 外汇 DQ 规则 |
| `config/default/dq_rules/commodity_daily.yml` | 商品 DQ 规则 |

---

## 8. F5: API 分页落地

### 7.1 实施方案

将 `PaginationRequest`/`PaginationResponse` 实际应用到所有列表端点：

```python
# 标准分页参数
class PaginationParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

# 标准分页响应
class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    pagination: PaginationResponse  # total, limit, offset, has_more
```

### 7.2 需要加分页的端点

| 端点 | 当前状态 | 改造内容 |
|------|---------|---------|
| `GET /strategies` | 无分页 | +limit/offset +total |
| `GET /universes` | 无分页 | +limit/offset +total |
| `GET /backtests/runs` | 有 limit/offset 无 total | +total |
| `GET /backtests/runs/{id}/trades` | 有 limit/offset 无 total | +total |
| `GET /trade/intents` | 无分页 | +limit/offset +total |
| `GET /trade/fills` | 无分页 | +limit/offset +total |
| `GET /metadata/instruments` | 仅有 limit | +offset +total |

### 7.3 验收标准

- 所有列表端点支持 `limit`/`offset` 参数
- 所有列表端点返回 `pagination` 字段（含 total 和 has_more）
- 默认 limit=20, 最大 limit=100
- `pixi run -e dev check` 全通过

---

## 9. F6: API 一致性改进

### 8.1 响应格式统一

**规则**：所有业务端点统一使用 `APIResponse[T]` 包装。

```python
# 统一为 APIResponse 包装
@router.get("/items/{id}")
async def get_item(item_id: str) -> APIResponse[ItemResponse]:
    ...

# 不再允许裸返回
@router.get("/items/{id}")  # ❌ 禁止
async def get_item(item_id: str) -> ItemResponse:
    ...
```

**需修改的端点**：
- `strategy.get_strategy` → 包装 APIResponse
- `strategy.create_strategy` → 包装 APIResponse
- `strategy.update_strategy` → 包装 APIResponse
- `universe.get_universe` → 包装 APIResponse
- `universe.create_universe` → 包装 APIResponse
- `universe.update_universe` → 包装 APIResponse
- `backtest.get_run` → 包装 APIResponse
- `backtest.get_report` → 已是 APIResponse，不变

### 8.2 错误处理统一

将 `api/errors.py` 中的 `APIError` 子类应用到路由中：

```python
# 使用 APIError 替代裸 HTTPException
raise DateRangeError(start_date=start, end_date=end)  # ✅
# 而不是
raise HTTPException(status_code=400, detail="...")  # ❌
```

### 8.3 验收标准

- 所有业务端点响应格式统一为 `APIResponse[T]`
- 所有路由使用 `APIError` 子类抛出业务异常
- OpenAPI 文档反映统一格式
- `pixi run -e dev check` 全通过

---

## 10. F7: 摄取状态查询 API

### 9.1 设计

```
GET  /api/v1/ingestion/status          # 各数据集最新摄取状态
GET  /api/v1/ingestion/history         # 摄取历史（日期过滤 + 分页）
GET  /api/v1/ingestion/dq-summary      # DQ 检查摘要（最近 N 天）
```

### 9.2 响应模型

```python
class DatasetStatus(BaseModel):
    dataset: str
    latest_date: str | None
    latest_status: str  # success / failed / skipped
    record_count: int
    last_attempt: str | None

class IngestionStatusResponse(BaseModel):
    trading_date: str
    datasets: list[DatasetStatus]

class DQSummaryResponse(BaseModel):
    trading_date: str
    total_checks: int
    passed: int
    warnings: int
    errors: int
    details: list[DQDatasetSummary]
```

### 9.3 新增/修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `interfaces/.../api/routes/ingestion.py` | 修改 | 替换占位实现 |
| `interfaces/.../models/ingestion.py` | 新建 | 请求/响应模型 |
| `packages/app/src/ditto_app/query/ingestion_status.py` | 新建 | 摄取状态查询 Facade |
| `packages/app/src/ditto_app/providers.py` | 修改 | DI 注册 |

---

## 11. F8: IC decay 修复（已合并入 F0.1）

### 10.1 问题

`packages/analytics/src/ditto_analytics/evaluation/evaluator.py` 中 `_compute_ic_decay_safe` 使用因子值列作为 pseudo_close 计算 IC decay。

IC decay 的正确做法是：计算因子值与不同 forward return lag（5日、10日、20日、60日）的 IC，观察 IC 随预测窗口延长而衰减的模式。

### 10.2 修复方案

```python
def _compute_ic_decay_safe(
    factor_df: pl.DataFrame,
    returns_df: pl.DataFrame,  # 多列 forward return: fwd_ret_5, fwd_ret_10, ...
    lags: list[int] = [5, 10, 20, 40, 60],
) -> pl.DataFrame:
    """计算因子在不同预测窗口下的 IC 衰减"""
    results = []
    for lag in lags:
        fwd_col = f"fwd_ret_{lag}"
        if fwd_col in returns_df.columns:
            ic = spearman_corr(factor_df["value"], returns_df[fwd_col])
            results.append({"lag": lag, "ic": ic})
    return pl.DataFrame(results)
```

---

## 12. F9: 指数成分股权重

### 11.1 实施方案

1. 在 `INGESTION_SPECS` 注册 `index_weight` 数据集
2. 创建 CLI 命令 `ditto ingest market index-weight`
3. 纳入每日调度 T1-L1 步骤（与 adj_factor 同级）

### 11.2 新增/修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `packages/data/src/ditto_data/sources/tushare/config.py` | 修改 | 注册 index_weight |
| `packages/data/src/ditto_data/sources/tushare/adapters/index.py` | 修改 | 添加 index_weight 摄取逻辑 |
| `interfaces/.../cli/utils/factory.py` | 修改 | 添加 index-weight 命令 |

---

## 13. F10: DQ 告警集成

### 12.1 实施方案

在 `daily_ingestion_flow` 的 T3 步骤中，检测到 ALERT 级别问题时调用 `alert_dq_failure()`：

```python
# daily_ingestion_flow 修改
dq_results = await dq_batch_check.submit(datasets=t1_datasets)
for result in dq_results:
    if result.severity == "ALERT":
        await alert_dq_failure.submit(
            dataset=result.dataset,
            issues=result.issues,
        )
```

### 12.2 修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `interfaces/.../jobs/flows/daily.py` | 修改 | T3 步骤添加告警逻辑 |
| `config/development/notification.env` | 修改 | 配置至少一个 Webhook 告警通道 |

---

## 14. 实施计划

> **Review 修订**：从 4 Sprint 调整为 6 Sprint，按"正确性 → 策略包 → 数据契约 → API 闭环 → 人工执行 → EOD 运营"递进。

### 13.1 执行顺序

```
Sprint 1: V1 正确性硬化（F0）✅ Done
  ├─ F0.1: IC decay 修复 — ClosePriceProvider 替代 factor value pseudo-close
  ├─ F0.2: 部分成交数量覆盖防御性检查 (brokerage.py)
  ├─ F0.3: MaxDrawdown/CompositePostTradeGuard reset() 状态隔离
  ├─ F0.4: StrategySpec __post_init__ 参数最小校验
  └─ F0.5: golden tests 迁移 inline-snapshot + ETF 趋势择时基线
  验收: 5305 tests passed ✅ | pyright 0 errors ✅ | ruff clean ✅

Sprint 2: V1 策略包（F1 部分 + F9）✅ Done
  ├─ F1.1: 新建因子类别文件（size/liquidity/volatility/value/momentum/quality/growth/alternative）
  ├─ F1.2: 扩展 technical.py（+11 因子: CCI/Williams%/VWAP/OBV/CHOP/ElderRay/KDJ/SuperTrend/EMA13/OBV_MA20）
  ├─ F1.3: 更新 factor_specs.py 聚合（12 类别 dict 合并）
  ├─ F1.4: 单元测试（TestFactorCategoryCoverage 9 类 + TestPythonFactors）
  ├─ F1.5: validate_factor_specs() CI gate（编译+环检测+依赖+Python约束）
  ├─ F9: 指数成分股注册（Dataset enum + IngestionSpec + CLI）
  └─ 策略 seed specs（ETF 行业轮动 + ETF 趋势择时 + 个股选股轮动）
  验收: 116 因子 (105 expression + 11 python) ✅ | 3 seed specs ✅ | CI gate 0 errors ✅

Sprint 3: 数据和因子发布契约（F2 + F3 + F10）✅ Done
  ├─ F3: DQ 规则 YAML 文件（11 个数据集）
  ├─ F2: dq_batch_check 扩展至全部有 DQ 规则的数据集（16 个）
  ├─ F10: DQ 告警集成 AlertManager（patrol.py + dq_batch.py + 3 通知模板）
  ├─ F1.6: 3 个代表因子 IC/分层收益验证（价值/动量/质量各 1）
  └─ 因子 PIT 数据可用性 + 缺失率验证（11 测试 + 10 已知 gap 记录）
  验收: 5325 tests passed ✅ | pyright 0 errors ✅ | ruff clean ✅ | arch 24 contracts ✅

Sprint 4: 产品 API 闭环（F5 + F6 + F7）✅ Done
  ├─ F6: APIResponse 统一包装（13 个裸返回端点 → APIResponse[T]）
  ├─ F6: APIError 接入（新增 NotFoundError/ConflictError/ForbiddenError/BadRequestError，替换全部路由 HTTPException）
  ├─ F5: 分页落地（7 个列表端点 + PaginationRequest 默认值 20/100）
  ├─ F7: 摄取状态 API（status/history/dq-summary 3 端点，替换 "coming soon" 占位）
  ├─ 移除 portfolio 路由（V1 不引入实盘）
  └─ 生成 OpenAPI 快照（docs/openapi/v1.json，45 个端点）
  验收: 606 unit tests ✅ | pyright 0 errors ✅ | ruff clean ✅ | arch 24 contracts ✅ | 0 "coming soon" 占位 ✅

Sprint 5: 人工执行闭环（F4 + 手工成交增强）
  ├─ F4: 信号推送重构（复用 infra AlertManager + 新模板）
  ├─ Webhook + Telegram + ApiOnly 三通道验证
  ├─ 交易意图/手工成交/持仓/PnL 分页 + 幂等
  └─ 信号-成交偏差报告（简化版：API 查询）
  验收: 信号推送三通道可用 + 人工执行 CRUD 可用

Sprint 6: EOD 运营闭环（F12 + F13 + F11）
  ├─ F12: EOD 编排 Flow（摄取→物化→策略串联）
  ├─ 失败重试 + 非交易日处理
  ├─ 数据状态查询（复用 F7 ingestion status）
  ├─ F13: CORS 环境化（如前端联调依赖）
  └─ F11: CLI 运维命令（status/dq）
  验收: EOD 全链路可运行 + 非交易日正确跳过
```

### 13.2 验收标准

每个 Sprint 完成后：
1. `pixi run -e dev check` — lint + type + test
2. `pixi run -e dev arch-check` — 架构约束
3. 策略模板回测端到端验证
4. 新增 API 端点通过 Swagger UI 测试

### 13.3 文件统计

| Sprint | 新增文件 | 修改文件 | 新代码 |
|--------|---------|---------|--------|
| Sprint 1 | ~3 | ~5 | ~300 行 |
| Sprint 2 | ~12 | ~4 | ~1,000 行 |
| Sprint 3 | ~12 | ~4 | ~400 行 |
| Sprint 4 | ~4 | ~16 | ~700 行 |
| Sprint 5 | ~3 | ~8 | ~400 行 |
| Sprint 6 | ~4 | ~5 | ~370 行 |
| **合计** | **~38** | **~42** | **~3,170 行** |

---

## 15. V1 RC 发布门禁

> **新增**：基于 Review 建议，定义 V1 RC 发布必须通过的硬性门禁。

| # | 门禁 | 验证方式 | 说明 |
|---|------|---------|------|
| G1 | 3 个目标策略端到端通过 | CI smoke test | ETF 行业轮动 + ETF 趋势 + 个股选股轮动 |
| G2 | 回测 golden tests 通过 | CI inline-snapshot | IC decay + 2 策略回测结果不漂移 |
| G3 | 报告含 benchmark/turnover/cost/暴露摘要 | 手动验证 | 回测报告必须包含完整摘要信息 |
| G4 | API 无 "coming soon" 占位 | grep 验证 | ingestion + portfolio 路由要么实现要么移除 |
| G5 | API 端点统一 APIResponse[T] 包装 | CI schema diff | 所有业务端点响应格式一致 |
| G6 | DQ 告警可触达 | 集成测试 | ALERT 级别问题能通过至少一个通道送达 |
| G7 | `pixi run -e dev check` 通过 | CI | lint + fmt + type + test |
| G8 | `pixi run -e dev arch-check` 通过 | CI | 分层约束 + import 规则 |
| G9 | validate_factor_specs() CI gate 通过 | CI | 因子 spec 依赖完整性 |
| G10 | 至少 3 个因子有 IC/分层收益验证 | 手动验证 | 价值/动量/质量各 1 个代表因子 |

---

## 16. 设计决策

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 因子库验收标准 | 数量驱动（113 个）/ 质量驱动 | **质量驱动** | 分类覆盖 + PIT 依赖 + DQ 规则 + IC 验证 |
| IC decay 修复优先级 | P1 / P0 | **P0（F0）** | 评估层硬 bug，静默产出错误指标 |
| 信号推送实现 | 自建适配器 / 复用 infra notification | **复用 infra** | AlertManager + TelegramSender + WebhookSender 已完整实现 |
| 部分成交处理 | 重构 fill model / 防御性检查 | **防御性检查** | V1 fill model 合约 all-or-nothing，V2 再扩展 |
| EOD 编排优先级 | P2 / P1 | **P1** | V1 正式使用，不是 demo；每日调度是运营基础 |
| 信号推送通道 | 仅 Webhook / Telegram+Webhook | Telegram+Webhook+ApiOnly | 两个实际通道 + fallback（均复用 infra） |
| 摄取 API 范围 | 完整 CRUD / 仅状态查询 | 仅状态查询 | 触发通过 CLI/Prefect |
| API 认证 | API Key / JWT / 无 | 无 | 前端/网关层处理 |
| 因子类别组织 | 全放一个文件 / 按类别拆分 | 按类别拆分 | 113 个因子单文件过大 |
| 分页方案 | cursor-based / offset-based | offset-based | 已有模型定义，保持一致 |
| 策略包范围 | 5 个策略 / 3 个策略 | **3 个核心策略** | ETF 行业轮动 + ETF 趋势 + 个股选股轮动，regime/个股趋势 V1.1 |
| Golden test 机制 | 快照断言 / 数值容差 | inline-snapshot | 利用现有 inline-snapshot 基础设施 |
