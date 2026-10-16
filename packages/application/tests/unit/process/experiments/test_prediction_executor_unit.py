"""Unit tests for the prediction-driven backtest leg (#565 W3).

Covers the frozen PredictionExecutorBinding contract, its semantics-level
snapshot cross-checks, the frozen raw-score pipeline, the bundle-builder
mutual exclusion, and the published-record → frozen frame adapter.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_analysis.experiments.model_lineage import (
    ModelPredictionRecord,
    ModelPredictionRow,
)
from ditto_application.builders.service_factory import (
    build_frozen_prediction_pipeline,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution._factor_bundle import (
    build_prediction_aware_bundle_builder,
)
from ditto_application.processes.execution.backtest_process import (
    BacktestServiceOptions,
)
from ditto_application.processes.execution.factor_bridge import (
    build_backtest_input_bundle_builder,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    PREDICTION_EXECUTOR_IMPLEMENTATION_KEY,
    PredictionExecutorBinding,
)
from ditto_application.processes.experiments.model_predictions_frame import (
    prediction_frame_from_record,
    prediction_frame_parquet_bytes,
    prediction_input_evidence,
)
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceCollector

_REGISTRATION = "a" * 64
_OTHER_HASH = "b" * 64
_BAD_HASH = "not-a-hash"


def _binding(
    *,
    input_id: str = "model-predictions-fold-1",
    top_k: int = 3,
    implementation_key: str = PREDICTION_EXECUTOR_IMPLEMENTATION_KEY,
) -> PredictionExecutorBinding:
    return PredictionExecutorBinding(
        model_registration_hash=_REGISTRATION,
        model_kind="linear",
        predictions_input_id=input_id,
        predictions_content_hash=_OTHER_HASH,
        predictions_schema_hash=_OTHER_HASH,
        top_k=top_k,
        implementation_key=implementation_key,
        executor_contract_version=1,
    )


def test_prediction_binding_freezes_identity_and_hash() -> None:
    binding = _binding()
    assert binding.binding_hash
    assert _binding() == binding
    assert _binding(top_k=5) != binding
    assert binding.as_payload()["implementation_key"] == (
        PREDICTION_EXECUTOR_IMPLEMENTATION_KEY
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"model_registration_hash": _BAD_HASH},
        {"model_kind": "deepnet"},
        {"predictions_input_id": ""},
        {"predictions_content_hash": _BAD_HASH},
        {"predictions_schema_hash": _BAD_HASH},
        {"top_k": 0},
        {"implementation_key": "research.prediction.experimental.v9"},
        {"executor_contract_version": 2},
    ],
)
def test_prediction_binding_rejects_unregistered_identity(kwargs: dict) -> None:
    fields = {
        "model_registration_hash": _REGISTRATION,
        "model_kind": "linear",
        "predictions_input_id": "model-predictions-fold-1",
        "predictions_content_hash": _OTHER_HASH,
        "predictions_schema_hash": _OTHER_HASH,
        "top_k": 3,
        "implementation_key": PREDICTION_EXECUTOR_IMPLEMENTATION_KEY,
        "executor_contract_version": 1,
    }
    fields.update(kwargs)
    with pytest.raises(AppProcessError):
        PredictionExecutorBinding(**fields)


def test_bundle_builder_rejects_factor_and_prediction_conflict() -> None:
    class _Pipeline:
        pass

    with pytest.raises(AppProcessError) as error:
        build_backtest_input_bundle_builder(
            compiled=object(),  # type: ignore[arg-type]
            pipeline=_Pipeline(),  # type: ignore[arg-type]
            data_feed=object(),  # type: ignore[arg-type]
            strategy_id="s",
            run_id="r",
            prediction_signals=pl.DataFrame(
                {"instrument_id": [], "signal_value": []},
                schema={"instrument_id": pl.String, "signal_value": pl.Float64},
            ),
        )
    assert error.value.details["reason"] == "prediction_and_factor_signals_conflict"


def test_options_carry_prediction_signals_without_compiled() -> None:
    frame = pl.DataFrame(
        {"instrument_id": ["000001.SZ"], "signal_value": [0.5]},
        schema={"instrument_id": pl.String, "signal_value": pl.Float64},
    )
    options = BacktestServiceOptions(prediction_signals=frame)
    assert options.prediction_signals is frame
    assert options.compiled_expressions is None


def _record() -> ModelPredictionRecord:
    return ModelPredictionRecord(
        schema="ditto.model.prediction-artifact.v1",
        registration_hash=_REGISTRATION,
        model_artifact_hash=_OTHER_HASH,
        prediction_window_start="2026-01-02",
        prediction_window_end="2026-01-05",
        rows=(
            ModelPredictionRow("2000001", "2026-01-02", 0.25),
            ModelPredictionRow("2000002", "2026-01-02", 0.75),
            ModelPredictionRow("2000001", "2026-01-05", 0.5),
        ),
    )


def test_prediction_frame_from_record_projects_contract() -> None:
    frame = prediction_frame_from_record(_record(), source_snapshot_id="snap-1")
    assert frame.schema == {
        "trade_date": pl.Date,
        "instrument_id": pl.Int64,
        "signal_value": pl.Float64,
        "source_snapshot_id": pl.String,
    }
    assert frame.height == 3
    assert frame.get_column("trade_date").to_list() == [
        date(2026, 1, 2),
        date(2026, 1, 2),
        date(2026, 1, 5),
    ]
    assert frame.get_column("source_snapshot_id").unique().to_list() == ["snap-1"]


def test_prediction_frame_round_trips_through_content_addressing() -> None:
    frame = prediction_frame_from_record(_record(), source_snapshot_id="snap-1")
    evidence = prediction_input_evidence(
        prediction_frame_parquet_bytes(frame),
        input_id="model-predictions-fold-1",
    )
    assert evidence.artifact_kind == "predictions"
    assert evidence.input_id == "model-predictions-fold-1"
    assert len(evidence.content_hash) == 64
    # Identical frames address identically; drifted frames do not.
    same = prediction_input_evidence(
        prediction_frame_parquet_bytes(frame),
        input_id="model-predictions-fold-1",
    )
    drifted = prediction_frame_from_record(_record(), source_snapshot_id="snap-2")
    other = prediction_input_evidence(
        prediction_frame_parquet_bytes(drifted),
        input_id="model-predictions-fold-1",
    )
    assert same == evidence
    assert other.content_hash != evidence.content_hash


def test_prediction_frame_adapter_rejects_bad_contracts() -> None:
    record = _record()
    with pytest.raises(AppProcessError):
        prediction_frame_from_record(record, source_snapshot_id="  ")
    # Empty frames refuse at the shared contract gate.
    empty = prediction_frame_from_record(record, source_snapshot_id="snap-1").filter(
        pl.lit(False),
    )
    with pytest.raises(AppProcessError) as error:
        prediction_frame_parquet_bytes(empty)
    assert error.value.details["reason"] == "prediction_frame_empty"
    # Duplicate (trade_date, instrument_id) keys refuse even when the bytes
    # arrive from an arbitrary producer rather than a published record.
    duplicated = pl.DataFrame(
        {
            "trade_date": [date(2026, 1, 2), date(2026, 1, 2)],
            "instrument_id": [2000001, 2000001],
            "signal_value": [0.25, 0.75],
            "source_snapshot_id": ["snap-1", "snap-1"],
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "signal_value": pl.Float64,
            "source_snapshot_id": pl.String,
        },
    )
    # Non-canonical (ticker-style) identities refuse instead of mapping onto
    # the wrong integer instrument.
    with pytest.raises(AppProcessError) as ticker_error:
        prediction_frame_from_record(
            ModelPredictionRecord(
                schema=record.schema,
                registration_hash=record.registration_hash,
                model_artifact_hash=record.model_artifact_hash,
                prediction_window_start=record.prediction_window_start,
                prediction_window_end=record.prediction_window_end,
                rows=(ModelPredictionRow("000001.SZ", "2026-01-02", 0.25),),
            ),
            source_snapshot_id="snap-1",
        )
    assert ticker_error.value.details["reason"] == "prediction_entity_not_canonical"
    with pytest.raises(AppProcessError) as dup_error:
        prediction_frame_parquet_bytes(duplicated)
    assert dup_error.value.details["reason"] == "prediction_frame_duplicate_keys"


def test_prediction_builder_refuses_unscored_session() -> None:
    frame = pl.DataFrame(
        {
            "trade_date": [date(2026, 1, 2)],
            "instrument_id": [2000001],
            "signal_value": [0.5],
            "source_snapshot_id": ["snap-1"],
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "signal_value": pl.Float64,
            "source_snapshot_id": pl.String,
        },
    )

    class _Ctx:
        class time_context:  # noqa: N801
            trade_date = "2026-01-05"

    builder = build_prediction_aware_bundle_builder(
        prediction_signals=frame,
        data_feed=None,  # type: ignore[arg-type]
        strategy_id="s",
        run_id="r",
    )
    with pytest.raises(AppProcessError) as error:
        builder(_Ctx())  # type: ignore[arg-type]
    assert error.value.details["reason"] == "prediction_session_scores_missing"


def test_prediction_pipeline_drops_unscored_instruments() -> None:
    pipeline = build_frozen_prediction_pipeline(
        _binding(top_k=3),
        evidence_sink=SelectionEvidenceCollector(),
    )
    frame = pl.DataFrame(
        {
            "instrument_id": [2000001, 2000002],
            "signal_value": [0.5, None],
        },
        schema={"instrument_id": pl.Int64, "signal_value": pl.Float64},
    ).with_columns(pl.col("signal_value").alias("score"))
    scored = pipeline.stages[2].process(frame, None)  # type: ignore[arg-type]
    # The unscored instrument carries no signal: it must not ride into
    # top-k selection on identity ordering.
    assert scored.get_column("instrument_id").to_list() == [2000001]


def test_prediction_frame_refuses_null_contract_values() -> None:
    nulled = pl.DataFrame(
        {
            "trade_date": [date(2026, 1, 2), date(2026, 1, 5)],
            "instrument_id": [2000001, 2000002],
            "signal_value": [0.5, None],
            "source_snapshot_id": ["snap-1", "snap-1"],
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "signal_value": pl.Float64,
            "source_snapshot_id": pl.String,
        },
    )
    with pytest.raises(AppProcessError) as error:
        prediction_frame_parquet_bytes(nulled)
    assert error.value.details["reason"] == "prediction_frame_null_values"
    assert error.value.details["column"] == "signal_value"


def test_prediction_frame_refuses_full_width_identity() -> None:
    record = _record()
    fullwidth = ModelPredictionRecord(
        schema=record.schema,
        registration_hash=record.registration_hash,
        model_artifact_hash=record.model_artifact_hash,
        prediction_window_start=record.prediction_window_start,
        prediction_window_end=record.prediction_window_end,
        rows=(ModelPredictionRow("\uff11\uff12\uff13", "2026-01-02", 0.25),),
    )
    with pytest.raises(AppProcessError) as error:
        prediction_frame_from_record(fullwidth, source_snapshot_id="snap-1")
    assert error.value.details["reason"] == "prediction_entity_not_canonical"
