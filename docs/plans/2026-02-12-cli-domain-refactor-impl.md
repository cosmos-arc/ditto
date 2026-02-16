# CLI Domain Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 CLI 命令从混合结构重构为 ACTION-DOMAIN-DATASET 三层结构

**Architecture:**
- 新增 `ingest/` 和 `backfill/` 两个顶级命令组
- 每个 DOMAIN 下按 DATASET 组织子命令
- 删除旧的按资产类型划分的命令文件

**Tech Stack:** typer, Python 3.12+

---

## Task 1: Dataset 枚举重命名 FUTURES → FUTURES_POSITION

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/models/common.py:70`
- Modify: `apps/port/src/ditto_port/models/config.py:52,604-611`

**Step 1: 修改 DataHub Dataset 枚举**

```python
# packages/datahub/src/ditto_datahub/models/common.py
# 将 FUTURES = "futures" 改为：
FUTURES_POSITION = "futures_position"
```

**Step 2: 修改 Port Dataset 枚举**

```python
# apps/port/src/ditto_port/models/config.py
# 将 FUTURES = "futures" 改为：
FUTURES_POSITION = "futures_position"
```

**Step 3: 更新 INGESTION_SPECS 配置**

```python
# apps/port/src/ditto_port/models/config.py
# 将 Dataset.FUTURES 改为 Dataset.FUTURES_POSITION
# 更新 description 为 "期货持仓数据"
Dataset.FUTURES_POSITION: create_t1_config(
    dataset=Dataset.FUTURES_POSITION,
    description="期货持仓数据",
    typical_available_time=time(21, 0),
    depends_on=[Dataset.CALENDAR],
    critical_fields=["instrument_id", "trade_date", "knowledge_date"],
    task_name="ingest_futures_position",
    priority=60,
),
```

**Step 4: 验证类型检查**

```bash
pixi run -e dev type
```

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/models/common.py apps/port/src/ditto_port/models/config.py
git commit -m "refactor: Dataset.FUTURES → FUTURES_POSITION"
```

---

## Task 2: 更新 FUTURES 引用 - DataHub 层

**Files:**
- Modify: `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- Modify: `apps/port/src/ditto_port/services/ingestion/data_writer.py`
- Modify: `packages/datahub/src/ditto_datahub/sources/tushare/adapters/capital.py`
- Modify: `packages/datahub/src/ditto_datahub/sources/schemas/capital_schemas.py`
- Modify: `packages/datahub/src/ditto_datahub/sources/schemas/__init__.py`

**Step 1: 查找所有 FUTURES 引用**

```bash
pixi run -e dev grep "FUTURES" packages/datahub apps/port
```

**Step 2: 全局替换 FUTURES → FUTURES_POSITION**

使用编辑器或 sed 全局替换（排除设计文档）：
- `Dataset.FUTURES` → `Dataset.FUTURES_POSITION`
- `"futures"` → `"futures_position"` (仅在相关上下文)

**Step 3: 验证**

```bash
pixi run -e dev type
pixi run -e dev lint
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: 更新 FUTURES → FUTURES_POSITION 引用"
```

---

## Task 3: 重命名 Store 目录 futures → futures_position

**Files:**
- Rename: `packages/datahub/src/ditto_datahub/stores/capital/futures/` → `futures_position/`
- Modify: `packages/datahub/src/ditto_datahub/stores/capital/__init__.py`

**Step 1: 重命名目录**

```bash
mv packages/datahub/src/ditto_datahub/stores/capital/futures packages/datahub/src/ditto_datahub/stores/capital/futures_position
```

**Step 2: 更新 __init__.py 导出**

更新 `packages/datahub/src/ditto_datahub/stores/capital/__init__.py`

**Step 3: 更新导入此模块的文件**

使用 Grep 查找引用：
```bash
pixi run -e dev grep "stores/capital/futures" packages/datahub
```

**Step 4: 验证**

```bash
pixi run -e dev type
```

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 重命名 futures → futures_position Store 目录"
```

---

## Task 4: 创建 ingest 命令组目录结构

**Files:**
- Create: `apps/port/src/ditto_port/cli/commands/ingest/__init__.py`
- Create: `apps/port/src/ditto_port/cli/commands/ingest/metadata.py`
- Create: `apps/port/src/ditto_port/cli/commands/ingest/market.py`
- Create: `apps/port/src/ditto_port/cli/commands/ingest/fundamental.py`
- Create: `apps/port/src/ditto_port/cli/commands/ingest/capital.py`
- Create: `apps/port/src/ditto_port/cli/commands/ingest/macro.py`

