# Market 域宏观相关数据设计文档

**日期**: 2026-02-26
**状态**: 设计完成，待实施
**前置文档**:
- [Macro 与 Market 域边界设计](2026-02-25-macro-and-market-domain-boundary-design.md)
- [宏观数据源统一设计](2026-02-25-macro-data-source-design.md)

---

## 1. 背景与范围

### 1.1 设计背景

根据 [Macro 与 Market 域边界设计](2026-02-25-macro-and-market-domain-boundary-design.md)，以下数据归属 **Market 域**但具有宏观相关性：

| 数据类型 | 归属域 | 判定依据 |
|---------|--------|---------|
| **利率** | Market | 本质是价格（债券收益率、拆借利率） |
| **汇率** | Market | 本质是价格（货币对价格） |
| **商品** | Market | 本质是价格（商品市场价格） |

### 1.2 设计范围

本文档覆盖：
- ✅ 利率数据（Shibor、LPR、国债收益率等）
- ✅ 汇率数据（USD/CNY、EUR/USD 等）
- ✅ 大宗商品数据（能源、贵金属、有色金属、农产品）
- ✅ VIX 波动率指数
- ✅ 黄金/白银 ETF 持仓量（归属 **Capital 域**）

---

## 2. 决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-02-26 | 整体规划，分批实施 | 降低首期复杂度 |
| 2026-02-26 | 利率数据：Tushare（中国）+ FRED（美国） | 复用现有架构，覆盖完整 |
| 2026-02-26 | 利率数据：完整集 | Shibor全期限 + LPR + Libor/Hibor + 国债收益率曲线 |
| 2026-02-26 | 汇率数据：Tushare 为主 | 复用现有架构，中国视角 |
| 2026-02-26 | PIT 支持：不需要 | 利率/汇率是市场价格，不会事后修订 |
| 2026-02-26 | **大宗商品：FRED 为主** | 首期仅实现能源/贵金属（FRED），有色/农产品后续扩展 |
| 2026-02-26 | **VIX 指数：FRED** | 官方稳定，日频数据 |
| 2026-02-26 | **AKShare：暂不引入** | 有色/农产品延后，避免首期引入新数据源 |
| 2026-02-26 | **ETF 持仓：暂不实现** | 黄金/白银 ETF 持仓延后，归属 Capital 域 |

---

## 3. 数据源策略

### 3.1 数据源总览

#### 首期实施（P0）

| 数据类型 | 主数据源 | 频率 | 归属域 | 状态 |
|---------|---------|------|--------|------|
| **利率（中国）** | Tushare | 日频/月频 | Market | ✅ 首期 |
| **利率（美国）** | FRED | 日频 | Market | ✅ 首期 |
| **汇率** | Tushare | 日频 | Market | ✅ 首期 |
| **能源（原油）** | FRED | 日频 | Market | ✅ 首期 |
| **贵金属价格（金/银）** | FRED | 日频 | Market | ✅ 首期 |
| **VIX 指数** | FRED | 日频 | Market | ✅ 首期 |

#### 后续扩展（P1/P2）

| 数据类型 | 主数据源 | 频率 | 归属域 | 状态 |
|---------|---------|------|--------|------|
| **有色金属（铜等）** | AKShare（需新增） | 日频 | Market | ⏳ 后续 |
| **农产品（大豆/玉米/小麦）** | AKShare（需新增） | 日频 | Market | ⏳ 后续 |
| **黄金/白银 ETF 持仓** | 新浪爬取（需实现） | 日频 | Capital | ⏳ 后续 |

### 3.2 数据源能力矩阵

| 数据类型 | Tushare | FRED | AKShare | 新浪爬取 |
|---------|---------|------|---------|---------|
| Shibor/LPR | ✅ | ❌ | ❌ | ❌ |
| 中国国债收益率 | ✅ `yc_cb` | ❌ | ❌ | ❌ |
| Libor/Hibor | ✅ | ❌ | ❌ | ❌ |
| 美国国债收益率 | ⚠️ `us_trycr` | ✅ `DGS*` | ❌ | ❌ |
| 联邦基金利率 | ❌ | ✅ | ❌ | ❌ |
| 人民币汇率 | ✅ `fx_daily` | ✅ `DEXCHUS` | ❌ | ❌ |
| WTI/布伦特原油 | ❌ | ✅ | ✅ | ❌ |
| 黄金/白银价格 | ❌ | ✅ | ✅ | ❌ |
| LME 铜/铝/镍/锌 | ❌ | ⚠️ 月频 | ✅ 日频 | ❌ |
| CBOT 大豆/玉米/小麦 | ❌ | ⚠️ 月频 | ✅ 日频 | ❌ |
| VIX 指数 | ❌ | ✅ | ❌ | ❌ |
| GLD/SLV ETF 持仓 | ❌ | ❌ | ❌ | ✅ |

