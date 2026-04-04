"""CLI market 域查询命令."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import orjson
import typer
from ditto_app.query.market import MarketQueryFacade
from rich.console import Console
from rich.table import Table

from ditto_interfaces.cli.context import create_cli_host
from ditto_interfaces.models.market import to_bar_list

_TABLE_DISPLAY_LIMIT = 20

app = typer.Typer(help="行情数据查询")
console = Console()


@contextmanager
def _get_market_facade() -> Generator[MarketQueryFacade, None, None]:
    """获取 MarketQueryFacade 实例."""
    with create_cli_host() as bundle:
        yield MarketQueryFacade(market_service=bundle.market_service)


def _output_json(items: list[Any]) -> None:
    """输出 JSON 格式."""
    data = [item.model_dump() for item in items]
    typer.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())


def _output_json_dicts(data: list[dict[str, Any]]) -> None:
    """输出字典列表的 JSON 格式."""
    typer.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())


def _print_truncated_hint(total: int) -> None:
    """打印分页提示."""
    typer.echo(f"\n共 {total} 条记录, 仅显示前 {_TABLE_DISPLAY_LIMIT} 条")


def _parse_date(value: str) -> datetime:
    """解析日期字符串."""
    return datetime.strptime(value, "%Y-%m-%d")


def _validate_date_range(start_date: str, end_date: str) -> None:
    """验证日期范围."""
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start > end:
        typer.secho(
            f"错误: start_date ({start_date}) 不能大于 end_date ({end_date})",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)


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
    _validate_date_range(start_date, end_date)

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
            _output_json(bars)
            return

        table = Table(title=f"K 线数据 (标的 {instrument_id})")
        table.add_column("日期", style="cyan")
        table.add_column("开盘", style="green", justify="right")
        table.add_column("最高", style="red", justify="right")
        table.add_column("最低", style="green", justify="right")
        table.add_column("收盘", style="yellow", justify="right")
        table.add_column("成交量", style="white", justify="right")

        for bar in bars[:_TABLE_DISPLAY_LIMIT]:
            table.add_row(
                str(bar.trade_date),
                f"{bar.open:.2f}",
                f"{bar.high:.2f}",
                f"{bar.low:.2f}",
                f"{bar.close:.2f}",
                f"{bar.volume:,.0f}",
            )

        console.print(table)
        _print_truncated_hint(len(bars))


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
            _output_json_dicts(df.to_dicts())
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