**Step 1: 创建 ingest/__init__.py**

```python
"""CLI ingest 命令组."""

import typer

from ditto_port.cli.commands.ingest.capital import app as capital_app
from ditto_port.cli.commands.ingest.fundamental import app as fundamental_app
from ditto_port.cli.commands.ingest.macro import app as macro_app
from ditto_port.cli.commands.ingest.market import app as market_app
from ditto_port.cli.commands.ingest.metadata import app as metadata_app

app = typer.Typer(help="摄取数据")

app.add_typer(metadata_app, name="metadata")
app.add_typer(market_app, name="market")
app.add_typer(fundamental_app, name="fundamental")
app.add_typer(capital_app, name="capital")
app.add_typer(macro_app, name="macro")
```

**Step 2: 创建 ingest/metadata.py**

```python
"""Metadata 域摄取命令 (calendar + basic)."""

import typer

from ditto_port.cli.commands.factory import create_basic_command, create_daily_command

app = typer.Typer(help="元数据摄取")

# calendar
_calendar_impl = create_daily_command("calendar", "摄取交易日历")

# basic (stock/etf/index 基础信息)
_stock_basic_impl = create_basic_command("stock_basic", "摄取股票基础信息")
_etf_basic_impl = create_basic_command("etf_basic", "摄取ETF基础信息")
_index_basic_impl = create_basic_command("index_basic", "摄取指数基础信息")


@app.command("calendar")
def calendar(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取交易日历."""
    return _calendar_impl(ctx, date, force)


@app.command("basic")
def basic(
    ctx: typer.Context,
    asset: str = typer.Argument(..., help="资产类型 (stock/etf/index)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取基础信息 (stock/etf/index)."""
    asset = asset.lower()
    if asset == "stock":
        return _stock_basic_impl(ctx, force)
    elif asset == "etf":
        return _etf_basic_impl(ctx, force)
    elif asset == "index":
        return _index_basic_impl(ctx, force)
    else:
        typer.echo(f"未知资产类型: {asset}，支持: stock/etf/index", err=True)
        raise typer.Exit(1)
```

**Step 3: 创建 ingest/market.py**

```python
"""Market 域摄取命令 (stock/etf/index/adj/status)."""

import typer

from ditto_port.cli.commands.factory import create_daily_command

app = typer.Typer(help="行情数据摄取")

# daily (stock/etf/index 日行情)
_stock_daily_impl = create_daily_command("stock_daily", "摄取股票日行情")
_etf_daily_impl = create_daily_command("etf_daily", "摄取ETF日行情")
_index_daily_impl = create_daily_command("index_daily", "摄取指数日行情")

# adj (复权因子)
_adj_factor_impl = create_daily_command("adj_factor", "摄取股票复权因子")
_fund_adj_impl = create_daily_command("fund_adj", "摄取ETF/基金复权因子")

# status (股票状态)
_stock_status_impl = create_daily_command("stock_status", "摄取股票状态")


@app.command("stock")
def stock(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股票日行情."""
    return _stock_daily_impl(ctx, date, force)


@app.command("etf")
def etf(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取ETF日行情."""
    return _etf_daily_impl(ctx, date, force)


@app.command("index")
def index(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取指数日行情."""
    return _index_daily_impl(ctx, date, force)


@app.command("adj")
def adj(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
    fund: bool = typer.Option(False, "--fund", help="摄取ETF/基金复权因子"),
) -> None:
    """摄取复权因子."""
    if fund:
        return _fund_adj_impl(ctx, date, force)
    return _adj_factor_impl(ctx, date, force)


@app.command("status")
def status(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股票状态."""
    return _stock_status_impl(ctx, date, force)
```

**Step 4: 创建 ingest/fundamental.py**

