# Features & Factors Domain 架构设计

**创建日期**: 2026-02-01
**状态**: 设计草案
**作者**: Claude
**相关阶段**: Phase 7 (Features), Phase 8 (Factors)

---

## 一、设计原则

基于业界最佳实践调研，采用**三层架构**：

```
第一层：基础数据 (Market, Fundamental, Macro)
         ↓
第二层：特征/指标层 (Features = Indicators + Fundamental Features)
         ↓
第三层：因子/信号层 (Factors = 验证后的策略信号)
```

**核心设计原则**：
- **Features** 是原材料，包含技术指标 (`indicator_*`) 和基本面特征 (`feature_*`)
- **Factors** 是加工后的策略信号 (`factor_*`)，支持 PIT 查询
- 窄表为主，宽表为辅 — 灵活性 vs 性能的平衡
- 按 `indicator_type` 和 `factor_class/factor_family` 分类

---

## 二、数据层级体系

### 2.1 层级关系

| 层级 | 命名前缀 | 示例 | 分类字段 | 用途 |
|------|---------|------|---------|------|
| **第二层：技术指标** | `indicator_` | `indicator_rsi_14`, `indicator_ma_20` | `indicator_type` | 原材料 |
| **第二层：基本面特征** | `feature_` | `feature_pe_ratio`, `feature_roe_ttm` | `feature_category` | 原材料 |
| **第三层：因子** | `factor_` | `factor_momentum_12m`, `factor_quality_zscore` | `factor_class`, `factor_family` | 策略信号 |

### 2.2 分类体系

**Indicator Types** (基于 [ScienceDirect 2025]):
- `trend` - 趋势类 (MA, EMA, MACD)
- `momentum` - 动量类 (RSI, CCI, Stochastic)
- `volatility` - 波动率类 (ATR, Bollinger Bands, Historical Volatility)
- `volume` - 成交量类 (OBV, Volume ROC, VWAP)

**Factor Classes** (基于 CFA Curriculum):
- `fundamental` - 基本面因子 (Value, Quality, Growth)
- `technical` - 技术面因子 (Momentum, Reversal)
- `macro` - 宏观因子 (Interest Rate, GDP)
- `statistical` - 统计因子 (PCA 主成分)

**Factor Families** (基于 MSCI Barra / WorldQuant):
- `value` - 价值 (PE, PB, PCF)
- `momentum` - 动量 (12M Return, 1M Return)
- `quality` - 质量 (ROE, Financial Health)
- `size` - 规模 (Market Cap)
- `volatility` - 波动率 (Historical Vol, Idiosyncratic Vol)

---

## 三、存储结构设计

### 3.1 目录结构

```
data_root/
├── features/                          # 第二层：特征域
│   ├── technical/
│   │   ├── indicators_narrow/         # 窄表（按年分区）
│   │   │   ├── 2024/
│   │   │   └── 2025/
│   │   └── indicators_wide/           # 宽表（每周更新）
│   │       └── weekly/
│   └── fundamental/                   # 未来扩展
│
└── factors/                           # 第三层：因子域
    ├── factors_narrow/                # 窄表（Parquet + PIT 列）
    │   ├── 2024/
    │   └── 2025/
    └── factors_wide/                  # 宽表（每周更新）
        └── weekly/
```

### 3.2 Schema 设计

#### Technical Indicators 窄表

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券标识符 | ✗ |
| trade_date | date | 交易日期 | ✗ |
| indicator_id | string | 指标标识符 (`indicator_rsi_14`) | ✗ |
| indicator_type | string | 类型 (`trend`/`momentum`/`volatility`/`volume`) | ✗ |
| value | float64 | 指标值 | ✗ |
| calc_time | datetime | 计算时间戳 | ✗ |

**分区策略**: 按 `trade_date` 年份分区
**存储格式**: Parquet
**主键**: `(trade_date, sid, indicator_id)`

#### Factors 窄表 (带 PIT 支持)

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券标识符 | ✗ |
| trade_date | date | 交易日期 | ✗ |
| factor_id | string | 因子标识符 (`factor_momentum_12m`) | ✗ |
| factor_class | string | 类别 (`fundamental`/`technical`/`macro`/`statistical`) | ✗ |
| factor_family | string | 系列 (`value`/`momentum`/`quality`/`size`/`volatility`) | ✗ |
| exposure | float64 | 因子暴露度（标准化后） | ✗ |
| raw_value | float64 | 原始因子值 | ✓ |
| effective_from | date | 生效开始日期 | ✗ |
| effective_to | date | 生效结束日期 | ✓ |

**分区策略**: 按 `trade_date` 年份分区
**存储格式**: Parquet
**主键**: `(sid, trade_date, factor_id, effective_from)`

#### 元数据

