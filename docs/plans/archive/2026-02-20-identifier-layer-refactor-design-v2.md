# 标识符层重构设计 v2

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 重构摄入入口的标识符设计，修复当前实现的架构问题，建立清晰的命名规范和扩展模式。

---

## 1. 问题诊断

### 1.1 当前实现的问题

| 问题 | 描述 | 影响 |
|------|------|------|
| CLI 结构混乱 | 独立的 `ticker` 命令组破坏了域分类结构 | 用户体验不一致 |
| 命名不规范 | `ingest_by_ticker` 混用了"标识符"和"摄取模式"概念 | 代码可读性差 |
| 功能重复 | `ticker_resolver.py` 与 `MetadataService.resolve_source_ticker()` 功能重复 | 维护成本高 |
| Protocol 冗余 | `IngestionDataSource` 与 `DataSource` 基类重复 | 无实际价值 |
| 位置不当 | `DATASET_ASSET_CLASS_MAP` 在 port 层定义 | 应该在 datahub 层 |
| 扩展性不足 | 只有 `stock_daily` 支持单标的摄取 | 其他数据集无法使用 |

### 1.2 设计原则

1. **命名一致性**：`by_instrument` 表示"按标的"的摄取模式
2. **职责单一**：标识符解析由 `MetadataService` 统一负责
3. **位置正确**：资产类型枚举和数据集映射在 datahub/models 层
4. **渐进扩展**：先建立架构模式，再逐步扩展各数据集

---

## 2. 标识符体系（保留）

### 2.1 层次定义

| 层级 | 名称 | 示例 | 说明 |
|------|------|------|------|
| 用户层 | `ticker` | "000001" | 裸代码，用户最常用 |
| 用户层 | `standard_ticker` | "000001.XSHE" | Ditto 标准格式 |
| 用户层 | `instrument_id` | 1000001 | 内部 ID，最精确 |
| 转换后 | `source_ticker` | "000001.SZ" | 数据源特有格式 |

### 2.2 转换规则

```
用户输入（三选一）         转换层              数据源
ticker ─────────────┐
standard_ticker ────┼──► MetadataService.resolve_source_ticker ──► source_ticker
instrument_id ──────┘
```

**优先级**: `instrument_id` > `standard_ticker` > `ticker`

---

## 3. CLI 命令结构调整

### 3.1 现有结构（删除）

```bash
# 独立的 ticker 命令组 - 删除
pixi run ingest ticker stock -t 000001 -s 2024-01-01 -e 2024-01-31
pixi run ingest ticker etf -t 510300 -s 2024-01-01 -e 2024-01-31
```

### 3.2 新结构（合并到域命令）

```bash
# 市场行情域
pixi run ingest market stock 2024-01-15                    # 按日期批量（现有）
pixi run ingest market stock --ticker 000001 \
    --start 2024-01-01 --end 2024-01-31                    # 按标的+时间段（新增）
pixi run ingest market etf --instrument-id 1001001 \
    --start 2024-01-01 --end 2024-01-31                    # 使用 instrument_id

# 基本面域
pixi run ingest fundamental balance_sheet 2024-01-15       # 按日期批量（现有）
pixi run ingest fundamental balance_sheet --ticker 000001 \
    --start 2024-01-01 --end 2024-06-30                    # 按标的+时间段（新增）
```

### 3.3 参数设计

**标识符参数（三选一）**：
- `--ticker, -t`：裸代码（如 000001）
- `--standard-ticker`：Ditto 标准格式（如 000001.XSHE）
- `--instrument-id, -i`：内部 ID

**时间参数**：
- 按日期模式：`date` 位置参数（如 2024-01-15）
- 按标的模式：`--start/-s` 和 `--end/-e` 必须同时指定

**互斥规则**：
- 指定了 `date` → 按日期批量模式
- 指定了 `--ticker`/`--standard-ticker`/`--instrument-id` 之一 + `--start`/`--end` → 按标的模式

### 3.4 文件变更

