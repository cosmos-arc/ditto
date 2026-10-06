"""Capital 域回补命令."""

from __future__ import annotations

import typer

from ditto_apps.cli.commands.factory import create_backfill_command

app = typer.Typer(help="资本面数据回补")

# 估值指标
_valuation_impl = create_backfill_command("valuation_metrics", "回补估值指标")

# 融资融券
_margin_impl = create_backfill_command("margin_trading", "回补融资融券")

# 股权质押
_pledge_impl = create_backfill_command("pledge_ratio", "回补股权质押")


@app.command("valuation")
def valuation(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补估值指标."""
    return _valuation_impl(ctx, start, end, parallel)


@app.command("margin")
def margin(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补融资融券."""
    return _margin_impl(ctx, start, end, parallel)


@app.command("pledge")
def pledge(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补股权质押."""
    return _pledge_impl(ctx, start, end, parallel)


# ── #518-#523 增补回补命令 ──
_moneyflow_bf = create_backfill_command("moneyflow", "回补个股资金流向")
_cyq_perf_bf = create_backfill_command("cyq_perf", "回补每日筹码及胜率")
_hk_hold_bf = create_backfill_command("hk_hold", "回补沪深港通持股")
_hsgt_top10_bf = create_backfill_command("hsgt_top10", "回补沪深港通十大成交股")
_top_list_bf = create_backfill_command("top_list", "回补龙虎榜个股明细")
_top_inst_bf = create_backfill_command("top_inst", "回补龙虎榜席位明细")
_limit_list_bf = create_backfill_command("limit_list", "回补涨跌停与炸板名单")
_fund_share_bf = create_backfill_command("fund_share", "回补基金份额")
_fina_indicator_bf = create_backfill_command("fina_indicator", "回补官方口径财务指标")
_fund_portfolio_bf = create_backfill_command("fund_portfolio", "回补基金季度持仓")


@app.command("moneyflow")
def moneyflow(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补个股资金流向 (#518)."""
    return _moneyflow_bf(ctx, start, end, parallel)


@app.command("cyq")
def cyq(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补每日筹码及胜率 (#523)."""
    return _cyq_perf_bf(ctx, start, end, parallel)


@app.command("hk-hold")
def hk_hold(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补沪深港通持股 (#520)."""
    return _hk_hold_bf(ctx, start, end, parallel)


@app.command("hsgt-top10")
def hsgt_top10(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补沪深港通十大成交股 (#520)."""
    return _hsgt_top10_bf(ctx, start, end, parallel)


@app.command("top-list")
def top_list(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补龙虎榜个股明细 (#519)."""
    return _top_list_bf(ctx, start, end, parallel)


@app.command("top-inst")
def top_inst(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补龙虎榜席位明细 (#519)."""
    return _top_inst_bf(ctx, start, end, parallel)


@app.command("limit-list")
def limit_list(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补涨跌停与炸板名单 (#519)."""
    return _limit_list_bf(ctx, start, end, parallel)


@app.command("fund-share")
def fund_share(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补基金份额 (#522)."""
    return _fund_share_bf(ctx, start, end, parallel)


@app.command("fina-indicator")
def fina_indicator(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补官方口径财务指标 (#521)."""
    return _fina_indicator_bf(ctx, start, end, parallel)


@app.command("portfolio")
def portfolio(
    ctx: typer.Context,
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="并行度"),
) -> None:
    """回补基金季度持仓 (#522)."""
    return _fund_portfolio_bf(ctx, start, end, parallel)
