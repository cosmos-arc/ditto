# Tushare 数据源

[Tushare](https://tushare.pro/) 是中国领先的财经数据接口社区，提供股票、基金、期货等金融数据。

本模块使用 **HTTP 直接调用** 方式接入 Tushare API，完全基于 `polars` 处理数据，符合 Ditto 项目技术栈规范。

---

## 快速开始

### 1. Token 配置

Tushare Token 通过上层配置注入，推荐在 `config/{env}/data_source.env` 中配置，并由 Interfaces 层加载后构造 `DataSourceSettings`。

```env
# config/{env}/data_source.env
TUSHARE_TOKEN=your_token_here
```

如果在应用外部直接使用，可显式构造配置：

```python
from ditto_data.config import DataSourceSettings

settings = DataSourceSettings(tushare_token="your_token_here")
```

### 2. 基本使用

```python
from ditto_data.config import DataSourceSettings
from ditto_data.sources import TushareSource

# 通过 DI 注入的 Services 获取数据源（推荐）
# source: TushareSource = container.get(TushareSource)

# 或显式构造配置
settings = DataSourceSettings(tushare_token="your_token_here")
source = TushareSource(settings=settings)

# 获取交易日历
calendar = source.fetch_calendar("2024-01-01", "2024-01-31")

# 获取股票列表
stocks = source.fetch_stock_basic()

# 获取日线数据
daily = source.fetch_stock_daily("2024-01-02")
```

---

## 支持的数据集

| 数据集 | API 方法 | 说明 | 更新频率 |
|--------|----------|------|----------|
| calendar | `fetch_calendar()` | 交易日历 | T0（盘中） |
| stock_basic | `fetch_stock_basic()` | 股票列表 | T0（盘中） |
| etf_basic | `fetch_etf_basic()` | ETF 列表 | T0（盘中） |
| stock_daily | `fetch_stock_daily()` | 股票日线 | T1（盘后） |
| etf_daily | `fetch_etf_daily()` | ETF 日线 | T1（盘后） |
| adj_factor | `fetch_adj_factor()` | 股票复权因子 | T1（盘后） |
| fund_adj | `fetch_fund_adj()` | 基金复权因子 | T1（盘后） |

---

## HTTP API 规范

### 请求格式

```json
POST http://api.tushare.pro
Content-Type: application/json

{
  "api_name": "daily",
  "token": "your_token",
  "params": {
    "ts_code": "000001.SZ",
    "trade_date": "20240102"
  },
  "fields": "ts_code,trade_date,open,high,low,close,vol,amount"
}
```

### 响应格式

```json
{
  "code": 0,
  "msg": null,
  "data": {
    "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"],
    "items": [
      ["000001.SZ", "20240102", 10.5, 10.8, 10.4, 10.7, 1234567.89, 1234567890.12]
    ]
  }
}
```

### 错误码

| 错误码 | 说明 | 处理方式 |
|--------|------|----------|
| 0 | 成功 | - |
| 2002 | 没有权限 | 抛出 `SourceAuthenticationError` |
| 40101 | Token 格式错误 | 抛出 `SourceAuthenticationError` |
| 429 | 请求过于频繁 | 抛出 `SourceRateLimitError` |
| 其他 | 业务错误 | 抛出 `SourceFetchError` |

---

## 限流配置

### 默认限流策略

Tushare API 限流规则（普通用户）：

| 维度 | 限制 | 说明 |
|------|------|------|
| 每分钟 | 200 次 | 适用于所有 API |
| 每天总积分 | 20,000 | 不同 API 消耗不同积分 |

### 限流器配置

本模块使用 `TushareRateLimiter` 实现限流控制：

```python
from ditto_data.sources.tushare.utils.rate_limiter import (
    TushareRateLimiter,
    TushareRateLimitConfig,
)

# 自定义配置
config = TushareRateLimitConfig(
    requests_per_minute=200,  # 每分钟请求数
    burst_size=10,            # 突发容量
)

limiter = TushareRateLimiter(config)

# 使用限流器
limiter.wait_if_needed()  # 如需限流会自动等待
```

### API 分组限流

为避免突发请求，同一 API 的连续请求会自动加入限流组：

```python
# client.py 实现
self._limiters: dict[str, TushareRateLimiter] = {}
```

---

## 重试机制

### 重试策略

使用 `tenacity` 实现指数退避重试：

| 参数 | 值 | 说明 |
|------|------|------|
| 最大重试次数 | 3 | 仅可重试错误 |
| 退避时间 | 1-10 秒 | 指数增长 |
| 可重试错误 | 网络错误、5xx | 认证错误不重试 |

### 重试示例

```python
# 网络错误会自动重试
# 5xx 服务器错误会自动重试
# 4xx 客户端错误不重试
# 认证错误不重试
```

---

## 错误处理

### 错误类型

```python
from ditto_data.sources.base import (
    SourceAuthenticationError,  # 认证失败（Token 无效）
    SourceRateLimitError,       # 限流（请求过于频繁）
    SourceFetchError,           # 其他获取错误（网络、超时等）
)

try:
    data = source.fetch_stock_daily("2024-01-02")
except SourceAuthenticationError:
    # 检查 Token 配置
    pass
except SourceRateLimitError:
    # 等待后重试
    pass
except SourceFetchError:
    # 检查网络连接
    pass
```

---

## 测试

### 单元测试

```bash
# 运行所有单元测试
pixi run -e dev pytest packages/data/tests/unit/sources/tushare/

# 查看覆盖率
pixi run -e dev pytest --cov packages/data/src/ditto_data/sources/tushare/
```

### 集成测试（需要真实 Token）

```bash
# 运行端到端测试（需要 TUSHARE_TOKEN）
pixi run -e dev pytest packages/data/tests/integration/sources/tushare/test_end_to_end.py -m external
```

---

## 性能说明

| 指标 | 值 |
|------|------|
| 单次请求延迟 | ~280ms |
| 并发支持 | 串行（限流保护） |
| 数据处理 | polars（内存高效） |

---

## 架构说明

### 模块结构

```
tushare/
├── __init__.py              # 导出 StockTushareAdapter, TushareClient, TushareExchangeTransformer
├── client.py                # TushareClient HTTP 客户端（httpx 封装）
├── tushare_source.py        # DataSource 实现（fetch 方法）
├── transformer.py           # 数据转换工具类
├── adapters/                # 数据适配器
│   ├── base.py              # 适配器基类
│   ├── bond_yield.py        # 债券收益率
│   ├── calendar.py          # 交易日历
│   ├── capital.py           # 资本数据（融资融券/质押）
│   ├── etf.py               # ETF 数据
│   ├── fundamental.py       # 基本面（财报/分红/估值）
│   ├── fx.py                # 外汇数据
│   ├── index.py             # 指数数据
│   ├── industry.py          # 行业分类
│   ├── macro.py             # 宏观指标
│   ├── metal.py             # 贵金属数据
│   └── stock.py             # 股票数据
├── processors/              # 数据处理器
│   ├── column_mapping.py    # 列映射配置
│   ├── error_handler.py     # 错误处理
│   ├── merger.py            # 数据合并
│   ├── transformer.py       # 数据转换
│   └── mappings/            # 列映射定义
│       ├── basic.py         # 基础数据映射
│       ├── capital.py       # 资本数据映射
│       ├── common.py        # 通用映射
│       └── macro.py         # 宏观数据映射
├── utils/                   # 工具
│   ├── http_utils.py        # HTTP 工具（响应验证、错误映射）
│   └── rate_limiter.py      # 限流器
└── README.md                # 本文档
```

### 数据转换工具 (transformer.py)

`transformer.py` 提供统一的数据转换逻辑，消除重复代码：

```python
from ditto_data.sources.tushare.transformer import (
    TushareDataTransformer,
    DAILY_OHLCV_MAPPING,
)

# 使用 transformer 统一转换 OHLCV 数据
result = TushareDataTransformer.transform_daily_ohlcv(
    df=response,
    dataset_name="etf_daily",
    mapping=DAILY_OHLCV_MAPPING,
)
```

**核心组件**:
- `ColumnMapping`: 列映射配置（frozen dataclass）
- `TushareDataTransformer`: 数据转换工具类
- `DAILY_OHLCV_MAPPING`: OHLCV 数据的通用配置

### 数据流

```
TushareSource.fetch_xxx()
    ↓
adapters/xxx  数据适配器（API 调用 + 字段映射）
    ↓
TushareClient.query()  限流 → HTTP 请求 → 响应验证
    ↓
utils/http_utils.response_to_dataframe()  JSON → polars DataFrame
    ↓
processors/  列映射、数据转换、合并
    ↓
返回 polars DataFrame
```

---

## 常见问题

### Q1: Token 如何获取？

访问 [Tushare 官网](https://tushare.pro/)，注册登录后在用户中心获取。

### Q2: 限流太慢怎么办？

1. 升级 Tushare 会员等级获取更高额度
2. 使用批量请求（后续优化）
3. 本地缓存基础数据

### Q3: 为什么不使用 SDK？

1. SDK 依赖 pandas（不符合项目规范）
2. HTTP 调用更透明，便于监控
3. 减少第三方依赖风险

### Q4: 如何切换到其他数据源？

Ditto 支持多数据源（Tushare、FRED、通达信），通过 DI 注入不同的 Source 实现：

```python
# 通过 DI 容器获取不同的数据源
from ditto_data.sources import TushareSource
from ditto_data.sources.fred import FredSource
from ditto_data.sources.tdx import TdxSource

source = container.get(TushareSource)
source = container.get(FredSource)
source = container.get(TdxSource)
```

---

## 参考资料

- [Tushare 官方文档](https://tushare.pro/)
- [Sources 层文档](../README.md)
- 数据层设计文档：`docs/design/02_data_design.md`
- 数据层架构规范：[`packages/data/CLAUDE.md`](../../../CLAUDE.md)
