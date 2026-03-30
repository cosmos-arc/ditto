# Identifier Resolver 语义统一 + Fundamental CLI 标识符补全 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一 `resolve_instrument_identifier()` 的查询语义（查不到返回 None），并将 Fundamental CLI 的标识符解析对齐到 Capital CLI 的三选一模式。

**Architecture:** 核心改动在 `InstrumentService.resolve_instrument_identifier()`——移除 instrument_id passthrough、移除 not-found 抛错、改为返回 `InstrumentId | None`。所有上游调用方（API `_resolve_identifier`、CLI `_resolve_identifier`）适配 Optional 返回值。Fundamental CLI 平移 Capital CLI 的三选一标识符模式。

**Tech Stack:** Python 3.12, FastAPI, Typer, Pytest, Polars

---

## Task 1: 改造核心 Resolver 语义

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/services/metadata/instrument.py:598-659`
- Test: `packages/datahub/tests/unit/services/test_metadata_service_identifier_resolution_unit.py`

### Step 1: 更新测试 — 写 failing tests

修改 `test_metadata_service_identifier_resolution_unit.py`，将以下测试的行为反转：

```python
# --- 替换 test_instrument_id_passthrough (line 63-81) ---

def test_instrument_id_queries_existence(
    self,
    mock_dependencies: dict[str, MagicMock],
    exchange_transformers: ExchangeTransformers,
) -> None:
    """传入 instrument_id 时应查询 metadata，存在则返回 InstrumentId."""
    mock_dependencies[
        "instrument_reader"
    ].get_by_instrument_id.return_value = {"instrument_id": 1000001}

    service = _make_service(mock_dependencies, exchange_transformers)

    result = service.resolve_instrument_identifier(
        instrument_id=1000001,
        source="tushare",
    )

    assert isinstance(result, int)
    assert result == 1000001
    # 必须调用 reader 查询存在性
    mock_dependencies["instrument_reader"].get_by_instrument_id.assert_called_once_with(
        1000001
    )

# --- 新增 test ---

def test_instrument_id_not_found_returns_none(
    self,
    mock_dependencies: dict[str, MagicMock],
    exchange_transformers: ExchangeTransformers,
) -> None:
    """传入不存在的 instrument_id 时应返回 None，不抛异常."""
    mock_dependencies[
        "instrument_reader"
    ].get_by_instrument_id.return_value = None

    service = _make_service(mock_dependencies, exchange_transformers)

    result = service.resolve_instrument_identifier(
        instrument_id=9999999,
        source="tushare",
    )

    assert result is None

# --- 替换 test_not_found_raises_identifier_not_found_error (line 173-190) ---

def test_ticker_not_found_returns_none(
    self,
    mock_dependencies: dict[str, MagicMock],
    exchange_transformers: ExchangeTransformers,
) -> None:
    """ticker 解析后找不到映射时应返回 None，不抛异常."""
    mock_dependencies[
        "instrument_reader"
    ].find_securities.return_value = pl.DataFrame()

    service = _make_service(mock_dependencies, exchange_transformers)

    result = service.resolve_instrument_identifier(
        ticker="999999",
        source="tushare",
        asset_class="stock",
    )

    assert result is None

# --- 替换 test_standard_ticker_not_found_raises_identifier_not_found_error (line 192-206) ---

def test_standard_ticker_not_found_returns_none(
    self,
    mock_dependencies: dict[str, MagicMock],
    exchange_transformers: ExchangeTransformers,
) -> None:
    """standard_ticker 解析后找不到映射时应返回 None，不抛异常."""
    mock_dependencies[
        "instrument_reader"
    ].resolve_instrument_id.return_value = None

    service = _make_service(mock_dependencies, exchange_transformers)

    result = service.resolve_instrument_identifier(
        standard_ticker="000001.XSHE",
        source="tushare",
    )

    assert result is None

# --- 替换 test_priority_instrument_id_over_ticker (line 141-158) ---

def test_priority_instrument_id_over_ticker(
    self,
    mock_dependencies: dict[str, MagicMock],
    exchange_transformers: ExchangeTransformers,
) -> None:
    """同时传入 instrument_id 和 ticker 时，instrument_id 优先."""
    mock_dependencies[
        "instrument_reader"
    ].get_by_instrument_id.return_value = {"instrument_id": 1000001}

    service = _make_service(mock_dependencies, exchange_transformers)

    result = service.resolve_instrument_identifier(
        instrument_id=1000001,
        ticker="600519",
        source="tushare",
    )

    assert isinstance(result, int)
    assert result == 1000001
    # ticker 不应触发 find_securities 查询
    mock_dependencies["instrument_reader"].find_securities.assert_not_called()
