# 按股票维度摄取能力实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增按股票+时间段摄取数据的能力，支持 CLI 命令、REST API 和 Prefect 任务三种触发方式。

**Architecture:** 扩展现有 DataSource 接口支持按股票查询参数，在 Coordinator 层新增 `ingest_by_ticker()` 方法，复用现有 ParquetStore 合并写入逻辑。

**Tech Stack:** Python 3.12+, polars, typer, fastapi, prefect

**设计文档:** [2026-02-18-ticker-ingestion-design.md](./2026-02-18-ticker-ingestion-design.md)

---

## Phase 1: 命名规范修复 [S]

### Task 1.1: 修复测试 fixtures 中的 `symbol` 使用

**Files:**
- Modify: `apps/port/tests/conftest.py`
- Test: 运行现有测试验证无回归

**Step 1: 检查现有 fixtures 中的 symbol 使用**

```bash
grep -n "symbol" apps/port/tests/conftest.py
```

**Step 2: 将 `symbol` 重命名为 `ticker` 或 `source_ticker`**

根据设计文档 4.2 节，将所有 `symbol` 改为 `ticker`（裸代码）或 `source_ticker`（带后缀）。

**Step 3: 验证测试通过**

Run: `pixi run -e dev test apps/port/tests/`
Expected: All tests pass

**Step 4: Commit**

```bash
git add apps/port/tests/conftest.py
git commit -m "refactor(test): rename symbol to ticker/source_ticker"
```

---

## Phase 2: DataSource 接口扩展 [M]

### Task 2.1: 新增标识符解析异常类

**Files:**
- Create: `apps/port/src/ditto_port/services/ingestion/ticker_resolver.py`
- Test: `apps/port/tests/unit/services/ingestion/test_ticker_resolver_unit.py`

**Step 1: 编写失败测试 - AmbiguousTickerError**

```python
# apps/port/tests/unit/services/ingestion/test_ticker_resolver_unit.py
import pytest
from ditto_port.services.ingestion.ticker_resolver import AmbiguousTickerError


def test_ambiguous_ticker_error_contains_matches():
    """AmbiguousTickerError 应包含所有匹配项."""
    matches = [
        {"source_ticker": "000001.SZ", "instrument_id": 1000001, "name": "平安银行"},
        {"source_ticker": "000001.SH", "instrument_id": 1000002, "name": "上证指数"},
    ]
    error = AmbiguousTickerError(ticker="000001", matches=matches)

    assert error.ticker == "000001"
    assert len(error.matches) == 2
    assert "000001.SZ" in str(error)
```

**Step 2: 运行测试验证失败**

Run: `pixi run -e dev test apps/port/tests/unit/services/ingestion/test_ticker_resolver_unit.py`
Expected: FAIL - Module not found

**Step 3: 实现异常类和解析函数**

```python
# apps/port/src/ditto_port/services/ingestion/ticker_resolver.py
"""标识符解析模块."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ditto_data.stores.metadata.instrument.instrument_reader import (
        InstrumentReader,
    )


class AmbiguousTickerError(Exception):
    """Ticker 不唯一异常."""

    def __init__(self, ticker: str, matches: list[dict]) -> None:
        self.ticker = ticker
        self.matches = matches
        match_list = "\n  - ".join(
            f"{m['source_ticker']} (ID: {m['instrument_id']}, 名称: {m['name']})"
            for m in matches
        )
        super().__init__(
            f"Ticker '{ticker}' 存在歧义，匹配到 {len(matches)} 个标的：\n  - {match_list}"
        )


class NotFoundError(Exception):
    """标识符未找到异常."""

    def __init__(self, identifier: str, identifier_type: str) -> None:
        super().__init__(f"未找到 {identifier_type}: '{identifier}'")


@dataclass
class TickerIngestParams:
    """按股票摄取的参数."""

    source_ticker: str
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD


def resolve_source_ticker(
    ticker: str | None,
    source_ticker: str | None,
    instrument_id: int | None,
    instrument_reader: InstrumentReader,
) -> str:
    """
    将任意标识符解析为 source_ticker.

    优先级: instrument_id > source_ticker > ticker

    Args:
        ticker: 裸代码（如 "000001"）
        source_ticker: 数据源代码（如 "000001.SZ"）
        instrument_id: 内部 ID（如 1000001）
        instrument_reader: 证券主数据查询接口

    Returns:
        source_ticker 字符串

    Raises:
        ValueError: 未提供任何标识符
        AmbiguousTickerError: ticker 不唯一
        NotFoundError: 标识符无效

    """
    if instrument_id is not None:
        result = instrument_reader.get_source_ticker(instrument_id, source="tushare")
        if result is None:
            raise NotFoundError(str(instrument_id), "instrument_id")
        return result

    if source_ticker is not None:
        return source_ticker

    if ticker is not None:
        matches = find_by_ticker(ticker, instrument_reader)
        if len(matches) == 0:
            raise NotFoundError(ticker, "ticker")
        elif len(matches) == 1:
            return matches[0]["source_ticker"]
        else:
            raise AmbiguousTickerError(ticker=ticker, matches=matches)

    raise ValueError("必须指定 ticker / source_ticker / instrument_id 之一")


def find_by_ticker(
    ticker: str, instrument_reader: InstrumentReader
) -> list[dict]:
    """
    根据裸代码查找所有匹配的证券.

    Args:
        ticker: 裸代码
        instrument_reader: 证券主数据查询接口

    Returns:
        匹配列表，每项包含 source_ticker, instrument_id, name

    """
    df = instrument_reader.find_securities(is_active=True)
    if df.is_empty():
        return []

    # 过滤 ticker 匹配的记录
    matches_df = df.filter(pl.col("ticker") == ticker)

    result = []
    for row in matches_df.to_dicts():
        result.append({
            "source_ticker": row.get("source_ticker", ""),
            "instrument_id": row.get("instrument_id", 0),
            "name": row.get("name", ""),
        })
    return result
```

