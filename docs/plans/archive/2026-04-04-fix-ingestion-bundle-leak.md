# 修复 IngestionBundle 数据层泄漏

**日期**: 2026-04-04
**状态**: 待实施
**类型**: 架构清理

## Context

`IngestionBundle` 暴露 8 个 data service 具体类型（`MetadataService`, `MarketService` 等），导致 interfaces 层 12+ 个文件直接 `from ditto_data.services.*`。app 层 query facade 已完整覆盖所有只读场景，但 CLI query 命令和 Prefect flows 绕过 facade 直接使用 raw services。

方案分两步：
1. 创建 `QueryContext` 封装只读查询路径
2. 精简 `IngestionBundle` 只暴露 process 层类型

## Step 1: 创建 QueryContext + query context manager

**新建** `interfaces/src/ditto_interfaces/registry/contexts/query.py`

```python
@dataclass(frozen=True)
class QueryContext:
    """只读查询上下文 — 封装 app 层 query facades."""
    metadata: MetadataQueryFacade
    market: MarketQueryFacade
    capital: CapitalQueryFacade
    fundamental: FundamentalQueryFacade
    macro: MacroQueryFacade

@contextmanager
def create_query_context() -> Iterator[QueryContext, None, None]:
    container = make_app_container()
    try:
        # 从 DI 获取 services，构建 facades
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        ...
        yield QueryContext(
            metadata=MetadataQueryFacade(metadata_service=metadata_service),
            market=MarketQueryFacade(market_service=market_service),
            ...
        )
    finally:
        container.close()
```

> 这里 `create_query_context` 需要导入 data services —— 但仅在 registry/contexts/ 内部（Composition Root），不泄漏到其他 interfaces 模块。

## Step 2: 更新 CLI query 命令（5 个文件）

将 `create_cli_host() -> bundle.xxx_service -> Facade(...)` 改为 `create_query_context() -> context.xxx`

| 文件 | 变更 |
|------|------|
| `cli/commands/query/market.py` | `create_cli_host() -> bundle.market_service` → `create_query_context() -> ctx.market` |
| `cli/commands/query/capital.py` | 同上模式 → `ctx.capital` + `ctx.metadata` |
| `cli/commands/query/fundamental.py` | 同上 → `ctx.fundamental` + `ctx.metadata` |
| `cli/commands/query/macro.py` | 同上 → `ctx.macro` |
| `cli/commands/query/metadata.py` | 同上 → `ctx.metadata` |

## Step 3: 更新 flow consumers（3 个文件）

### daily.py
- `bundle.metadata_service.is_trading_day()` → `bundle.metadata_facade.is_trading_day()`
- 或者：在 IngestionBundle 上新增 `is_trading_day()` 委托方法

### backfill.py
- `BackfillManager(coordinator=bundle.coordinator, metadata_service=bundle.metadata_service, ...)` → 直接用 `bundle.backfill_manager`（已存在但未使用）
- `bundle.exchange_transformers.get(source)` → 在 IngestionBundle 新增 `resolve_ticker_transformer(source)` 委托方法
- `bundle.coordinator.ingest_by_instrument(...)` → 保留（coordinator 是 app 层类型）

### repair.py
- `RetryManager(coordinator=..., ingestion_log_service=...)` → 在 IngestionBundle 新增 `retry_manager` 属性
- `BackfillManager(coordinator=..., metadata_service=..., ingestion_log_service=...)` → 直接用 `bundle.backfill_manager`

## Step 4: 精简 IngestionBundle

**修改** `registry/contexts/bundle.py`:

```python
@dataclass(frozen=True)
class IngestionBundle:
    """摄取上下文 — 只暴露 app 层类型."""
    coordinator: IngestionCoordinator          # app 层
    backfill_manager: BackfillManager          # app 层
    retry_manager: RetryManager                # app 层
    exchange_transformers: ExchangeTransformers  # 保留（ ticker 解析，process 使用）

    # query facades（替代 raw services）
    metadata_facade: MetadataQueryFacade
    is_trading_day = delegate  # 便捷方法
```

移除: `metadata_service`, `market_service`, `fundamental_service`, `capital_service`, `macro_service`, `source_service`, `ingestion_log_service` 字段。

**修改** `registry/contexts/ingestion.py`:
- `create_ingestion_bundle()` 内部获取 data services → 构建 coordinator + backfill_manager + retry_manager + facades
- 不再暴露 raw services

## Step 5: 更新测试

**修改** `tests/integration/flows/test_helpers_integration.py`:
- 断言从 `bundle.metadata_service` 改为 `bundle.metadata_facade` 或 `bundle.coordinator`

**修改** `tests/unit/jobs/flows/test_backfill_unit.py`:
- mock 从 `bundle.metadata_service` 改为 `bundle.backfill_manager`（直接用预构建对象）

**修改** `tests/unit/jobs/flows/test_daily_unit.py`:
- mock `bundle.is_trading_day` 替代 `bundle.metadata_service.is_trading_day`

## 关键文件清单

| 文件 | 操作 |
|------|------|
| `interfaces/src/ditto_interfaces/registry/contexts/query.py` | **新建** |
| `interfaces/src/ditto_interfaces/registry/contexts/bundle.py` | 修改 |
| `interfaces/src/ditto_interfaces/registry/contexts/ingestion.py` | 修改 |
| `interfaces/src/ditto_interfaces/registry/contexts/__init__.py` | 修改 |
| `interfaces/src/ditto_interfaces/cli/context.py` | 修改 |
| `interfaces/src/ditto_interfaces/cli/commands/query/*.py` (5 文件) | 修改 |
| `interfaces/src/ditto_interfaces/jobs/flows/daily.py` | 修改 |
| `interfaces/src/ditto_interfaces/jobs/flows/backfill.py` | 修改 |
| `interfaces/src/ditto_interfaces/jobs/flows/repair.py` | 修改 |
| `interfaces/tests/` 相关测试文件 | 修改 |

## 验证

```bash
pixi run -e dev check
pixi run -e dev arch-check
# interfaces src 中（除 registry/contexts/ingestion.py 外）不应有 ditto_data.services 引用
grep -rn "ditto_data\.services" interfaces/src/ --include="*.py" | grep -v registry/contexts/ingestion.py
```
