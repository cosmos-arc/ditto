"""Fundamental 域摄取命令."""

from pathlib import Path

import typer

from ditto_apps.cli.commands.factory import (
    create_daily_command,
    create_instrument_command,
)
from ditto_apps.cli.context import create_executor
from ditto_apps.cli.utils.output import output_json_dict
from ditto_apps.cli.utils.validation import validate_date_range

app = typer.Typer(help="基本面数据摄取")


@app.command("portfolio-report")
def portfolio_report(
    evidence: Path = typer.Option(..., "--evidence", exists=True, dir_okay=False),
    document: Path = typer.Option(..., "--document", exists=True, dir_okay=False),
) -> None:
    """附加人工核实的原文与元数据；校验文档及持仓内容哈希，拒绝覆盖证据。"""
    with create_executor() as executor:
        result = executor.coordinator.register_fund_report(
            evidence.read_bytes(), document.read_bytes()
        )
    output_json_dict(result)


@app.command("portfolio-batch")
def portfolio_batch(
    start: str = typer.Option(..., "--start"),
    end: str = typer.Option(..., "--end"),
    after: str = typer.Option("", "--after"),
    limit: int = typer.Option(100, "--limit", min=1, max=1000),
    roster_sha256: str = typer.Option("", "--roster-sha256"),
) -> None:
    """逐基金有界摄取; 续跑使用上批 next_after 与 roster_sha256。"""
    validate_date_range(start, end)
    with create_executor() as executor:
        result = executor.coordinator.ingest_fund_portfolio_batch(
            start,
            end,
            after=after,
            limit=limit,
            roster_sha256=roster_sha256,
        )
        output_json_dict(result)
        if result["failed"]:
            raise typer.Exit(1)


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
# #434 业绩预告/快报（公告日全市场或按标的回填）
app.command("forecast")(
    create_instrument_command(
        "earnings_forecast",
        "摄取业绩预告",
        cli_path="ingest fundamental forecast",
    )
)
app.command("express")(
    create_instrument_command(
        "earnings_express",
        "摄取业绩快报",
        cli_path="ingest fundamental express",
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


# ── #521/#522 增补：官方财务指标/基金持仓 ──
app.command("fina-indicator")(
    create_instrument_command(
        "fina_indicator",
        "摄取官方口径财务指标",
        cli_path="ingest fundamental fina-indicator",
    )
)
app.command("portfolio")(
    create_instrument_command(
        "fund_portfolio",
        "摄取公募披露持仓",
        cli_path="ingest fundamental portfolio",
    )
)