```

同时移除测试文件中对 `IdentifierNotFoundError` 的 import（保留 `NoIdentifierProvidedError` 和 `AmbiguousTickerError`）。

### Step 2: 运行测试确认失败

Run: `pixi run -e dev pytest packages/datahub/tests/unit/services/test_metadata_service_identifier_resolution_unit.py -v`
Expected: FAIL — passthrough test fails (instrument_id path still returns directly without querying)

### Step 3: 实现核心改动

修改 `packages/datahub/src/ditto_datahub/services/metadata/instrument.py` 的 `resolve_instrument_identifier()` 方法：

```python
@traced("metadata.identity.resolve_instrument_identifier")
def resolve_instrument_identifier(
    self,
    *,
    instrument_id: int | None = None,
    standard_ticker: str | None = None,
    ticker: str | None = None,
    asset_class: str | None = None,
    source: str,
    asof: str | None = None,
) -> InstrumentId | None:
    """
    统一标识符解析入口.

    将 instrument_id / standard_ticker / ticker 中的一种解析为
    类型安全的 InstrumentId。查不到返回 None（正常流程）。

    优先级: instrument_id > standard_ticker > ticker

    Args:
        instrument_id: 内部 ID（如 1000001）.
        standard_ticker: Ditto 标准格式（如 "000001.XSHE"）.
        ticker: 裸代码（如 "000001"）.
        asset_class: 资产类型（stock | etf | index），ticker 解析时必需.
        source: 数据源名称（如 "tushare"）.
        asof: 时间点日期 (YYYY-MM-DD).

    Returns:
        InstrumentId 类型安全的证券标识符，查不到返回 None.

    Raises:
        NoIdentifierProvidedError: 未提供任何标识符.
        AmbiguousTickerError: ticker 不唯一.

    """
    if instrument_id is not None:
        # 查询存在性，不存在返回 None
        record = self._instrument_reader.get_by_instrument_id(instrument_id)
        if record is None:
            return None
        return InstrumentId(instrument_id)

    # 至少需要一个非 instrument_id 标识符
    if standard_ticker is None and ticker is None:
        raise NoIdentifierProvidedError(
            "未提供任何标识符 (instrument_id / standard_ticker / ticker)"
        )

    # 复用 resolve_source_ticker 得到 source_ticker，再解析为 instrument_id
    source_ticker = self.resolve_source_ticker(
        ticker=ticker,
        standard_ticker=standard_ticker,
        asset_class=asset_class or "stock",
        source=source,
    )

    resolved_id = self._instrument_reader.resolve_instrument_id(
        source_ticker, source, asof
    )
    if resolved_id is None:
        return None
    return InstrumentId(resolved_id)
```

**关键变更：**
1. 返回类型 `InstrumentId` → `InstrumentId | None`
2. instrument_id 路径：`return InstrumentId(instrument_id)` → `get_by_instrument_id()` 查询 + None 检查
3. ticker/standard_ticker 路径：`raise IdentifierNotFoundError` → `return None`
4. `AmbiguousTickerError` 保留（ticker 歧义仍然抛错）
5. `NoIdentifierProvidedError` 保留（无标识符仍然抛错）
6. 移除 docstring 中 `IdentifierNotFoundError` 的 Raises 声明

### Step 4: 运行测试确认通过

Run: `pixi run -e dev pytest packages/datahub/tests/unit/services/test_metadata_service_identifier_resolution_unit.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add packages/datahub/src/ditto_datahub/services/metadata/instrument.py \
        packages/datahub/tests/unit/services/test_metadata_service_identifier_resolution_unit.py
git commit -m "refactor: resolve_instrument_identifier 查不到返回 None，移除 IdentifierNotFoundError"
```

---

## Task 2: 更新 MetadataService Facade 返回类型

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/services/metadata_service.py:410-428`

### Step 1: 更新 facade 返回类型

修改 `MetadataService.resolve_instrument_identifier()` 的返回类型注解：

