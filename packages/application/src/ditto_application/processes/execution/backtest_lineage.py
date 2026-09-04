"""Backtest run lineage mapping."""

from __future__ import annotations

from datetime import UTC, datetime

from ditto_backtest.manifest import InputRef, ReplayContextInputRef, RunManifest
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.lineage.contracts import (
    DataLineageRecorder,
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)
from ditto_platform.foundation import logger

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process_types import (
    BacktestLineageConfig,
)

__all__ = ["record_backtest_lineage"]


def _parse_manifest_timestamp(value: str) -> datetime:
    if not value:
        raise AppProcessError("manifest created_at is required for lineage")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppProcessError("manifest created_at is invalid") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _strategy_asset(
    manifest: RunManifest,
    config: BacktestLineageConfig,
) -> DataAssetRef:
    version = manifest.strategy_version or config.strategy_version
    partition_keys = (f"version={version}",) if version else ()
    return DataAssetRef(
        dataset_id=manifest.strategy_id or config.strategy_id,
        namespace="strategy",
        partition_keys=partition_keys,
    )


def _market_input_asset(ref: InputRef) -> DataAssetRef:
    start_date, end_date = ref.date_range
    return DataAssetRef(
        dataset_id="market_data",
        namespace="backtest_input",
        partition_keys=(
            f"source={ref.source}",
            f"instrument_id={ref.instrument_id}",
            f"start_date={start_date}",
            f"end_date={end_date}",
            f"data_hash={ref.data_hash}",
            f"source_snapshot_id={ref.source_snapshot_id}",
        ),
    )


def _context_input_asset(ref: ReplayContextInputRef) -> DataAssetRef:
    return DataAssetRef(
        dataset_id=ref.context_id,
        namespace="backtest_context_input",
        partition_keys=(
            f"content_hash={ref.content_hash}",
            f"as_of={ref.as_of}",
            f"knowledge_cutoff={ref.knowledge_cutoff}",
            f"publication_cutoff={ref.publication_cutoff}",
            *(
                f"source_snapshot_id={snapshot_id}"
                for snapshot_id in ref.source_snapshot_ids
            ),
        ),
    )


def _output_asset(run_id: str, config: BacktestLineageConfig) -> DataAssetRef:
    return DataAssetRef(
        dataset_id="backtest_report",
        namespace="backtest",
        partition_keys=(
            f"run_id={run_id}",
            f"strategy_id={config.strategy_id}",
            f"start_date={config.start_date}",
            f"end_date={config.end_date}",
        ),
    )


def _lineage_inputs(
    manifest: RunManifest,
    config: BacktestLineageConfig,
) -> tuple[LineageInputRef, ...]:
    return (
        LineageInputRef(
            asset=_strategy_asset(manifest, config),
            role="strategy",
        ),
        *(
            LineageInputRef(
                asset=_market_input_asset(input_ref),
                role="market_data",
            )
            for input_ref in manifest.input_ref_details
        ),
        *(
            LineageInputRef(
                asset=_context_input_asset(context_ref),
                role=context_ref.context_kind.value,
            )
            for context_ref in manifest.context_input_refs
        ),
    )


def record_backtest_lineage(
    *,
    recorder: DataLineageRecorder | None,
    run_id: str,
    config: BacktestLineageConfig,
    manifest: RunManifest | None,
) -> None:
    """Record a successful backtest run lineage event."""
    if recorder is None or manifest is None:
        return
    try:
        recorder.record_event(
            LineageEvent(
                run_id=run_id,
                operation="backtest",
                inputs=_lineage_inputs(manifest, config),
                outputs=(
                    LineageOutputRef(
                        asset=_output_asset(run_id, config),
                        role="backtest_report",
                    ),
                ),
                timestamp=_parse_manifest_timestamp(manifest.created_at),
            )
        )
    except Exception:
        logger.exception(
            "backtest_lineage_record_failed",
            event="backtest_lineage_record_error",
            run_id=run_id,
            strategy_id=config.strategy_id,
        )
