"""CLI macro 域查询命令."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import orjson
import typer
from ditto_app.query.macro import MacroQueryFacade
from rich.console import Console
from rich.table import Table

from ditto_interfaces.cli.context import create_cli_host
from ditto_interfaces.models.macro import to_indicator_list

_TABLE_DISPLAY_LIMIT = 20

# 支持的枚举值（字符串）
_VALID_CATEGORIES = ("economic", "interest_rate", "exchange_rate", "money_supply")
_VALID_FREQUENCIES = ("daily", "monthly", "quarterly")

app = typer.Typer(help="宏观数据查询")
console = Console()


@contextmanager
def _get_macro_facade() -> Generator[MacroQueryFacade, None, None]:
    """获取 MacroQueryFacade 实例."""
    with create_cli_host() as bundle:
        yield MacroQueryFacade(macro_service=bundle.macro_service)


def _output_json(items: list[Any]) -> None:
    """输出 JSON 格式."""
    data = [item.model_dump() for item in items]
    typer.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())


def _output_json_dicts(data: list[dict[str, Any]]) -> None:
    """输出字典列表的 JSON 格式."""
    typer.echo(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())


def _print_truncated_hint(total: int) -> None:
    """打印分页提示."""
    typer.echo(f"\n共 {total} 条记录, 仅显示前 {_TABLE_DISPLAY_LIMIT} 条")


def _parse_date(value: str) -> datetime:
    """解析日期字符串."""
    return datetime.strptime(value, "%Y-%m-%d")


def _validate_date_range(start_date: str | None, end_date: str | None) -> None:
    """验证日期范围."""
    if start_date and end_date:
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        if start > end:
            typer.secho(
                f"错误: start_date ({start_date}) 不能大于 end_date ({end_date})",
                fg=typer.colors.RED,
            )
            raise typer.Exit(1)


def _validate_value(
    value: str | None,
    valid_values: tuple[str, ...],
    field_name: str,
) -> str | None:
    """验证字符串值是否在可选范围内."""
    if value is None:
        return None

    if value not in valid_values:
        typer.secho(
            f"错误: 无效的{field_name} '{value}', 可选: {', '.join(valid_values)}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    return value


@app.command("indicators")
def query_indicators(
    category: str | None = typer.Option(
        None,
        "--category",
        "-c",
        help="类别 (economic/interest_rate/exchange_rate/money_supply)",
    ),
    frequency: str | None = typer.Option(
        None, "--frequency", "-f", help="频率 (daily/monthly/quarterly)"
    ),
    start_date: str | None = typer.Option(None, "--start-date", "-s", help="开始日期"),
    end_date: str | None = typer.Option(None, "--end-date", "-e", help="结束日期"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    查询宏观指标数据.

    示例:
        ditto query macro indicators -c economic -s 2024-01-01 -e 2024-12-31
        ditto query macro indicators --frequency monthly

    """
    _validate_date_range(start_date, end_date)
    cat_value = _validate_value(category, _VALID_CATEGORIES, "类别")
    freq_value = _validate_value(frequency, _VALID_FREQUENCIES, "频率")

    with _get_macro_facade() as facade:
        df = facade.find_indicators(
            start=start_date,
            end=end_date,
            category=cat_value,
            frequency=freq_value,
        )

        if df.is_empty():
            typer.echo("未找到宏观指标数据")
            return

        indicators = to_indicator_list(df)

        if json_output:
            _output_json(indicators)
            return

        table = Table(title="宏观指标数据")
        table.add_column("日期", style="cyan")
        table.add_column("指标", style="green")
        table.add_column("值", style="yellow", justify="right")
        table.add_column("单位", style="white")

        for ind in indicators[:_TABLE_DISPLAY_LIMIT]:
            table.add_row(
                ind.date,
                ind.name or ind.code,
                f"{ind.value:,.4f}",
                ind.unit or "-",
            )

        console.print(table)
        _print_truncated_hint(len(indicators))


@app.command("metadata")
def list_metadata(
    category: str | None = typer.Option(
        None,
        "--category",
        "-c",
        help="类别过滤 (economic/interest_rate/exchange_rate/money_supply)",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
) -> None:
    """
    列出宏观指标元数据.

    示例:
        ditto query macro metadata
        ditto query macro metadata -c economic

    """
    cat_value = _validate_value(category, _VALID_CATEGORIES, "类别")

    with _get_macro_facade() as facade:
        df = facade.find_indicators(
            category=cat_value,
        )

        if df.is_empty():
            typer.echo("未找到宏观指标元数据")
            return

        subset_cols = ["indicator_id", "code", "name", "category", "frequency"]
        has_indicator_id = "indicator_id" in df.columns
        metadata_df = df.unique(subset=subset_cols) if has_indicator_id else df

        if json_output:
            _output_json_dicts(metadata_df.to_dicts())
            return

        table = Table(title="宏观指标元数据")
        table.add_column("ID", style="cyan")
        table.add_column("代码", style="green")
        table.add_column("名称", style="white")
        table.add_column("类别", style="yellow")
        table.add_column("频率", style="blue")

        for row in metadata_df.iter_rows(named=True):
            table.add_row(
                str(row.get("indicator_id", "-")),
                str(row.get("code", "-")),
                str(row.get("name", "-")),
                str(row.get("category", "-")),
                str(row.get("frequency", "-")),
            )

        console.print(table)