```python
"""Fundamental 域摄取命令."""

import typer

from ditto_port.cli.commands.factory import create_daily_command

app = typer.Typer(help="基本面数据摄取")

# 财务报表
_balance_impl = create_daily_command("balance_sheet", "摄取资产负债表")
_income_impl = create_daily_command("income_statement", "摄取利润表")
_cash_flow_impl = create_daily_command("cash_flow", "摄取现金流量表")
_dividend_impl = create_daily_command("dividend", "摄取分红送配")

# 公司行为
_corporate_actions_impl = create_daily_command(
    "corporate_actions", "摄取公司行为"
)


@app.command("balance")
def balance(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取资产负债表."""
    return _balance_impl(ctx, date, force)


@app.command("income")
def income(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取利润表."""
    return _income_impl(ctx, date, force)


@app.command("cash-flow")
def cash_flow(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取现金流量表."""
    return _cash_flow_impl(ctx, date, force)


@app.command("dividend")
def dividend(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取分红送配."""
    return _dividend_impl(ctx, date, force)


@app.command("corporate-actions")
def corporate_actions(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取公司行为."""
    return _corporate_actions_impl(ctx, date, force)
```

**Step 5: 创建 ingest/capital.py**

```python
"""Capital 域摄取命令."""

import typer

from ditto_port.cli.commands.factory import create_daily_command

app = typer.Typer(help="资本面数据摄取")

# 估值指标
_valuation_impl = create_daily_command("valuation_metrics", "摄取估值指标")

# 融资融券
_margin_impl = create_daily_command("margin_trading", "摄取融资融券")

# 股权质押
_pledge_impl = create_daily_command("pledge_ratio", "摄取股权质押")

# 期货持仓
_futures_position_impl = create_daily_command(
    "futures_position", "摄取期货持仓"
)


@app.command("valuation")
def valuation(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取估值指标."""
    return _valuation_impl(ctx, date, force)


@app.command("margin")
def margin(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取融资融券."""
    return _margin_impl(ctx, date, force)


@app.command("pledge")
def pledge(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取股权质押."""
    return _pledge_impl(ctx, date, force)


@app.command("futures-position")
def futures_position(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取期货持仓."""
    return _futures_position_impl(ctx, date, force)
```

**Step 6: 创建 ingest/macro.py**

```python
"""Macro 域摄取命令."""

import typer

from ditto_port.cli.commands.factory import create_daily_command

app = typer.Typer(help="宏观数据摄取")

_indicators_impl = create_daily_command("macro_indicators", "摄取宏观指标")


@app.command("indicators")
def indicators(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取宏观指标."""
    return _indicators_impl(ctx, date, force)
```

**Step 7: 验证**

```bash
pixi run -e dev type
pixi run -e dev lint
```

**Step 8: Commit**

```bash
git add apps/port/src/ditto_port/cli/commands/ingest/
git commit -m "feat(cli): 创建 ingest 命令组"
```

---

## Task 5: 创建 backfill 命令组

**Files:**
- Create: `apps/port/src/ditto_port/cli/commands/backfill/__init__.py`
- Create: `apps/port/src/ditto_port/cli/commands/backfill/metadata.py`
- Create: `apps/port/src/ditto_port/cli/commands/backfill/market.py`
- Create: `apps/port/src/ditto_port/cli/commands/backfill/fundamental.py`
- Create: `apps/port/src/ditto_port/cli/commands/backfill/capital.py`
- Create: `apps/port/src/ditto_port/cli/commands/backfill/macro.py`

**Step 1: 创建 backfill/__init__.py**

```python
"""CLI backfill 命令组."""

import typer

from ditto_port.cli.commands.backfill.capital import app as capital_app
from ditto_port.cli.commands.backfill.fundamental import app as fundamental_app
from ditto_port.cli.commands.backfill.macro import app as macro_app
from ditto_port.cli.commands.backfill.market import app as market_app
from ditto_port.cli.commands.backfill.metadata import app as metadata_app

app = typer.Typer(help="回补历史数据")

app.add_typer(metadata_app, name="metadata")
app.add_typer(market_app, name="market")
app.add_typer(fundamental_app, name="fundamental")
app.add_typer(capital_app, name="capital")
app.add_typer(macro_app, name="macro")
```

**Step 2: 创建 backfill/metadata.py**

```python
"""Metadata 域回补命令."""

import typer

from ditto_port.cli.commands.factory import create_backfill_command

app = typer.Typer(help="元数据回补")

_calendar_impl = create_backfill_command("calendar", "回补交易日历历史数据")


@app.command("calendar")
def calendar(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补交易日历历史数据."""
    return _calendar_impl(ctx, start, end, parallel)
```

**Step 3: 创建 backfill/market.py**