**Indicator Metadata**:
```python
{
    "indicator_id": "indicator_rsi_14",
    "name": "RSI(14)",
    "type": "momentum",
    "description": "14日相对强弱指标",
    "formula": "RSI = 100 - 100/(1 + RS)",
    "parameters": {"period": 14},
    "created_at": "2024-01-01",
    "status": "active"
}
```

**Factor Metadata**:
```python
{
    "factor_id": "factor_momentum_12m",
    "name": "12月动量因子",
    "class": "technical",
    "family": "momentum",
    "description": "过去12个月累计收益率",
    "formula": "return_12m = price_today / price_252_ago - 1",
    "pit_enabled": true,
    "status": "active"
}
```

---

## 四、代码结构设计

```
packages/data/src/ditto_data/domains/
│
├── features/                          # 第二层：特征域
│   ├── __init__.py
│   ├── feature_service.py             # 统一查询入口
│   │
│   ├── metadata/                      # 特征元数据
│   │   ├── __init__.py
│   │   ├── feature_metadata_store.py
│   │   └── metadata.py
│   │
│   └── technical/                     # 技术指标特征
│       ├── __init__.py
│       ├── indicator_store.py         # 窄表存储 (Parquet)
│       ├── indicator_metadata_store.py
│       └── query.py
│
└── factors/                           # 第三层：因子域
    ├── __init__.py
    ├── factor_service.py              # 统一查询入口 (支持 PIT)
    ├── factor_store.py                # 窄表存储 (Parquet + PIT)
    ├── factor_metadata_store.py
    └── query.py                       # PIT 查询逻辑
```

---

## 五、关键设计决策

| 决策点 | 方案 | 理由 |
|--------|------|------|
| **Features 存储** | Parquet 窄表 | 灵活、支持任意指标扩展 |
| **Factors 存储** | Parquet 窄表 + PIT 列 | 回测必须避免 look-ahead bias |
| **宽表生成** | 定期 Pivot（每周） | 平衡灵活性与查询性能 |
| **分区策略** | 按年份分区 | 时序数据的标准做法 |
| **元数据管理** | 独立 Store | 便于数据发现和版本管理 |
| **PIT 支持** | 仅 Factors 需要 | Indicators 是历史计算，无修正问题 |

---

## 六、与现有域的关系

### 6.1 数据流向

```
Market Domain (price data)
    ↓
Features Technical Indicators (MA, RSI, MACD...)
    ↓
Factors (经过验证的策略信号)
    ↓
Core Engine (回测、组合构建)
```

### 6.2 与 Macro Domain 的对比

| 域 | PIT 需求 | 存储格式 | 原因 |
|----|----------|----------|------|
| **Macro** | 需要 | SQLite + PIT | 数据有修正（初值/修订值） |
| **Features** | 不需要 | Parquet | 纯历史计算，无修正 |
| **Factors** | 需要 | Parquet + PIT 列 | 回测必须避免 look-ahead bias |

---

## 七、业界参考

1. **Indicator 分类** - [Key technical indicators for stock market prediction (ScienceDirect 2025)](https://www.sciencedirect.com/science/article/pii/S2666827025000143)
2. **Factor 分类** - [Macroeconomic, Fundamental, and Statistical Factor Models (CFA)](https://analystprep.com/study-notes/cfa-level-2/describe-and-compare-macroeconomic-factor-models-fundamental-factor-models-and-statistical-factor-models/)
3. **PIT 重要性** - [Point-In-Time vs. Lagged Fundamentals (S&P Global)](https://www.spglobal.com/content/dam/spglobal/mi/en/documents/general/sp-capitaliq-quantamental-point-in-time-vs-lagged-fundamentals.pdf)
4. **存储格式** - [Trading Data Analytics — Part 0: Parquet Files and MinIO S3](https://medium.com/quant-factory/trading-data-analytics-part-0-parquet-files-and-minio-s3-ccdeaf4d59e5)
5. **Look-ahead Bias** - [Look-Ahead Bias Prevention in Quantitative Trading](https://medium.com/@jpolec_72972/look-ahead-bias-prevention-and-signal-processing-in-quantitative-trading-9def856db5a6)

---

## 八、实施计划

### Phase 7: Features Domain (Technical Indicators)

1. 创建 `features/technical` 目录结构
2. 实现 `IndicatorStore` (Parquet 窄表存储)
3. 实现 `IndicatorMetadataStore`
4. 实现 `FeatureService` (统一查询入口)
5. 编写单元测试

### Phase 8: Factors Domain

1. 创建 `factors` 目录结构
2. 实现 `FactorStore` (Parquet 窄表 + PIT)
3. 实现 `FactorMetadataStore`
4. 实现 `FactorService` (支持 PIT 查询)
5. 编写单元测试

---

**文档版本**: v1.0
**最后更新**: 2026-02-01
