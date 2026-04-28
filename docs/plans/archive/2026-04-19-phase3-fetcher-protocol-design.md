# Phase 3: DataSource Fetcher Protocol 设计

## Context

基于全架构审计发现：DataSource ABC 有 25 个抽象方法（God Interface，违反 ISP），FredSource 23 个 NotImplementedError。Phase 2 已完成 Port Protocol 替换和 Reader/Writer 参数化，Phase 3 聚焦 DataSource 层。

## 决策记录

| # | 决策项 | 选择 | 理由 |
|---|--------|------|------|
| 1 | Protocol 拆分粒度 | 5 个域级 Protocol（按 Adapter 域聚合） | 匹配现有代码结构，消除 God Interface，LEAN 验证 |
| 2 | Query 对象 vs 原签名 | 保持原方法签名 | 消费端零改动，扩展性等价 |
| 3 | SourceMixin | 不引入（YAGNI） | 重试/限流已在 Client 层实现 |
| 4 | SourceRegistry | 现在引入 | 为未来多 Source 插件化预留 |
| 5 | DataSources 保留 | 保留为向后兼容包装 | 内部用 SourceRegistry |
| 6 | FullDataSource | 不引入（显式参数） | 符合 ISP，消费者只声明需要的 Protocol |

## 设计

### 1. 5 个域级 Protocol

文件：`packages/data/src/ditto_data/sources/protocols.py`

| Protocol | 方法数 | 覆盖的 fetch 方法 |
|----------|--------|-------------------|
| `MetadataFetcher` | 5 | `fetch_stock_basic`, `fetch_etf_basic`, `fetch_index_basic`, `fetch_calendar`, `fetch_sw_industry` |
| `MarketFetcher` | 7 | `fetch_stock_daily`, `fetch_etf_daily`, `fetch_index_daily`, `fetch_adj_factor`, `fetch_adj_factor_by_ticker`, `fetch_fund_adj`, `fetch_stock_status` |
| `FundamentalFetcher` | 5 | `fetch_balance_sheet`, `fetch_income_statement`, `fetch_cash_flow`, `fetch_dividend`, `fetch_corporate_actions` |
| `CapitalFetcher` | 3 | `fetch_valuation_metrics`, `fetch_margin_trading`, `fetch_pledge_ratio` |
| `MacroFetcher` | 4 | `fetch_macro_indicators`, `fetch_fx_daily`, `fetch_commodities`, `fetch_metal_daily` |

### 2. DataSource ABC 删除

- `base.py` 仅保留异常 re-export（`DataSourceError` 等已在 `errors.py` 有权威定义）
- `TushareSource` 不再继承 ABC，通过结构化子类型满足 Protocol
- `FredSource` 大幅简化 — 仅实现 `MacroFetcher` 中的 2 个真实方法（`fetch_macro_indicators`, `fetch_commodities`），删除 23 个 NotImplementedError

### 3. SourceRegistry

文件：`packages/data/src/ditto_data/sources/registry.py`

```python
class SourceRegistry:
    def register(self, name: str, protocol: type[T], source: T) -> None: ...
    def get(self, name: str, protocol: type[T]) -> T: ...
    def get_all(self, protocol: type[T]) -> list[T]: ...
```

### 4. DataSources 保留

`DataSources` 保留为向后兼容包装，内部委托 `SourceRegistry`：

```python
class DataSources:
    def __init__(self, registry: SourceRegistry) -> None: ...
    def get(self, name: str | Source) -> object: ...  # 返回满足所有 Protocol 的源
```

### 5. 消费端改动

- `IngestionCoordinator` — 接收 5 个独立 Protocol 参数（显式声明依赖）
- `fetch_handlers.py` — 参数类型从 `DataSource` 改为对应 Protocol
- `SourceService` — 类型从 `DataSource` 改为具体 Protocol
- 测试 mock — `MagicMock()` 替换为满足 Protocol 的 mock

## 预计改动

~30 文件（新增 3，修改 ~20，删除 0）