**Step 4: 添加缺失的 import**

```python
import polars as pl
```

**Step 5: 运行测试验证通过**

Run: `pixi run -e dev test apps/port/tests/unit/services/ingestion/test_ticker_resolver_unit.py`
Expected: PASS

**Step 6: Commit**

```bash
git add apps/port/src/ditto_port/services/ingestion/ticker_resolver.py
git add apps/port/tests/unit/services/ingestion/test_ticker_resolver_unit.py
git commit -m "feat(port): add ticker resolver with AmbiguousTickerError"
```

---

### Task 2.2: 扩展 StockTushareAdapter 支持按股票查询

**Files:**
- Modify: `packages/data/src/ditto_data/sources/tushare/adapters/stock.py`
- Test: `packages/data/tests/unit/sources/tushare/adapters/test_stock_adapter_unit.py`

**Step 1: 编写失败测试 - 按股票查询 stock_daily**

```python
# packages/data/tests/unit/sources/tushare/adapters/test_stock_adapter_unit.py
import pytest
from unittest.mock import MagicMock, patch


def test_fetch_stock_daily_by_ticker_uses_ts_code():
    """按股票查询应使用 ts_code 参数."""
    from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

    mock_client = MagicMock()
    mock_client.query.return_value = pl.DataFrame({
        "ts_code": ["000001.SZ"],
        "trade_date": ["20240115"],
        "open": [10.0],
        "high": [11.0],
        "low": [9.5],
        "close": [10.5],
        "pre_close": [10.0],
        "vol": [1000000],
        "amount": [10500000],
        "pct_chg": [5.0],
    })

    adapter = StockTushareAdapter(_client=mock_client)

    # 按股票+时间段查询
    result = adapter.fetch_stock_daily_by_ticker(
        source_ticker="000001.SZ",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    # 验证调用了正确的 API
    mock_client.query.assert_called_once()
    call_kwargs = mock_client.query.call_args.kwargs
    assert call_kwargs["api_name"] == "daily"
    assert call_kwargs["ts_code"] == "000001.SZ"
    assert call_kwargs["start_date"] == "20240101"
    assert call_kwargs["end_date"] == "20240131"


def test_fetch_stock_daily_mutual_exclusive_params():
    """trade_date 和 source_ticker 互斥."""
    from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

    mock_client = MagicMock()
    adapter = StockTushareAdapter(_client=mock_client)

    with pytest.raises(ValueError, match="互斥"):
        adapter.fetch_stock_daily(
            trade_date="2024-01-15",
            source_ticker="000001.SZ",
        )
```

**Step 2: 运行测试验证失败**

Run: `pixi run -e dev test packages/data/tests/unit/sources/tushare/adapters/test_stock_adapter_unit.py`
Expected: FAIL - AttributeError

**Step 3: 实现按股票查询方法**

