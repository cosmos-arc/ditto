"""CLI market 域查询命令."""

from collections.abc import Generator
from contextlib import contextmanager

import typer
from ditto_app.query.market import MarketQueryFacade
from rich.console import Console
from rich.table import Table

from ditto_interfaces.cli.context import create_cli_host
from ditto_interfaces.cli.utils.output import (
    TABLE_DISPLAY_LIMIT,
    output_json,
    output_json_dicts,
    print_truncated_hint,
)
from ditto_interfaces.cli.utils.validation import validate_date_range
from ditto_interfaces.models.market import to_bar_list

app = typer.Typer(help="行情数据查询")
console = Console()


@contextmanager
def _get_market_facade() -> Generator[MarketQueryFacade, None, None]:
    """获取 MarketQueryFacade 实例."""
    with create_cli_host() as bundle:
        yield MarketQueryFacade(market_service=bundle.market_service)


@app.command("bars")
def query_bars(
    instrument_id: int = typer.Option(..., "--instrument-id", "-i", help="标的 ID"),
    start_date: str = typer.Option(..., "--start-date", "-s", help="开始日期"),
    end_date: str = typer.Option(..., "--end-date", "-e", help="结束日期"),
    adjustment: str = typer.Option(
        "none", "--adjustment", "-a", help="复权类型 (none/qfq/hfq)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询 K 线数据.

    示例:
        ditto query market bars -i 1 -s 2024-01-01 -e 2024-12-31
        ditto query market bars -i 1 -s 2024-01-01 -e 2024-12-31 -a qfq

    """
    validate_date_range(start_date, end_date)

    with _get_market_facade() as facade:
        df = facade.find_bars(
            instrument_ids=[instrument_id],
            start=start_date,
            end=end_date,
            adj=adjustment,
        )

        if df.is_empty():
            typer.echo("未找到匹配的 K 线数据")
            return

        bars = to_bar_list(df)

        if json_output:
            output_json(bars)
            return

        table = Table(title=f"K 线数据 (标的 {instrument_id})")
        table.add_column("日期", style="cyan")
        table.add_column("开盘", style="green", justify="right")
        table.add_column("最高", style="red", justify="right")
        table.add_column("最低", style="green", justify="right")
        table.add_column("收盘", style="yellow", justify="right")
        table.add_column("成交量", style="white", justify="right")

        for bar in bars[:TABLE_DISPLAY_LIMIT]:
            table.add_row(
                str(bar.trade_date),
                f"{bar.open:.2f}",
                f"{bar.high:.2f}",
                f"{bar.low:.2f}",
                f"{bar.close:.2f}",
                f"{bar.volume:,.0f}",
            )

        console.print(table)
        print_truncated_hint(len(bars))


@app.command("constituents")
def get_constituents(
    index_id: int = typer.Argument(..., help="指数 ID"),
    as_of_date: str = typer.Option(..., "--date", "-d", help="查询日期"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询指数成分股.

    示例:
        ditto query market constituents 1 --date 2024-12-31

    """
    with _get_market_facade() as facade:
        df = facade.get_constituents(index_id, as_of_date)

        if df.is_empty():
            typer.echo("未找到成分股数据")
            return

        if json_output:
            output_json_dicts(df.to_dicts())
            return

        table = Table(title=f"指数成分股 (ID: {index_id}, 日期: {as_of_date})")
        table.add_column("成分 ID", style="cyan")
        table.add_column("权重", style="yellow", justify="right")

        for row in df.iter_rows(named=True):
            table.add_row(
                str(row.get("instrument_id", "-")),
                f"{row.get('weight', 0):.4f}",
            )

        console.print(table)
