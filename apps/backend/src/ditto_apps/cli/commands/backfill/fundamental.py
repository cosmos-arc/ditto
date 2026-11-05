"""Fundamental 域回补命令."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import create_backfill_command

app = typer.Typer(help="基本面数据回补")

# 财务报表
app.command("balance")(create_backfill_command("balance_sheet", "回补资产负债表."))
app.command("income")(create_backfill_command("income_statement", "回补利润表."))
app.command("cash-flow")(create_backfill_command("cash_flow", "回补现金流量表."))
app.command("dividend")(create_backfill_command("dividend", "回补分红送配."))

# 公司行为
app.command("corporate-actions")(
    create_backfill_command("corporate_actions", "回补公司行为.")
)

# #629 P5 支撑源：业绩预告/快报历史回补（公告日驱动，季块日级请求）
app.command("forecast")(
    create_backfill_command("earnings_forecast", "回补业绩预告（市场级公告日驱动）.")  # noqa: RUF001 — 帮助文本与收敛前逐字一致
)
app.command("express")(
    create_backfill_command("earnings_express", "回补业绩快报（市场级公告日驱动）.")  # noqa: RUF001 — 帮助文本与收敛前逐字一致
)