```python
def resolve_instrument_identifier(
    self,
    *,
    instrument_id: int | None = None,
    standard_ticker: str | None = None,
    ticker: str | None = None,
    asset_class: str | None = None,
    source: str,
    asof: str | None = None,
) -> InstrumentId | None:
    """统一标识符解析入口。委托到 InstrumentService。"""
    return self._instrument.resolve_instrument_identifier(
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        asset_class=asset_class,
        source=source,
        asof=asof,
    )
```

唯一变更：返回类型 `InstrumentId` → `InstrumentId | None`。

### Step 2: 运行类型检查

Run: `pixi run -e dev type`
Expected: 此处应有 type errors（调用方尚未适配），这些 errors 在 Task 3/4 中修复。

### Step 3: Commit

```bash
git add packages/datahub/src/ditto_datahub/services/metadata_service.py
git commit -m "refactor: MetadataService.resolve_instrument_identifier 返回 InstrumentId | None"
```

---

## Task 3: 适配 API 层 `_resolve_identifier`

**Files:**
- Modify: `apps/port/src/ditto_port/api/routes/capital.py:25-76`
- Modify: `apps/port/src/ditto_port/api/routes/fundamental.py:28-79`
- Test: `apps/port/tests/unit/api/routes/test_capital_identifier_query_unit.py`
- Test: `apps/port/tests/unit/api/routes/test_fundamental_identifier_query_unit.py`

### Step 1: 更新测试 — capital API

替换 `test_capital_identifier_query_unit.py` 中 `test_identifier_not_found_raises_400`：

```python
def test_identifier_not_found_returns_none(self) -> None:
    """IdentifierNotFoundError resolved to None should return None."""
    mock_meta = MagicMock()
    mock_meta.resolve_instrument_identifier.return_value = None
    result = _resolve_identifier(
        mock_meta,
        instrument_id=None,
        standard_ticker=None,
        ticker="999999",
    )
    assert result is None
```

### Step 2: 更新测试 — fundamental API

同样替换 `test_fundamental_identifier_query_unit.py` 中 `test_identifier_not_found_raises_400`：

```python
def test_identifier_not_found_returns_none(self) -> None:
    """IdentifierNotFoundError resolved to None should return None."""
    mock_meta = MagicMock()
    mock_meta.resolve_instrument_identifier.return_value = None
    result = _resolve_identifier(
        mock_meta,
        instrument_id=None,
        standard_ticker=None,
        ticker="999999",
    )
    assert result is None
```

两个测试文件中移除 `IdentifierNotFoundError` 的 import（只保留 `AmbiguousTickerError`）。

### Step 3: 运行测试确认失败

Run: `pixi run -e dev pytest apps/port/tests/unit/api/routes/test_capital_identifier_query_unit.py apps/port/tests/unit/api/routes/test_fundamental_identifier_query_unit.py -v`
Expected: FAIL — `_resolve_identifier` 仍然将 None 走到 try/except

### Step 4: 修改 API 路由 `_resolve_identifier`

**capital.py** 和 **fundamental.py** 的 `_resolve_identifier` 做相同修改：

```python
def _resolve_identifier(
    metadata_service: MetadataService,
    *,
    instrument_id: int | None,
    standard_ticker: str | None,
    ticker: str | None,
) -> int | None:
    """
    解析标识符为 canonical instrument_id.

    至少提供一个标识符（instrument_id / standard_ticker / ticker），
    委托给 MetadataService.resolve_instrument_identifier 进行统一解析。

    Returns:
        解析后的 canonical instrument_id (int)，查不到返回 None.

    Raises:
        HTTPException: 标识符缺失或解析失败时.

    """
    if not any([instrument_id, standard_ticker, ticker]):
        raise HTTPException(
            status_code=422,
            detail="必须提供 instrument_id、standard_ticker 或 ticker 之一",
        )

    try:
        result = metadata_service.resolve_instrument_identifier(
            instrument_id=instrument_id,
            standard_ticker=standard_ticker,
            ticker=ticker,
            source="tushare",
            asset_class="stock",
        )
    except AmbiguousTickerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        exc_name = type(exc).__name__
        if exc_name == "NoIdentifierProvidedError":
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.exception("Unexpected error resolving identifier")
        raise HTTPException(
            status_code=500, detail="Failed to resolve identifier"
        ) from exc

    return result  # int | None
```

**关键变更：**
1. 返回类型 `int` → `int | None`
2. 移除对 `IdentifierNotFoundError` 的 catch（不再抛了）
3. `AmbiguousTickerError` 仍然 catch → 400
4. resolver 返回 None 时直接透传

