# Sources - 外部数据源适配层

**版本**: v0.6.0
**最后更新**: 2026-04-08
**状态**: 稳定

## 概要

统一的外部数据源接口，支持多数据源适配，提供从 Tushare、FRED、通达信等数据源获取市场数据的统一访问接口。所有数据源返回 `polars.DataFrame`，通过 `DataSource` 抽象基类统一行为契约。

## 目录结构

```
sources/
├── __init__.py                # 公共导出（DataSource、异常、标准化工具等）
├── base.py                    # DataSource 抽象基类 + 异常层级
├── source.py                  # DataSources 数据源注册/路由
├── source_schema.py           # 数据源 Schema 定义
├── exchange_transformers.py   # 交易所代码转换器
├── normalization.py           # 数据标准化（Currency/Exchange/InstrumentType）
├── schemas/                   # 数据源 Schema 定义
│   ├── capital_schemas.py     # 资本数据（估值/融资融券/质押）
│   ├── commodity_schemas.py   # 商品数据
│   ├── fx_schemas.py          # 外汇数据
│   ├── macro_schemas.py       # 宏观数据
│   ├── market_schemas.py      # 市场数据（ETF/股票/指数）
│   └── metadata_schemas.py    # 元数据（日历/工具/行业）
├── fred/                      # FRED 数据源（宏观/商品）
│   ├── __init__.py
│   ├── client.py              # FRED API 客户端
│   ├── fred_source.py         # DataSource 实现
│   ├── indicators.py          # 指标定义
│   └── adapters/              # 适配器
│       ├── base.py, commodity.py, macro.py
├── tdx/                       # 通达信数据源
│   ├── __init__.py
│   ├── reader.py              # 数据读取器
│   ├── source.py              # DataSource 实现
│   └── transformer.py         # 数据转换
└── tushare/                   # Tushare 数据源（详见 tushare/README.md）
    ├── __init__.py
    ├── client.py              # TushareClient HTTP 客户端
    ├── tushare_source.py      # DataSource 实现
    ├── transformer.py         # 数据转换工具类
    ├── adapters/              # 数据适配器（ETF/股票/宏观/资金等）
    ├── processors/            # 数据处理器（列映射/合并/转换/映射）
    └── utils/                 # 工具（HTTP/限流）
```

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    DataSource (抽象基类)                         │
│                                                                  │
│  元数据: fetch_calendar, fetch_etf_basic, fetch_stock_basic,     │
│          fetch_index_basic, fetch_sw_industry                    │
│  日线:   fetch_etf_daily, fetch_stock_daily, fetch_index_daily   │
│  复权:   fetch_adj_factor, fetch_fund_adj,                       │
│          fetch_adj_factor_by_ticker                              │
│  财务:   fetch_balance_sheet, fetch_income_statement,            │
│          fetch_cash_flow, fetch_dividend,                        │
│          fetch_valuation_metrics                                 │
│  状态:   fetch_stock_status, fetch_st_history                    │
│  信用:   fetch_margin_trading, fetch_pledge_ratio                │
│  宏观:   fetch_macro_indicators, fetch_corporate_actions         │
│  FX/商品: fetch_fx_daily, fetch_commodities, fetch_metal_daily   │
└─────────────────────────────────────────────────────────────────┘
                            △
            ┌───────────────┼───────────────┐
            △               △               △
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ TushareSource │  │  FredSource   │  │   TdxSource   │
│               │  │               │  │               │
│ adapters/     │  │ adapters/     │  │ reader.py     │
│ processors/   │  │   macro.py    │  │ transformer   │
│ utils/        │  │ commodity.py  │  │               │
│               │  │               │  │               │
│ - 限流+重试   │  │ - 宏观指标    │  │ - 本地文件    │
│ - HTTP 直连   │  │ - 商品价格    │  │ - 实时数据    │
└───────────────┘  └───────────────┘  └───────────────┘
```

### 设计模式

数据源实现采用 **adapters/processors** 分层模式：

- **adapters/**: 每个适配器负责一个数据域（如 stock、etf、macro），封装 API 调用和数据转换
- **processors/**: 通用数据处理管道（列映射、错误处理、数据合并、转换映射）
- **utils/**: 基础设施（HTTP 工具、限流器）

## DataSource 抽象方法

### 元数据类

| 方法 | 说明 | 返回 Schema |
|------|------|-------------|
| `fetch_calendar(start, end)` | 交易日历 | `trade_date, is_open` |
| `fetch_etf_basic()` | ETF 基础信息 | `source_ticker, ticker, name, exchange, list_date` |
| `fetch_stock_basic(source_ticker?)` | 股票基础信息 | `source_ticker, ticker, name, exchange, list_date, list_status` |
| `fetch_index_basic()` | 指数基础信息 | `source_ticker, ticker, name, exchange, list_date` |
| `fetch_sw_industry(level)` | 申万行业分类 | `source_ticker, industry_name, level` |

### 日线数据类（支持按日期批量 / 按代码+区间两种模式）

| 方法 | 说明 | 返回 Schema |
|------|------|-------------|
| `fetch_etf_daily(trade_date?)` | ETF 日线 | OHLCV + `pre_close, amount, pct_change` |
| `fetch_stock_daily(trade_date?)` | 股票日线 | OHLCV + `pre_close, amount, pct_change` |
| `fetch_index_daily(trade_date?)` | 指数日线 | OHLCV + `pre_close, amount, pct_change` |

### 复权因子类

| 方法 | 说明 | 返回 Schema |
|------|------|-------------|
| `fetch_adj_factor(trade_date)` | 股票复权因子（按日期） | `source_ticker, trade_date, adj_factor` |
| `fetch_adj_factor_by_ticker(ts_code, start, end)` | 股票复权因子（按代码） | `source_ticker, trade_date, adj_factor` |
| `fetch_fund_adj(trade_date?)` | ETF/基金复权因子 | `source_ticker, trade_date, adj_factor` |

### 财务数据类（支持按日期批量 / 按代码+区间两种模式）

| 方法 | 说明 |
|------|------|
| `fetch_balance_sheet(trade_date?)` | 资产负债表 |
| `fetch_income_statement(trade_date?)` | 利润表 |
| `fetch_cash_flow(trade_date?)` | 现金流量表 |
| `fetch_dividend(trade_date?)` | 分红数据 |
| `fetch_valuation_metrics(trade_date?)` | 估值指标 |

### 状态与信用类

| 方法 | 说明 |
|------|------|
| `fetch_stock_status(trade_date)` | 股票状态（停牌/ST） |
| `fetch_st_history(ts_code?, start?, end?)` | ST 变更历史 |
| `fetch_margin_trading(trade_date?)` | 融资融券数据 |
| `fetch_pledge_ratio(trade_date?)` | 质押比例 |

### 宏观与另类数据类

| 方法 | 说明 |
|------|------|
| `fetch_macro_indicators(trade_date)` | 宏观指标 |
| `fetch_corporate_actions(trade_date)` | 公司行为 |
| `fetch_fx_daily(ts_codes, start, end)` | 外汇日线 |
| `fetch_commodities(codes, start, end)` | 商品价格 |
| `fetch_metal_daily(codes, start, end)` | 贵金属价格 |

## 异常体系

```python
DataSourceError (基类)
├── SourceConfigurationError   # 配置错误（token 缺失、无效设置）
├── SourceAuthenticationError  # 认证失败（token 无效）
├── SourceRateLimitError       # API 限流
├── SourceFetchError           # 数据获取失败（网络、超时等）
└── SourceTransformationError  # 数据转换失败（schema 不匹配、类型转换）
```

## 数据标准化

`normalization.py` 提供跨数据源的数据标准化工具：

```python
from ditto_data.sources import (
    Currency,
    Exchange,
    InstrumentType,
    NormalizationConfig,
)
from ditto_data.sources import ExchangeTransformer, ExchangeTransformers
```

## 使用示例

### 直接调用 TushareSource

```python
from ditto_data.config import DataSourceSettings
from ditto_data.sources import TushareSource

