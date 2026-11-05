"""Capital 域回补命令."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import (
    _raise_if_backfill_failed,
    create_backfill_command,
)
from ditto_apps.cli.context import create_executor
from ditto_apps.cli.utils.output import print_backfill_summary
from ditto_apps.cli.utils.validation import validate_date_format

app = typer.Typer(help="资本面数据回补")

# 估值指标 / 融资融券 / 股权质押
app.command("valuation")(create_backfill_command("valuation_metrics", "回补估值指标."))
app.command("margin")(create_backfill_command("margin_trading", "回补融资融券."))
app.command("pledge")(create_backfill_command("pledge_ratio", "回补股权质押."))


@app.command("index-weight")
def index_weight(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """
    回补指数成分股权重 (#196).

    月度观察事实，按权重服务宇宙（宽基+风格）逐指数年度区间回补.
    """
    validate_date_format(start)
    validate_date_format(end)

    with create_executor() as executor:
        result = executor.backfill_index_weight(start, end, parallel)
        print_backfill_summary(result)
        _raise_if_backfill_failed(result)


# ── #518-#523/#627 增补回补命令 ──
app.command("moneyflow")(
    create_backfill_command("moneyflow", "回补个股资金流向 (#518).")
)
app.command("cyq")(create_backfill_command("cyq_perf", "回补每日筹码及胜率 (#523)."))
app.command("hk-hold")(create_backfill_command("hk_hold", "回补沪深港通持股 (#520)."))
app.command("hsgt-top10")(
    create_backfill_command("hsgt_top10", "回补沪深港通十大成交股 (#520).")
)
app.command("top-list")(
    create_backfill_command("top_list", "回补龙虎榜个股明细 (#519).")
)
app.command("top-inst")(
    create_backfill_command("top_inst", "回补龙虎榜席位明细 (#519).")
)
app.command("limit-list")(
    create_backfill_command("limit_list", "回补涨跌停与炸板名单 (#519).")
)
app.command("fund-share")(create_backfill_command("fund_share", "回补基金份额 (#522)."))
app.command("fina-indicator")(
    create_backfill_command("fina_indicator", "回补官方口径财务指标 (#521).")
)
app.command("portfolio")(
    create_backfill_command("fund_portfolio", "回补基金季度持仓 (#522).")
)
app.command("top10-holders")(
    create_backfill_command("top10_holders", "回补前十大股东 (#627).")
)
app.command("top10-floatholders")(
    create_backfill_command("top10_floatholders", "回补前十大流通股东 (#627).")
)