---

## 4. Tushare 接口详情

### 4.1 利率接口

| 接口名 | 描述 | 权限要求 |
|--------|------|---------|
| `shibor` | 上海银行间同业拆放利率（全期限） | 基础权限 |
| `shibor_lpr` | 贷款市场报价利率（1年/5年） | 基础权限 |
| `libor` | 伦敦银行间同业拆放利率 | 基础权限 |
| `hibor` | 香港银行间同业拆放利率 | 基础权限 |
| `yc_cb` | 中债国债收益率曲线 | 120 积分 |

### 4.2 汇率接口

| 接口名 | 描述 | 权限要求 |
|--------|------|---------|
| `fx_daily` | 外汇日线行情 | 基础权限 |

---

## 5. FRED 接口详情

### 5.1 利率数据

| Series ID | 描述 | 频率 |
|-----------|------|------|
| `DGS1` | 1年期国债收益率 | 日频 |
| `DGS2` | 2年期国债收益率 | 日频 |
| `DGS5` | 5年期国债收益率 | 日频 |
| `DGS10` | 10年期国债收益率 | 日频 |
| `DGS30` | 30年期国债收益率 | 日频 |
| `T10Y2Y` | 10Y-2Y 国债利差 | 日频 |
| `FEDFUNDS` | 联邦基金有效利率 | 月频 |
| `DFF` | 联邦基金有效利率 | 日频 |

### 5.2 大宗商品数据

| Series ID | 描述 | 频率 |
|-----------|------|------|
| `DCOILWTICO` | WTI 原油价格 | 日频 |
| `DCOILBRENTEU` | 布伦特原油价格 | 日频 |
| `GOLDAMGBD228NLBM` | 伦敦黄金定盘价（上午） | 日频 |
| `SLVPRUSD` | 伦敦白银定盘价 | 日频 |
| `PCOPPUSDM` | 国际铜价（IMF） | 月频 |

### 5.3 VIX 指数

| Series ID | 描述 | 频率 |
|-----------|------|------|
| `VIXCLS` | VIX 波动率指数（30天） | 日频 |
| `VIX9D` | VIX 9天波动率指数 | 日频 |

---

## 6. AKShare 外盘期货接口

### 6.1 核心接口

| 函数 | 功能 | 返回类型 |
|------|------|---------|
| `futures_hq_subscribe_exchange_symbol()` | 外盘品种代码表 | pandas DataFrame |
| `futures_foreign_commodity_realtime()` | 实时行情 | pandas DataFrame |
| `futures_foreign_hist(symbol)` | 历史行情 | pandas DataFrame |

### 6.2 支持的品种代码

| 品种 | 代码 | 交易所 |
|------|------|--------|
| LME 铜 3M | `CAD` | LME |
| LME 铝 3M | `AHD` | LME |
| LME 锌 3M | `ZSD` | LME |
| LME 镍 3M | `NID` | LME |
| LME 铅 3M | `PBD` | LME |
| LME 锡 3M | `SND` | LME |
| COMEX 黄金 | `GC` | CME |
| COMEX 白银 | `SI` | CME |
| COMEX 铜 | `HG` | CME |
| NYMEX WTI 原油 | `CL` | CME |
| NYMEX 天然气 | `NG` | CME |
| CBOT 大豆 | `ZS=F` | CME |
| CBOT 玉米 | `ZC=F` | CME |
| CBOT 小麦 | `ZW=F` | CME |

### 6.3 pandas → polars 转换

```python
import akshare as ak
import polars as pl

# 获取 LME 铜历史数据
df_pandas = ak.futures_foreign_hist(symbol="CAD")

# 转换为 polars
df_polars = pl.from_pandas(df_pandas)
```

---

## 7. 新浪 ETF 持仓爬取

### 7.1 数据源

- **黄金 ETF 持仓**：新浪财经/金投网
- **白银 ETF 持仓**：新浪财经/金投网

### 7.2 数据字段

| 字段 | 说明 |
|------|------|
| date | 日期 |
| gld_holdings | GLD 黄金持仓量（吨） |
| gld_change | GLD 持仓变化（吨） |
| slv_holdings | SLV 白银持仓量（吨） |
| slv_change | SLV 持仓变化（吨） |

### 7.3 实现方式

