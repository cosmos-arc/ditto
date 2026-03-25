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
def _get_services() -> Generator[
    tuple[FundamentalService, MetadataService], None, None
]:
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
        ditto query fundamental financials -i 1000001
            -r balance_sheet --date 2024-12-31
        ditto query fundamental financials -s 000001.XSHE
            -r balance_sheet --date 2024-12-31
        ditto query fundamental financials -t 000001
            -r balance_sheet --date 2024-12-31

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


@app.command("corporate-actions")
def list_corporate_actions(
    instrument_id: int | None = typer.Option(
        None, "--instrument-id", "-i", help="Canonical 标的 ID"
    ),
    ticker: str | None = typer.Option(None, "--ticker", "-t", help="裸代码, 如 000001"),
    standard_ticker: str | None = typer.Option(
        None, "--standard-ticker", "-s", help="标准代码, 如 000001.XSHE"
    ),
    start_date: str = typer.Option(..., "--start-date", help="开始日期"),
    end_date: str = typer.Option(..., "--end-date", "-e", help="结束日期"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询公司行动列表.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
        ditto query fundamental corporate-actions -i 1
            --start-date 2024-01-01 -e 2024-12-31
        ditto query fundamental corporate-actions -t 000001
            --start-date 2024-01-01 -e 2024-12-31

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