settings = DataSourceSettings(tushare_token="your_token_here")
source = TushareSource(settings=settings)

# 获取交易日历
calendar = source.fetch_calendar("2024-01-01", "2024-01-31")

# 获取 ETF 日线
etf_daily = source.fetch_etf_daily("2024-01-02")

# 获取股票日线（按代码+区间）
stock_daily = source.fetch_stock_daily(
    source_ticker="000001.SZ",
    start_date="2024-01-01",
    end_date="2024-01-31",
)
```

### Token 配置

推荐在 `config/{env}/data_source.env` 中配置，并由上层应用注入 `DataSourceSettings`。

```env
# config/{env}/data_source.env
TUSHARE_TOKEN=YOUR_TOKEN
```

## 注意事项

1. **Token 安全**: 仅通过 `DataSourceSettings` 注入，禁止硬编码或隐式读取环境
2. **API 限流**: Tushare 免费账号 200 次/分钟，付费账号更高
3. **数据格式**: 所有 fetch 方法返回 `polars.DataFrame`
4. **字段命名**: 使用 Ditto 标准（`source_ticker`, `trade_date`, `volume`, `pct_change`）
5. **日期格式**: 统一使用 YYYY-MM-DD 格式
6. **日志规范**: 使用 `ditto_infra.foundation.observability`，包含 `event` 字段
7. **查询模式**: 日线/财务/复权等数据支持按日期批量查询和按代码+区间查询两种模式

## 测试

```bash
# 运行所有 sources 测试
pixi run -e dev pytest packages/data/tests/unit/sources/

# 运行 Tushare 测试
pixi run -e dev pytest packages/data/tests/unit/sources/tushare/ -v

# 运行 FRED 测试
pixi run -e dev pytest packages/data/tests/unit/sources/fred/ -v

# 运行 TDX 测试
pixi run -e dev pytest packages/data/tests/unit/sources/tdx/ -v
```

## 相关文档

- Tushare 详细文档：[`tushare/README.md`](./tushare/README.md)
- 数据层设计文档：`docs/design/02_data_design.md`
- 数据层架构规范：[`packages/data/CLAUDE.md`](../../CLAUDE.md)
