"""Unit tests for governed model-candidate fold orchestration (#565 W1).

Covers the stage taxonomy (data/label/train/publish), publish-first success,
byte-stable crash replay, and the fold-level PIT counterexamples: future
label mutations and post-cutoff knowledge must not change early training.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

import polars as pl
import pytest
from ditto_analysis.experiments.model_lineage import (
    ModelCandidateLineage,
    ModelKind,
    TrainFittedTransformSpec,
)
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import DateWindow, FoldRole, LeaseFence
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.model_artifact_publication import (
    IndexedModelArtifactSink,
)
from ditto_application.processes.experiments.model_candidate_folds import (
    ModelCandidateFoldFailure,
    ModelCandidateFoldRequest,
    ModelCandidateFoldSuccess,
    ModelFoldData,
    ModelFoldInputBinding,
    ModelFoldInputKind,
    ModelFoldInputSet,
    execute_model_candidate_fold,
)
from ditto_application.research_validation_windows import ValidationFoldPlan
from ditto_features.evaluation.research_labels import label_spec_hash

_START = date(2026, 3, 2)
SESSIONS = tuple(_START + timedelta(days=index) for index in range(30))
ENTITIES = ("000001.SZ", "000002.SZ", "600000.SH")
_EPOCH_BASE = 5_000_000_000_000_000
_KNOWLEDGE_CUTOFF = _EPOCH_BASE + 60 * 86_400_000_000
_TRAINED_AT = _KNOWLEDGE_CUTOFF + 1
_LABEL_HASH = label_spec_hash()
_CODE_ENV = {
    "implementation_key": "ditto_application.model_candidates.ridge.v1",
    "python": "3.13.14",
    "lockfile_sha256": "b" * 64,
}
_EXPERIMENT = ExperimentId("experiment-1")
_CANDIDATE = CandidateId("candidate-1")
_FOLD = FoldId("fold-1")
_FINGERPRINT = ContentHash("1" * 64)
_FENCE = LeaseFence(experiment_id=_EXPERIMENT, owner_token="owner-1", revision=3)
_NOW_US = 1_000_000


def _binding(kind: ModelFoldInputKind) -> ModelFoldInputBinding:
    digest = hashlib.sha256(kind.value.encode()).hexdigest()
    return ModelFoldInputBinding(
        kind=kind,
        input_id=f"model-fold-{kind.value}",
        content_hash=digest,
        schema_hash=digest,
        source_snapshot_ids=("snap-test-1",),
    )


def _inputs() -> ModelFoldInputSet:
    return ModelFoldInputSet(
        label_prices=_binding(ModelFoldInputKind.LABEL_PRICES),
        feature_frame=_binding(ModelFoldInputKind.FEATURES),
        calendar=_binding(ModelFoldInputKind.CALENDAR),
    )


def _price_frame(
    *,
    sessions: tuple[date, ...] = SESSIONS,
    unfillable_entry_sessions: tuple[date, ...] = (),
    corrupt_prices_after: date | None = None,
) -> pl.DataFrame:
    rows: dict[str, list[object]] = {
        "instrument_id": [],
        "session": [],
        "open": [],
        "close": [],
        "adj_factor": [],
        "buy_fillable_open": [],
        "sell_fillable_close": [],
        "session_close_known_at_epoch_us": [],
    }
    for offset, instrument in enumerate(ENTITIES):
        for index, session in enumerate(sessions):
            base = 10.0 + offset
            multiplier = (
                7.0
                if corrupt_prices_after is not None and session > corrupt_prices_after
                else 1.0
            )
            rows["instrument_id"].append(instrument)
            rows["session"].append(session)
            rows["open"].append((base + index) * multiplier)
            rows["close"].append((base + 0.5 + index) * multiplier)
            rows["adj_factor"].append(1.0)
            rows["buy_fillable_open"].append(session not in unfillable_entry_sessions)
            rows["sell_fillable_close"].append(True)
            rows["session_close_known_at_epoch_us"].append(
                _EPOCH_BASE + index * 86_400_000_000
            )
    schema = {
        "instrument_id": pl.String,
        "session": pl.Date,
        "open": pl.Float64,
        "close": pl.Float64,
        "adj_factor": pl.Float64,
        "buy_fillable_open": pl.Boolean,
        "sell_fillable_close": pl.Boolean,
        "session_close_known_at_epoch_us": pl.Int64,
    }
    return pl.DataFrame(rows, schema=schema)


def _feature_frame() -> pl.DataFrame:
    rows: dict[str, list[object]] = {
        "instrument_id": [],
        "session": [],
        "momentum_20d": [],
        "ep_ttm": [],
    }
    for offset, instrument in enumerate(ENTITIES):
        for index, session in enumerate(SESSIONS):
            rows["instrument_id"].append(instrument)
            rows["session"].append(session)
            rows["momentum_20d"].append(float(offset * 0.1 + (index % 7) * 0.05))
            rows["ep_ttm"].append(float(offset * 0.2 + (index % 5) * 0.03))
    return pl.DataFrame(
        rows,
        schema={
            "instrument_id": pl.String,
            "session": pl.Date,
            "momentum_20d": pl.Float64,
            "ep_ttm": pl.Float64,
        },
    )


def _lineage() -> ModelCandidateLineage:
    return ModelCandidateLineage(
        model_kind=ModelKind.LINEAR,
        feature_names=("momentum_20d", "ep_ttm"),
        label_id="research.label.forward_return.next_open_hold5.v1",
        label_spec_hash=_LABEL_HASH,
        transform_spec=TrainFittedTransformSpec(),
        hyperparameters={"alpha": 1.0},
        seed=7,
        code_environment=dict(_CODE_ENV),
    )


def _fold_plan() -> ValidationFoldPlan:
    return ValidationFoldPlan(
        ordinal=1,
        role=FoldRole.WALK_FORWARD,
        train_window=DateWindow(start=SESSIONS[0], end=SESSIONS[19]),
        test_window=DateWindow(start=SESSIONS[25], end=SESSIONS[29]),
        purge_sessions=5,
        embargo_sessions=5,
    )


def _request(
    *,
    prices: pl.DataFrame | None = None,
    features: pl.DataFrame | None = None,
    attempt_id: AttemptId | None = None,
    knowledge_cutoff: int = _KNOWLEDGE_CUTOFF,
) -> ModelCandidateFoldRequest:
    return ModelCandidateFoldRequest(
        experiment_id=_EXPERIMENT,
        candidate_id=_CANDIDATE,
        fold_id=_FOLD,
        attempt_id=attempt_id,
        lineage=_lineage(),
        fold=_fold_plan(),
        inputs=_inputs(),
        snapshot_id="snap-test-1",
        knowledge_cutoff_epoch_us=knowledge_cutoff,
        trained_at_epoch_us=_TRAINED_AT,
        reproduction_fingerprint=_FINGERPRINT,
    )


class MemoryFoldDataPort:
    """Test port returning preset frames; refuses on demand."""

    def __init__(self, data: ModelFoldData | None, error: Exception | None = None):
        self._data = data
        self._error = error

    def load(self, inputs: ModelFoldInputSet) -> ModelFoldData:
        if self._error is not None:
            raise self._error
        assert self._data is not None
        return self._data


def _data(
    *,
    prices: pl.DataFrame | None = None,
    features: pl.DataFrame | None = None,
    sessions: tuple[date, ...] = SESSIONS,
) -> ModelFoldData:
    return ModelFoldData(
        feature_frame=features if features is not None else _feature_frame(),
        label_prices=(
            prices if prices is not None else _price_frame(sessions=sessions)
        ),
        trading_sessions=sessions,
    )


def _execute(
    request: ModelCandidateFoldRequest,
    *,
    artifact_service,
    data_port=None,
    sink=None,
):
    if sink is None:
        sink = IndexedModelArtifactSink(artifact_service)
    return execute_model_candidate_fold(
        request,
        data_port=data_port if data_port is not None else MemoryFoldDataPort(_data()),
        sink=sink,
        lease_fence=_FENCE,
        now_epoch_us=_NOW_US,
    )


def test_fold_execution_publishes_all_artifacts(artifact_service) -> None:
    result = _execute(_request(), artifact_service=artifact_service)
    assert isinstance(result, ModelCandidateFoldSuccess)
    assert len(result.artifacts) == 4
    joined_ids = "".join(record.artifact_id for record in result.artifacts)
    assert result.training.artifact_hash[:16] in joined_ids
    # Label statistics partition the fold-span decision samples.
    stats = result.labels
    assert stats.decision_sample_count == 3 * 25  # decisions 0..24 x 3 instruments
    assert (
        stats.mature
        + stats.mature_after_cutoff
        + stats.unfillable_entry
        + stats.unfillable_exit
        + stats.path_incomplete
        == stats.decision_sample_count
    )
    assert stats.mature == stats.decision_sample_count
    assert stats.mature_after_cutoff == 0
    # Training-side isolation is surfaced as evidence.
    assert result.isolation.retained_sample_count == 45


def test_data_port_failure_maps_to_data_stage(artifact_service) -> None:
    port = MemoryFoldDataPort(
        None,
        AppProcessError(
            "port refused", details={"code": "X", "reason": "hash_mismatch"}
        ),
    )
    result = _execute(_request(), data_port=port, artifact_service=artifact_service)
    assert isinstance(result, ModelCandidateFoldFailure)
    assert result.stage == "data"
    assert result.reason == "hash_mismatch"


def test_data_port_wrong_return_type_refused(artifact_service) -> None:
    class BadPort:
        def load(self, inputs: ModelFoldInputSet) -> ModelFoldData:
            return object()  # type: ignore[return-value]

    result = _execute(
        _request(),
        data_port=BadPort(),  # type: ignore[arg-type]
        artifact_service=artifact_service,
    )
    assert isinstance(result, ModelCandidateFoldFailure)
    assert (result.stage, result.reason) == ("data", "fold_data_invalid")


def test_label_build_failure_maps_to_label_stage(artifact_service) -> None:
    broken = _price_frame().drop("adj_factor")
    result = _execute(
        _request(),
        data_port=MemoryFoldDataPort(_data(prices=broken)),
        artifact_service=artifact_service,
    )
    assert isinstance(result, ModelCandidateFoldFailure)
    assert result.stage == "label"
    assert result.reason == "price_frame_schema_invalid"


def test_train_failure_maps_to_train_stage(artifact_service) -> None:
    # No label is mature at an early cutoff, so training refuses.
    result = _execute(
        _request(knowledge_cutoff=_EPOCH_BASE + 2 * 86_400_000_000),
        artifact_service=artifact_service,
    )
    assert isinstance(result, ModelCandidateFoldFailure)
    assert result.stage == "train"
    assert result.reason == "no_mature_training_samples"


def test_publish_failure_maps_to_publish_stage(artifact_service) -> None:
    class FailingSink:
        def publish_training(self, *args: object, **kwargs: object) -> object:
            raise AppProcessError("publish refused", details={"reason": "lease_lost"})

        def publish_predictions(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("training publish must fail first")

    result = _execute(
        _request(),
        artifact_service=artifact_service,
        sink=FailingSink(),  # type: ignore[arg-type]
    )
    assert isinstance(result, ModelCandidateFoldFailure)
    assert (result.stage, result.reason) == ("publish", "lease_lost")


def test_crash_replay_is_idempotent(artifact_service, memory_artifact_index) -> None:
    first = _execute(_request(), artifact_service=artifact_service)
    second = _execute(_request(), artifact_service=artifact_service)
    assert isinstance(first, ModelCandidateFoldSuccess)
    assert isinstance(second, ModelCandidateFoldSuccess)
    assert [record.artifact_id for record in first.artifacts] == [
        record.artifact_id for record in second.artifacts
    ]
    assert first.training.artifact_hash == second.training.artifact_hash
    assert len(memory_artifact_index.records) == 4


@pytest.mark.pit
def test_future_price_mutation_leaves_training_unchanged(artifact_service) -> None:
    baseline = _execute(_request(), artifact_service=artifact_service)
    assert isinstance(baseline, ModelCandidateFoldSuccess)
    mutated = _execute(
        _request(),
        data_port=MemoryFoldDataPort(
            _data(prices=_price_frame(corrupt_prices_after=SESSIONS[23]))
        ),
        artifact_service=artifact_service,
    )
    assert isinstance(mutated, ModelCandidateFoldSuccess)
    # Early training artifacts are byte-identical despite post-window prices.
    assert baseline.training.artifact_hash == mutated.training.artifact_hash
    assert baseline.training.model_state_sha256 == mutated.training.model_state_sha256
    assert [row.prediction for row in baseline.predictions.rows] == [
        row.prediction for row in mutated.predictions.rows
    ]


@pytest.mark.pit
def test_predictions_restricted_to_test_window(artifact_service) -> None:
    result = _execute(_request(), artifact_service=artifact_service)
    assert isinstance(result, ModelCandidateFoldSuccess)
    sessions = {row.decision_session for row in result.predictions.rows}
    expected = {SESSIONS[index].isoformat() for index in range(25, 30)}
    assert sessions == expected
    assert len(result.predictions.rows) == 15


def test_unfillable_entry_counted_in_statistics(artifact_service) -> None:
    # Instrument-independent fillability: sessions 5..8 unfillable at open
    # make decisions 4..7 unfillable for every instrument.
    prices = _price_frame(unfillable_entry_sessions=SESSIONS[5:9])
    result = _execute(
        _request(),
        data_port=MemoryFoldDataPort(_data(prices=prices)),
        artifact_service=artifact_service,
    )
    assert isinstance(result, ModelCandidateFoldSuccess)
    assert result.labels.unfillable_entry == 3 * 4
    assert result.labels.mature == 3 * 25 - 3 * 4
    assert result.labels.mature_after_cutoff == 0


@pytest.mark.pit
def test_mature_after_cutoff_kept_in_separate_bucket(artifact_service) -> None:
    # Cutoff at day 10: only decisions 0..5 (exit ordinal <= 10) are mature
    # as of the cutoff; the remaining fold-span labels mature later.
    result = _execute(
        _request(knowledge_cutoff=_EPOCH_BASE + 10 * 86_400_000_000),
        artifact_service=artifact_service,
    )
    assert isinstance(result, ModelCandidateFoldSuccess)
    stats = result.labels
    assert stats.mature == 3 * 6
    assert stats.mature_after_cutoff == 3 * 25 - 3 * 6
    assert stats.decision_sample_count == 3 * 25
    # Training only consumed the as-of mature, isolated decisions.
    assert result.isolation.retained_sample_count == 3 * 6


def test_statistics_restricted_to_fold_span(artifact_service) -> None:
    # A calendar extending ten sessions past the fold's test window yields
    # decisions beyond the span; statistics must not count them.
    extended = SESSIONS + tuple(
        _START + timedelta(days=index) for index in range(30, 40)
    )
    result = _execute(
        _request(),
        data_port=MemoryFoldDataPort(_data(sessions=extended)),
        artifact_service=artifact_service,
    )
    assert isinstance(result, ModelCandidateFoldSuccess)
    stats = result.labels
    assert stats.decision_sample_count == 3 * 30  # decisions 0..29 only
    assert stats.mature_after_cutoff == 0


def test_input_set_rejects_kind_field_mismatch() -> None:
    with pytest.raises(AppProcessError) as error:
        ModelFoldInputSet(
            label_prices=_binding(ModelFoldInputKind.FEATURES),
            feature_frame=_binding(ModelFoldInputKind.FEATURES),
            calendar=_binding(ModelFoldInputKind.CALENDAR),
        )
    assert error.value.details.get("reason") == "input_set_kind_field_mismatch"


def test_request_rejects_knowledge_cutoff_after_training_time() -> None:
    with pytest.raises(AppProcessError) as error:
        ModelCandidateFoldRequest(
            experiment_id=_EXPERIMENT,
            candidate_id=_CANDIDATE,
            fold_id=_FOLD,
            attempt_id=None,
            lineage=_lineage(),
            fold=_fold_plan(),
            inputs=_inputs(),
            snapshot_id="snap-test-1",
            knowledge_cutoff_epoch_us=_TRAINED_AT + 1,
            trained_at_epoch_us=_TRAINED_AT,
            reproduction_fingerprint=_FINGERPRINT,
        )
    assert "knowledge_cutoff_after_training_time" in str(error.value.details)


def test_request_rejects_invalid_binding_hash() -> None:
    with pytest.raises(AppProcessError) as error:
        ModelFoldInputBinding(
            kind=ModelFoldInputKind.FEATURES,
            input_id="features",
            content_hash="not-a-hash",
            schema_hash="0" * 64,
            source_snapshot_ids=("snap",),
        )
    assert error.value.details.get("reason") == "input_binding_hash_invalid"


def test_execute_requires_typed_lease(artifact_service) -> None:
    with pytest.raises(AppProcessError) as error:
        execute_model_candidate_fold(
            _request(),
            data_port=MemoryFoldDataPort(_data()),
            sink=IndexedModelArtifactSink(artifact_service),
            lease_fence="fence",  # type: ignore[arg-type]
            now_epoch_us=_NOW_US,
        )
    assert error.value.details.get("reason") == "fold_lease_invalid"


def test_attempt_id_flows_into_publication_path(artifact_service) -> None:
    request = _request(attempt_id=AttemptId("attempt-1"))
    result = _execute(request, artifact_service=artifact_service)
    assert isinstance(result, ModelCandidateFoldSuccess)
    paths = {record.relative_path for record in result.artifacts}
    assert all("attempts/attempt-1/" in path for path in paths)
