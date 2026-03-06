# Macro 与 Market 域边界设计文档

**日期**: 2026-02-25
**状态**: 设计完成，待实施
**参与者**: Brainstorming Session

---

## 1. 设计背景

### 1.1 问题陈述

在量化数据系统中，以下数据存在分类 ambiguity：
- **利率数据**：国债收益率、SHIBOR、LPR 等
- **汇率数据**：USD/CNY、EUR/CNY 等
- **商品数据**：黄金、原油、铜等

这些数据既有"市场价格"属性，又常被当作"宏观指标"使用，导致域边界不清晰。

### 1.2 核心矛盾

| 数据 | 本质 | 常被当作 |
|------|------|---------|
| 国债收益率 | 债券的价格（收益率曲线） | 利率宏观指标 |
| 汇率 | 货币对的价格 | 汇率宏观指标 |
| 黄金价格 | 商品/资产的价格 | 避险/通胀指标 |

---

## 2. 架构哲学决策

### 2.1 两种哲学对比

| 哲学 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A. 按本质存储** | 价格数据放 Market 域，通过标签/视图派生宏观因子 | 数据一致、无冗余、扩展性好 | 需要额外的标签机制 |
| **B. 按用途分域** | 同一数据可能同时存在于 Market 和 Macro 域 | 查询简单 | 数据冗余、一致性风险 |

### 2.2 决策：采用哲学 A

**理由**：
1. **数据一致性**：价格就是价格，不应因用途不同而存储两次
2. **存储效率**：避免数据冗余
3. **扩展性**：未来支持交易时，数据已在正确位置
4. **代码复用**：所有价格数据复用同一套 Market 基础设施

**业界参考**：Bloomberg、大型量化团队均采用此模式。

---

## 3. 域边界定义

### 3.1 Market 域（可交易资产价格）

**存储内容**：所有有市场价格的可交易资产

| 数据类型 | 示例 | 存储结构 |
|---------|------|---------|
| 股票 | 000001.SZ | OHLCV |
| ETF | 510300.SH | OHLCV |
| 指数 | 000001.SH | OHLCV |
| **债券** | CN10Y（10年期国债） | 收益率曲线 |
| **货币** | USD.CNY | 汇率价格 |
| **商品** | XAU.USD, CL.WTI | 现货/期货价格 |
| 期货 | SC2401（原油期货） | OHLCV + 期限结构 |

**特点**：
- 标准化 OHLCV 结构（或收益率曲线结构）
- 支持按交易日期查询
- 支持按标的查询历史数据

### 3.2 Macro 域（不可交易统计指标）

**存储内容**：由国家/机构发布的统计指标，无直接交易市场

| 数据类型 | 示例 | 频率 |
|---------|------|------|
| 经济增长 | GDP（同比/环比） | 季度 |
| 通胀指标 | CPI、PPI | 月度 |
| 经济景气 | PMI | 月度 |
| 货币供应 | M0、M1、M2 | 月度 |
| 就业数据 | 失业率、非农就业 | 月度 |
| 社会融资 | 社会融资规模 | 月度 |

**特点**：
- 窄表结构（indicator_code + date + value）
- 支持 PIT（Point-in-Time）
- 可能需要 knowledge_date（数据发布日期）

### 3.3 边界判定规则

```
if (数据是否有市场价格？) {
    → Market 域
} else if (数据是官方/机构发布的统计指标？) {
    → Macro 域
}
```

**具体判定**：

| 数据 | 有市场价格？ | 归属域 |
|------|-------------|--------|
| 10年期国债收益率 | ✅（债券价格） | Market |
| SHIBOR 隔夜利率 | ✅（银行间拆借价格） | Market |
| LPR 利率 | ⚠️（报价，但不是交易价格） | Macro |
| USD/CNY 汇率 | ✅（外汇市场价格） | Market |
| 黄金价格 | ✅（商品市场价格） | Market |
| GDP 同比 | ❌ | Macro |
| CPI 同比 | ❌ | Macro |
| M2 同比 | ❌ | Macro |

---

## 4. 标签/分类机制

### 4.1 资产类型标签

```python
class InstrumentCategory(StrEnum):
    """资产类型标签"""
    EQUITY = "equity"           # 股票
    INDEX = "index"             # 指数
    ETF = "etf"                 # ETF
    BOND = "bond"               # 债券
    CURRENCY = "currency"       # 货币/汇率
    COMMODITY = "commodity"     # 商品
    FUTURES = "futures"         # 期货
```

### 4.2 宏观相关性标签

为 Market 域中的资产打上"宏观相关性"标签，便于按宏观因子视角查询：

```python
class MacroRelevance(StrEnum):
    """宏观相关性标签"""
    NONE = "none"                     # 无宏观相关性（普通股票）
    INTEREST_RATE = "interest_rate"   # 利率相关（国债、SHIBOR）
    INFLATION = "inflation"           # 通胀相关（商品）
    RISK_SENTIMENT = "risk_sentiment" # 风险情绪（黄金、VIX）
    CURRENCY = "currency"             # 汇率相关
```