```python
# 待实现：新浪 ETF 持仓爬虫
class ETFFoldingsSpider:
    """黄金/白银 ETF 持仓数据爬虫"""

    def fetch_gld_holdings(self, start_date: str, end_date: str) -> pl.DataFrame:
        """获取 GLD 黄金 ETF 持仓数据"""
        ...

    def fetch_slv_holdings(self, start_date: str, end_date: str) -> pl.DataFrame:
        """获取 SLV 白银 ETF 持仓数据"""
        ...
```

---

## 8. 数据范围定义

### 8.1 利率数据（完整集）

#### 中国利率（Tushare）

| 指标代码 | 指标名称 | 接口 | 字段 | 频率 |
|---------|---------|------|------|------|
| CN_SHIBOR_ON | 隔夜Shibor | `shibor` | `on` | 日频 |
| CN_SHIBOR_1W | 1周Shibor | `shibor` | `1w` | 日频 |
| CN_SHIBOR_2W | 2周Shibor | `shibor` | `2w` | 日频 |
| CN_SHIBOR_1M | 1个月Shibor | `shibor` | `1m` | 日频 |
| CN_SHIBOR_3M | 3个月Shibor | `shibor` | `3m` | 日频 |
| CN_SHIBOR_6M | 6个月Shibor | `shibor` | `6m` | 日频 |
| CN_SHIBOR_9M | 9个月Shibor | `shibor` | `9m` | 日频 |
| CN_SHIBOR_1Y | 1年Shibor | `shibor` | `1y` | 日频 |
| CN_LPR_1Y | 1年期LPR | `shibor_lpr` | `lpr_1y` | 月频 |
| CN_LPR_5Y | 5年期LPR | `shibor_lpr` | `lpr_5y` | 月频 |
| CN_LIBOR_USD | 美元Libor | `libor` | `usd` | 日频 |
| CN_HIBOR_ON | 隔夜Hibor | `hibor` | `on` | 日频 |

#### 中国国债收益率（Tushare `yc_cb`）

| 指标代码 | 期限 | ts_code |
|---------|------|---------|
| CN_BOND_YIELD_3M | 3个月 | `3M` |
| CN_BOND_YIELD_6M | 6个月 | `6M` |
| CN_BOND_YIELD_1Y | 1年 | `1Y` |
| CN_BOND_YIELD_3Y | 3年 | `3Y` |
| CN_BOND_YIELD_5Y | 5年 | `5Y` |
| CN_BOND_YIELD_7Y | 7年 | `7Y` |
| CN_BOND_YIELD_10Y | 10年 | `10Y` |
| CN_BOND_YIELD_30Y | 30年 | `30Y` |

#### 美国利率（FRED）

| 指标代码 | 指标名称 | Series ID | 频率 |
|---------|---------|-----------|------|
| US_BOND_YIELD_1Y | 1年期国债收益率 | `DGS1` | 日频 |
| US_BOND_YIELD_2Y | 2年期国债收益率 | `DGS2` | 日频 |
| US_BOND_YIELD_5Y | 5年期国债收益率 | `DGS5` | 日频 |
| US_BOND_YIELD_10Y | 10年期国债收益率 | `DGS10` | 日频 |
| US_BOND_YIELD_30Y | 30年期国债收益率 | `DGS30` | 日频 |
| US_BOND_SPREAD_10Y2Y | 10Y-2Y利差 | `T10Y2Y` | 日频 |
| US_FEDFUNDS_M | 联邦基金利率(月) | `FEDFUNDS` | 月频 |
| US_FEDFUNDS_D | 联邦基金利率(日) | `DFF` | 日频 |

### 8.2 汇率数据（Tushare）

| 指标代码 | 货币对 | ts_code | 说明 |
|---------|--------|---------|------|
| FX_USDCNH | 美元/离岸人民币 | `USDCNH.FXCM` | 离岸人民币 |
| FX_EURUSD | 欧元/美元 | `EURUSD.FXCM` | 主要货币对 |
| FX_GBPUSD | 英镑/美元 | `GBPUSD.FXCM` | 主要货币对 |
| FX_USDJPY | 美元/日元 | `USDJPY.FXCM` | 主要货币对 |
| FX_AUDUSD | 澳元/美元 | `AUDUSD.FXCM` | 商品货币 |
| FX_USDCAD | 美元/加元 | `USDCAD.FXCM` | 商品货币 |

### 8.3 大宗商品数据

#### 能源（FRED）- ✅ 首期实施

| 指标代码 | 指标名称 | Series ID | 频率 |
|---------|---------|-----------|------|
| COMMOD_WTI | WTI 原油 | `DCOILWTICO` | 日频 |
| COMMOD_BRENT | 布伦特原油 | `DCOILBRENTEU` | 日频 |