### Step 5: 修改 API 路由处理 None

在每个路由处理函数中，`resolved_id` 后加 None 检查：

**capital.py — `get_margin` (line 98-103):**

```python
    resolved_id = _resolve_identifier(
        metadata_service,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
    )

    if resolved_id is None:
        return APIResponse(data=[])

    df = await asyncio.to_thread(service.get_margin_trading, resolved_id, as_of_date)
```

**capital.py — `get_valuation` (line 133-138):** 同样加 None 检查。

**fundamental.py — `get_financials` (line 102-107):** 同样加 None 检查。

**fundamental.py — `get_dividend` (line 158-163):** 同样加 None 检查。

**fundamental.py — `list_corporate_actions` (line 210-215):** 同样加 None 检查。

### Step 6: 运行测试确认通过

Run: `pixi run -e dev pytest apps/port/tests/unit/api/routes/test_capital_identifier_query_unit.py apps/port/tests/unit/api/routes/test_fundamental_identifier_query_unit.py -v`
Expected: PASS

### Step 7: Commit

```bash
git add apps/port/src/ditto_port/api/routes/capital.py \
        apps/port/src/ditto_port/api/routes/fundamental.py \
        apps/port/tests/unit/api/routes/test_capital_identifier_query_unit.py \
        apps/port/tests/unit/api/routes/test_fundamental_identifier_query_unit.py
git commit -m "refactor: API _resolve_identifier 适配 Optional 返回值，查不到返回空列表"
```

---

## Task 4: 适配 Capital CLI `_resolve_identifier`

**Files:**
- Modify: `apps/port/src/ditto_port/cli/commands/query/capital.py:34-66`

### Step 1: 修改 Capital CLI `_resolve_identifier`

```python
def _resolve_identifier(
    metadata_service: MetadataService,
    *,
    instrument_id: int | None,
    ticker: str | None,
    standard_ticker: str | None,
) -> int | None:
    """
    解析标识符为 canonical instrument_id.

    至少提供一个标识符，委托给 MetadataService.resolve_instrument_identifier。

    Returns:
        解析后的 canonical instrument_id (int)，查不到返回 None.

    """
    if not any([instrument_id, standard_ticker, ticker]):
        typer.echo("错误: 必须提供 --instrument-id、--ticker 或 --standard-ticker 之一")
        raise typer.Exit(code=1)

    return metadata_service.resolve_instrument_identifier(
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        source="tushare",
        asset_class="stock",
    )
```

**关键变更：** 返回类型 `int` → `int | None`。

### Step 2: Capital CLI 命令中加 None 检查

**`get_margin`** — 在 `resolved_id` 赋值后：

```python
        resolved_id = _resolve_identifier(
            metadata_service,
            instrument_id=instrument_id,
            ticker=ticker,
            standard_ticker=standard_ticker,
        )
        if resolved_id is None:
            typer.echo("未找到匹配的标的")
            return
        df = service.get_margin_trading(resolved_id, as_of)
```

**`get_valuation`** — 同样加 None 检查。

### Step 3: Commit

```bash
git add apps/port/src/ditto_port/cli/commands/query/capital.py
git commit -m "refactor: Capital CLI _resolve_identifier 适配 Optional 返回值"
```

---

## Task 5: Fundamental CLI 标识符补全

**Files:**
- Modify: `apps/port/src/ditto_port/cli/commands/query/fundamental.py`

### Step 1: 重写 fundamental.py

将 Capital CLI 的三选一模式完整平移到 Fundamental CLI。完整改动：

```python
"""CLI fundamental 域查询命令."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import orjson
import typer
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.metadata_service import MetadataService
from rich.console import Console
from rich.table import Table

from ditto_port.cli.context import create_cli_host
from ditto_port.models.fundamental import (
    FinancialType,
    to_corporate_action_list,
    to_dividend_list,
    to_financial_list,
)

_TABLE_DISPLAY_LIMIT = 20

app = typer.Typer(help="基本面数据查询")
console = Console()


@contextmanager
def _get_services() -> Generator[tuple[FundamentalService, MetadataService], None, None]:
    """获取 FundamentalService 和 MetadataService 实例."""
    with create_cli_host() as bundle:
        yield bundle.fundamental_service, bundle.metadata_service


def _resolve_identifier(
    metadata_service: MetadataService,
    *,
    instrument_id: int | None,
    ticker: str | None,
    standard_ticker: str | None,
) -> int | None:
    """
    解析标识符为 canonical instrument_id.

    至少提供一个标识符，委托给 MetadataService.resolve_instrument_identifier。

    Returns:
        解析后的 canonical instrument_id (int)，查不到返回 None.

    """
    if not any([instrument_id, standard_ticker, ticker]):
        typer.echo("错误: 必须提供 --instrument-id、--ticker 或 --standard-ticker 之一")
        raise typer.Exit(code=1)

    return metadata_service.resolve_instrument_identifier(
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        source="tushare",
        asset_class="stock",
    )
```