| 文件 | 操作 |
|------|------|
| `apps/port/.../cli/commands/ingest/ticker.py` | **删除** |
| `apps/port/.../cli/commands/ingest/__init__.py` | 移除 ticker_app 注册 |
| `apps/port/.../cli/commands/ingest/market.py` | 增加 `--ticker` 等参数 |
| `apps/port/.../cli/commands/ingest/fundamental.py` | 增加 `--ticker` 等参数 |
| `apps/port/.../cli/commands/ingest/capital.py` | 增加 `--ticker` 等参数 |

---

## 4. 命名规范统一

### 4.1 需要修改的命名

| 类型 | 当前命名 | 修改为 | 位置 |
|------|---------|--------|------|
| 方法 | `ingest_by_ticker()` | `ingest_by_instrument()` | `executor.py` |
| Flow | `backfill_single_ticker_flow` | `backfill_single_instrument_flow` | `backfill.py` |
| Flow | `backfill_multiple_tickers_flow` | `backfill_multiple_instruments_flow` | `backfill.py` |
| 类 | `TickerBackfillConfig` | `InstrumentBackfillConfig` | `backfill.py` |
| 类 | `TickerBackfillResult` | `InstrumentBackfillResult` | `backfill.py` |
| 测试文件 | `test_coordinator_ticker_unit.py` | `test_coordinator_instrument_unit.py` | tests/ |
| 测试文件 | `test_ticker_resolver_unit.py` | 删除 | tests/ |

### 4.2 保留不变的命名（数据字段）

| 命名 | 含义 | 示例 |
|------|------|------|
| `ticker` | 裸代码 | "000001" |
| `source_ticker` | 数据源代码 | "000001.SZ" |
| `standard_ticker` | Ditto 标准格式 | "000001.XSHE" |

---

## 5. 模块重构

### 5.1 删除 `ticker_resolver.py`

**当前内容**：
- `InstrumentIngestParams` - 摄取参数数据类
- `resolve_source_ticker()` - 标识符解析函数
- `AmbiguousTickerError` - 歧义异常
- `NotFoundError` - 未找到异常
- `find_by_ticker()` - 查找函数

**处理方式**：

| 内容 | 处理 | 新位置 |
|------|------|--------|
| `InstrumentIngestParams` | 移动 | `ditto_port/models/ingestion.py`（新建） |
| `resolve_source_ticker()` | **删除** | 使用 `MetadataService.resolve_source_ticker()` |
| `AmbiguousTickerError` | **删除** | 已在 `datahub/errors.py` 定义 |
| `NotFoundError` | **删除** | 已在 `datahub/errors.py` 定义（`IdentifierNotFoundError`） |
| `find_by_ticker()` | **删除** | 功能由 `MetadataService` 提供 |

### 5.2 删除 `IngestionDataSource` Protocol

**理由**：`DataSource` 基类（`datahub/sources/base.py`）已经定义了所有 `fetch_*` 方法，`IngestionDataSource` 完全冗余。

**处理**：
- 删除 `apps/port/.../services/ingestion/protocols.py`
- Coordinator 直接依赖 `DataSource` 类型

### 5.3 新建 `ditto_port/models/ingestion.py`

```python
"""摄入相关数据模型."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentIngestParams:
    """
    按标的摄取的参数.

    标识符三选一，优先级: instrument_id > standard_ticker > ticker
    """

    # 标识符（三选一）
    instrument_id: int | None = None
    standard_ticker: str | None = None  # Ditto 标准格式，如 "000001.XSHE"
    ticker: str | None = None  # 裸代码，如 "000001"

    # 时间范围
    start_date: str = ""  # YYYY-MM-DD
    end_date: str = ""  # YYYY-MM-DD
```

---

## 6. 资产类型枚举重构

### 6.1 新建 `datahub/models/asset_class.py`

```python
"""资产类型枚举."""

from enum import StrEnum


class AssetClass(StrEnum):
    """资产类型枚举."""

    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"
    FUTURE = "future"
    BOND = "bond"
    FUND = "fund"
```

### 6.2 修改 `datahub/models/dataset.py`