#### 贵金属（FRED）- ✅ 首期实施

| 指标代码 | 指标名称 | Series ID | 频率 |
|---------|---------|-----------|------|
| COMMOD_GOLD | 伦敦金 | `GOLDAMGBD228NLBM` | 日频 |
| COMMOD_SILVER | 伦敦银 | `SLVPRUSD` | 日频 |

#### 有色金属（AKShare）- ⏳ 后续扩展

> **状态**: 暂不实施，需要引入 AKShare 依赖

| 指标代码 | 指标名称 | 代码 | 频率 |
|---------|---------|------|------|
| COMMOD_LME_CU | LME 铜 3M | `CAD` | 日频 |
| COMMOD_LME_AL | LME 铝 3M | `AHD` | 日频 |
| COMMOD_LME_ZN | LME 锌 3M | `ZSD` | 日频 |
| COMMOD_LME_NI | LME 镍 3M | `NID` | 日频 |

#### 农产品（AKShare）- ⏳ 后续扩展

> **状态**: 暂不实施，需要引入 AKShare 依赖

| 指标代码 | 指标名称 | 代码 | 频率 |
|---------|---------|------|------|
| COMMOD_CBOT_SOYBEAN | CBOT 大豆 | `ZS=F` | 日频 |
| COMMOD_CBOT_CORN | CBOT 玉米 | `ZC=F` | 日频 |
| COMMOD_CBOT_WHEAT | CBOT 小麦 | `ZW=F` | 日频 |

### 8.4 VIX 指数（FRED）- ✅ 首期实施

| 指标代码 | 指标名称 | Series ID | 频率 |
|---------|---------|-----------|------|
| VIX_30D | VIX 波动率指数（30天） | `VIXCLS` | 日频 |
| VIX_9D | VIX 9天波动率指数 | `VIX9D` | 日频 |

### 8.5 黄金/白银 ETF 持仓（Capital 域）- ⏳ 后续扩展

> **状态**: 暂不实施，需要实现新浪爬虫，归属 Capital 域

| 指标代码 | 指标名称 | 数据源 | 频率 |
|---------|---------|--------|------|
| ETF_GLD_HOLDINGS | GLD 黄金 ETF 持仓量 | 新浪爬取 | 日频 |
| ETF_SLV_HOLDINGS | SLV 白银 ETF 持仓量 | 新浪爬取 | 日频 |

---

## 9. 架构设计

### 9.1 存储模型

#### Market 域（利率/汇率/商品/VIX）

```python
# 利率/汇率/商品数据 Schema（Market 域）
RATE_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,      # 标的ID
    "trade_date": pl.Date,          # 交易日期
    "open": pl.Float64,             # 开盘价
    "high": pl.Float64,             # 最高价
    "low": pl.Float64,              # 最低价
    "close": pl.Float64,            # 收盘价
    # 利率数据通常没有成交量
}
```

#### Capital 域（ETF 持仓）

```python
# ETF 持仓数据 Schema（Capital 域）
ETF_HOLDINGS_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,      # 标的ID
    "trade_date": pl.Date,          # 交易日期
    "holdings": pl.Float64,         # 持仓量（吨）
    "change": pl.Float64,           # 持仓变化（吨）
}
```

### 9.2 标的分类

扩展 `AssetClass` 枚举：

```python
class AssetClass(StrEnum):
    """资产类型枚举"""
    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"
    FUTURE = "future"
    BOND = "bond"
    FUND = "fund"
    # 新增
    CURRENCY = "currency"      # 货币/汇率
    COMMODITY = "commodity"    # 商品
    RATE = "rate"              # 利率（Shibor、国债收益率等）
```

### 9.3 宏观相关性标签

```python
class MacroRelevance(StrEnum):
    """宏观相关性标签"""
    NONE = "none"
    INTEREST_RATE = "interest_rate"   # 利率相关
    INFLATION = "inflation"           # 通胀相关
    RISK_SENTIMENT = "risk_sentiment" # 风险情绪（VIX、黄金）
    CURRENCY = "currency"             # 汇率相关
```

### 9.4 目录结构

