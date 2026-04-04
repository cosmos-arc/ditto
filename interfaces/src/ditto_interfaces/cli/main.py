"""Ditto CLI 主入口."""

import typer

from ditto_interfaces.cli.commands.backfill import app as backfill_app
from ditto_interfaces.cli.commands.ingest import app as ingest_app
from ditto_interfaces.cli.commands.init import app as init_app
from ditto_interfaces.cli.commands.query import app as query_app
from ditto_interfaces.cli.commands.strategy import app as strategy_app

app = typer.Typer(
    name="ditto",
    help="Ditto 量化系统命令行工具",
    no_args_is_help=True,
    add_completion=True,
)

# 注册命令组
app.add_typer(init_app, name="init")
app.add_typer(ingest_app, name="ingest")
app.add_typer(backfill_app, name="backfill")
app.add_typer(query_app, name="query")
app.add_typer(strategy_app, name="strategy")


@app.callback()
def main(
    ctx: typer.Context,
    data_root: str = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出模式"),
) -> None:
    """初始化 CLI 上下文."""
    ctx.ensure_object(dict)

    # 存储配置供后续使用（显式传递，不再设置 os.environ）
    ctx.obj["data_root"] = data_root
    ctx.obj["verbose"] = verbose


@app.command()
def version() -> None:
    """显示版本信息."""
    typer.echo("ditto-cli v0.1.0")


if __name__ == "__main__":
    app()
