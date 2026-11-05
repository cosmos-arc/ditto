"""Market 域回补命令 (stock/etf/index/adj/status)."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import (
    _raise_if_backfill_failed,
    create_backfill_command,
)
from ditto_apps.cli.context import create_executor
from ditto_apps.cli.utils.output import print_backfill_summary
from ditto_apps.cli.utils.validation import validate_date_format

app = typer.Typer(help="行情数据回补")

# daily (stock/etf/index 日行情) — 注册顺序即 --help 命令面板顺序
app.command("stock")(create_backfill_command("stock_daily", "回补股票日行情."))
app.command("etf")(create_backfill_command("etf_daily", "回补ETF日行情."))
app.command("index")(create_backfill_command("index_daily", "回补指数日行情."))

# adj (复权因子) — --fund 通道切换数据集
_adj_factor_impl = create_backfill_command("adj_factor", "回补股票复权因子")
_fund_adj_impl = create_backfill_command("fund_adj", "回补ETF/基金复权因子")


@app.command("adj")
def adj(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
    fund: bool = typer.Option(False, "--fund", help="回补ETF/基金复权因子"),
) -> None:
    """回补复权因子."""
    if fund:
        return _fund_adj_impl(ctx, start, end, parallel)
    return _adj_factor_impl(ctx, start, end, parallel)


# nav (ETF 单位净值, #196 P2)
app.command("nav")(create_backfill_command("etf_nav", "回补ETF单位净值 (#196 P2)."))

# status (股票状态)
app.command("status")(create_backfill_command("stock_status", "回补股票状态."))

# futures/index valuation (期货日线与指数估值, #658 批次4)
app.command("futures")(
    create_backfill_command("futures_daily", "回补期货日线(六所实际合约, #658 批次4).")
)
app.command("index-valuation")(
    create_backfill_command("index_valuation", "回补指数估值(#658 批次4).")
)

# limit (涨跌停价格, #517) — --force 行级补数通道 #575
_stock_limit_impl = create_backfill_command("stock_limit", "回补股票涨跌停价格")


@app.command("limit")
def limit(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
    force: bool = typer.Option(
        False,
        "--force",
        help="连 COMPLETE 检查点的月份 chunk 一并重拉; 行级补数通道 #575",
    ),
) -> None:
    """回补股票涨跌停价格 (#517)."""
    if not force:
        return _stock_limit_impl(ctx, start, end, parallel)
    validate_date_format(start)
    validate_date_format(end)
    with create_executor() as executor:
        result = executor.backfill_range(
            "stock_limit", start, end, parallel, include_complete=True
        )
        print_backfill_summary(result)
        _raise_if_backfill_failed(result)
