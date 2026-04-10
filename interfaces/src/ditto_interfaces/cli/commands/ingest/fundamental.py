"""Fundamental 域摄取命令."""

import typer

from ditto_interfaces.cli.commands.factory import (
    create_daily_command,
    create_instrument_command,
)

app = typer.Typer(help="基本面数据摄取")

# 双模式命令（按日期/按标的）
app.command("balance")(
    create_instrument_command(
        "balance_sheet",
        "摄取资产负债表",
        cli_path="ingest fundamental balance",
    )
)
app.command("income")(
    create_instrument_command(
        "income_statement",
        "摄取利润表",
        cli_path="ingest fundamental income",
    )
)
app.command("cash-flow")(
    create_instrument_command(
        "cash_flow",
        "摄取现金流量表",
        cli_path="ingest fundamental cash-flow",
    )
)
app.command("dividend")(
    create_instrument_command(
        "dividend",
        "摄取分红送配",
        cli_path="ingest fundamental dividend",
    )
)

# 公司行为（仅按日期）
_corporate_actions_impl = create_daily_command("corporate_actions", "摄取公司行为")


@app.command("corporate-actions")
def corporate_actions(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取公司行为."""
    return _corporate_actions_impl(ctx, date, force)
