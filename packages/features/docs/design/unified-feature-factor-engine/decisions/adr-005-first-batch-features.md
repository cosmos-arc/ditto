> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-005: 首批特征与因子清单

**状态**: 已决策（2026-03-04）

---

## 首批特征清单（Phase 0）

### A. 技术指标特征（12 个核心指标）

| 特征 ID | 表达式 | 类型 | lookback | 依赖 |
|---------|--------|------|----------|------|
| `rsi_{n}` | `100 - 100 / (1 + ts_mean(up, n) / ts_mean(down, n))` | momentum | n+1 | market.close |
| `ma_{n}` | `ts_mean(market.close, n)` | trend | n | market.close |
| `ema_{n}` | `ts_ema(market.close, n)` | trend | n*2 | market.close |
| `macd_dif` | `ts_ema(market.close, 12) - ts_ema(market.close, 26)` | trend | 52 | market.close |
| `macd_dea` | `ts_ema(@macd_dif, 9)` | trend | 70 | @macd_dif |
| `macd_hist` | `@macd_dif - @macd_dea` | trend | 70 | @macd_dif, @macd_dea |
| `boll_upper_{n}` | `ts_mean(close, n) + 2 * ts_std(close, n)` | volatility | n | market.close |
| `boll_lower_{n}` | `ts_mean(close, n) - 2 * ts_std(close, n)` | volatility | n | market.close |
| `atr_{n}` | `ts_mean(@tr, n)` | volatility | n+1 | market.high/low/close |
| `volatility_{n}` | `ts_std(@returns_1, n)` | volatility | n+1 | market.close |
| `volume_ma_{n}` | `ts_mean(market.volume, n)` | volume | n | market.volume |
| `returns_{n}` | `ts_pct_change(market.close, n)` | trend | n+1 | market.close |

**常用参数值**: `n = {5, 10, 14, 20, 60}`

### B. 基本面特征（8 个核心指标）

| 特征 ID | 表达式 | 类型 | PIT | 依赖 |
|---------|--------|------|-----|------|
| `pe_ttm` | `fund.pe_ttm` | value | Yes | fund.* |
| `pb_lf` | `fund.pb_lf` | value | Yes | fund.* |
| `ps_ttm` | `fund.ps_ttm` | value | Yes | fund.* |
| `debt_ratio` | `balance.total_liab / balance.total_assets` | quality | Yes | balance.* |
| `roe` | `income.net_profit / balance.total_equity` | quality | Yes | income.*, balance.* |
| `net_margin` | `income.net_profit / income.revenue` | quality | Yes | income.* |
| `asset_turnover` | `income.revenue / balance.total_assets` | quality | Yes | income.*, balance.* |
| `earnings_growth_yoy` | `(net_profit - delay(net_profit, 252)) / abs(...)` | growth | Yes | income.* |

### C. Alpha 因子（10 个核心因子）

| 因子 ID | 表达式 | 家族 | 标准化 |
|---------|--------|------|--------|
| `alpha_momentum_1m` | `cs_rank(ts_pct_change(market.close, 20))` | momentum | rank→zscore |
| `alpha_momentum_12m` | `cs_rank(ts_mean(@returns_1, 250))` | momentum | rank→zscore |
| `alpha_reversal_1w` | `cs_rank(-ts_pct_change(market.close, 5))` | momentum | rank→zscore |
| `alpha_value_pe` | `cs_rank(-fund.pe_ttm)` | value | rank→zscore |
| `alpha_value_pb` | `cs_rank(-fund.pb_lf)` | value | rank→zscore |
| `alpha_quality_roe` | `cs_rank(income.net_profit / balance.total_equity)` | quality | rank→zscore |
| `alpha_quality_margin` | `cs_rank(income.net_profit / income.revenue)` | quality | rank→zscore |
| `alpha_volatility` | `cs_rank(-ts_std(@returns_1, 20))` | volatility | rank→zscore |
| `alpha_liquidity` | `cs_rank(ts_mean(market.volume, 20) / market.total_mv)` | size | rank→zscore |
| `alpha_001` | WorldQuant Alpha001 完整表达式 | composite | rank→zscore |

---

## 计算优先级（DAG 拓扑序）

```
P1: 原始数据摄入 (market.*, fund.*, balance.*, income.*)
    ↓
P2: 1日延迟计算 (@returns_1, @tr)
    ↓
P3: 短周期指标 (@ma_5, @ema_12, @ema_26, @volume_ma_5)
    ↓
P4: 中周期指标 (@rsi_14, @atr_14, @boll_*, @volatility_20)
    ↓
P5: 二级依赖 (@macd_dif → @macd_dea → @macd_hist)
    ↓
P6: Alpha 因子 (@alpha_*)
    ↓
P7: 组合因子 (@alpha_value_combo, etc.)
```