### 4.3 数据存储示例

**instruments 表**（扩展）：

```sql
CREATE TABLE instruments (
    instrument_id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,        -- InstrumentCategory
    macro_relevance TEXT,          -- MacroRelevance（可选）
    exchange TEXT,
    list_date DATE,
    -- ...
);
```

**示例数据**：

| ticker | name | category | macro_relevance |
|--------|------|----------|-----------------|
| 000001.SZ | 平安银行 | equity | none |
| USD.CNY | 美元人民币 | currency | currency |
| XAU.USD | 黄金现货 | commodity | risk_sentiment |
| CL.WTI | WTI原油 | commodity | inflation |
| CN10Y | 中国10年期国债 | bond | interest_rate |
| SHIBOR_ON | 隔夜Shibor | bond | interest_rate |

---

## 5. Macro 域简化后的结构

### 5.1 类别枚举（简化）

```python
class MacroCategory(StrEnum):
    """宏观指标类别（仅限不可交易指标）"""
    ECONOMIC = "economic"           # 经济增长：GDP、工业增加值
    PRICES = "prices"               # 物价：CPI、PPI
    MONEY_SUPPLY = "money_supply"   # 货币：M0、M1、M2
    EMPLOYMENT = "employment"       # 就业：失业率、非农
    CREDIT = "credit"               # 信贷：社融、贷款
    SURVEY = "survey"               # 调查：PMI、消费者信心
```

**移除的类别**（转移到 Market 域）：
- ~~`INTEREST_RATE`~~ → Market 域（债券类别）
- ~~`EXCHANGE_RATE`~~ → Market 域（货币类别）

### 5.2 数据来源

| 地区 | 数据源 | 指标范围 |
|------|--------|---------|
| 中国 | Tushare | GDP、CPI、PPI、M2、PMI、社融等 |
| 美国 | FRED | GDP、CPI、PCE、就业、货币供应等 |

---

## 6. 查询模式

### 6.1 查询价格数据（利率/汇率/商品）

```python
# 通过 Market 域查询
market_service.get_bars(
    tickers=["USD.CNY", "XAU.USD", "CN10Y"],
    start_date="2024-01-01",
    end_date="2024-12-31",
)

# 按宏观相关性筛选
market_service.get_instruments_by_macro_relevance(
    relevance="interest_rate"
)
```

### 6.2 查询宏观指标

```python
# 通过 Macro 域查询
macro_service.get_indicators(
    codes=["GDP_QOQ", "CPI_YOY", "M2_YOY"],
    start_date="2024-01-01",
    end_date="2024-12-31",
)
```

---

## 7. 实施影响

### 7.1 需要调整的代码

| 组件 | 调整内容 |
|------|---------|
| `MacroCategory` | 移除 `INTEREST_RATE`、`EXCHANGE_RATE` |
| `InstrumentCategory` | 新增 `BOND`、`CURRENCY`、`COMMODITY` |
| `instruments` 表 | 新增 `macro_relevance` 字段 |
| Market 域 | 新增债券、货币、商品的数据模型和存储 |
| 现有 `shibor` 实现 | 迁移到 Market 域（或保留作为过渡） |

### 7.2 优先级建议

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | FRED 数据源接入 | 支持美国宏观数据 |
| P1 | Market 域扩展 | 新增债券/汇率/商品支持 |
| P1 | 标签机制实现 | `macro_relevance` 字段 |
| P2 | 迁移现有 SHIBOR | 从 Macro 迁移到 Market |
| P2 | CLI/API 更新 | 按新架构调整命令 |

---

## 8. 决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-02-25 | 采用"按本质存储"哲学 | 数据一致性、无冗余、扩展性好 |
| 2026-02-25 | 利率/汇率/商品 → Market 域 | 本质是价格数据 |
| 2026-02-25 | GDP/CPI/M2 等 → Macro 域 | 不可交易的统计指标 |
| 2026-02-25 | 通过标签实现宏观相关性查询 | 保持域边界清晰，同时支持多视角查询 |

---

## 附录：参考架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据架构                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Market 域                             │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐   │   │
│  │  │ 股票    │ │ ETF/指数│ │ 债券    │ │ 货币/商品   │   │   │
│  │  │ (OHLCV) │ │ (OHLCV) │ │(收益率) │ │ (价格)      │   │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘   │   │
│  │       │            │          │              │         │   │
│  │       └────────────┴──────────┴──────────────┘         │   │
│  │                          │                              │   │
│  │              macro_relevance 标签                       │   │
│  │                          │                              │   │
│  │              ▼────────────▼─────────────▼               │   │
│  │         interest_rate  inflation  risk_sentiment        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Macro 域                              │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐   │   │
│  │  │ 经济    │ │ 物价    │ │ 货币    │ │ 就业/信贷   │   │   │
│  │  │ GDP     │ │ CPI/PPI │ │ M0/M1/M2│ │ 社融/失业率 │   │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘   │   │
│  │         (不可交易的官方统计指标)                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