```python
"""Market 域回补命令."""

import typer

from ditto_port.cli.commands.factory import create_backfill_command

app = typer.Typer(help="行情数据回补")

_stock_impl = create_backfill_command("stock_daily", "回补股票历史数据")
_etf_impl = create_backfill_command("etf_daily", "回补ETF历史数据")
_index_impl = create_backfill_command("index_daily", "回补指数历史数据")
_adj_impl = create_backfill_command("adj_factor", "回补复权因子历史数据")
_fund_adj_impl = create_backfill_command("fund_adj", "回补ETF/基金复权因子历史数据")
_status_impl = create_backfill_command("stock_status", "回补股票状态历史数据")


@app.command("stock")
def stock(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补股票历史数据."""
    return _stock_impl(ctx, start, end, parallel)


@app.command("etf")
def etf(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补ETF历史数据."""
    return _etf_impl(ctx, start, end, parallel)


@app.command("index")
def index(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补指数历史数据."""
    return _index_impl(ctx, start, end, parallel)


@app.command("adj")
def adj(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
    fund: bool = typer.Option(False, "--fund", help="回补ETF/基金复权因子"),
) -> None:
    """回补复权因子历史数据."""
    if fund:
        return _fund_adj_impl(ctx, start, end, parallel)
    return _adj_impl(ctx, start, end, parallel)


@app.command("status")
def status(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补股票状态历史数据."""
    return _status_impl(ctx, start, end, parallel)
```

**Step 4: 创建 backfill/fundamental.py**

```python
"""Fundamental 域回补命令."""

import typer

from ditto_port.cli.commands.factory import create_backfill_command

app = typer.Typer(help="基本面数据回补")

_balance_impl = create_backfill_command("balance_sheet", "回补资产负债表历史数据")
_income_impl = create_backfill_command("income_statement", "回补利润表历史数据")
_cash_flow_impl = create_backfill_command("cash_flow", "回补现金流量表历史数据")
_dividend_impl = create_backfill_command("dividend", "回补分红送配历史数据")
_corporate_actions_impl = create_backfill_command(
    "corporate_actions", "回补公司行为历史数据"
)


@app.command("balance")
def balance(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补资产负债表历史数据."""
    return _balance_impl(ctx, start, end, parallel)


@app.command("income")
def income(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补利润表历史数据."""
    return _income_impl(ctx, start, end, parallel)


@app.command("cash-flow")
def cash_flow(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补现金流量表历史数据."""
    return _cash_flow_impl(ctx, start, end, parallel)


@app.command("dividend")
def dividend(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补分红送配历史数据."""
    return _dividend_impl(ctx, start, end, parallel)


@app.command("corporate-actions")
def corporate_actions(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补公司行为历史数据."""
    return _corporate_actions_impl(ctx, start, end, parallel)
```

**Step 5: 创建 backfill/capital.py**

```python
"""Capital 域回补命令."""

import typer

from ditto_port.cli.commands.factory import create_backfill_command

app = typer.Typer(help="资本面数据回补")

_valuation_impl = create_backfill_command("valuation_metrics", "回补估值指标历史数据")
_margin_impl = create_backfill_command("margin_trading", "回补融资融券历史数据")
_pledge_impl = create_backfill_command("pledge_ratio", "回补股权质押历史数据")
_futures_position_impl = create_backfill_command(
    "futures_position", "回补期货持仓历史数据"
)


@app.command("valuation")
def valuation(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补估值指标历史数据."""
    return _valuation_impl(ctx, start, end, parallel)


@app.command("margin")
def margin(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补融资融券历史数据."""
    return _margin_impl(ctx, start, end, parallel)


@app.command("pledge")
def pledge(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补股权质押历史数据."""
    return _pledge_impl(ctx, start, end, parallel)


@app.command("futures-position")
def futures_position(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补期货持仓历史数据."""
    return _futures_position_impl(ctx, start, end, parallel)
```

**Step 6: 创建 backfill/macro.py**

```python
"""Macro 域回补命令."""

import typer

from ditto_port.cli.commands.factory import create_backfill_command

app = typer.Typer(help="宏观数据回补")

_indicators_impl = create_backfill_command("macro_indicators", "回补宏观指标历史数据")


@app.command("indicators")
def indicators(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补宏观指标历史数据."""
    return _indicators_impl(ctx, start, end, parallel)
```

**Step 7: 验证**

```bash
pixi run -e dev type
pixi run -e dev lint
```

**Step 8: Commit**

