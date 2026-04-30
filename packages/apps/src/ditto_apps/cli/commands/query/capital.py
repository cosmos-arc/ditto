"""CLI capital 域查询命令."""

from collections.abc import Generator
from contextlib import contextmanager

import typer
from ditto_app.query.capital import CapitalQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade
from rich.console import Console
from rich.table import Table

from ditto_apps.cli.utils.identifier import resolve_identifier_for_cli
from ditto_apps.cli.utils.output import (
    TABLE_DISPLAY_LIMIT,
    output_json,
    print_truncated_hint,
)
from ditto_apps.cli.utils.validation import parse_date
from ditto_apps.models.capital import (
    to_margin_list,
    to_valuation_list,
)
from ditto_apps.registry.contexts import create_query_context

app = typer.Typer(help="资本数据查询")
console = Console()


@contextmanager
def _get_facades() -> Generator[
    tuple[CapitalQueryFacade, MetadataQueryFacade], None, None
]:
    """获取 CapitalQueryFacade 和 MetadataQueryFacade 实例."""
    with create_query_context() as ctx:
        yield (ctx.capital, ctx.metadata)


@app.command("margin")
def get_margin(
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
    查询融资融券数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
        ditto query capital margin -i 1000001 --date 2024-12-31
        ditto query capital margin -s 000001.XSHE --date 2024-12-31
        ditto query capital margin -t 000001 --date 2024-12-31

    """
    as_of = parse_date(as_of_date).date()
    with _get_facades() as (facade, metadata_facade):
        resolved_id = resolve_identifier_for_cli(
            metadata_facade,
            instrument_id=instrument_id,
            ticker=ticker,
            standard_ticker=standard_ticker,
            as_of_date=as_of_date,
        )
        if resolved_id is None:
            typer.echo("未找到匹配的标的")
            return
        df = facade.get_margin_trading(resolved_id, as_of)

        if df.is_empty():
            typer.echo("未找到融资融券数据")
            return

        margins = to_margin_list(df)

        if json_output:
            output_json(margins)
            return

        table = Table(title="融资融券数据")
        table.add_column("日期", style="cyan")
        table.add_column("融资余额", style="yellow", justify="right")
        table.add_column("融券余额", style="yellow", justify="right")

        for margin in margins[:TABLE_DISPLAY_LIMIT]:
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
        print_truncated_hint(len(margins))


@app.command("valuation")
def get_valuation(
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
    查询估值指标数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
        ditto query capital valuation -i 1000001 --date 2024-12-31
        ditto query capital valuation -s 000001.XSHE --date 2024-12-31
        ditto query capital valuation -t 000001 --date 2024-12-31

    """
    as_of = parse_date(as_of_date).date()
    with _get_facades() as (facade, metadata_facade):
        resolved_id = resolve_identifier_for_cli(
            metadata_facade,
            instrument_id=instrument_id,
            ticker=ticker,
            standard_ticker=standard_ticker,
            as_of_date=as_of_date,
        )
        if resolved_id is None:
            typer.echo("未找到匹配的标的")
            return
        df = facade.get_valuation_metrics(resolved_id, as_of)

        if df.is_empty():
            typer.echo("未找到估值指标数据")
            return

        valuations = to_valuation_list(df)

        if json_output:
            output_json(valuations)
            return

        table = Table(title="估值指标数据")
        table.add_column("日期", style="cyan")
        table.add_column("PE", style="yellow", justify="right")
        table.add_column("PB", style="yellow", justify="right")
        table.add_column("市值", style="green", justify="right")

        for val in valuations[:TABLE_DISPLAY_LIMIT]:
            market_cap = f"{val.market_cap:,.0f}" if val.market_cap else "-"
            table.add_row(
                str(val.trade_date) if val.trade_date else "-",
                f"{val.pe_ratio:.2f}" if val.pe_ratio else "-",
                f"{val.pb_ratio:.2f}" if val.pb_ratio else "-",
                market_cap,
            )

        console.print(table)
        print_truncated_hint(len(valuations))
