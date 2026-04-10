"""CLI 命令参数分组类型与摄取辅助函数."""

from __future__ import annotations

from dataclasses import dataclass

from click import get_current_context

from ditto_interfaces.cli.context import create_executor
from ditto_interfaces.cli.utils.output import print_ingestion_result


@dataclass(frozen=True)
class CLIIngestOptions:
    """
    CLI 摄取选项分组.

    将标识符、时间范围和控制标志组合为单一对象，
    减少函数参数数量并提高可读性。
    """

    ticker: str | None
    standard_ticker: str | None
    instrument_id: int | None
    start: str | None
    end: str | None
    force: bool


def run_instrument_ingest(dataset: str, params: CLIIngestOptions) -> None:
    """执行按标的摄取."""
    ctx = get_current_context()
    with create_executor() as executor:
        result = executor.ingest_by_instrument(
            dataset=dataset,
            ticker=params.ticker,
            standard_ticker=params.standard_ticker,
            instrument_id=params.instrument_id,
            start_date=params.start or "",
            end_date=params.end or "",
            force=params.force,
        )
        print_ingestion_result(result, ctx.obj["verbose"])
