# Tushare 数据源

[Tushare](https://tushare.pro/) 是中国领先的财经数据接口社区，提供股票、基金、期货等金融数据。

本模块使用 **HTTP 直接调用** 方式接入 Tushare API，完全基于 `polars` 处理数据，符合 Ditto 项目技术栈规范。

---

## 快速开始

### 1. Token 配置

Tushare API 需要 Token 认证。支持三种配置方式（按优先级排序）：

#### 方式 1: Secrets.toml（推荐）

```toml
# ~/.ditto/secrets.toml
TUSHARE_TOKEN = "your_token_here"
```

#### 方式 2: Keyring

```bash
# 使用 keyring 存储
keyring set ditto tushare_token
```

#### 方式 3: 环境变量

```bash
export TUSHARE_TOKEN=your_token_here
```

### 2. 基本使用

```python
from ditto_datahub import DataHub

# 初始化 DataHub
hub = DataHub(data_root="data")

# 获取 Tushare 数据源
source = hub.sources.get("tushare")

# 获取交易日历
calendar = source.fetch_calendar("2024-01-01", "2024-01-31")

# 获取股票列表
stocks = source.fetch_stock_basic()

# 获取日线数据
daily = source.fetch_stock_daily("2024-01-02")

# 关闭连接
hub.close()
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
from ditto_datahub.sources.tushare.rate_limiter import (
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
from ditto_datahub.sources.base import (
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
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/

# 查看覆盖率
pixi run -e dev pytest --cov packages/datahub/src/ditto_datahub/sources/tushare/
```

### 集成测试（需要真实 Token）

```bash
# 运行端到端测试（需要 TUSHARE_TOKEN）
pixi run -e dev pytest packages/datahub/tests/integration/sources/tushare/test_end_to_end.py -m external
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
├── __init__.py              # 导出 TushareSource
├── client.py                # HTTP 客户端（httpx 封装）
├── source.py                # DataSource 实现（7 个 fetch 方法）
├── http_utils.py            # HTTP 工具（响应验证、错误映射）
├── rate_limiter.py          # 限流器
├── IMPLEMENTATION_SUMMARY.md # HTTP 重构实施总结
└── README.md                # 本文档
```

### 数据流

```
TushareSource.fetch_xxx()
    ↓
TushareClient.query() 限流 → HTTP 请求 → 响应验证
    ↓
http_utils.response_to_dataframe()  JSON → polars DataFrame
    ↓
source.py 转换逻辑  列重命名、类型转换、过滤
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

DataHub 支持多数据源，初始化时指定：

```python
source = hub.sources.get("akshare")  # 切换到 Akshare
```

---

## 参考资料

- [Tushare 官方文档](https://tushare.pro/)
- [HTTP 重构实施总结](./IMPLEMENTATION_SUMMARY.md)
- [重构计划](../../../../../docs/plans/2026-01-03-tushare-http-refactor.md)
