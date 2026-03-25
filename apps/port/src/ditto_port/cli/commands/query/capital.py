"""CLI capital 域查询命令."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import orjson
import typer
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.metadata_service import MetadataService
from rich.console import Console
from rich.table import Table

from ditto_port.cli.context import create_cli_host
from ditto_port.models.capital import (
    to_margin_list,
    to_valuation_list,
)
from ditto_port.models.identifier import resolve_instrument_identifier

_TABLE_DISPLAY_LIMIT = 20

app = typer.Typer(help="资本数据查询")
console = Console()


@contextmanager
def _get_services() -> Generator[tuple[CapitalService, MetadataService], None, None]:
    """获取 CapitalService 和 MetadataService 实例."""
    with create_cli_host() as bundle:
        yield bundle.capital_service, bundle.metadata_service


def _resolve_identifier(
    metadata_service: MetadataService,
    *,
    instrument_id: int | None,
    ticker: str | None,
    standard_ticker: str | None,
    as_of_date: str | None = None,
) -> int | None:
    """
    解析标识符为 canonical instrument_id.

    至少提供一个标识符，委托给共享的 resolve_instrument_identifier。

    Returns:
        解析后的 canonical instrument_id (int)，查不到返回 None.

    """
    if not any([instrument_id, standard_ticker, ticker]):
        typer.echo("错误: 必须提供 --instrument-id、--ticker 或 --standard-ticker 之一")
        raise typer.Exit(code=1)

    return resolve_instrument_identifier(
        metadata_service,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        asof=as_of_date,
    )


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
    as_of = _parse_date(as_of_date).date()
    with _get_services() as (service, metadata_service):
        resolved_id = _resolve_identifier(
            metadata_service,
            instrument_id=instrument_id,
            ticker=ticker,
            standard_ticker=standard_ticker,
            as_of_date=as_of_date,
        )
        if resolved_id is None:
            typer.echo("未找到匹配的标的")
            return
        df = service.get_margin_trading(resolved_id, as_of)

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
    as_of = _parse_date(as_of_date).date()
    with _get_services() as (service, metadata_service):
        resolved_id = _resolve_identifier(
            metadata_service,
            instrument_id=instrument_id,
            ticker=ticker,
            standard_ticker=standard_ticker,
            as_of_date=as_of_date,
        )
        if resolved_id is None:
            typer.echo("未找到匹配的标的")
            return
        df = service.get_valuation_metrics(resolved_id, as_of)

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
