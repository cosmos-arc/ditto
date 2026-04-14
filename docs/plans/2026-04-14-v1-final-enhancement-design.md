# Ditto V1 最终功能补齐设计

> **创建**: 2026-04-14
> **状态**: Draft
> **前置**: V1 Sprint Phase 0-3 + Enhancement 全部完成
> **目标**: 补齐 V1 对外展示版本的全部缺口，提供完整 API 能力

---

## 1. 背景与定位

### 1.1 V1 版本定位

**对外展示版本**：面向前端团队和外部评审，展示 Ditto 量化平台的完整 API 能力。

- 完整回测 + 策略能力接入
- 不引入实盘和实时因子
- 人工执行和记录（信号推送至少一个通道可用）
- 前端功能由另一团队负责，Ditto 仅提供 API
- 不需要备份能力

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

| 维度 | 当前 | V1 补齐后 | 说明 |
|------|------|----------|------|
| 架构分层 | 8 | 8 | 已领先 |
| 数据基础设施 | 8 | 8.5 | 全数据集调度 + DQ 覆盖 |
| 因子引擎 | 9 | 9.5 | 113 因子 + IC 修复 |
| 策略引擎 | 8 | 8.5 | Regime 增强 + 信号推送 |
| 回测引擎 | 8 | 8.5 | 基准注入 + API 完善 |
| 交易执行 | 2 | 2 | V1 不引入实盘 |
| 生产运维 | 3 | 5 | 告警集成 + 摄取状态 API |
| 研究工具链 | 5 | 6 | 因子库扩展 + 评估修复 |
| API/产品化 | 2 | 7 | 分页 + 一致性 + 完整端点 |
| **综合** | **6.35** | **7.5** | |

---

## 2. 缺口全景与优先级

### P0 — 阻塞发布

| # | 模块 | 缺口 | 工作量 |
|---|------|------|--------|
| F1 | 因子库 | 传统多因子不够丰富（56→113） | ~800 行 |
| F2 | 每日调度 | 12 个 T1 数据集未纳入自动调度 | ~100 行 |
| F3 | DQ 规则 | 财务/资金数据无质量规则 | ~80 行 YAML |
| F4 | 信号推送 | 设计完成但实现推迟 | ~400 行 |
| F5 | API 分页 | 模型定义但未实际使用 | ~150 行 |

### P1 — 强烈建议

| # | 模块 | 缺口 | 工作量 |
|---|------|------|--------|
| F6 | API 一致性 | 响应格式/错误处理不统一 | ~200 行 |
| F7 | 摄取状态 API | 仅占位 "coming soon" | ~300 行 |
| F8 | IC decay 修复 | 评估实现有 bug | ~20 行 |
| F9 | 指数成分股 | 数据集未注册 | ~80 行 |
| F10 | DQ 告警集成 | 基础设施就位但未接入 | ~50 行 |

### P2 — 锦上添花

| # | 模块 | 缺口 | 工作量 |
|---|------|------|--------|
| F11 | CLI 运维命令 | 缺 status/dq/deploy | ~200 行 |
| F12 | EOD 编排 Flow | 摄取→物化→策略未串联 | ~150 行 |
| F13 | CORS 环境化 | 硬编码 localhost:3000 | ~20 行 |
| F14 | Regime 宏观指标 | LPR/MLF/M2/CPI | ~200 行 |

**总工作量估算**：P0 ~1,530 行 + P1 ~650 行 + P2 ~570 行 ≈ **2,750 行新代码**

---

## 3. F1: 因子库扩展

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

### 3.12 实施策略

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

**验收标准**：
- 全部 ~113 个因子通过 `validate_factor_specs()` 校验
- 每个新因子至少有 1 个单元测试
- `pixi run -e dev check` 全通过

---

## 4. F4: 信号推送实现

### 4.1 设计

基于 V1 Enhancement R4 设计，实现至少 2 个推送通道：

```
SignalDeliveryService (interfaces 层实现)
  └─ DeliveryRouter (app 层 Protocol，已定义)
       ├─ WebhookChannel    ← V1 实现
       ├─ TelegramChannel   ← V1 实现
       ├─ EmailChannel      ← V1 可选
       └─ ApiOnlyChannel    ← V1 实现（默认 fallback）
```

### 4.2 推送内容

基于 `SignalSnapshot`，包含以下信息：

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

### 4.3 新增/修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `interfaces/.../services/signal_delivery.py` | 修改 | 实现 WebhookChannel + TelegramChannel |
| `config/production/notification.env` | 修改 | 配置 Telegram Bot Token + Webhook URL |
| `config/development/notification.env` | 修改 | 配置开发环境通知渠道 |

### 4.4 验收标准

- Telegram 推送能成功发送调仓信号
- Webhook 推送能成功 POST 到目标 URL
- ApiOnlyChannel 作为默认 fallback 正常工作
- 推送失败时 graceful 降级（不影响回测流程）

---

## 5. F2: 每日调度全覆盖

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

## 6. F3: DQ 规则扩展

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

## 7. F5: API 分页落地

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

## 8. F6: API 一致性改进

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

## 9. F7: 摄取状态查询 API

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

## 10. F8: IC decay 修复

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

## 11. F9: 指数成分股权重

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

## 12. F10: DQ 告警集成

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

## 13. 实施计划

### 13.1 执行顺序

```
Sprint 1 (P0 核心): F1 因子库 + F8 IC decay 修复
  ├─ F1.1: 新建因子类别文件（size/liquidity/volatility/value/momentum/quality/growth/alternative）
  ├─ F1.2: 扩展 technical.py（+10 因子）
  ├─ F1.3: 更新 factor_specs.py 聚合
  ├─ F1.4: 单元测试
  └─ F8: IC decay 修复

Sprint 2 (P0 基础设施): F2 每日调度 + F3 DQ 规则 + F10 告警
  ├─ F3: DQ 规则 YAML 文件
  ├─ F2: daily_ingestion_flow 扩展
  ├─ F10: DQ 告警集成
  └─ F9: 指数成分股注册

Sprint 3 (P0 API): F5 分页 + F6 一致性 + F4 信号推送
  ├─ F5: 分页落地
  ├─ F6: 响应格式统一 + 错误处理统一
  ├─ F4: 信号推送实现
  └─ F7: 摄取状态 API

Sprint 4 (P2 完善): F11-F14
  ├─ F11: CLI 运维命令
  ├─ F12: EOD 编排 Flow
  ├─ F13: CORS 环境化
  └─ F14: Regime 宏观指标
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
| Sprint 1 | ~10 | ~3 | ~900 行 |
| Sprint 2 | ~12 | ~3 | ~300 行 |
| Sprint 3 | ~3 | ~15 | ~850 行 |
| Sprint 4 | ~3 | ~5 | ~570 行 |
| **合计** | **~28** | **~26** | **~2,620 行** |

---

## 14. 设计决策

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 因子库规模 | 80 个核心 / ~113 完整 | ~113 完整 | 对外展示需要全面覆盖 |
| 信号推送通道 | 仅 Webhook / Telegram+Webhook | Telegram+Webhook+ApiOnly | 两个实际通道 + fallback |
| 摄取 API 范围 | 完整 CRUD / 仅状态查询 | 仅状态查询 | 触发通过 CLI/Prefect |
| API 认证 | API Key / JWT / 无 | 无 | 前端/网关层处理 |
| 因子类别组织 | 全放一个文件 / 按类别拆分 | 按类别拆分 | 113 个因子单文件过大 |
| 分页方案 | cursor-based / offset-based | offset-based | 已有模型定义，保持一致 |