```python
"""数据集枚举."""

from enum import StrEnum

from ditto_datahub.models.asset_class import AssetClass


class Dataset(StrEnum):
    """数据集枚举."""

    # Metadata
    CALENDAR = "calendar"
    STOCK_BASIC = "stock_basic"
    ETF_BASIC = "etf_basic"
    INDEX_BASIC = "index_basic"

    # Market
    STOCK_DAILY = "stock_daily"
    ETF_DAILY = "etf_daily"
    INDEX_DAILY = "index_daily"
    ADJ_FACTOR = "adj_factor"
    FUND_ADJ = "fund_adj"
    STOCK_STATUS = "stock_status"
    STOCK_LIMIT = "stock_limit"

    # Fundamental
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"
    DIVIDEND = "dividend"
    VALUATION_METRICS = "valuation_metrics"

    # Capital
    MARGIN_TRADING = "margin_trading"
    PLEDGE_RATIO = "pledge_ratio"

    # Macro
    MACRO_INDICATORS = "macro_indicators"
    FUTURES_POSITION = "futures_position"
    CORPORATE_ACTIONS = "corporate_actions"

    @property
    def asset_class(self) -> AssetClass | None:
        """
        返回该数据集关联的资产类型.

        Returns:
            AssetClass 或 None（对于无资产关联的数据集，如 calendar）
        """
        # Stock 数据集
        if self in (
            Dataset.STOCK_DAILY,
            Dataset.ADJ_FACTOR,
            Dataset.STOCK_STATUS,
            Dataset.STOCK_LIMIT,
            Dataset.VALUATION_METRICS,
            Dataset.BALANCE_SHEET,
            Dataset.INCOME_STATEMENT,
            Dataset.CASH_FLOW,
            Dataset.DIVIDEND,
            Dataset.MARGIN_TRADING,
            Dataset.PLEDGE_RATIO,
        ):
            return AssetClass.STOCK

        # ETF 数据集
        if self in (Dataset.ETF_DAILY, Dataset.FUND_ADJ):
            return AssetClass.ETF

        # Index 数据集
        if self == Dataset.INDEX_DAILY:
            return AssetClass.INDEX

        # 无资产关联
        return None

    def supports_instrument_ingestion(self) -> bool:
        """是否支持按标的摄取."""
        return self.asset_class is not None
```

### 6.3 删除 `dataset_mapping.py`

处理方式：

| 内容 | 处理 |
|------|------|
| `DATASET_ASSET_CLASS_MAP` | 删除，使用 `Dataset.asset_class` |
| `infer_asset_class()` | 删除，使用 `Dataset(asset_class).asset_class` |
| `source_ticker_to_standard_ticker()` | 移动到 `datahub/models/exchange.py` |

---

## 7. DataSource 扩展模式

### 7.1 扩展原则

为 `DataSource` 基类中的 `fetch_*` 方法增加单标的摄取能力，遵循以下模式：

```python
def fetch_xxx(
    self,
    # 按日期模式参数
    trade_date: str | None = None,
    # 按标的模式参数
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    获取 xxx 数据.

    支持两种查询模式:
    - 按日期: 指定 trade_date
    - 按标的+时间段: 指定 source_ticker + start_date + end_date
    """
    # 参数校验
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥")

    if trade_date:
        return self._fetch_xxx_by_date(trade_date)

    if source_ticker and start_date and end_date:
        return self._fetch_xxx_by_instrument(source_ticker, start_date, end_date)

    raise ValueError("必须指定 trade_date 或 (source_ticker + start_date + end_date)")
```

### 7.2 扩展优先级

**Phase 1（当前）**：
- `stock_daily` ✅ 已支持
- `etf_daily`
- `index_daily`

**Phase 2**：
- `adj_factor`
- `fund_adj`
- `valuation_metrics`

**Phase 3**：
- `balance_sheet`（使用 ann_date）
- `income_statement`
- `cash_flow`
- `dividend`

**Phase 4**：
- `margin_trading`
- `pledge_ratio`

