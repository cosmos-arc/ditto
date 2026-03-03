"""CLI capital 域查询命令."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import orjson
import typer
from ditto_datahub.services.capital_service import CapitalService
from rich.console import Console
from rich.table import Table

from ditto_port.cli.context import create_cli_host
from ditto_port.models.capital import (
    to_margin_list,
    to_valuation_list,
)

_TABLE_DISPLAY_LIMIT = 20

app = typer.Typer(help="资本数据查询")
console = Console()


@contextmanager
def _get_capital_service() -> Generator[CapitalService, None, None]:
    """获取 CapitalService 实例."""
    with create_cli_host() as bundle:
        yield bundle.capital_service


def _output_json(items: list[Any]) -> None:
    """输出 JSON 格式."""
    data = [item.model_dump() for item in items]
    typer.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())


def _print_truncated_hint(total: int) -> None:
    """打印分页提示."""
    typer.echo(f"\n共 {total} 条记录, 仅显示前 {_TABLE_DISPLAY_LIMIT} 条")


def _parse_date(value: str) -> datetime:
    """解析日期字符串."""
    return datetime.strptime(value, "%Y-%m-%d")


@app.command("margin")
def get_margin(
    instrument_id: str = typer.Option(..., "--instrument-id", "-i", help="标的 ID"),
    as_of_date: str = typer.Option(..., "--date", "-d", help="PIT 查询日期"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询融资融券数据.

    示例:
        ditto query capital margin -i 1 --date 2024-12-31

    """
    as_of = _parse_date(as_of_date).date()
    with _get_capital_service() as service:
        df = service.get_margin_trading(instrument_id, as_of)

        if df.is_empty():
            typer.echo("未找到融资融券数据")
            return

        margins = to_margin_list(df)

        if json_output:
            _output_json(margins)
            return

        table = Table(title="融资融券数据")
        table.add_column("日期", style="cyan")
        table.add_column("融资余额", style="yellow", justify="right")
        table.add_column("融券余额", style="yellow", justify="right")

        for margin in margins[:_TABLE_DISPLAY_LIMIT]:
            margin_bal = (
                f"{margin.margin_buy_balance:,.0f}"
                if margin.margin_buy_balance
                else "-"
            )
            short_bal = (
                f"{margin.short_sell_balance:,.0f}"
                if margin.short_sell_balance
                else "-"
            )
            table.add_row(
                str(margin.trade_date) if margin.trade_date else "-",
                margin_bal,
                short_bal,
            )

        console.print(table)
        _print_truncated_hint(len(margins))


@app.command("valuation")
def get_valuation(
    instrument_id: str = typer.Option(..., "--instrument-id", "-i", help="标的 ID"),
    as_of_date: str = typer.Option(..., "--date", "-d", help="PIT 查询日期"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询估值指标数据.

    示例:
        ditto query capital valuation -i 1 --date 2024-12-31

    """
    as_of = _parse_date(as_of_date).date()
    with _get_capital_service() as service:
        df = service.get_valuation_metrics(instrument_id, as_of)

        if df.is_empty():
            typer.echo("未找到估值指标数据")
            return

        valuations = to_valuation_list(df)

        if json_output:
            _output_json(valuations)
            return

        table = Table(title="估值指标数据")
        table.add_column("日期", style="cyan")
        table.add_column("PE", style="yellow", justify="right")
        table.add_column("PB", style="yellow", justify="right")
        table.add_column("市值", style="green", justify="right")

        for val in valuations[:_TABLE_DISPLAY_LIMIT]:
            market_cap = f"{val.market_cap:,.0f}" if val.market_cap else "-"
            table.add_row(
                str(val.trade_date) if val.trade_date else "-",
                f"{val.pe_ratio:.2f}" if val.pe_ratio else "-",
                f"{val.pb_ratio:.2f}" if val.pb_ratio else "-",
                market_cap,
            )

        console.print(table)
        _print_truncated_hint(len(valuations))
