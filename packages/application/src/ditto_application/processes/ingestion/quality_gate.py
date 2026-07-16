"""Write-time L1/L2 quality gate for ingestion pipelines."""

from __future__ import annotations

import polars as pl
from ditto_data.models.ingestion import IngestionResult
from ditto_platform.foundation import WriteResult

from ditto_application.contracts import CheckDataQualityCommand
from ditto_application.processes.ingestion.ports import QualityCheckerProtocol
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler


def run_write_quality_gate(
    df: pl.DataFrame,
    *,
    dataset: str,
    trade_date: str,
    quality_checker: QualityCheckerProtocol | None,
    result_handler: IngestionResultHandler,
) -> tuple[pl.DataFrame, IngestionResult | None]:
    """Return checked rows and a fail-closed result when L1/L2 blocks the write."""
    if quality_checker is None:
        return df, None
    checked_df, should_block = quality_checker.handle(
        CheckDataQualityCommand(
            df=df,
            dataset=dataset,
            context={"trade_date": trade_date},
        ),
    )
    if not should_block:
        return checked_df, None
    return checked_df, result_handler.handle_dq_blocked(
        dataset,
        trade_date,
        WriteResult(
            file_path="",
            checksum="",
            rows_written=0,
            rows_total=df.height,
            blocked=True,
        ),
    )
