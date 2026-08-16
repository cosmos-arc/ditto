"""Exact, bounded research evidence reads for governed consumers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

import orjson

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.backtest import BacktestQueryFacade
from ditto_application.queries.evaluation import (
    EvaluationOptions,
    FactorEvaluationFacade,
)
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)
from ditto_application.queries.experiments import (
    ExperimentArtifactReadModel,
    ExperimentDetailReadModel,
    ExperimentQueryFacade,
)
from ditto_application.queries.strategy import StrategyQueryFacade

__all__ = [
    "EvidenceTemporalContext",
    "FactorEvidenceQuery",
    "ResearchEvidenceKind",
    "ResearchEvidenceQueryFacade",
    "ResearchEvidenceReadModel",
]

_MAX_EXPERIMENT_RECORDS = 1_000
_SHA256_HEX_LENGTH = 64


class ResearchEvidenceKind(StrEnum):
    """Closed set of read-only research evidence capabilities."""

    EXPERIMENT = "experiment"
    FACTOR = "factor"
    STRATEGY = "strategy"
    BACKTEST = "backtest"


@dataclass(frozen=True, slots=True)
class FactorEvidenceQuery:
    """Exact factor evaluation identity without any latest-version fallback."""

    factor_id: str
    factor_version: int
    dataset_id: str
    catalog_snapshot_id: str
    universe: str
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchEvidenceReadModel:
    """One application-owned evidence result with explicit PIT provenance."""

    kind: ResearchEvidenceKind
    subject_id: str
    subject_version: str
    strategy_id: str | None
    strategy_version: str | None
    dataset_id: str | None
    temporal_context: EvidenceTemporalContext
    payload: EvidencePayloadReadModel
    artifact_refs: tuple[EvidenceArtifactReference, ...]
    lineage: tuple[str, ...]


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"research evidence failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _required(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _error(
            "EVIDENCE_IDENTITY_REQUIRED",
            "missing_or_noncanonical_identity",
            field=field_name,
        )
    return value


def _artifact_ref(artifact: ExperimentArtifactReadModel) -> EvidenceArtifactReference:
    return EvidenceArtifactReference(
        artifact_id=artifact.artifact_id,
        artifact_kind=artifact.artifact_kind,
        content_hash=artifact.content_hash,
        schema_hash=artifact.schema_hash,
    )


def _optional_identity(value: str | None, *, field_name: str) -> str | None:
    return None if value is None else _required(value, field_name=field_name)


def _matches_scope(
    *,
    item_candidate_id: str | None,
    item_fold_id: str | None,
    candidate_id: str | None,
    fold_id: str | None,
) -> bool:
    return (candidate_id is None or item_candidate_id == candidate_id) and (
        fold_id is None or item_fold_id == fold_id
    )


def _select_experiment_detail(
    detail: ExperimentDetailReadModel,
    *,
    candidate_id: str | None,
    fold_id: str | None,
) -> ExperimentDetailReadModel:
    candidates = tuple(
        item
        for item in detail.candidates
        if candidate_id is None or item.candidate_id == candidate_id
    )
    if candidate_id is not None and not candidates:
        raise _error("EVIDENCE_NOT_FOUND", "candidate_not_found")
    folds = tuple(
        item
        for item in detail.folds
        if _matches_scope(
            item_candidate_id=item.candidate_id,
            item_fold_id=item.fold_id,
            candidate_id=candidate_id,
            fold_id=fold_id,
        )
    )
    if fold_id is not None and not folds:
        raise _error("EVIDENCE_NOT_FOUND", "fold_not_found")
    return replace(detail, candidates=candidates, folds=folds)


class ResearchEvidenceQueryFacade:
    """Compose existing leaf queries behind exact, fail-closed evidence reads."""

    def __init__(
        self,
        *,
        experiment_query: ExperimentQueryFacade,
        factor_evaluation: FactorEvaluationFacade,
        strategy_query: StrategyQueryFacade,
        backtest_query: BacktestQueryFacade,
    ) -> None:
        self._experiment_query = experiment_query
        self._factor_evaluation = factor_evaluation
        self._strategy_query = strategy_query
        self._backtest_query = backtest_query

    def get_experiment_evidence(
        self,
        *,
        experiment_id: str,
        context: EvidenceTemporalContext,
        candidate_id: str | None = None,
        fold_id: str | None = None,
    ) -> ResearchEvidenceReadModel:
        """Read one experiment scope without exposing artifact storage paths."""
        experiment_id = _required(experiment_id, field_name="experiment_id")
        candidate_id = _optional_identity(candidate_id, field_name="candidate_id")
        fold_id = _optional_identity(fold_id, field_name="fold_id")
        detail = self._experiment_query.get(experiment_id)
        if detail is None:
            raise _error(
                "EVIDENCE_NOT_FOUND",
                "experiment_not_found",
                experiment_id=experiment_id,
            )
        if detail.experiment_id != experiment_id:
            raise _error("EVIDENCE_IDENTITY_MISMATCH", "experiment_identity_mismatch")
        if detail.snapshot_id != context.source_snapshot_id:
            raise _error(
                "EVIDENCE_SNAPSHOT_MISMATCH",
                "experiment_snapshot_mismatch",
                expected=context.source_snapshot_id,
                actual=detail.snapshot_id,
            )

        selected_detail = _select_experiment_detail(
            detail,
            candidate_id=candidate_id,
            fold_id=fold_id,
        )

        gates = tuple(
            gate
            for gate in self._experiment_query.list_gate_evaluations(experiment_id)
            if _matches_scope(
                item_candidate_id=gate.candidate_id,
                item_fold_id=gate.fold_id,
                candidate_id=candidate_id,
                fold_id=fold_id,
            )
        )
        artifacts = tuple(
            artifact
            for artifact in self._experiment_query.list_artifacts(experiment_id)
            if _matches_scope(
                item_candidate_id=artifact.candidate_id,
                item_fold_id=artifact.fold_id,
                candidate_id=candidate_id,
                fold_id=fold_id,
            )
        )
        if (
            len(selected_detail.folds) + len(gates) + len(artifacts)
            > _MAX_EXPERIMENT_RECORDS
        ):
            raise _error("EVIDENCE_RESULT_TOO_LARGE", "experiment_scope_exceeds_limit")
        artifact_refs = tuple(
            sorted(
                (_artifact_ref(item) for item in artifacts),
                key=lambda item: item.artifact_id,
            )
        )
        known_artifact_ids = {item.artifact_id for item in artifact_refs}
        if any(
            gate.artifact_id is not None and gate.artifact_id not in known_artifact_ids
            for gate in gates
        ):
            raise _error(
                "EVIDENCE_PROVENANCE_INCOMPLETE",
                "gate_artifact_reference_missing",
            )
        review = self._experiment_query.get_review_packet(experiment_id)
        if (
            review is not None
            and candidate_id is not None
            and review.candidate_id != candidate_id
        ):
            review = None
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "detail": selected_detail,
                "gates": gates,
                "review": review,
            },
        )
        lineage = [f"experiment:{experiment_id}"]
        if candidate_id is not None:
            lineage.append(f"candidate:{candidate_id}")
        if fold_id is not None:
            lineage.append(f"fold:{fold_id}")
        return ResearchEvidenceReadModel(
            kind=ResearchEvidenceKind.EXPERIMENT,
            subject_id=experiment_id,
            subject_version=str(detail.revision),
            strategy_id=None,
            strategy_version=detail.strategy_version,
            dataset_id=None,
            temporal_context=context,
            payload=payload,
            artifact_refs=artifact_refs,
            lineage=tuple(lineage),
        )

    def get_factor_evidence(
        self,
        *,
        query: FactorEvidenceQuery,
        context: EvidenceTemporalContext,
    ) -> ResearchEvidenceReadModel:
        """Evaluate one exact factor artifact; version fallback is impossible."""
        factor_id = _required(query.factor_id, field_name="factor_id")
        dataset_id = _required(query.dataset_id, field_name="dataset_id")
        catalog_snapshot_id = _required(
            query.catalog_snapshot_id,
            field_name="catalog_snapshot_id",
        )
        universe = _required(query.universe, field_name="universe")
        factor_version = query.factor_version
        if isinstance(factor_version, bool) or factor_version < 1:
            raise _error("EVIDENCE_IDENTITY_REQUIRED", "factor_version_invalid")
        if catalog_snapshot_id != context.source_snapshot_id:
            raise _error("EVIDENCE_SNAPSHOT_MISMATCH", "factor_snapshot_mismatch")
        report = self._factor_evaluation.evaluate(
            factor_id,
            factor_version,
            options=EvaluationOptions(
                start=query.start,
                end=query.end,
                dataset_id=dataset_id,
                catalog_snapshot_id=catalog_snapshot_id,
                universe=universe,
            ),
        )
        if (
            report.factor_id != factor_id
            or report.factor_version != factor_version
            or report.dataset_id != dataset_id
            or report.catalog_snapshot_id != catalog_snapshot_id
            or report.universe != universe
        ):
            raise _error(
                "EVIDENCE_IDENTITY_MISMATCH", "factor_report_identity_mismatch"
            )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={"factor_evaluation": report},
        )
        reference = EvidenceArtifactReference(
            artifact_id=f"factor:{factor_id}:v{factor_version}:{catalog_snapshot_id}",
            artifact_kind="factor_evaluation",
            content_hash=payload.payload_hash,
        )
        return ResearchEvidenceReadModel(
            kind=ResearchEvidenceKind.FACTOR,
            subject_id=factor_id,
            subject_version=str(factor_version),
            strategy_id=None,
            strategy_version=None,
            dataset_id=dataset_id,
            temporal_context=context,
            payload=payload,
            artifact_refs=(reference,),
            lineage=(
                f"factor:{factor_id}:v{factor_version}",
                f"snapshot:{catalog_snapshot_id}",
            ),
        )

    def get_strategy_evidence(
        self,
        *,
        strategy_id: str,
        version: int,
        context: EvidenceTemporalContext,
    ) -> ResearchEvidenceReadModel:
        """Read one immutable strategy version without latest fallback."""
        strategy_id = _required(strategy_id, field_name="strategy_id")
        if isinstance(version, bool) or version < 1:
            raise _error("EVIDENCE_IDENTITY_REQUIRED", "strategy_version_invalid")
        detail = self._strategy_query.get_version_detail(strategy_id, version)
        if detail is None:
            raise _error("EVIDENCE_NOT_FOUND", "strategy_version_not_found")
        if detail.strategy_id != strategy_id or detail.version != version:
            raise _error("EVIDENCE_IDENTITY_MISMATCH", "strategy_identity_mismatch")
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={"strategy_version": detail},
        )
        reference = EvidenceArtifactReference(
            artifact_id=f"strategy:{strategy_id}:v{version}",
            artifact_kind="strategy_spec",
            content_hash=detail.spec_hash,
        )
        return ResearchEvidenceReadModel(
            kind=ResearchEvidenceKind.STRATEGY,
            subject_id=strategy_id,
            subject_version=str(version),
            strategy_id=strategy_id,
            strategy_version=str(version),
            dataset_id=None,
            temporal_context=context,
            payload=payload,
            artifact_refs=(reference,),
            lineage=(f"strategy:{strategy_id}:v{version}",),
        )

    def get_backtest_evidence(
        self,
        *,
        run_id: str,
        strategy_id: str,
        strategy_version: str,
        dataset_id: str,
        context: EvidenceTemporalContext,
        include_replay_proof: bool = False,
    ) -> ResearchEvidenceReadModel:
        """Read one completed run with its immutable snapshot manifest identity."""
        run_id = _required(run_id, field_name="run_id")
        strategy_id = _required(strategy_id, field_name="strategy_id")
        strategy_version = _required(strategy_version, field_name="strategy_version")
        dataset_id = _required(dataset_id, field_name="dataset_id")
        run = self._backtest_query.get_run(run_id)
        if run is None:
            raise _error("EVIDENCE_NOT_FOUND", "backtest_run_not_found")
        if (
            run.run_id != run_id
            or run.strategy_id != strategy_id
            or run.strategy_version != strategy_version
        ):
            raise _error("EVIDENCE_IDENTITY_MISMATCH", "backtest_identity_mismatch")
        if run.status != "completed":
            raise _error("EVIDENCE_NOT_FINAL", "backtest_run_not_completed")
        config = _backtest_config(run.config_json)
        snapshot_id = config.get("research_snapshot_id")
        manifest_hash = config.get("research_snapshot_manifest_hash")
        if snapshot_id != context.source_snapshot_id or not _is_sha256(manifest_hash):
            raise _error(
                "EVIDENCE_PROVENANCE_INCOMPLETE",
                "backtest_snapshot_manifest_incomplete",
            )
        report = self._backtest_query.get_report(run_id)
        if report is None or report.get("run_id") != run_id:
            raise _error("EVIDENCE_PROVENANCE_INCOMPLETE", "backtest_report_missing")
        proof: dict[str, object] | None = None
        if include_replay_proof:
            proof = self._backtest_query.get_replay_proof(run_id)
            if proof is None or proof.get("replay_run_id") != run_id:
                raise _error("EVIDENCE_PROVENANCE_INCOMPLETE", "replay_proof_missing")
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={"run": run, "report": report, "replay_proof": proof},
        )
        report_payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={"report": report},
        )
        refs = [
            EvidenceArtifactReference(
                artifact_id=f"backtest-report:{run_id}",
                artifact_kind="backtest_report",
                content_hash=report_payload.payload_hash,
            ),
            EvidenceArtifactReference(
                artifact_id=f"research-snapshot-manifest:{snapshot_id}",
                artifact_kind="research_snapshot_manifest",
                content_hash=cast(str, manifest_hash),
            ),
        ]
        if proof is not None:
            proof_payload = EvidencePayloadReadModel.seal(
                schema_version=1,
                value={"replay_proof": proof},
            )
            refs.append(
                EvidenceArtifactReference(
                    artifact_id=f"replay-proof:{run_id}",
                    artifact_kind="replay_proof",
                    content_hash=proof_payload.payload_hash,
                )
            )
        return ResearchEvidenceReadModel(
            kind=ResearchEvidenceKind.BACKTEST,
            subject_id=run_id,
            subject_version=strategy_version,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            dataset_id=dataset_id,
            temporal_context=context,
            payload=payload,
            artifact_refs=tuple(sorted(refs, key=lambda item: item.artifact_kind)),
            lineage=(
                f"strategy:{strategy_id}:v{strategy_version}",
                f"run:{run_id}",
                f"snapshot:{snapshot_id}",
            ),
        )


def _backtest_config(raw: str) -> dict[str, object]:
    try:
        value = orjson.loads(raw)
    except orjson.JSONDecodeError as exc:
        raise _error(
            "EVIDENCE_PROVENANCE_INCOMPLETE",
            "backtest_config_invalid",
        ) from exc
    if not isinstance(value, dict):
        raise _error("EVIDENCE_PROVENANCE_INCOMPLETE", "backtest_config_invalid")
    mapping = cast("dict[object, object]", value)
    if any(not isinstance(key, str) for key in mapping):
        raise _error("EVIDENCE_PROVENANCE_INCOMPLETE", "backtest_config_invalid")
    return {cast(str, key): item for key, item in mapping.items()}


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )
