"""CLI metadata 域查询命令."""

from collections.abc import Generator
from contextlib import contextmanager

import polars as pl
import typer
from ditto_app.query.metadata import MetadataQueryFacade
from rich.console import Console
from rich.table import Table

from ditto_interfaces.cli.context import create_cli_host
from ditto_interfaces.cli.utils.output import (
    TABLE_DISPLAY_LIMIT,
    output_json,
    output_json_single,
    print_truncated_hint,
)
from ditto_interfaces.models.metadata import to_instrument_list

app = typer.Typer(help="标的元数据查询")
console = Console()


@contextmanager
def _get_metadata_facade() -> Generator[MetadataQueryFacade, None, None]:
    """获取 MetadataQueryFacade 实例."""
    with create_cli_host() as bundle:
        yield MetadataQueryFacade(metadata_service=bundle.metadata_service)


@app.command("instruments")
def query_instruments(
    source_ticker: str | None = typer.Option(None, "--ticker", "-t", help="股票代码"),
    asset_class: str | None = typer.Option(
        None, "--asset-class", "-a", help="资产类型 (stock/etf/index)"
    ),
    exchange: str | None = typer.Option(None, "--exchange", "-e", help="交易所"),
    is_active: bool | None = typer.Option(True, "--active", help="只显示活跃标的"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询标的列表.

    示例:
        ditto query metadata instruments -t 600000
        ditto query metadata instruments --asset-class stock --exchange SH
        ditto query metadata instruments -a etf

    """
    with _get_metadata_facade() as facade:
        source_tickers = [source_ticker] if source_ticker else None

        df = facade.find_securities(
            source_tickers=source_tickers,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
        )

        if df.is_empty():
            typer.echo("未找到匹配的标的")
            return

        instruments = to_instrument_list(df)

        if json_output:
            output_json(instruments)
            return

        table = Table(title="标的列表")
        table.add_column("ID", style="cyan")
        table.add_column("代码", style="green")
        table.add_column("名称", style="white")
        table.add_column("类型", style="yellow")
        table.add_column("交易所", style="blue")

        for inst in instruments[:TABLE_DISPLAY_LIMIT]:
            table.add_row(
                str(inst.instrument_id),
                inst.ticker or "-",
                inst.name or "-",
                inst.asset_class.value if inst.asset_class else "-",
                inst.exchange or "-",
            )

        console.print(table)
        print_truncated_hint(len(instruments))


@app.command("instrument")
def get_instrument(
    instrument_id: int = typer.Argument(..., help="标的 ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询单个标的详情.

    示例:
        ditto query metadata instrument 1

    """
    with _get_metadata_facade() as facade:
        result = facade.get_instrument(instrument_id)

        if result is None:
            typer.secho(f"未找到标的 ID: {instrument_id}", fg=typer.colors.RED)
            raise typer.Exit(1)

        df = pl.DataFrame([result])
        inst = to_instrument_list(df)[0]

        if json_output:
            output_json_single(inst)
            return

        table = Table(title=f"标的详情 - {inst.ticker}")
        table.add_column("属性", style="cyan")
        table.add_column("值", style="white")

        table.add_row("ID", str(inst.instrument_id))
        table.add_row("代码", inst.ticker or "-")
        table.add_row("名称", inst.name or "-")
        table.add_row("类型", inst.asset_class.value if inst.asset_class else "-")
        table.add_row("交易所", inst.exchange or "-")
        table.add_row("上市日期", str(inst.list_date) if inst.list_date else "-")
        table.add_row("活跃状态", "是" if inst.is_active else "否")

        console.print(table)