然后三个命令函数改为三选一标识符 + None 检查：

**`get_financials`:**
```python
@app.command("financials")
def get_financials(
    instrument_id: int | None = typer.Option(
        None, "--instrument-id", "-i", help="Canonical 标的 ID"
    ),
    ticker: str | None = typer.Option(None, "--ticker", "-t", help="裸代码, 如 000001"),
    standard_ticker: str | None = typer.Option(
        None, "--standard-ticker", "-s", help="标准代码, 如 000001.XSHE"
    ),
    report_type: str = typer.Option(
        "balance_sheet",
        "--type",
        "-r",
        help="报表类型 (balance_sheet/income_statement/cash_flow)",
    ),
    as_of_date: str = typer.Option(..., "--date", "-d", help="PIT 查询日期"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询财务报表数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
        ditto query fundamental financials -i 1000001 -r balance_sheet --date 2024-12-31
        ditto query fundamental financials -s 000001.XSHE -r balance_sheet --date 2024-12-31
        ditto query fundamental financials -t 000001 -r balance_sheet --date 2024-12-31

    """
    type_map = {
        "balance_sheet": FinancialType.BALANCE_SHEET,
        "income_statement": FinancialType.INCOME_STATEMENT,
        "cash_flow": FinancialType.CASH_FLOW,
    }

    if report_type not in type_map:
        valid_types = "balance_sheet, income_statement, cash_flow"
        typer.secho(
            f"错误: 无效的报表类型 '{report_type}', 可选: {valid_types}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    financial_type = type_map[report_type]
    as_of = _parse_date(as_of_date).date()

    with _get_services() as (service, metadata_service):
        resolved_id = _resolve_identifier(
            metadata_service,
            instrument_id=instrument_id,
            ticker=ticker,
            standard_ticker=standard_ticker,
        )
        if resolved_id is None:
            typer.echo("未找到匹配的标的")
            return

        df = None
        if financial_type == FinancialType.BALANCE_SHEET:
            df = service.get_balance_sheet(resolved_id, as_of)
        elif financial_type == FinancialType.INCOME_STATEMENT:
            df = service.get_income_statement(resolved_id, as_of)
        elif financial_type == FinancialType.CASH_FLOW:
            df = service.get_cash_flow(resolved_id, as_of)

        if df is None or df.is_empty():
            typer.echo("未找到财务数据")
            return

        financials = to_financial_list(df, financial_type)

        if json_output:
            _output_json(financials)
            return

        table = Table(title=f"财务报表 - {report_type}")
        table.add_column("标的 ID", style="cyan")
        table.add_column("报告期", style="white")
        table.add_column("报表类型", style="yellow")

        for fin in financials[:_TABLE_DISPLAY_LIMIT]:
            table.add_row(
                str(fin.instrument_id),
                fin.report_date or "-",
                fin.report_type or "-",
            )

        console.print(table)
        _print_truncated_hint(len(financials))
```

