# Factor Library Taxonomy - 业界因子分类体系

**目标**: 建立符合业界最佳实践的因子分类体系，整合主流开源因子库和技术指标。

---

## 目录

- [1. 因子层级架构](#1-因子层级架构)
- [2. 技术指标 (Technical Indicators)](#2-技术指标-technical-indicators)
- [3. Alpha 因子库](#3-alpha-因子库)
- [4. Barra 风格因子](#4-barra-风格因子)
- [5. 中国 A 股特有因子](#5-中国-a-股特有因子)
- [6. 因子元数据设计](#6-因子元数据设计)
- [7. 实现优先级](#7-实现优先级)

---

## 1. 因子层级架构

### 1.1 数据层次

```
Raw Data (原始数据)
    ↓
Features/Indicators (技术指标特征)
    ├─ Price-based: MA, EMA, RSI, MACD...
    ├─ Volume-based: OBV, Volume MA...
    └─ Volatility-based: ATR, Bollinger Bands...
    ↓
Factors (量化因子)
    ├─ Fundamental: PE, PB, ROE...
    ├─ Technical: Momentum, Reversal...
    ├─ Macro: Interest Rate, Inflation...
    └─ Statistical: Z-score, Rank...
    ↓
Alpha Signals (Alpha 信号)
    ├─ Alpha101: WorldQuant 101 formulas
    ├─ Alpha191: 国泰君安 191 因子
    └─ Alpha360: Qlib 360 因子
```

### 1.2 因子命名规范

| 类型 | 前缀 | 示例 | 说明 |
|------|------|------|------|
| 技术指标 | `indicator_` | `indicator_rsi_14` | TA-Lib 风格 |
| 价值因子 | `factor_value_` | `factor_value_pe` | 价值类 |
| 动量因子 | `factor_momentum_` | `factor_momentum_12m` | 动量类 |
| 质量因子 | `factor_quality_` | `factor_quality_roe` | 质量类 |
| 波动因子 | `factor_volatility_` | `factor_volatility_hist` | 波动类 |
| 规模因子 | `factor_size_` | `factor_size_log_cap` | 规模类 |
| Alpha101 | `alpha101_` | `alpha101_001` | WorldQuant |
| Alpha191 | `alpha191_` | `alpha191_001` | 国泰君安 |
| Alpha360 | `alpha360_` | `alpha360_001` | Qlib |

---

## 2. 技术指标 (Technical Indicators)

### 2.1 分类体系 (基于 TA-Lib 150+ 指标)

#### 2.1.1 Overlap Studies (趋势指标)

| 指标 ID | 中文名 | 所需数据 | 参数 |
|---------|--------|----------|------|
| `indicator_sma_n` | 简单移动平均 | close | period |
| `indicator_ema_n` | 指数移动平均 | close | period |
| `indicator_wma_n` | 加权移动平均 | close | period |
| `indicator_dema_n` | 双指数移动平均 | close | period |
| `indicator_tema_n` | 三指数移动平均 | close | period |
| `indicator_trima_n` | 三角移动平均 | close | period |
| `indicator_kama_n` | Kaufman 自适应移动平均 | close | period |
| `indicator_mama_n` | MESA 自适应移动平均 | close | fastlimit, slowlimit |
| `indicator_t3_n` | T3 三重指数移动平均 | close | period |
| `indicator_vwma_n` | 成交量加权移动平均 | close, volume | period |
| `indicator_hull_ma_n` | Hull 移动平均 | close | period |
| `indicator_mcginley_dynamic_n` | McGinley Dynamic | close | period |
| `indicator_bollinger_bands_n` | 布林带 | close | period, std_dev |
| `indicator_sar_n` | 抛物线 SAR | high, low | acceleration, maximum |

#### 2.1.2 Momentum Indicators (动量指标)

| 指标 ID | 中文名 | 所需数据 | 参数 |
|---------|--------|----------|------|
| `indicator_rsi_n` | 相对强弱指数 | close | period |
| `indicator_stoch_n` | 随机指标 (KD) | high, low, close | k_period, d_period |
| `indicator_macd` | MACD | close | fast, slow, signal |
| `indicator_stochrsi_n` | 随机 RSI | close | period, stoch_period |
| `indicator_willr_n` | 威廉指标 %R | high, low, close | period |
| `indicator_ao_n` | Awesome Oscillator | high, low | fast, slow |
| `indicator_uo_n` | 终极振荡器 | high, low, close | fast, medium, slow |
| `indicator_sr_n` | 随机震荡器 | close | k_period, d_period |
| `indicator_stc_n` | Schaff Trend Cycle | close | fast, slow, cycle |
| `indicator_trix_n` | TRIX | close | period |
| `indicator_dx_n` | 趋向指数 | high, low, close | period |
| `indicator_minus_di_n` | 负向指标 | high, low, close | period |
| `indicator_plus_di_n` | 正向指标 | high, low, close | period |
| `indicator_minus_dm_n` | 负向运动 | high, low | period |
| `indicator_plus_dm_n` | 正向运动 | high, low | period |
| `indicator_bbands_n` | 布林带 %b | close | period, std_dev |
| `indicator_cci_n` | 商品通道指数 | high, low, close | period |
| `indicator_cmo_n` | 钱德动量摆动指标 | close | period |
| `indicator_mfi_n` | 资金流量指数 | high, low, close, volume | period |
| `indicator_mom_n` | 动量 | close | period |
| `indicator_pgo_n` | Pretty Good Oscillator | close | period |
| `indicator_roc_n` | 变化率 | close | period |
| `indicator_rocp_n` | 变化率百分比 | close | period |
| `indicator_rocr_n` | 变化率比率 | close | period |
| `indicator_rocr100_n` | 变化率比率 * 100 | close | period |
| `indicator_apo_n` | 绝对价格振荡器 | close | fast, slow |
| `indicator_ppo_n` | 百分比价格振荡器 | close | fast, slow |
| `indicator_aroondown_n` | Aroon Down | high, low | period |
| `indicator_aronup_n` | Aroon Up | high, low | period |
| `indicator_aroonosc_n` | Aroon Oscillator | high, low | period |
| `indicator_bop_n` | 均势指标 | open, high, low, close | - |
| `indicator_cc_n` | 商品通道指数 | close | period |

#### 2.1.3 Volume Indicators (成交量指标)

| 指标 ID | 中文名 | 所需数据 | 参数 |
|---------|--------|----------|------|
| `indicator_ad` | 累积/派发线 | high, low, close, volume | - |
| `indicator_adosc` | 累积/派发振荡器 | high, low, close, volume | fast, slow |
| `indicator_obv` | 能量潮 | close, volume | - |
| `indicator_natr_n` | 归一化 ATR | high, low, close | period |
| `indicator_vwap_n` | 成交量加权平均价 | high, low, close, volume | period |
| `indicator vwma_n` | 成交量加权移动平均 | close, volume | period |
| `indicator_pvi` | 正成交量指数 | close, volume | - |
| `indicator_nvi` | 负成交量指数 | close, volume | - |
| `indicator_mfi_n` | 资金流量指数 | high, low, close, volume | period |
| `indicator_cvi_n` | Chaikin 波动率 | high, low, close | period |
| `indicator_ease_n` | Ease of Movement | high, low, volume | period |
| `indicator_emv_n` | EMV | high, low, volume | period |
| `indicator_fi_n` | Force Index | close, volume | period |
| `indicator_vmacd` | 成交量 MACD | volume | fast, slow, signal |
| `indicator_vosc` | 成交量振荡器 | volume | fast, slow |
| `indicator_kvo` | Klinger Volume Oscillator | high, low, close, volume | fast, slow |
| `indicator_wad` | Williams Accumulation/Distribution | high, low, close | - |
| `indicator_willr_n` | Williams %R | high, low, close | period |

#### 2.1.4 Volatility Indicators (波动率指标)

| 指标 ID | 中文名 | 所需数据 | 参数 |
|---------|--------|----------|------|
| `indicator_atr_n` | 平均真实波幅 | high, low, close | period |
| `indicator_natr_n` | 归一化 ATR | high, low, close | period |
| `indicator_trange` | 真实波幅 | high, low, close | - |
| `indicator_bollinger_bands_n` | 布林带 | close | period, std_dev |
| `indicator_keltner_n` | 肯特纳通道 | high, low, close | period |
| `indicator_donchian_n` | 唐奇安通道 | high, low | period |
| `indicator_stddev_n` | 标准差 | close | period |
| `indicator_var_n` | 方差 | close | period |

#### 2.1.5 Cycle Indicators (周期指标)

| 指标 ID | 中文名 | 所需数据 | 参数 |
|---------|--------|----------|------|
| `indicator_ht_dcperiod` | Hilbert Transform - 周期 | close | - |
| `indicator_ht_dcphase` | Hilbert Transform - 相位 | close | - |
| `indicator_ht_phasor` | Hilbert Transform - 相位器 | close | - |
| `indicator_ht_sine` | Hilbert Transform - 正弦波 | close | - |
| `indicator_ht_trendmode` | Hilbert Transform - 趋势模式 | close | - |

#### 2.1.6 Price Transform (价格变换)

| 指标 ID | 中文名 | 所需数据 | 参数 |
|---------|--------|----------|------|
| `indicator_avgprice` | 平均价格 | open, high, low, close | - |
| `indicator_medprice` | 中位数价格 | high, low | - |
| `indicator_typprice` | 典型价格 | high, low, close | - |
| `indicator_wclprice` | 加权收盘价 | high, low, close | - |

#### 2.1.7 Pattern Recognition (K线形态识别)

| 指标 ID | 中文名 | 说明 |
|---------|--------|------|
| `pattern_doji` | Doji | 十字星 |
| `pattern_hammer` | Hammer | 锤子线 |
| `pattern_engulfing` | Engulfing | 吞没形态 |
| `pattern_harami` | Harami | 孕线形态 |
| `pattern_morning_star` | Morning Star | 早晨之星 |
| `pattern_evening_star` | Evening Star | 黄昏之星 |
| `pattern_piercing` | Piercing | 刺透形态 |
| `pattern_dark_cloud` | Dark Cloud Cover | 乌云盖顶 |
| ... | ... | (60+ K线形态) |

---

## 3. Alpha 因子库

### 3.1 WorldQuant Alpha101

**来源**: 101 Formulaic Alphas (Kakushadze 2015)

**特点**: 公式化表达式，基于价量数据的纯技术因子

#### 示例因子 (部分)

| Alpha ID | 公式描述 | 类型 |
|----------|----------|------|
| `alpha101_001` | rank(ts_argmax(close, 10)) | 动量 |
| `alpha101_002` | (-1 * correlation(rank(delta(log(volume)), 1)), rank(((close - open) / open))) | 反转 |
| `alpha101_003` | (-1 * correlation(rank(open), rank(volume), 10)) | 量价 |
| `alpha101_004` | (-1 * ts_rank(rank(low), 9)) | 反转 |
| `alpha101_005` | rank((open - (sum(vwap / 10) / 10))) * (-1 * abs(rank((close - vwap)))) | 趋势 |
| ... | ... | ... |

**完整实现需要**: 101 个公式的 Polars 表达式转换

### 3.2 国泰君安 Alpha191

**来源**: 《数量化专题: 基于短周期价量特征的多因子选股体系》(2017)

**特点**: 短周期价量特征，针对 A 股优化

#### 因子分类

| 类别 | 数量 | 示例 |
|------|------|------|
| 规模因子 | ~15 | 市值、流通市值 |
| 估值因子 | ~20 | PE, PB, PS, PCF |
| 成长因子 | ~18 | 营收增长率、利润增长率 |
| 盈利因子 | ~22 | ROE, ROA, 毛利率 |
| 动量反转 | ~25 | 累计收益、反转强度 |
| 交投因子 | ~20 | 换手率、成交量变化 |
| 波动率 | ~18 | 历史波动率、特雷诺比率 |
| 分析师预测 | ~15 | 预测上调比例、目标涨幅 |
| 其他 | ~38 | 资金流、北向资金 |

### 3.3 Microsoft Qlib Alpha360

**来源**: Qlib - AI-oriented Quantitative Investment Platform (Microsoft Research)

**特点**: 360 维特征向量，标准化设计

#### 因子分类 (参考 Qlib 源码)

| 类别 | 数量 | 特点 |
|------|------|------|
| Price-based | ~60 | 基于价格的收益率、波动 |
| Volume-based | ~30 | 成交量、换手率 |
| Price-Volume | ~80 | 价量结合 |
| Rolling Features | ~100 | 滚动统计特征 |
| Time-series | ~90 | 时序模式 |

---

## 4. Barra 风格因子

### 4.1 MSCI Barra CNE5 十大风格因子

**来源**: MSCI Barra China Equity Model (CNE5)

**特点**: 风险模型因子，用于组合风险分析和归因

#### 风格因子列表

| 因子 ID | 中文名 | 子因子 | 说明 |
|---------|--------|--------|------|
| `barra_size` | 规模因子 | log_cap, ln_me_adj | 市值对数 |
| `barra_beta` | Beta 因子 | beta_hist, beta_reg | 系统性风险 |
| `barra_momentum` | 动量因子 | momentum_12m_1m, strength | 12个月动量 |
| `barra_resvol` | 波动率因子 | dastd, cmra, hra | 剩余波动率 |
| `barra_nlsiz` | 非线性规模 | nlsiz_cube, nlsiz_square | 市值非线性 |
| `barra_btop` | 账面市值比 | btop | Book-to-Price |
| `barra_liquidity` | 流动性 | stom, stoa, turnover | 换手率相关 |
| `barra_earn` | 盈利能力 | earn_yield_forecast, earn_yield | 预测盈利 |
| `barra_growth` | 成长性 | growth_ltg_rev, growth_ltg_op | 长期增长率 |
| `barra_leverage` | 杠杆 | mlev, dto, blest | 财务杠杆 |

#### 子因子构成

**RESVOL = 0.74 × DASTD + 0.16 × CMRA + 0.10 × HRA**

- **DASTD**: Daily Standard Deviation (日收益标准差)
- **CMRA**: Cumulative Range (累计区间波动)
- **HRA**: Historical R-squared (历史拟合优度)

---

## 5. 中国 A 股特有因子

### 5.1 资金流因子

| 因子 ID | 说明 | 数据来源 |
|---------|--------|----------|
| `factor_northbound_flow` | 北向资金净流入 | 陆股通 |
| `factor_northbound_hold_pct` | 北向资金持仓占比 | 陆股通 |
| `factor_margin_debt` | 融资余额 | 两融数据 |
| `factor_margin_buy` | 融资买入额 | 两融数据 |

### 5.2 交易行为因子

| 因子 ID | 说明 | 计算方式 |
|---------|--------|----------|
| `factor_turnover_5d` | 5日换手率 | 5日平均成交量/流通股本 |
| `factor_turnover_20d` | 20日换手率 | 20日平均成交量/流通股本 |
| `factor_turnover_std_20d` | 换手率波动率 | 20日换手率标准差 |
| `factor_amplitude` | 振幅 | (high - low) / prev_close |

### 5.3 A 股特色因子

| 因子 ID | 说明 | 特点 |
|---------|--------|------|
| `factor_overnight_ret` | 隔夜收益率 | A 股隔夜收益显著 |
| `factor_auction_return` | 集合竞价收益 | 9:15-9:25 信息 |
| `factor_limit_up_count` | 涨停板次数 | 情绪指标 |
| `factor_limit_down_count` | 跌停板次数 | 情绪指标 |
| `factor_st_flag` | ST 标志 | 风险规避 |
| `factor_new_share_flag` | 次新股标志 | 次新股效应 |

---

## 6. 因子元数据设计

### 6.1 Indicator 元数据

```python
@dataclass(frozen=True)
class IndicatorMetadata:
    """技术指标元数据."""
    indicator_id: str              # indicator_rsi_14
    type: str                      # trend/momentum/volatility/volume
    name: str                      # 14-Day RSI
    description: str               # Relative Strength Index...
    category: str                  # technical
    required_columns: list[str]    # ["close"]
    params: dict[str, Any]         # {"period": 14}
    min_periods: int               # 15
    author: str | None             # Wilder / TA-Lib
    source: str                    # ta-lib / custom
    created_at: str                # ISO datetime
```

### 6.2 Factor 元数据

```python
@dataclass(frozen=True)
class FactorMetadata:
    """因子元数据."""
    factor_id: str                 # factor_momentum_12m
    class_: str                    # fundamental/technical/macro/statistical
    family: str                    # value/momentum/quality/size/volatility
    name: str                      # 12-Month Momentum
    description: str               # Cumulative return over 12 months...
    required_features: list[str]   # []
    required_columns: list[str]    # ["close"]
    pit_required: bool             # True (factors need PIT)
    normalization: str             # z-score / rank / minmax
    author: str | None             # Fama-French / Barra / Custom
    source: str                    # academic / barra / custom
    created_at: str                # ISO datetime
```

### 6.3 Alpha 元数据

```python
@dataclass(frozen=True)
class AlphaMetadata:
    """Alpha 因子元数据."""
    alpha_id: str                  # alpha101_001
    library: str                   # alpha101 / alpha191 / alpha360
    formula: str                   # 公式表达式
    description: str               # 公式说明
    type: str                      # momentum / reversal / volume / ...
    required_data: list[str]       # ["close", "volume", "vwap"]
    parameters: dict[str, Any]     # 公式参数
    author: str                    # WorldQuant / GTJA / Microsoft
    paper: str | None              # 来源论文
    created_at: str                # ISO datetime
```

---

## 7. 实现优先级

### Phase 1: 核心技术指标 (P0 - 立即实现)

**数量**: ~20 个核心指标

| 类别 | 指标 |
|------|------|
| Trend | SMA(5,10,20,60), EMA(12,26), MACD |
| Momentum | RSI(14), Stochastic, Williams %R, CCI |
| Volatility | ATR(14), Bollinger Bands(20), STDDEV |
| Volume | OBV, Volume MA, A/D Line |

### Phase 2: 常用 Alpha 因子 (P1 - 短期实现)

**数量**: ~50 个

| 来源 | 选取 |
|------|------|
| Alpha101 | 前 20 个高频使用因子 |
| Alpha191 | 规模、估值、动量类各选 5-10 个 |
| Barra CNE5 | 十大风格因子 |

### Phase 3: A 股特色因子 (P1 - 短期实现)

**数量**: ~15 个

| 类别 | 因子 |
|------|------|
| 资金流 | 北向资金、融资融券 |
| 交易行为 | 换手率、振幅 |
| A 股特色 | 隔夜收益、集合竞价 |

### Phase 4: 扩展指标库 (P2 - 中长期)

**数量**: ~100+ 个

| 来源 | 覆盖 |
|------|------|
| TA-Lib | 完整 150+ 指标 |
| Alpha191 | 完整 191 个因子 |
| Alpha360 | 完整 360 个因子 |

---

## 8. 数据依赖

### 8.1 基础数据 (OHLCV)

| 字段 | 说明 | 来源 |
|------|------|------|
| open | 开盘价 | Market Domain |
| high | 最高价 | Market Domain |
| low | 最低价 | Market Domain |
| close | 收盘价 | Market Domain |
| volume | 成交量 | Market Domain |
| amount | 成交额 | Market Domain |
| vwap | 成交量加权均价 | 计算字段 |

### 8.2 衍生数据

| 字段 | 说明 | 来源 |
|------|------|------|
| turnover_rate | 换手率 | Market/交易数据 |
| pe_ratio | 市盈率 | Fundamental Domain |
| pb_ratio | 市净率 | Fundamental Domain |
| ps_ratio | 市销率 | Fundamental Domain |
| roe | 净资产收益率 | Fundamental Domain |
| market_cap | 总市值 | 计算字段 |

### 8.3 特殊数据

| 字段 | 说明 | 来源 |
|------|------|------|
| northbound_flow | 北向资金流入 | 外部数据源 |
| margin_debt | 融资余额 | 外部数据源 |
| limit_up | 涨停标志 | Market Domain |

---

## 9. 计算框架设计

### 9.1 Calculator 接口

```python
# 所有 Calculator 统一接口
class Calculator(ABC):
    @property
    @abstractmethod
    def required_columns(self) -> list[str]: ...

    @abstractmethod
    def calculate(self, df: pl.DataFrame) -> pl.DataFrame: ...

# Indicator Calculator (通常无需 PIT)
class FeatureCalculator(Calculator):
    """技术指标计算器 - 公式固定时无需 PIT，公式/参数变化时需要 PIT"""
    pass

# Factor Calculator (有 PIT)
class FactorCalculator(Calculator):
    """因子计算器 - 需要 PIT 支持"""
    def normalize(self, df: pl.DataFrame) -> pl.DataFrame: ...
    def add_pit_metadata(self, df: pl.DataFrame) -> pl.DataFrame: ...

# Alpha Calculator (表达式)
class AlphaCalculator(Calculator):
    """Alpha 公式计算器 - 表达式求值"""
    @property
    def expression(self) -> str: ...  # Polars 表达式
```

### 9.2 表达式引擎 (针对 Alpha101/191/360)

```python
# 支持的表达式函数
EXPRESSION_FUNCTIONS = {
    # 时间序列
    "ts_rank": lambda col, n: col.shift(n).rank(),
    "ts_sum": lambda col, n: col.rolling_sum(n),
    "ts_mean": lambda col, n: col.rolling_mean(n),
    "ts_std": lambda col, n: col.rolling_std(n),
    "ts_argmax": lambda col, n: col.shift(n).arg_max(),
    "ts_argmin": lambda col, n: col.shift(n).arg_min(),
    "ts_delta": lambda col, n: col.shift(n) - col,
    "ts_correlation": lambda col1, col2, n: col1.rolling_corr(col2, n),

    # 统计
    "rank": lambda col: col.rank(),
    "sign": lambda col: pl.sign(col),
    "log": lambda col: pl.log(col),
    "abs": lambda col: pl.abs(col),
    "delay": lambda col, n: col.shift(n),

    # 条件
    "cond": lambda condition, true_val, false_val: pl.when(condition).then(true_val).otherwise(false_val),
}
```

---

## 10. 参考资源

### 10.1 开源项目

| 项目 | URL | 说明 |
|------|-----|------|
| TA-Lib | https://ta-lib.org/ | 150+ 技术指标 C 库 |
| Qlib | https://github.com/microsoft/qlib | Microsoft 量化平台 |
| Pandas TA | https://github.com/twopirllc/pandas-ta | 150+ Python 指标 |
| Alphalens | https://github.com/quantopian/alphalens | 因子分析工具 |
| DolphinDB | https://www.dolphindb.com/ | 时序数据库 (含因子库) |

### 10.2 学术资源

| 资源 | 说明 |
|------|------|
| 101 Formulaic Alphas | Kakushadze 2015, WorldQuant 公式 |
| Fama-French 5-Factor | Eugene Fama, Kenneth French |
| MSCI Barra CNE5 | 中国股票风险模型 |
| 国泰君安 Alpha191 | 《数量化专题: 基于短周期价量特征的多因子选股体系》 |

### 10.3 业界实践

| 公司/机构 | 说明 |
|-----------|------|
| WorldQuant | Alpha101 因子库 |
| 国泰君安 | Alpha191 因子库 |
| Microsoft Research | Qlib / Alpha360 |
| MSCI | Barra 风险模型 |
| BigQuant | 因子计算平台 |

---

## 总结

本文档建立了完整的因子分类体系，包括:

1. **150+ 技术指标** (TA-Lib 标准)
2. **Alpha101/191/360 因子库**
3. **Barra CNE5 十大风格因子**
4. **中国 A 股特有因子**

**下一步**:
1. 实现 Phase 1 核心技术指标 (~20 个)
2. 实现计算引擎和表达式解析
3. 建立因子有效性测试框架