```bash
git add apps/port/src/ditto_port/cli/commands/backfill/
git commit -m "feat(cli): 创建 backfill 命令组"
```

---

## Task 6: 更新 CLI 主入口 main.py

**Files:**
- Modify: `apps/port/src/ditto_port/cli/main.py`

**Step 1: 更新导入和注册**

```python
"""Ditto CLI 主入口."""

import os

import typer

from ditto_port.cli.commands.backfill import app as backfill_app
from ditto_port.cli.commands.init import app as init_app
from ditto_port.cli.commands.ingest import app as ingest_app

app = typer.Typer(
    name="ditto",
    help="Ditto 量化系统命令行工具",
    no_args_is_help=True,
    add_completion=True,
)

# 注册命令组
app.add_typer(init_app, name="init")
app.add_typer(ingest_app, name="ingest")
app.add_typer(backfill_app, name="backfill")


@app.callback()
def main(
    ctx: typer.Context,
    data_root: str = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出模式"),
) -> None:
    """初始化 CLI 上下文."""
    ctx.ensure_object(dict)

    # 透传 data_root 到环境变量，供 ConfigProvider 使用
    if data_root:
        os.environ["DITTO_DATA_ROOT"] = data_root

    # 延迟初始化 DataHub，存储配置供后续使用
    ctx.obj["data_root"] = data_root
    ctx.obj["verbose"] = verbose


@app.command()
def version() -> None:
    """显示版本信息."""
    typer.echo("ditto-cli v0.1.0")


if __name__ == "__main__":
    app()
```

**Step 2: 验证**

```bash
pixi run -e dev type
pixi run -e dev lint
```

**Step 3: Commit**

```bash
git add apps/port/src/ditto_port/cli/main.py
git commit -m "refactor(cli): 更新主入口注册新命令组"
```

---

## Task 7: 删除旧命令文件

**Files:**
- Delete: `apps/port/src/ditto_port/cli/commands/stock.py`
- Delete: `apps/port/src/ditto_port/cli/commands/etf.py`
- Delete: `apps/port/src/ditto_port/cli/commands/index.py`
- Delete: `apps/port/src/ditto_port/cli/commands/calendar.py`
- Delete: `apps/port/src/ditto_port/cli/commands/adj.py`
- Delete: `apps/port/src/ditto_port/cli/commands/futures_cmd.py`
- Delete: `apps/port/src/ditto_port/cli/commands/corporate_actions.py`
- Delete: `apps/port/src/ditto_port/cli/commands/fundamental.py`
- Delete: `apps/port/src/ditto_port/cli/commands/capital.py`
- Delete: `apps/port/src/ditto_port/cli/commands/macro.py`

**Step 1: 删除文件**

```bash
rm apps/port/src/ditto_port/cli/commands/stock.py
rm apps/port/src/ditto_port/cli/commands/etf.py
rm apps/port/src/ditto_port/cli/commands/index.py
rm apps/port/src/ditto_port/cli/commands/calendar.py
rm apps/port/src/ditto_port/cli/commands/adj.py
rm apps/port/src/ditto_port/cli/commands/futures_cmd.py
rm apps/port/src/ditto_port/cli/commands/corporate_actions.py
rm apps/port/src/ditto_port/cli/commands/fundamental.py
rm apps/port/src/ditto_port/cli/commands/capital.py
rm apps/port/src/ditto_port/cli/commands/macro.py
```

**Step 2: 验证**

```bash
pixi run -e dev type
pixi run -e dev lint
```

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor(cli): 删除旧命令文件"
```

---

## Task 8: 更新测试文件

**Files:**
- Delete: `apps/port/tests/unit/cli/commands/test_stock_unit.py`
- Delete: `apps/port/tests/unit/cli/commands/test_etf_unit.py`
- Delete: `apps/port/tests/unit/cli/commands/test_calendar_unit.py`
- Delete: `apps/port/tests/unit/cli/commands/test_adj_unit.py`
- Delete: `apps/port/tests/unit/cli/test_index_command_unit.py`
- Delete: `apps/port/tests/unit/cli/test_adj_command_unit.py`
- Create: `apps/port/tests/unit/cli/commands/ingest/__init__.py`
- Create: `apps/port/tests/unit/cli/commands/ingest/test_metadata_unit.py`
- Create: `apps/port/tests/unit/cli/commands/ingest/test_market_unit.py`

**Step 1: 删除旧测试文件**

```bash
rm -f apps/port/tests/unit/cli/commands/test_stock_unit.py
rm -f apps/port/tests/unit/cli/commands/test_etf_unit.py
rm -f apps/port/tests/unit/cli/commands/test_calendar_unit.py
rm -f apps/port/tests/unit/cli/commands/test_adj_unit.py
rm -f apps/port/tests/unit/cli/test_index_command_unit.py
rm -f apps/port/tests/unit/cli/test_adj_command_unit.py
```

**Step 2: 创建新测试目录**

```bash
mkdir -p apps/port/tests/unit/cli/commands/ingest
```

**Step 3: 创建 ingest/__init__.py**

```python
"""CLI ingest 命令测试."""
```

**Step 4: 创建 test_metadata_unit.py**

```python
"""Metadata 域摄取命令单元测试."""

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture

