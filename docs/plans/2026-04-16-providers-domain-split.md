# Task 4.5: `providers.py` 按领域拆分

> **状态**: 已完成 (2026-04-16)

## Context

`providers.py` 当前 759 行，包含 4 个 Provider 类。其中 `AppQueryProvider` 独占 222 行（22 个 `@provide` 方法），是最大的单一类。按领域拆分可提升可维护性，使每个 Provider 职责更聚焦。

## 拆分方案

将 `AppQueryProvider` 的 22 个方法按领域拆为 3 个 Provider：

### 新文件 1: `providers_market.py` — 市场数据查询（12 方法）

| 方法 | 产出类型 |
|------|----------|
| `forward_return_service` | `ForwardReturnService` |
| `derived_query_facade` | `DerivedQueryFacade` |
| `market_query_facade` | `MarketQueryFacade` |
| `source_query_facade` | `SourceQueryFacade` |
| `research_dataset_facade` | `ResearchDatasetFacade` |
| `metadata_query_facade` | `MetadataQueryFacade` |
| `capital_query_facade` | `CapitalQueryFacade` |
| `fundamental_query_facade` | `FundamentalQueryFacade` |
| `macro_query_facade` | `MacroQueryFacade` |
| `fx_query_facade` | `FXQueryFacade` |
| `commodity_query_facade` | `CommodityQueryFacade` |
| `ingestion_status_query_facade` | `IngestionStatusQueryFacade` |

### 新文件 2: `providers_strategy.py` — 策略/回测查询（7 方法）

| 方法 | 产出类型 |
|------|----------|
| `backtest_trade_query_facade` | `BacktestTradeQueryFacade` |
| `backtest_artifact_reader` | `BacktestArtifactReader` |
| `backtest_query_facade` | `BacktestQueryFacade` |
| `run_read_model` | `RunReadModel` |
| `strategy_query_facade` | `StrategyQueryFacade` |
| `lineage_query_facade` | `LineageQueryFacade` |
| `comparison_query_facade` | `ComparisonQueryFacade` |

### 新文件 3: `providers_portfolio.py` — 组合/交易查询（3 方法）

| 方法 | 产出类型 |
|------|----------|
| `trade_query_facade` | `TradeQueryFacade` |
| `portfolio_actual_query_facade` | `PortfolioActualQueryFacade` |
| `signal_query_facade` | `SignalQueryFacade` |

> 注：`universe_query_facade` 归入 market（Universe 是元数据域概念）；`lineage_query_facade` 归入 strategy（运行血统属于策略域）。

### 修改文件: `providers.py` — 保留 3 个 Provider + 聚合

- 保留 `AppCommandProvider`（不变）
- 保留 `AppProcessProvider`（不变）
- 保留 `AppBuilderFactory`（不变）
- 保留 `get_trading_calendar_range()`（不变）
- **删除** `AppQueryProvider` 类
- **更新** `get_app_providers()` 返回 6 个 Provider
- **更新** `__all__` 导出 3 个新类名

### 修改文件: 消费者更新

| 文件 | 变更 |
|------|------|
| [test_providers_unit.py](packages/app/tests/unit/test_providers_unit.py) | `AppQueryProvider` → 3 个新 Provider；`get_app_providers()` 返回 6 个 |
| [test_research_dataset_facade_unit.py](interfaces/tests/unit/registry/test_research_dataset_facade_unit.py:61) | `AppQueryProvider` → `AppMarketQueryProvider` |
| [test_derived_provider_unit.py](interfaces/tests/registry/test_derived_provider_unit.py:137) | 注释更新（`AppQueryProvider` → `AppMarketQueryProvider`） |
| [packages/app/CLAUDE.md](packages/app/CLAUDE.md) | Provider 表更新 |

### 不需修改

- `container.py` — 只用 `get_app_providers()`，自动适配
- `README.md` — 只引用 `get_app_providers()`

## 关键约束

1. **R8 互斥规则**：新 Provider 文件仅 import `ditto_app.query.*`，不触及 command/process/builders
2. **无循环依赖**：新文件 import 方向为 `query.*` ← `providers_*.py` ← `providers.py`
3. **Dishka 兼容**：多个 Provider 注册同类型不会冲突（每个 `@provide` 的返回类型在全局唯一）

## 实施步骤

### Step 1: RED — 更新测试

1. 修改 `test_providers_unit.py`：
   - import 改为 `AppMarketQueryProvider, AppStrategyQueryProvider, AppPortfolioQueryProvider`
   - `test_get_app_providers_returns_*`: 断言 6 个 Provider
   - `test_app_query_provider_methods` → 拆为 3 个测试（market/strategy/portfolio）
   - 集成测试中 `get_app_providers()` 仍用聚合入口，无需改

2. 修改 `test_research_dataset_facade_unit.py:61`：
   - `from ditto_app.providers import AppQueryProvider` → `from ditto_app.providers_market import AppMarketQueryProvider`
   - 使用处 `AppQueryProvider()` → `AppMarketQueryProvider()`

3. 运行测试确认 RED（import 失败）

### Step 2: GREEN — 创建新文件 + 修改 providers.py

1. 创建 `providers_market.py`（~130 行）
2. 创建 `providers_strategy.py`（~100 行）
3. 创建 `providers_portfolio.py`（~50 行）
4. 修改 `providers.py`：
   - 删除 `AppQueryProvider` 类（lines 301-527）
   - 删除 query 层 import（lines 118-140）
   - 更新 `__all__`
   - 更新 `get_app_providers()` 返回 6 个 Provider
   - 更新模块 docstring

### Step 3: SIMPLIFIER + REFACTOR

- 检查 import 是否精简
- 确认各文件 docstring 一致
- 更新 `packages/app/CLAUDE.md` Provider 表

### Step 4: 验证

```bash
pixi run -e dev check          # lint + type + test --fast
pixi run -e dev arch-check     # 确认无新违规
```

## 预期结果

| 文件 | 修改前行数 | 修改后行数 |
|------|-----------|-----------|
| `providers.py` | 759 | ~400 |
| `providers_market.py` | — | ~130 |
| `providers_strategy.py` | — | ~100 |
| `providers_portfolio.py` | — | ~50 |
