"""CLI 摄取命令共享工具。"""

from __future__ import annotations

import typer

from ditto_interfaces.cli.context import create_executor
from ditto_interfaces.cli.utils.output import print_ingestion_result


def run_instrument_ingest(  # noqa: PLR0913
    ctx: typer.Context,
    dataset: str,
    ticker: str | None,
    standard_ticker: str | None,
    instrument_id: int | None,
    start: str | None,
    end: str | None,
    force: bool,
) -> None:
    """执行按标的摄取."""
    with create_executor() as executor:
        result = executor.ingest_by_instrument(
            dataset=dataset,
            ticker=ticker,
            standard_ticker=standard_ticker,
            instrument_id=instrument_id,
            start_date=start or "",
            end_date=end or "",
            force=force,
        )
        print_ingestion_result(result, ctx.obj["verbose"])