from ditto_port.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    """创建 CLI 测试运行器."""
    return CliRunner()


@pytest.mark.unit
class TestMetadataCommands:
    """Metadata 命令测试."""

    def test_ingest_metadata_calendar_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取交易日历."""
        mock_executor = mocker.MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "calendar",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 1,
            "message": "成功",
            "error": None,
        }
        mocker.patch(
            "ditto_port.cli.context.create_executor"
        ).return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "metadata", "calendar", "2024-01-02"])
        assert result.exit_code == 0

    def test_ingest_metadata_basic_stock(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取股票基础信息."""
        mock_executor = mocker.MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "stock_basic",
            "trade_date": "",
            "status": "success",
            "row_count": 500,
            "message": "成功",
            "error": None,
        }
        mocker.patch(
            "ditto_port.cli.context.create_executor"
        ).return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "metadata", "basic", "stock"])
        assert result.exit_code == 0
```

**Step 5: 创建 test_market_unit.py**

```python
"""Market 域摄取命令单元测试."""

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture

from ditto_port.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    """创建 CLI 测试运行器."""
    return CliRunner()


@pytest.mark.unit
class TestMarketCommands:
    """Market 命令测试."""

    def test_ingest_market_stock_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取股票日行情."""
        mock_executor = mocker.MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "stock_daily",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 4000,
            "message": "成功",
            "error": None,
        }
        mocker.patch(
            "ditto_port.cli.context.create_executor"
        ).return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "market", "stock", "2024-01-02"])
        assert result.exit_code == 0

    def test_ingest_market_adj_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取复权因子."""
        mock_executor = mocker.MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "adj_factor",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 4000,
            "message": "成功",
            "error": None,
        }
        mocker.patch(
            "ditto_port.cli.context.create_executor"
        ).return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "market", "adj", "2024-01-02"])
        assert result.exit_code == 0
```

**Step 6: 验证**

```bash
pixi run -e dev test --unit
```

**Step 7: Commit**

```bash
git add -A
git commit -m "test(cli): 更新 CLI 命令测试"
```

---

## Task 9: 验收测试

**Files:**
- N/A

**Step 1: 运行完整检查**

```bash
pixi run -e dev check
```

**Step 2: 验证 CLI 命令帮助**

```bash
pixi run -e dev ditto --help
pixi run -e dev ditto ingest --help
pixi run -e dev ditto ingest metadata --help
pixi run -e dev ditto ingest market --help
pixi run -e dev ditto ingest fundamental --help
pixi run -e dev ditto ingest capital --help
pixi run -e dev ditto backfill --help
```

**Step 3: 验收标准确认**

- [ ] `ditto ingest --help` 显示帮助
- [ ] `ditto ingest metadata --help` 显示帮助
- [ ] `ditto ingest market --help` 显示帮助
- [ ] `ditto ingest fundamental --help` 包含 corporate-actions
- [ ] `ditto ingest capital --help` 包含 futures-position
- [ ] `ditto backfill --help` 显示帮助
- [ ] `pixi run -e dev check` 全部通过

---

## Task 10: 最终提交

**Step 1: 确认所有变更**

```bash
git status
git log --oneline -10
```

**Step 2: 更新设计文档状态**

编辑 `docs/plans/2026-02-12-cli-domain-refactor-design.md`，将状态更新为 `Completed`

**Step 3: 最终提交**

```bash
git add docs/plans/2026-02-12-cli-domain-refactor-design.md
git commit -m "docs: CLI Domain Refactor 完成"
```
