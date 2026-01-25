"""交易日历命令."""

import typer

from ditto_port.cli.context import create_executor
from ditto_port.cli.utils.output import print_ingestion_result

app = typer.Typer(help="交易日历命令", invoke_without_command=True)


@app.command()
def update(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """更新交易日历."""
    with create_executor() as executor:
        result = executor.ingest_daily("calendar", "", force)
        print_ingestion_result(result, ctx.obj["verbose"])


@app.callback()
def calendar(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """交易日历命令."""
    # 当没有子命令时，执行默认更新操作
    if ctx.invoked_subcommand is None:
        ctx.invoke(update, ctx=ctx, force=force)
