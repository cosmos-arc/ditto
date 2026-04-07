"""CLI fundamental 域查询命令."""

from collections.abc import Generator
from contextlib import contextmanager

import typer
from ditto_app.query.fundamental import FundamentalQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade
from rich.console import Console
from rich.table import Table

from ditto_interfaces.cli.utils.identifier import resolve_identifier_for_cli
from ditto_interfaces.cli.utils.output import (
    TABLE_DISPLAY_LIMIT,
    output_json,
    print_truncated_hint,
)
from ditto_interfaces.cli.utils.validation import parse_date, validate_date_range
from ditto_interfaces.models.fundamental import (
    FinancialType,
    to_corporate_action_list,
    to_dividend_list,
    to_financial_list,
)
from ditto_interfaces.registry.contexts import create_query_context

app = typer.Typer(help="基本面数据查询")
console = Console()


@contextmanager
def _get_facades() -> Generator[
    tuple[FundamentalQueryFacade, MetadataQueryFacade], None, None
]:
    """获取 FundamentalQueryFacade 和 MetadataQueryFacade 实例."""
    with create_query_context() as ctx:
        yield (ctx.fundamental, ctx.metadata)


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

        df = None
        if financial_type == FinancialType.BALANCE_SHEET:
            df = facade.get_balance_sheet(resolved_id, as_of)
        elif financial_type == FinancialType.INCOME_STATEMENT:
            df = facade.get_income_statement(resolved_id, as_of)
        elif financial_type == FinancialType.CASH_FLOW:
            df = facade.get_cash_flow(resolved_id, as_of)

        if df is None or df.is_empty():
            typer.echo("未找到财务数据")
            return

        financials = to_financial_list(df, financial_type)

        if json_output:
            output_json(financials)
            return

        table = Table(title=f"财务报表 - {report_type}")
        table.add_column("标的 ID", style="cyan")
        table.add_column("报告期", style="white")
        table.add_column("报表类型", style="yellow")

        for fin in financials[:TABLE_DISPLAY_LIMIT]:
            table.add_row(
                str(fin.instrument_id),
                fin.report_date or "-",
                fin.report_type or "-",
            )

        console.print(table)
        print_truncated_hint(len(financials))


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

        df = facade.get_dividend(resolved_id, as_of)

        if df is None or df.is_empty():
            typer.echo("未找到分红数据")
            return

        dividends = to_dividend_list(df)

        if json_output:
            output_json(dividends)
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
    validate_date_range(start_date, end_date)
    start = parse_date(start_date).date()
    end = parse_date(end_date).date()

    with _get_facades() as (facade, metadata_facade):
        resolved_id = resolve_identifier_for_cli(
            metadata_facade,
            instrument_id=instrument_id,
            ticker=ticker,
            standard_ticker=standard_ticker,
        )
        if resolved_id is None:
            typer.echo("未找到匹配的标的")
            return

        df = facade.list_corporate_actions(resolved_id, start, end)

        if df.is_empty():
            typer.echo("未找到公司行动数据")
            return

        actions = to_corporate_action_list(df)

        if json_output:
            output_json(actions)
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
