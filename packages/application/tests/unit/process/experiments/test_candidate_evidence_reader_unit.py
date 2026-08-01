"""Candidate evidence bundle and opaque cursor contract tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    AttemptPersistenceSpec,
    AttemptProjection,
    AttemptView,
    BacktestRunId,
    CheckpointRef,
    ExperimentFailureCode,
    ExperimentStage,
    ExperimentStatus,
    LeaseFence,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import (
    candidate_evidence_reader as reader_module,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FoldSelectionTraceArtifactKind,
)
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CANDIDATE_EVIDENCE_ARTIFACT_KIND,
    CandidateEvidenceReader,
    CandidateEvidenceResourceKind,
    build_candidate_evidence_bundle,
    decode_candidate_evidence_cursor,
    encode_candidate_evidence_cursor,
)
from ditto_strategy.alpha.selection_evidence import (
    ExclusionEvidence,
    ExclusionReason,
    FactorContributionEvidence,
    InitialUniverseEvidence,
    SelectionEvidence,
    SelectionEvidenceLog,
    SelectionExposureDeclaration,
    SelectionExposureEvidence,
    SelectionExposurePolicy,
    SelectionExposureSizeBucket,
)
from packages.application.tests.unit.process.experiments.walk_forward_evidence_collection_fixtures import (  # noqa: E501
    BASELINE_ID,
    CANDIDATE_ID,
    NOW,
    NOW_US,
    build_case,
    trace_identity,
)


def _trace(fold_ordinal: int) -> SelectionEvidenceLog:
    trade_date = f"202{fold_ordinal + 2}-01-01"
    return SelectionEvidenceLog(
        initial_universe=(InitialUniverseEvidence(trade_date, 2, 1),),
        exclusions=(
            ExclusionEvidence(
                trade_date,
                2,
                "selector",
                ExclusionReason.BELOW_TOP_K,
            ),
        ),
        factor_contributions=(
            FactorContributionEvidence(
                trade_date,
                1,
                "momentum_1m",
                0.4,
                0.4,
                0.8,
                0.5,
                0.4,
                0.4,
                1,
                True,
            ),
        ),
        selections=(SelectionEvidence(trade_date, 1, 0.4, 1, True),),
        exposure_declarations=(
            SelectionExposureDeclaration.from_policy(
                trade_date,
                SelectionExposurePolicy.stock(),
            ),
        ),
        exposures=(
            SelectionExposureEvidence(
                trade_date,
                1,
                1.0,
                "bank",
                50_000_000_000.0,
                SelectionExposureSizeBucket.MID,
            ),
        ),
    )


def test_bundle_freezes_two_fold_lineage_and_stable_resource_order(tmp_path) -> None:
    case = build_case(tmp_path, trace_publish_indices=())
    # Reuse the same valid fence fields used by the fixture's artifact writer.
    for fold, attempt in zip(case.folds, case.attempts, strict=True):
        evidence = (
            SelectionEvidenceLog()
            if fold.spec.key.candidate_id == BASELINE_ID
            else _trace(fold.spec.ordinal)
        )
        case.trace_adapter.publish(
            trace_identity(fold, attempt),
            evidence,
            lease_fence=LeaseFence(
                fold.spec.key.experiment_id,
                "evidence-owner",
                1,
                NOW_US + 1_000_000,
            ),
            now_epoch_us=NOW_US,
        )

    collected = case.assemble()
    bundle = build_candidate_evidence_bundle(
        collected,
        candidate_id=str(CANDIDATE_ID),
        comparison_revision=7,
    )

    assert bundle.manifest["comparison_payload_hash"] == str(
        collected.comparison.content_hash
    )
    assert [source["validation_fold_ordinal"] for source in bundle.fold_sources] == [
        2,
        3,
    ]
    assert [item["validation_fold_ordinal"] for item in bundle.selections] == [2, 3]
    assert [item["validation_fold_ordinal"] for item in bundle.exclusions] == [2, 3]
    assert [
        item["validation_fold_ordinal"] for item in bundle.factor_contributions
    ] == [2, 3]
    assert all(item["evidence_hash"] for item in bundle.selections)
    rows = tuple(
        row for row in collected.source_rows if row.candidate_id == CANDIDATE_ID
    )
    for source, row in zip(bundle.fold_sources, rows, strict=True):
        assert source["attempt_id"] == str(row.attempt_id)
        assert source["run_id"] == str(row.run_id)
        trace = next(
            item
            for item in collected.selection_traces
            if item.identity.attempt_id == row.attempt_id
        )
        for source_key, kind in (
            (
                "candidate_selections",
                FoldSelectionTraceArtifactKind.CANDIDATE_SELECTIONS,
            ),
            (
                "candidate_exclusions",
                FoldSelectionTraceArtifactKind.CANDIDATE_EXCLUSIONS,
            ),
            (
                "factor_contributions",
                FoldSelectionTraceArtifactKind.FACTOR_CONTRIBUTIONS,
            ),
        ):
            record = trace.receipt.record(kind)
            assert source[source_key] == {
                "artifact_id": record.artifact_id,
                "artifact_kind": record.artifact_kind,
                "content_hash": str(record.content_hash),
                "schema_version": 1,
            }


def test_cursor_binds_bundle_hash_kind_and_offset() -> None:
    content_hash = "a" * 64
    cursor = encode_candidate_evidence_cursor(
        content_hash=content_hash,
        resource_kind=CandidateEvidenceResourceKind.SELECTIONS,
        offset=20,
    )

    decoded = decode_candidate_evidence_cursor(
        cursor,
        expected_content_hash=content_hash,
        expected_resource_kind=CandidateEvidenceResourceKind.SELECTIONS,
    )

    assert decoded.offset == 20


def test_cursor_rejects_cross_kind_and_stale_bundle_hash() -> None:
    cursor = encode_candidate_evidence_cursor(
        content_hash="a" * 64,
        resource_kind=CandidateEvidenceResourceKind.SELECTIONS,
        offset=1,
    )

    with pytest.raises(AppProcessError) as cross_kind:
        decode_candidate_evidence_cursor(
            cursor,
            expected_content_hash="a" * 64,
            expected_resource_kind=CandidateEvidenceResourceKind.EXCLUSIONS,
        )
    assert cross_kind.value.details["code"] == ("INVALID_CANDIDATE_EVIDENCE_CURSOR")

    with pytest.raises(AppProcessError) as stale:
        decode_candidate_evidence_cursor(
            cursor,
            expected_content_hash="b" * 64,
            expected_resource_kind=CandidateEvidenceResourceKind.SELECTIONS,
        )
    assert stale.value.details["code"] == "EVIDENCE_STALE"


def test_bundle_uses_successful_retry_lineage_and_excludes_failed_parent(
    tmp_path,
) -> None:
    case = build_case(tmp_path, publish_indices=(0, 1, 3))
    parent = replace(
        case.attempts[2],
        projection=replace(
            case.attempts[2].projection,
            status=ExperimentStatus.FAILED,
            checkpoint_ref=CheckpointRef("checkpoint-1"),
            failure_code=ExperimentFailureCode.CANDIDATE_FAILED,
        ),
    )
    created_at = NOW + timedelta(seconds=1)
    successor_id = AttemptId("attempt:candidate-selected:wf-2:retry-2")
    successor = AttemptView(
        AttemptPersistenceSpec(
            successor_id,
            parent.spec.fold_key,
            2,
            parent.spec.attempt_id,
            parent.projection.backtest_run_id,
            parent.spec.reproduction_fingerprint,
            created_at,
        ),
        AttemptProjection(
            successor_id,
            ExperimentStatus.COMPLETED,
            BacktestRunId("run:candidate-selected:wf-2:retry-2"),
            None,
            None,
            created_at,
            created_at,
            1,
        ),
    )
    case.publish(case.folds[2], successor)
    collected = case.assemble(
        attempts=(
            case.attempts[3],
            successor,
            case.attempts[0],
            parent,
            case.attempts[1],
        )
    )

    bundle = build_candidate_evidence_bundle(
        collected,
        candidate_id=str(CANDIDATE_ID),
        comparison_revision=9,
    )

    selected_source = next(
        source
        for source in bundle.fold_sources
        if source["validation_fold_ordinal"] == 2
    )
    assert selected_source["attempt_id"] == str(successor_id)
    assert selected_source["run_id"] == str(successor.projection.backtest_run_id)
    assert all(
        source["attempt_id"] != str(parent.spec.attempt_id)
        for source in bundle.fold_sources
    )


def test_reader_rejects_same_comparison_hash_from_old_revision(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path)
    collected = case.assemble()
    old_bundle = build_candidate_evidence_bundle(
        collected,
        candidate_id=str(CANDIDATE_ID),
        comparison_revision=7,
    )
    old_record = SimpleNamespace(
        artifact_id=old_bundle.artifact_id,
        artifact_kind=CANDIDATE_EVIDENCE_ARTIFACT_KIND,
        candidate_id=CANDIDATE_ID,
        content_hash=old_bundle.content_hash,
        manifest={
            "audit": {
                **dict(old_bundle.manifest),
                "schema_version": 1,
            }
        },
    )
    store = MagicMock()
    store.load_snapshot.return_value = case.snapshot()
    store.list_status_events.return_value = (
        SimpleNamespace(
            reason_code="scheduler_stage_complete",
            stage=ExperimentStage.CANDIDATE_SELECTION,
            subject_revision=8,
        ),
    )
    store.list_experiment_artifacts.return_value = (old_record,)
    assembler = MagicMock()
    assembler.assemble.return_value = collected
    artifact_reader = MagicMock()
    artifact_reader.read_indexed_json.return_value = old_bundle.payload
    monkeypatch.setattr(
        reader_module,
        "read_unique_preflight_detail",
        lambda *_args: {},
    )
    monkeypatch.setattr(
        reader_module,
        "project_snapshot_manifest",
        lambda _detail: object(),
    )

    loaded = CandidateEvidenceReader(
        scheduler_store=store,
        walk_forward_assembler=assembler,
        artifact_service=artifact_reader,
    ).load_current_bundle(
        str(case.snapshot().launch_spec.experiment_id),
        str(CANDIDATE_ID),
    )

    assert loaded is None
    artifact_reader.read_indexed_json.assert_not_called()