### 7.3 Coordinator 层扩展

```python
def _fetch_by_dataset(
    self,
    dataset_enum: Dataset,
    source_ticker: str,
    params: InstrumentIngestParams,
) -> pl.DataFrame:
    """根据数据集类型调用对应的 fetch 方法."""
    # 使用字典映射
    handlers: dict[Dataset, Callable[[], pl.DataFrame]] = {
        Dataset.STOCK_DAILY: lambda: self._source.fetch_stock_daily(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.ETF_DAILY: lambda: self._source.fetch_etf_daily(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        Dataset.INDEX_DAILY: lambda: self._source.fetch_index_daily(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        ),
        # ... 逐步扩展
    }

    if dataset_enum not in handlers:
        raise ValueError(f"不支持按标的摄取的数据集: {dataset_enum.value}")

    return handlers[dataset_enum]()
```

---

## 8. 文件变更汇总

### 8.1 删除文件

| 文件 | 原因 |
|------|------|
| `apps/port/.../cli/commands/ingest/ticker.py` | 合并到域命令 |
| `apps/port/.../services/ingestion/ticker_resolver.py` | 功能重复 |
| `apps/port/.../services/ingestion/protocols.py` | Protocol 冗余 |
| `apps/port/.../services/ingestion/dataset_mapping.py` | 迁移到 datahub |
| `apps/port/tests/.../test_ticker_resolver_unit.py` | 对应模块删除 |

### 8.2 新建文件

| 文件 | 内容 |
|------|------|
| `packages/datahub/.../models/asset_class.py` | `AssetClass` 枚举 |
| `packages/datahub/.../models/exchange.py` | exchange 转换函数 |
| `apps/port/.../models/ingestion.py` | `InstrumentIngestParams` |

### 8.3 修改文件

| 文件 | 修改内容 |
|------|----------|
| `packages/datahub/.../models/dataset.py` | 增加 `asset_class` 属性 |
| `packages/datahub/.../sources/base.py` | 扩展 fetch 方法签名 |
| `apps/port/.../cli/commands/ingest/__init__.py` | 移除 ticker_app |
| `apps/port/.../cli/commands/ingest/market.py` | 增加单标的参数 |
| `apps/port/.../cli/commands/ingest/fundamental.py` | 增加单标的参数 |
| `apps/port/.../cli/executor.py` | 重命名 `ingest_by_ticker` → `ingest_by_instrument` |
| `apps/port/.../services/ingestion/coordinator.py` | 移除 ticker_resolver 依赖，扩展 `_fetch_by_dataset` |
| `apps/port/.../jobs/flows/backfill.py` | 重命名 flow 和类 |

---

## 9. 数据流

```
┌─────────────────────────────────────────────────────────────────┐
│  CLI 命令                                                        │
│  pixi run ingest market stock --ticker 000001 -s ... -e ...     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  CLI Command (market.py)                                        │
│  解析参数 → 构造 InstrumentIngestParams                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Executor.ingest_by_instrument()                                │
│  调用 Coordinator.ingest_by_instrument()                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Coordinator.ingest_by_instrument()                             │
│  1. 获取 dataset.asset_class                                    │
│  2. 调用 MetadataService.resolve_source_ticker()                │
│  3. 调用 _fetch_by_dataset()                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  DataSource.fetch_xxx(source_ticker, start_date, end_date)      │
│  获取数据源数据                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. 验收标准

- [ ] `ticker.py` 命令文件已删除
- [ ] `ticker_resolver.py` 已删除，`InstrumentIngestParams` 已迁移
- [ ] `IngestionDataSource` Protocol 已删除
- [ ] `AssetClass` 枚举在 `datahub/models` 中定义
- [ ] `Dataset.asset_class` 属性可用
- [ ] `dataset_mapping.py` 已删除
- [ ] `ingest_by_ticker` 重命名为 `ingest_by_instrument`
- [ ] 域命令（market/fundamental/capital）支持 `--ticker` 等参数
- [ ] 所有测试通过
- [ ] 类型检查通过