**`get_dividend`:**
```python
@app.command("dividend")
def get_dividend(
    instrument_id: int | None = typer.Option(
        None, "--instrument-id", "-i", help="Canonical 标的 ID"
    ),
    ticker: str | None = typer.Option(None, "--ticker", "-t", help="裸代码, 如 000001"),
    standard_ticker: str | None = typer.Option(
        None, "--standard-ticker", "-s", help="标准代码, 如 000001.XSHE"
    ),
    as_of_date: str = typer.Option(..., "--date", "-d", help="PIT 查询日期"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询分红数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
        ditto query fundamental dividend -i 1000001 --date 2024-12-31
        ditto query fundamental dividend -s 000001.XSHE --date 2024-12-31
        ditto query fundamental dividend -t 000001 --date 2024-12-31

    """
    as_of = _parse_date(as_of_date).date()
    with _get_services() as (service, metadata_service):
        resolved_id = _resolve_identifier(
            metadata_service,
            instrument_id=instrument_id,
            ticker=ticker,
            standard_ticker=standard_ticker,
        )
        if resolved_id is None:
            typer.echo("未找到匹配的标的")
            return

        df = service.get_dividend(resolved_id, as_of)

        if df is None or df.is_empty():
            typer.echo("未找到分红数据")
            return

        dividends = to_dividend_list(df)

        if json_output:
            _output_json(dividends)
            return

        table = Table(title="分红数据")
        table.add_column("公告日期", style="cyan")
        table.add_column("分红类型", style="green")
        table.add_column("分红金额", style="yellow", justify="right")

        for div in dividends:
            table.add_row(
                str(div.announce_date) if div.announce_date else "-",
                div.dividend_type or "-",
                f"{div.amount:.4f}" if div.amount else "-",
            )

        console.print(table)
```

**`list_corporate_actions`:**
```python
@app.command("corporate-actions")
def list_corporate_actions(
    instrument_id: int | None = typer.Option(
        None, "--instrument-id", "-i", help="Canonical 标的 ID"
    ),
    ticker: str | None = typer.Option(None, "--ticker", "-t", help="裸代码, 如 000001"),
    standard_ticker: str | None = typer.Option(
        None, "--standard-ticker", "-s", help="标准代码, 如 000001.XSHE"
    ),
    start_date: str = typer.Option(..., "--start-date", "-s", help="开始日期"),
    end_date: str = typer.Option(..., "--end-date", "-e", help="结束日期"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询公司行动列表.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
        ditto query fundamental corporate-actions -i 1 -s 2024-01-01 -e 2024-12-31
        ditto query fundamental corporate-actions -t 000001 -s 2024-01-01 -e 2024-12-31

    """
    _validate_date_range(start_date, end_date)
    start = _parse_date(start_date).date()
    end = _parse_date(end_date).date()

    with _get_services() as (service, metadata_service):
        resolved_id = _resolve_identifier(
            metadata_service,
            instrument_id=instrument_id,
            ticker=ticker,
            standard_ticker=standard_ticker,
        )
        if resolved_id is None:
            typer.echo("未找到匹配的标的")
            return

        df = service.list_corporate_actions(resolved_id, start, end)

        if df.is_empty():
            typer.echo("未找到公司行动数据")
            return

        actions = to_corporate_action_list(df)

        if json_output:
            _output_json(actions)
            return

        table = Table(title="公司行动")
        table.add_column("行动日期", style="cyan")
        table.add_column("类型", style="yellow")
        table.add_column("描述", style="white")

        for action in actions:
            table.add_row(
                str(action.action_date) if action.action_date else "-",
                action.action_type or "-",
                action.description or "-",
            )

        console.print(table)
```

**注意：** `corporate-actions` 命令的 `--start-date` 短选项从 `-s` 改为无短选项（避免与 `--standard-ticker` 的 `-s` 冲突），`--end-date` 保持 `-e`。或者保留 `-s` / `-e` 但让 `--standard-ticker` 不设短选项（与 Capital CLI 保持一致——Capital CLI 中 `--standard-ticker` 的短选项是 `-s`）。

**最终决策：** 保持与 Capital CLI 完全一致的短选项映射：
- `-i` = `--instrument-id`
- `-t` = `--ticker`
- `-s` = `--standard-ticker`

`corporate-actions` 命令的 `--start-date` / `--end-date` **不设短选项**，避免冲突。

### Step 2: Commit

```bash
git add apps/port/src/ditto_port/cli/commands/query/fundamental.py
git commit -m "feat: Fundamental CLI 三选一标识符解析，对齐 Capital CLI 模式"
```

---

## Task 6: 全量验证

### Step 1: 运行完整检查

Run: `pixi run -e dev check`
Expected: ALL PASS (lint + fmt + type + test --fast)

### Step 2: 运行受影响的单元测试

Run: `pixi run -e dev pytest packages/datahub/tests/unit/services/test_metadata_service_identifier_resolution_unit.py apps/port/tests/unit/api/routes/test_capital_identifier_query_unit.py apps/port/tests/unit/api/routes/test_fundamental_identifier_query_unit.py -v`
Expected: ALL PASS

### Step 3: 类型检查

Run: `pixi run -e dev type --all`
Expected: 0 errors
