"""Ditto CLI 主入口."""

import typer

from ditto_port.cli.commands.stock import app as stock_app

app = typer.Typer(
    name="ditto",
    help="Ditto 量化系统命令行工具",
    no_args_is_help=True,
    add_completion=True,
)

# 注册命令组
app.add_typer(stock_app, name="stock")


@app.callback()
def main(
    ctx: typer.Context,
    data_root: str = typer.Option(None, "--data-root", "-d", help="数据根目录"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出模式"),
) -> None:
    """初始化 CLI 上下文."""
    ctx.ensure_object(dict)

    # 延迟初始化 DataHub，存储配置供后续使用
    ctx.obj["data_root"] = data_root
    ctx.obj["verbose"] = verbose


@app.command()
def version() -> None:
    """显示版本信息."""
    typer.echo("ditto-cli v0.1.0")


if __name__ == "__main__":
    app()