```
packages/data/src/ditto_data/
├── sources/
│   ├── tushare/
│   │   └── adapters/
│   │       ├── rate.py           # 新增：利率数据适配器
│   │       └── fx.py             # 新增：汇率数据适配器
│   ├── fred/
│   │   └── adapters/
│   │       ├── rate.py           # 新增：美国利率数据适配器
│   │       └── commodity.py      # 新增：大宗商品数据适配器
│   ├── akshare/
│   │   └── adapters/
│   │       └── commodity.py      # 新增：AKShare 外盘期货适配器
│   └── sina/
│       └── spiders/
│           └── etf_holdings.py   # 新增：ETF 持仓爬虫
├── stores/
│   ├── market/
│   │   ├── rate/                 # 新增：利率数据存储
│   │   ├── fx/                   # 新增：汇率数据存储
│   │   └── commodity/            # 新增：商品数据存储
│   └── capital/
│       └── etf_holdings/         # 新增：ETF 持仓存储
└── services/
    ├── market_service.py         # 扩展：支持利率/汇率/商品查询
    └── capital_service.py        # 扩展：支持 ETF 持仓查询
```

---

## 10. 实施优先级

### 首期实施（P0）- 仅使用现有数据源

#### Phase 1：基础设施

| 任务 | 说明 |
|------|------|
| 扩展 AssetClass 枚举 | 新增 CURRENCY、COMMODITY、RATE |
| 实现 MacroRelevance 标签 | 支持宏观相关性查询 |
| Market 域存储扩展 | 利率/汇率/商品存储 |

#### Phase 2：利率数据

| 任务 | 数据源 |
|------|--------|
| Tushare 利率适配器 | Tushare `shibor`, `shibor_lpr`, `libor`, `hibor` |
| Tushare 国债收益率适配器 | Tushare `yc_cb` |
| FRED 利率适配器 | FRED `DGS*`, `FEDFUNDS`, `DFF` |
| CLI 命令 | `ingest rate cn` / `ingest rate us` |

#### Phase 3：汇率数据

| 任务 | 数据源 |
|------|--------|
| Tushare 汇率适配器 | Tushare `fx_daily` |
| CLI 命令 | `ingest fx` |

#### Phase 4：大宗商品（能源/贵金属）

| 任务 | 数据源 |
|------|--------|
| FRED 大宗商品适配器 | FRED `DCOILWTICO`, `DCOILBRENTEU`, `GOLDAMGBD228NLBM`, `SLVPRUSD` |
| CLI 命令 | `ingest commodity energy` / `ingest commodity metals` |

#### Phase 5：VIX 指数

| 任务 | 数据源 |
|------|--------|
| FRED VIX 适配器 | FRED `VIXCLS`, `VIX9D` |
| CLI 命令 | `ingest vix` |

---

### 后续扩展（P1/P2）- 需要新增数据源

#### Phase 6：有色金属/农产品（P1）

| 任务 | 数据源 | 备注 |
|------|--------|------|
| 新增 AKShare 依赖 | `pip install akshare` | ⚠️ 需新增依赖 |
| AKShare 外盘期货适配器 | AKShare `futures_foreign_hist` | pandas→polars 转换 |
| CLI 命令 | `ingest commodity metals-lme` / `ingest commodity agri` | |

**涉及品种**：
- LME 铜（CAD）、铝（AHD）、锌（ZSD）、镍（NID）
- CBOT 大豆（ZS=F）、玉米（ZC=F）、小麦（ZW=F）

#### Phase 7：ETF 持仓（P2）

| 任务 | 数据源 | 备注 |
|------|--------|------|
| 新浪 ETF 持仓爬虫 | 新浪财经/金投网 | ⚠️ 需实现爬虫 |
| Capital 域存储 | - | 新增存储层 |
| CLI 命令 | `ingest capital etf-holdings` | |

**涉及品种**：
- GLD 黄金 ETF 持仓量
- SLV 白银 ETF 持仓量

---

## 11. 参考资料

### Tushare 文档
- [Shibor 接口](https://tushare.pro/document/2?doc_id=148)
- [LPR 接口](https://tushare.pro/document/2?doc_id=149)
- [中债收益率曲线](https://tushare.pro/document/2?doc_id=201)
- [外汇日线行情](https://tushare.pro/document/2?doc_id=179)

### FRED 文档
- [FRED API 文档](https://fred.stlouisfed.org/docs/api/fred/)
- [Series Observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- [DGS10 (10-Year Treasury)](https://fred.stlouisfed.org/series/DGS10)
- [VIXCLS (VIX Index)](https://fred.stlouisfed.org/series/VIXCLS)

### AKShare 文档
- [AKShare 官方文档](https://akshare.akfamily.xyz)
- [外盘期货接口](https://akshare.akfamily.xyz/data/futures/futures.html)

### 其他参考
- [World Gold Council](https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows) - 黄金 ETF 持仓权威数据
- [Trading Economics](https://tradingeconomics.com/forecast/commodity) - 商品数据与预测
- [中债收益率曲线官网](https://yield.chinabond.com.cn) - 官方权威数据
