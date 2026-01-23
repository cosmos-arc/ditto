# Sources - 外部数据源适配层

**版本**: v0.5.0
**最后更新**: 2026-01-23
**状态**: ✅ 稳定

## 概要

统一的外部数据源接口，支持多数据源适配，提供从 Tushare、AkShare 等数据源获取市场数据的统一访问接口。

## 核心功能

提供统一的外部数据源访问接口，支持从 Tushare、AkShare 等数据源获取市场数据，并转换为 Ditto 标准 Schema。

## 二、架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     DataSource (抽象基类)                     │
│                                                              │
│  - fetch_calendar()    - fetch_etf_basic()                 │
│  - fetch_etf_daily()    - fetch_stock_basic()              │
│  - fetch_stock_daily()  - fetch_adj_factor()               │
│  - fetch_fund_adj()                                         │
└─────────────────────────────────────────────────────────────┘
                          △
          ┌───────────────┴───────────────┐
          △                               △
┌─────────────────────┐      ┌─────────────────────┐
│   TushareSource     │      │  AkShareSource      │
│                     │      │  (Sprint-02)        │
│  - 7个fetch方法      │      │                     │
│  - 限流+重试         │      │  - 降级备选          │
└─────────────────────┘      └─────────────────────┘
```

## 三、数据源接口

### 3.1 DataSource 抽象方法

| 方法 | 说明 | 返回 Schema |
|------|------|-------------|
| `fetch_calendar(start, end)` | 交易日历 | `trade_date, is_open` |
| `fetch_etf_basic()` | ETF 基础信息 | `src_code, symbol, name, exchange, list_date` |
| `fetch_etf_daily(date)` | ETF 日线 | OHLCV + `pre_close, amount, pct_change` |
| `fetch_stock_basic()` | 股票基础信息 | `src_code, symbol, name, exchange, list_date` |
| `fetch_stock_daily(date)` | 股票日线 | OHLCV + `pre_close, amount, pct_change` |
| `fetch_adj_factor(date)` | 股票复权因子 | `src_code, trade_date, adj_factor` |
| `fetch_fund_adj(date)` | ETF/基金复权因子 | `src_code, trade_date, adj_factor` |

### 3.2 Tushare 适配器

**TushareClient** - API 客户端
- Token 安全管理（keyring → secrets.toml → env var）
- 限流：200 次/分钟
- 重试：指数退避（1min, 5min, 15min）
- 错误处理：认证错误、限流错误、网络错误

**TushareSource** - 数据适配器
- 实现 7 个 fetch 方法
- pandas → polars 转换
- 字段映射：`ts_code→src_code`, `vol→volume`, `pct_chg→pct_change`
- 交易所映射：`SSE→SSE`, `SZSE→SZSE`

## 四、异常体系

```python
DataSourceError (基类)
├── SourceConfigurationError  # 配置错误（token缺失）
├── SourceAuthenticationError  # 认证失败
├── SourceFetchError           # 数据获取失败
└── SourceRateLimitError       # API 限流
```

## 五、使用示例

### 5.1 直接调用 TushareSource

```python
from ditto_datahub.sources.tushare import TushareSource

source = TushareSource()

# 获取交易日历
calendar = source.fetch_calendar("2024-01-01", "2024-01-31")

# 获取ETF日线
etf_daily = source.fetch_etf_daily("2024-01-02")

# 获取股票日线
stock_daily = source.fetch_stock_daily("2024-01-02")

# 获取复权因子
adj_factor = source.fetch_adj_factor("2024-01-02")
```

### 5.2 通过 DataHub 访问

```python
from ditto_datahub import DataHub

hub = DataHub(data_root="data")

# 通过 DataSources 访问
etf_basic = hub.sources.tushare.fetch_etf_basic()

# 或使用工厂函数
source = hub.sources.get("tushare")
stock_daily = source.fetch_stock_daily("2024-01-02")
```

### 5.3 Token 配置

**方式 1 - keyring（推荐）**:
```bash
python -c "import keyring; keyring.set_password('ditto', 'tushare', 'YOUR_TOKEN')"
```

**方式 2 - secrets.toml（备选）**:
```toml
# ~/.ditto/secrets.toml
[tushare]
token = "YOUR_TOKEN"
```

**方式 3 - 环境变量（仅用于开发）**:
```bash
export TUSHARE_TOKEN="YOUR_TOKEN"
```

## 六、注意事项

1. **Token 安全**: 生产环境必须使用 keyring，禁止硬编码 token
2. **API 限流**: Tushare 免费账号 200 次/分钟，付费账号更高
3. **数据格式**: 所有 fetch 方法返回 polars.DataFrame
4. **字段命名**: 使用 Ditto 标准（`src_code`, `trade_date`, `volume`, `pct_change`）
5. **日期格式**: 统一使用 YYYY-MM-DD 格式
6. **日志规范**: 使用 `ditto_foundation.logger`，包含 `event` 字段

## 七、测试

```bash
# 运行所有测试
pytest packages/datahub/tests/unit/sources/

# 运行 TushareSource 测试
pytest packages/datahub/tests/unit/sources/tushare/test_source.py -v

# 查看覆盖率
pytest --cov=packages/datahub/src/ditto_datahub/sources/tushare/source.py
```

**测试覆盖**:
- Calendar: 3 个测试
- ETF: 5 个测试
- Stock: 9 个测试
- AdjFactor: 6 个测试
- 总计: 49/49 通过，TushareSource 覆盖率 95.95%

## 八、相关文档

- 设计文档：`docs/design/02_data_design.md`
- Server 层设计：`docs/plans/2025-12-27-server-layer-design.md`
- Sprint 文档：`docs/sprints/sprint-01-data-layer.md`