```python
# packages/data/src/ditto_data/sources/tushare/adapters/stock.py
# 在 StockTushareAdapter 类中添加:

def fetch_stock_daily_by_ticker(
    self,
    source_ticker: str,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """
    按股票+时间段获取日线数据.

    Args:
        source_ticker: 源代码 (e.g., "000001.SZ")
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        DataFrame with daily OHLCV schema

    Raises:
        SourceFetchError: If fetch fails.

    """
    logger.info(
        "Fetching Tushare stock daily by ticker",
        event="tushare_stock_daily_ticker_fetch_start",
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )

    with tushare_fetch_error_handler("stock_daily", "daily"):
        ts_start = start_date.replace("-", "")
        ts_end = end_date.replace("-", "")
        response = self._client.query(
            api_name="daily",
            ts_code=source_ticker,
            start_date=ts_start,
            end_date=ts_end,
            fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
        )

        return TushareDataTransformer.transform_daily_ohlcv(
            response,
            "stock_daily",
        )
```

**Step 4: 运行测试验证通过**

Run: `pixi run -e dev test packages/data/tests/unit/sources/tushare/adapters/test_stock_adapter_unit.py`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/data/src/ditto_data/sources/tushare/adapters/stock.py
git add packages/data/tests/unit/sources/tushare/adapters/test_stock_adapter_unit.py
git commit -m "feat(datahub): add fetch_stock_daily_by_ticker to StockTushareAdapter"
```

---

### Task 2.3: 扩展 TushareSource 门面类

**Files:**
- Modify: `packages/data/src/ditto_data/sources/tushare/tushare_source.py`

**Step 1: 添加按股票查询的委托方法**

```python
# packages/data/src/ditto_data/sources/tushare/tushare_source.py
# 添加以下方法:

def fetch_stock_daily_by_ticker(
    self,
    source_ticker: str,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """
    按股票+时间段获取股票日线数据.

    Args:
        source_ticker: 源代码 (e.g., "000001.SZ")
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        DataFrame with daily OHLCV schema

    """
    return self._stock.fetch_stock_daily_by_ticker(source_ticker, start_date, end_date)
```

**Step 2: 对其他数据集重复相同模式**

根据设计文档，需要为以下数据集添加按股票查询:
- `fetch_etf_daily_by_ticker`
- `fetch_adj_factor_by_ticker`
- `fetch_valuation_metrics_by_ticker`
- `fetch_balance_sheet_by_ticker` (使用 ann_date)
- `fetch_income_statement_by_ticker` (使用 ann_date)
- `fetch_cash_flow_by_ticker` (使用 ann_date)
- `fetch_dividend_by_ticker` (使用 ann_date)

**Step 3: Commit**

```bash
git add packages/data/src/ditto_data/sources/tushare/tushare_source.py
git commit -m "feat(datahub): add ticker-based fetch methods to TushareSource"
```

---

## Phase 3: Coordinator 扩展 [L]

### Task 3.1: 新增 `ingest_by_ticker()` 方法

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- Test: `apps/port/tests/unit/services/ingestion/test_coordinator_unit.py`

**Step 1: 编写失败测试**

```python
# apps/port/tests/unit/services/ingestion/test_coordinator_unit.py
def test_ingest_by_ticker_fetches_and_maps_data(mocker):
    """ingest_by_ticker 应获取数据并映射 instrument_id."""
    # ... 测试实现
```

**Step 2: 在 Coordinator 中添加方法**

```python
# apps/port/src/ditto_port/services/ingestion/coordinator.py
# 添加 import
from ditto_port.services.ingestion.ticker_resolver import (
    TickerIngestParams,
    resolve_source_ticker,
)

# IngestionCoordinator 类中添加:
def ingest_by_ticker(
    self,
    dataset: str,
    params: TickerIngestParams,
    force: bool = False,
) -> IngestionResult:
    """
    按股票+时间段摄取数据.

    Args:
        dataset: 数据集名称
        params: 摄取参数 (source_ticker, start_date, end_date)
        force: 是否强制覆盖已有数据

    Returns:
        IngestionResult: 摄取结果

    """
    logger.info(
        "开始按股票摄取数据",
        event="ingest_by_ticker_start",
        dataset=dataset,
        source_ticker=params.source_ticker,
        start_date=params.start_date,
        end_date=params.end_date,
    )

    # 1. 获取数据
    df = self._fetch_data_by_ticker(dataset, params)

    if df.is_empty():
        return IngestionResult(
            dataset=dataset,
            trade_date=f"{params.start_date}~{params.end_date}",
            status="skipped",
            message="无数据",
        )

    # 2. 映射 source_ticker → instrument_id
    instrument_id = self._get_instrument_id(params.source_ticker)
    df = df.with_columns(pl.lit(instrument_id).alias("instrument_id"))

    # 3. 按年份分组写入
    on_duplicate = OnDuplicate.KEEP_LAST if force else OnDuplicate.ERROR
    write_result = self._write_by_ticker(dataset, df, on_duplicate)

    # 4. 返回结果
    return self._result_handler.handle_success(
        dataset,
        f"{params.start_date}~{params.end_date}",
        df,
        write_result,
    )

def _fetch_data_by_ticker(
    self, dataset: str, params: TickerIngestParams
) -> pl.DataFrame:
    """根据数据集类型调用对应的按股票查询方法."""
    # 实现根据 dataset 调用对应的 fetch_xxx_by_ticker 方法
    ...

def _get_instrument_id(self, source_ticker: str) -> int:
    """获取 source_ticker 对应的 instrument_id."""
    # 使用 InstrumentReader 解析
    ...

def _write_by_ticker(
    self, dataset: str, df: pl.DataFrame, on_duplicate: OnDuplicate
) -> WriteResult:
    """按年份分组写入数据."""
    # 实现按年份分组写入逻辑
    ...
```

**Step 3: Commit**

```bash
git add apps/port/src/ditto_port/services/ingestion/coordinator.py
git add apps/port/tests/unit/services/ingestion/test_coordinator_unit.py
git commit -m "feat(port): add ingest_by_ticker to IngestionCoordinator"
```

---

## Phase 4: CLI 命令 [M]

### Task 4.1: 新增 `pixi run ingest ticker` 命令

**Files:**
- Create: `apps/port/src/ditto_port/cli/commands/ingest/ticker.py`
- Modify: `apps/port/src/ditto_port/cli/commands/ingest/__init__.py`

**Step 1: 创建 ticker 命令模块**

```python
# apps/port/src/ditto_port/cli/commands/ingest/ticker.py
"""按股票维度摄取命令."""

from datetime import datetime
from typing import Optional

import typer

from ditto_port.cli.context import create_executor
from ditto_port.cli.utils.output import print_ingestion_result
from ditto_port.cli.utils.validation import validate_date_format

app = typer.Typer(help="按股票摄取数据")


@app.command("ticker")
def ingest_ticker(
    ctx: typer.Context,
    dataset: str = typer.Option(..., "--dataset", "-d", help="数据集名称"),
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    ticker: Optional[str] = typer.Option(None, "--ticker", "-t", help="裸代码 (如 000001)"),
    source_ticker: Optional[str] = typer.Option(None, "--source-ticker", help="数据源代码 (如 000001.SZ)"),
    instrument_id: Optional[int] = typer.Option(None, "--instrument-id", "-i", help="内部 ID"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览，不写入"),
    force: bool = typer.Option(False, "--force", "-f", help="强制覆盖已有数据"),
) -> None:
    """
    按股票+时间段摄取数据.

    示例:
        pixi run ingest ticker --ticker 000001 --dataset stock_daily --start 2024-01-01 --end 2024-01-31
        pixi run ingest ticker --source-ticker 000001.SZ --dataset valuation_metrics --start 2024-01-01 --end 2024-06-30

    """
    validate_date_format(start)
    validate_date_format(end)

    if not any([ticker, source_ticker, instrument_id]):
        typer.echo("❌ 错误: 必须指定 --ticker, --source-ticker 或 --instrument-id 之一")
        raise typer.Exit(1)

    with create_executor() as executor:
        if dry_run:
            # 预览模式
            result = executor.preview_by_ticker(
                dataset=dataset,
                ticker=ticker,
                source_ticker=source_ticker,
                instrument_id=instrument_id,
                start_date=start,
                end_date=end,
            )
            typer.echo(f"预览: 将获取 {result.get('row_count', 0)} 条记录")
        else:
            result = executor.ingest_by_ticker(
                dataset=dataset,
                ticker=ticker,
                source_ticker=source_ticker,
                instrument_id=instrument_id,
                start_date=start,
                end_date=end,
                force=force,
            )
            print_ingestion_result(result, ctx.obj["verbose"])
```

**Step 2: 注册到 ingest 命令组**

```python
# apps/port/src/ditto_port/cli/commands/ingest/__init__.py
# 添加:
from ditto_port.cli.commands.ingest.ticker import app as ticker_app

# 在 app 中注册
app.add_typer(ticker_app, name="ticker")
```

**Step 3: 测试 CLI 命令**

Run: `pixi run ingest ticker --help`
Expected: 显示帮助信息

**Step 4: Commit**

```bash
git add apps/port/src/ditto_port/cli/commands/ingest/ticker.py
git add apps/port/src/ditto_port/cli/commands/ingest/__init__.py
git commit -m "feat(cli): add 'ingest ticker' command"
```

---

## Phase 5: REST API [M]

### Task 5.1: 新增 `/api/source/{dataset}` 端点

**Files:**
- Create: `apps/port/src/ditto_port/api/routes/source.py`
- Modify: `apps/port/src/ditto_port/api/routes/__init__.py`

**Step 1: 创建 source API 路由**

```python
# apps/port/src/ditto_port/api/routes/source.py
"""Source 数据查询 API 路由."""

import asyncio
import time
from datetime import date
from typing import Annotated, Optional

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query

from ditto_data.sources.base import DataSource
from ditto_port.models.common import APIResponse

router = APIRouter(prefix="/source", tags=["source"])


class SourceDataResponse(APIResponse[list[dict]]):
    """Source API 响应模型."""

    dataset: str
    source_ticker: str
    start_date: date
    end_date: date
    row_count: int
    query_time_ms: float
    source: str = "tushare"


@router.get("/{dataset}", response_model=SourceDataResponse)
@inject
async def get_source_data(
    dataset: str,
    source_ticker: Optional[str] = Query(None, description="数据源代码 (如 000001.SZ)"),
    ticker: Optional[str] = Query(None, description="裸代码 (如 000001)"),
    instrument_id: Optional[int] = Query(None, description="内部 ID"),
    start_date: date = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="结束日期 (YYYY-MM-DD)"),
    source: Annotated[DataSource, FromComponent()] = None,
) -> SourceDataResponse:
    """
    查询 Source 层数据（经过 Adapter 转换）.

    用途: 验证 ETL 逻辑、调试适配器、数据探索

    """
    start_time = time.monotonic()

    # 解析标识符
    resolved_ticker = source_ticker or ticker or str(instrument_id)

    # 调用 Source 获取数据
    df = await asyncio.to_thread(
        _fetch_source_data,
        source,
        dataset,
        resolved_ticker,
        start_date.isoformat(),
        end_date.isoformat(),
    )

    query_time_ms = (time.monotonic() - start_time) * 1000

    return SourceDataResponse(
        dataset=dataset,
        source_ticker=resolved_ticker,
        start_date=start_date,
        end_date=end_date,
        records=df.to_dicts() if not df.is_empty() else [],
        row_count=len(df),
        query_time_ms=query_time_ms,
        source="tushare",
    )


def _fetch_source_data(
    source: DataSource,
    dataset: str,
    source_ticker: str,
    start_date: str,
    end_date: str,
):
    """同步获取 Source 数据."""
    # 根据 dataset 调用对应方法
    ...
```

**Step 2: 注册路由**

```python
# apps/port/src/ditto_port/api/routes/__init__.py
from ditto_port.api.routes import source

__all__.append("source")
```

**Step 3: Commit**

```bash
git add apps/port/src/ditto_port/api/routes/source.py
git add apps/port/src/ditto_port/api/routes/__init__.py
git commit -m "feat(api): add /api/source/{dataset} endpoint"
```

---

## Phase 6: Prefect 任务 [M]

### Task 6.1: 新增 backfill flow 模块

**Files:**
- Create: `apps/port/src/ditto_port/flows/backfill.py`

**Step 1: 创建 Prefect flow**

```python
# apps/port/src/ditto_port/flows/backfill.py
"""按股票回填 Prefect Flows."""

from datetime import date

from prefect import flow, task

from ditto_data.models import Dataset
from ditto_port.services.ingestion.coordinator import IngestionCoordinator
from ditto_port.services.ingestion.ticker_resolver import TickerIngestParams


@task
def ingest_single_ticker(
    coordinator: IngestionCoordinator,
    source_ticker: str,
    dataset: str,
    start_date: str,
    end_date: str,
) -> dict:
    """单只股票摄取任务."""
    params = TickerIngestParams(
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )
    result = coordinator.ingest_by_ticker(Dataset(dataset), params)
    return result.model_dump()


@flow(name="backfill_single_stock")
def backfill_single_stock(
    source_ticker: str,
    dataset: str,
    start_date: str,
    end_date: str,
) -> dict:
    """
    回填单只股票数据.

    Args:
        source_ticker: 数据源代码 (如 "000001.SZ")
        dataset: 数据集名称 (如 "stock_daily")
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        摄取结果字典

    """
    # 获取 coordinator（需要实现依赖注入）
    coordinator = _get_coordinator()
    return ingest_single_ticker(
        coordinator, source_ticker, dataset, start_date, end_date
    )


@flow(name="backfill_multiple_stocks")
def backfill_multiple_stocks(
    source_tickers: list[str],
    dataset: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """
    批量回填多只股票数据（并行）.

    Args:
        source_tickers: 数据源代码列表
        dataset: 数据集名称
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        摄取结果列表

    """
    coordinator = _get_coordinator()

    futures = []
    for ticker in source_tickers:
        future = ingest_single_ticker.submit(
            coordinator, ticker, dataset, start_date, end_date
        )
        futures.append(future)

    return [f.result() for f in futures]


def _get_coordinator() -> IngestionCoordinator:
    """获取 IngestionCoordinator 实例（需要实现）."""
    # TODO: 实现依赖注入
    ...
```

**Step 2: Commit**

```bash
git add apps/port/src/ditto_port/flows/backfill.py
git commit -m "feat(port): add Prefect flows for ticker backfill"
```

---

## Phase 7: 测试 [L]

### Task 7.1: 单元测试 - 标识符解析

**Files:**
- Modify: `apps/port/tests/unit/services/ingestion/test_ticker_resolver_unit.py`

**测试用例:**
- `test_resolve_by_instrument_id` - instrument_id 优先级最高
- `test_resolve_by_source_ticker` - source_ticker 直接返回
- `test_resolve_by_unique_ticker` - 唯一 ticker 正常解析
- `test_ambiguous_ticker_raises_error` - 歧义 ticker 抛出异常
- `test_no_identifier_raises_error` - 无标识符抛出错误
- `test_not_found_raises_error` - 未找到标识符抛出错误

**覆盖率目标:** 100% 分支覆盖

---

### Task 7.2: 集成测试 - Source 按股票查询

**Files:**
- Create: `packages/data/tests/integration/sources/test_tushare_ticker_integration.py`

**测试用例:**
- `test_fetch_stock_daily_by_ticker_returns_data`
- `test_fetch_valuation_metrics_by_ticker`
- `test_fetch_balance_sheet_by_ticker_uses_ann_date`

**覆盖率目标:** ≥ 80%

---

### Task 7.3: E2E 测试 - CLI 完整链路

**Files:**
- Create: `apps/port/tests/e2e/test_ingest_ticker_e2e.py`

**测试用例:**
- `test_cli_ingest_ticker_success`
- `test_cli_ingest_ticker_ambiguous`
- `test_cli_ingest_ticker_dry_run`

---

## 验收标准

### Phase 完成标准

| Phase | 完成标准 |
|-------|---------|
| Phase 1 | 命名规范修复完成，测试通过 |
| Phase 2 | DataSource 支持按股票查询，Adapter 测试覆盖 ≥ 80% |
| Phase 3 | Coordinator `ingest_by_ticker()` 可用，测试覆盖 ≥ 90% |
| Phase 4 | `pixi run ingest ticker` 命令可用，支持 dry-run |
| Phase 5 | `/api/source/{dataset}` 端点可用 |
| Phase 6 | Prefect flows 可用，支持并行回填 |
| Phase 7 | 所有测试通过，分支覆盖率 ≥ 80% |

### 最终验收

```bash
# 运行完整检查
pixi run -e dev check

# 预期结果
# - lint: 通过
# - fmt: 通过
# - type: 通过
# - test: 通过，覆盖率 ≥ 80%
```

---

## 依赖关系图

```
Phase 1 (命名规范) ─────────────────────────────────────────┐
                                                              │
Phase 2 (DataSource 接口) ───────────────────────────────────┤
                                                              │
Phase 3 (Coordinator) ◄──────────────────────────────────────┤
         │                                                    │
         ├─► Phase 4 (CLI 命令)                               │
         │                                                    │
         ├─► Phase 5 (REST API)                               │
         │                                                    │
         └─► Phase 6 (Prefect 任务)                           │
                                                              │
Phase 7 (测试) ◄─────────────────────────────────────────────┘
```

> **并行可能**：Phase 4/5/6 可以并行开发，都依赖 Phase 3 完成。
