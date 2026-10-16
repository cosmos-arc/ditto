"""
Frozen prediction frames bridging model artifacts into research backtests (#565 W3).

Adapts the published ``ModelPredictionRecord`` rows into the exact Parquet
frame contract the frozen research backtest consumes: one row per
``(trade_date, instrument_id)`` carrying the frozen model score as
``signal_value``. The strategy layer keeps consuming a precomputed
``signal_value`` column — it never learns where the score came from, and
never imports analysis. Frame identity is content-addressed through the
same helpers every other research input uses.
"""

from __future__ import annotations

from io import BytesIO

import polars as pl
from ditto_analysis.experiments.model_lineage import ModelPredictionRecord

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    KEY_COLUMNS,
    REQUIRED_COLUMNS,
    ResearchFrameKind,
    research_artifact_content_hash,
    research_frame_schema_hash,
)

__all__ = [
    "prediction_frame_from_record",
    "prediction_frame_parquet_bytes",
    "prediction_input_evidence",
    "require_prediction_frame",
]

_PREDICTION_COLUMNS: tuple[tuple[str, pl.DataType], ...] = (
    ("trade_date", pl.Date()),
    ("instrument_id", pl.Int64()),
    ("signal_value", pl.Float64()),
    ("source_snapshot_id", pl.String()),
)


def _frame_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "prediction frame bridge failed closed",
        details={"code": "REPRODUCIBILITY_FAILED", "reason": reason, **details},
    )


def require_prediction_frame(frame: pl.DataFrame) -> None:
    """Validate the exact frozen prediction frame contract."""
    if type(frame) is not pl.DataFrame:
        raise _frame_error("prediction_frame_not_dataframe")
    schema = frame.schema
    for name, dtype in _PREDICTION_COLUMNS:
        if schema.get(name) != dtype:
            raise _frame_error(
                "prediction_frame_schema_invalid",
                column=name,
                expected=str(dtype),
                observed=str(schema.get(name)),
            )
    if set(schema) != set(REQUIRED_COLUMNS[ResearchFrameKind.PREDICTIONS]):
        raise _frame_error(
            "prediction_frame_columns_drift",
            expected=sorted(REQUIRED_COLUMNS[ResearchFrameKind.PREDICTIONS]),
            observed=sorted(schema),
        )
    if frame.is_empty():
        raise _frame_error("prediction_frame_empty")
    if (
        frame.select(list(KEY_COLUMNS[ResearchFrameKind.PREDICTIONS]))
        .is_duplicated()
        .any()
    ):
        raise _frame_error("prediction_frame_duplicate_keys")
    # Nulls anywhere in the frozen contract are evidence gaps, not missing
    # data to impute: is_finite ignores nulls, so check them explicitly.
    for column in ("trade_date", "instrument_id", "signal_value", "source_snapshot_id"):
        if frame.get_column(column).null_count():
            raise _frame_error("prediction_frame_null_values", column=column)
    if not frame.get_column("signal_value").is_finite().all():
        raise _frame_error("prediction_frame_values_non_finite")


def prediction_frame_from_record(
    predictions: ModelPredictionRecord,
    *,
    source_snapshot_id: str,
) -> pl.DataFrame:
    """
    Project one published prediction record into the frozen frame contract.

    ``decision_session`` becomes ``trade_date`` and ``entity_id`` becomes
    ``instrument_id``; every row carries the one source snapshot identity
    the caller binds (the model artifact's snapshot), so downstream trust
    boundaries can verify provenance exactly like market frames.
    """
    if type(predictions) is not ModelPredictionRecord:
        raise _frame_error("prediction_record_invalid")
    if type(source_snapshot_id) is not str or not source_snapshot_id.strip():
        raise _frame_error("prediction_source_snapshot_invalid")
    canonical_ids: list[int] = []
    for row in predictions.rows:
        entity = row.entity_id
        # The backtest joins on canonical integer instrument ids; refuse
        # non-canonical (e.g. ticker-style or zero-padded) identities rather
        # than silently mapping them onto the wrong instrument.
        if (
            not entity.isascii()
            or not entity.isdecimal()
            or (len(entity) > 1 and entity.startswith("0"))
        ):
            raise _frame_error(
                "prediction_entity_not_canonical",
                entity_id=entity,
            )
        try:
            canonical_ids.append(int(entity))
        except ValueError as error:
            raise _frame_error(
                "prediction_entity_not_canonical",
                entity_id=entity,
            ) from error
    frame = pl.DataFrame(
        {
            "trade_date": [row.decision_session for row in predictions.rows],
            "instrument_id": canonical_ids,
            "signal_value": [row.prediction for row in predictions.rows],
            "source_snapshot_id": [source_snapshot_id] * len(predictions.rows),
        },
        schema={
            "trade_date": pl.String,
            "instrument_id": pl.Int64,
            "signal_value": pl.Float64,
            "source_snapshot_id": pl.String,
        },
    )
    # decision_session is ISO text; parse under the pinned strict format so
    # lenient variants (2026/01/05, 2026-1-5) refuse instead of passing.
    frame = frame.with_columns(pl.col("trade_date").str.to_date("%Y-%m-%d"))
    frame = frame.sort(["trade_date", "instrument_id"])
    require_prediction_frame(frame)
    return frame


def prediction_frame_parquet_bytes(frame: pl.DataFrame) -> bytes:
    """Serialize one contract-valid prediction frame to exact Parquet bytes."""
    require_prediction_frame(frame)
    buffer = BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def prediction_input_evidence(
    artifact_bytes: bytes,
    *,
    input_id: str,
) -> ContentAddressedResearchInput:
    """Content-address the exact prediction frame bytes for snapshot binding."""
    frame = pl.read_parquet(BytesIO(artifact_bytes))
    require_prediction_frame(frame)
    if type(input_id) is not str or not input_id.strip():
        raise _frame_error("prediction_input_id_invalid")
    return ContentAddressedResearchInput(
        artifact_kind=ResearchFrameKind.PREDICTIONS.value,
        input_id=input_id,
        content_hash=research_artifact_content_hash(artifact_bytes),
        schema_hash=research_frame_schema_hash(frame),
    )
