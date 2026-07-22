"""Decode and validate durable research execution evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, cast

import orjson
from ditto_analysis.experiments import (
    ExperimentLaunchSpec as _ExperimentLaunchSpec,
)
from ditto_analysis.experiments import (
    ExperimentReaderProtocol as _ExperimentReaderProtocol,
)
from ditto_analysis.experiments import (
    ExperimentStatus,
    StatusEventRecord,
    StatusSubjectType,
    canonical_payload,
    encode_launch_spec,
)
from ditto_analysis.experiments import (
    FoldView as _FoldView,
)
from ditto_strategy.models import StrategySpecRecord

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._launch_reconstruction import (
    reconstruct_launch_candidates,
    reconstruct_launch_folds,
)
from ditto_application.processes.experiments._preflight_codec import (
    DecodedPreflightReport,
    decode_preflight_report,
)
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
    ResearchSnapshotBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactUniverseIdentity,
)
from ditto_application.processes.experiments.planning import (
    BaselineCandidatePlan,
    PlannedCandidate,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)
from ditto_application.processes.experiments.research_snapshot_manifest import (
    VerifiedResearchSnapshotManifest,
)

_PREFLIGHT_POLICY_VERSION = "r3-experiment-preflight-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")

type ResearchExperimentReader = _ExperimentReaderProtocol
type ResearchFoldView = _FoldView


class ResearchExecutionInputError(AppProcessError):
    """Frozen durable evidence cannot reconstruct the claimed numerical input."""


def research_execution_error(
    reason: str,
    **details: object,
) -> ResearchExecutionInputError:
    return ResearchExecutionInputError(
        "durable research execution evidence is invalid",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


def require_exact_fold_view(value: object) -> ResearchFoldView:
    """Narrow an untrusted execution input to the exact analysis fold DTO."""
    if type(value) is not _FoldView:
        raise research_execution_error("invalid_execution_fold")
    return value


def launch_spec_content_hash(spec: _ExperimentLaunchSpec) -> str:
    """Hash one exact launch spec through the analysis-owned canonical codec."""
    return str(encode_launch_spec(spec).content_hash)


def canonical_execution_payload_hash(payload: dict[str, object]) -> str:
    """Hash one execution identity through the shared canonical payload codec."""
    return str(canonical_payload(payload).content_hash)


def require_evidence_mapping(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise research_execution_error(
            "invalid_execution_evidence_shape", field=field_name
        )
    return cast("dict[str, object]", value)


def require_evidence_list(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise research_execution_error(
            "invalid_execution_evidence_shape", field=field_name
        )
    return cast("list[object]", value)


def require_evidence_string(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise research_execution_error(
            "invalid_execution_evidence_identity", field=field_name
        )
    return value


def require_evidence_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise research_execution_error(
            "invalid_execution_evidence_version", field=field_name
        )
    return value


class ExactStrategyVersionReader(Protocol):
    """Read one explicit strategy version; no moving-state method is exposed."""

    def get_spec(self, strategy_id: str, version: int) -> StrategySpecRecord | None:
        """Return only the requested exact version."""
        ...


@dataclass(frozen=True, slots=True)
class FrozenResearchInputRequest:
    """Exact immutable identities accepted by the research input boundary."""

    snapshot: ExactResearchSnapshot
    dataset_id: str
    source_snapshot_ids: tuple[str, ...]
    known_at_policy: str
    builder_version: str
    universe: ExactUniverseIdentity
    membership_projection_hash: str

    def __post_init__(self) -> None:
        """Canonicalize exact input identities before crossing the loader port."""
        if (
            type(self.snapshot) is not ExactResearchSnapshot
            or type(self.universe) is not ExactUniverseIdentity
        ):
            raise research_execution_error("invalid_frozen_input_request_identity")
        require_evidence_string(self.dataset_id, "dataset_id")
        require_evidence_string(self.builder_version, "builder_version")
        if self.known_at_policy != "sample_time":
            raise research_execution_error("unsupported_known_at_policy")
        raw_sources: object = self.source_snapshot_ids
        if type(raw_sources) is not tuple or not raw_sources:
            raise research_execution_error("missing_source_snapshot_identity")
        sources = tuple(
            sorted(
                require_evidence_string(item, "source_snapshot_id")
                for item in cast("tuple[object, ...]", raw_sources)
            )
        )
        if len(set(sources)) != len(sources):
            raise research_execution_error("duplicate_source_snapshot_identity")
        if (
            type(self.membership_projection_hash) is not str
            or _SHA256.fullmatch(self.membership_projection_hash) is None
        ):
            raise research_execution_error("invalid_membership_projection_hash")
        object.__setattr__(self, "source_snapshot_ids", sources)


@dataclass(frozen=True, slots=True)
class FrozenResearchExecutionInputs:
    """Verified content bindings returned without provider or latest lookup."""

    snapshot_manifest: VerifiedResearchSnapshotManifest
    universe: ExactUniverseIdentity
    membership_projection_hash: str
    instrument_rules: VerifiedInstrumentRulesArtifact

    def __post_init__(self) -> None:
        """Reject weak input DTOs before their hashes enter a fingerprint."""
        if (
            type(self.snapshot_manifest) is not VerifiedResearchSnapshotManifest
            or type(self.universe) is not ExactUniverseIdentity
            or type(self.membership_projection_hash) is not str
            or _SHA256.fullmatch(self.membership_projection_hash) is None
            or type(self.instrument_rules) is not VerifiedInstrumentRulesArtifact
        ):
            raise research_execution_error("invalid_frozen_research_inputs")
        snapshot_binding = self.snapshot_manifest.snapshot_binding
        rules_inputs = tuple(
            item
            for item in snapshot_binding.inputs
            if item.artifact_kind == "instrument_rules"
        )
        if (
            len(rules_inputs) != 1
            or rules_inputs[0] != self.instrument_rules.input_evidence
        ):
            raise research_execution_error("instrument_rules_evidence_drift")
        if not set(self.instrument_rules.source_snapshot_ids).issubset(
            snapshot_binding.source_snapshot_ids
        ):
            raise research_execution_error("instrument_rules_source_snapshot_drift")

    @property
    def snapshot_binding(self) -> ResearchSnapshotBinding:
        """Expose only the binding derived from verified canonical manifest bytes."""
        return self.snapshot_manifest.snapshot_binding


class FrozenResearchInputsResolver(Protocol):
    """Resolve content only from one complete exact input request."""

    def resolve(
        self,
        request: FrozenResearchInputRequest,
    ) -> FrozenResearchExecutionInputs:
        """Return verified hashes and versions for the exact snapshot."""
        ...


@dataclass(frozen=True, slots=True)
class DurableLaunchEvidence:
    report: DecodedPreflightReport
    detail: dict[str, object]
    preflight: dict[str, object]
    plan_preimage: dict[str, object]
    executor: dict[str, object]
    authority: dict[str, object]
    identities: dict[str, object]


def _enqueue_event(
    reader: ResearchExperimentReader,
    fold: ResearchFoldView,
) -> StatusEventRecord:
    events = tuple(
        event
        for event in reader.list_status_events(fold.spec.key.experiment_id)
        if event.subject_type is StatusSubjectType.EXPERIMENT
        and event.subject_revision == 1
        and event.status is ExperimentStatus.QUEUED
        and event.reason_code == "preflight_passed"
        and event.candidate_id is None
        and event.fold_id is None
        and event.attempt_id is None
    )
    if len(events) != 1:
        raise research_execution_error(
            "enqueue_event_missing_or_ambiguous",
            event_count=len(events),
        )
    event = events[0]
    if canonical_payload(event.detail).content_hash != event.detail_hash:
        raise research_execution_error("enqueue_event_detail_hash_mismatch")
    return event


def read_durable_launch(
    reader: ResearchExperimentReader,
    fold: ResearchFoldView,
) -> DurableLaunchEvidence:
    event = _enqueue_event(reader, fold)
    encoded = canonical_payload(event.detail)
    detail = require_evidence_mapping(
        cast("object", orjson.loads(encoded.json_bytes)),
        "detail",
    )
    try:
        report = decode_preflight_report(
            detail,
            expected_policy_version=_PREFLIGHT_POLICY_VERSION,
        )
    except AppProcessError as exc:
        raise research_execution_error(
            "persisted_preflight_decode_failed",
            source_code=exc.details.get("code"),
            source_reason=exc.details.get("reason"),
        ) from exc
    preflight = require_evidence_mapping(detail.get("preflight"), "preflight")
    plan_preimage = require_evidence_mapping(
        detail.get("plan_preimage"), "plan_preimage"
    )
    executor = require_evidence_mapping(preflight.get("executor"), "preflight.executor")
    authority = require_evidence_mapping(
        preflight.get("authority"), "preflight.authority"
    )
    identities = require_evidence_mapping(
        preflight.get("identities"), "preflight.identities"
    )
    return DurableLaunchEvidence(
        report,
        detail,
        preflight,
        plan_preimage,
        executor,
        authority,
        identities,
    )


def select_planned_candidate(
    launch: DurableLaunchEvidence,
    fold: ResearchFoldView,
) -> tuple[PlannedCandidate, bool]:
    candidates = launch.report.work_plan.candidate_matrix.candidates
    persisted_spec = None
    # Candidate IDs are generated from the stable ordinal and candidate hash.
    for item in candidates:
        expected_id = ":".join(
            (
                str(fold.spec.key.experiment_id),
                "candidate",
                str(item.ordinal),
                item.candidate_hash,
            )
        )
        if expected_id == str(fold.spec.key.candidate_id):
            persisted_spec = item
            break
    if persisted_spec is None:
        raise research_execution_error("fold_candidate_identity_mismatch")
    return persisted_spec, isinstance(persisted_spec, BaselineCandidatePlan)


def require_launch_parity(
    spec: _ExperimentLaunchSpec,
    launch: DurableLaunchEvidence,
    fold: ResearchFoldView,
    planned: PlannedCandidate,
    input_request: FrozenResearchInputRequest,
    persisted_folds: tuple[ResearchFoldView, ...],
    *,
    is_baseline: bool,
) -> None:
    identities = launch.identities
    executor = launch.executor
    work = launch.report.work_plan
    protocol = require_evidence_mapping(
        require_evidence_mapping(
            launch.preflight.get("validation"), "preflight.validation"
        ).get("fold_protocol"),
        "preflight.validation.fold_protocol",
    )
    strategy_id = require_evidence_string(
        identities.get("strategy_id"), "identities.strategy_id"
    )
    strategy_version = require_evidence_integer(
        identities.get("strategy_version"),
        "identities.strategy_version",
    )
    expected_candidates = reconstruct_launch_candidates(
        spec.experiment_id, launch.report
    )
    expected_folds = reconstruct_launch_folds(
        spec.experiment_id,
        launch.report,
        expected_candidates,
    )
    expected_fold_hashes = tuple(str(item.payload_hash) for item in expected_folds)
    persisted_fold_hashes = tuple(
        require_evidence_string(item, "plan_preimage.fold_payload_hash")
        for item in require_evidence_list(
            launch.plan_preimage.get("fold_payload_hashes"),
            "plan_preimage.fold_payload_hashes",
        )
    )
    current_matches = tuple(
        item for item in expected_folds if item.key == fold.spec.key
    )
    actual_folds_by_key = {item.spec.key: item.spec for item in persisted_folds}
    expected_folds_by_key = {item.key: item for item in expected_folds}
    checks = {
        "experiment": spec.experiment_id == fold.spec.key.experiment_id,
        "strategy_version": str(spec.strategy_version)
        == f"{strategy_id}@{strategy_version}",
        "strategy_spec_hash": str(spec.strategy_spec_hash)
        == require_evidence_string(
            executor.get("strategy_spec_hash"), "executor.strategy_spec_hash"
        ),
        "snapshot": str(spec.snapshot_id) == input_request.snapshot.snapshot_id,
        "seed": spec.seed == work.seed,
        "worker_count": spec.worker_count == work.worker_count,
        "failure_policy": spec.failure_policy is work.failure_policy,
        "candidate_budget": spec.budget.candidate_limit == work.budget.candidate_limit,
        "fold_budget": spec.budget.fold_run_limit == work.budget.fold_run_limit,
        "protocol_id": spec.fold_protocol.protocol_id
        == require_evidence_string(
            protocol.get("protocol_id"), "fold_protocol.protocol_id"
        ),
        "protocol_version": spec.fold_protocol.protocol_version
        == require_evidence_integer(
            protocol.get("protocol_version"),
            "fold_protocol.protocol_version",
        ),
        "protocol_hash": str(spec.fold_protocol.protocol_hash)
        == require_evidence_string(
            protocol.get("protocol_hash"), "fold_protocol.protocol_hash"
        ),
        "candidates": tuple(spec.candidates) == expected_candidates,
        "persisted_folds": len(actual_folds_by_key) == len(persisted_folds)
        and actual_folds_by_key == expected_folds_by_key,
        "fold_hashes": persisted_fold_hashes == expected_fold_hashes,
        "selected_fold": len(current_matches) == 1 and current_matches[0] == fold.spec,
    }
    drift = tuple(name for name, matches in checks.items() if not matches)
    if drift:
        raise research_execution_error("launch_spec_preflight_drift", fields=drift)
    launch_candidate = next(
        candidate
        for candidate in expected_candidates
        if candidate.candidate_id == fold.spec.key.candidate_id
    )
    if (
        launch_candidate.ordinal != planned.ordinal
        or launch_candidate.is_baseline is not is_baseline
        or launch_candidate.parameters != planned.persistence_parameters
    ):
        raise research_execution_error("launch_candidate_plan_drift")


def build_frozen_input_request(
    launch: DurableLaunchEvidence,
) -> FrozenResearchInputRequest:
    certification = require_evidence_mapping(
        launch.identities.get("certification"),
        "identities.certification",
    )
    snapshot = require_evidence_mapping(
        certification.get("snapshot_evidence"),
        "identities.certification.snapshot_evidence",
    )
    runtime = require_evidence_mapping(
        launch.executor.get("runtime_validation_evidence"),
        "executor.runtime_validation_evidence",
    )
    source_snapshot_ids = tuple(
        require_evidence_string(item, "snapshot_evidence.source_snapshot_id")
        for item in require_evidence_list(
            snapshot.get("source_snapshot_ids"),
            "snapshot_evidence.source_snapshot_ids",
        )
    )
    return FrozenResearchInputRequest(
        snapshot=ExactResearchSnapshot(
            require_evidence_string(
                snapshot.get("snapshot_id"), "snapshot_evidence.snapshot_id"
            ),
            require_evidence_string(
                snapshot.get("manifest_hash"),
                "snapshot_evidence.manifest_hash",
            ),
        ),
        dataset_id=require_evidence_string(
            snapshot.get("dataset_id"), "snapshot_evidence.dataset_id"
        ),
        source_snapshot_ids=source_snapshot_ids,
        known_at_policy=require_evidence_string(
            snapshot.get("known_at_policy"),
            "snapshot_evidence.known_at_policy",
        ),
        builder_version=require_evidence_string(
            snapshot.get("builder_version"),
            "snapshot_evidence.builder_version",
        ),
        universe=ExactUniverseIdentity(
            require_evidence_string(runtime.get("universe_id"), "runtime.universe_id"),
            require_evidence_string(
                launch.authority.get("universe_membership_hash"),
                "authority.universe_membership_hash",
            ),
        ),
        membership_projection_hash=require_evidence_string(
            launch.authority.get("membership_projection_hash"),
            "authority.membership_projection_hash",
        ),
    )


def validate_frozen_inputs(
    request: FrozenResearchInputRequest,
    inputs: FrozenResearchExecutionInputs,
    *,
    required_dataset_ids: tuple[str, ...],
) -> FrozenResearchExecutionInputs:
    if type(inputs) is not FrozenResearchExecutionInputs:
        raise research_execution_error("invalid_frozen_research_inputs")
    if (
        type(inputs.snapshot_binding) is not ResearchSnapshotBinding
        or inputs.snapshot_binding.exact_snapshot != request.snapshot
        or inputs.snapshot_binding.dataset_id != request.dataset_id
        or inputs.snapshot_binding.source_snapshot_ids != request.source_snapshot_ids
        or inputs.snapshot_binding.known_at_policy != request.known_at_policy
        or inputs.snapshot_binding.builder_version != request.builder_version
        or inputs.universe != request.universe
        or inputs.membership_projection_hash != request.membership_projection_hash
    ):
        raise research_execution_error("frozen_research_input_identity_drift")
    membership = tuple(
        item
        for item in inputs.snapshot_binding.inputs
        if item.artifact_kind == "membership"
    )
    if (
        len(membership) != 1
        or membership[0].content_hash != request.universe.membership_hash
    ):
        raise research_execution_error("membership_artifact_hash_mismatch")
    by_kind: dict[str, list[ContentAddressedResearchInput]] = {}
    for item in inputs.snapshot_binding.inputs:
        by_kind.setdefault(item.artifact_kind, []).append(item)
    required_kinds = ("bars", "calendar", "membership", "instrument_rules")
    if any(len(by_kind.get(kind, ())) != 1 for kind in required_kinds):
        raise research_execution_error("required_execution_input_set_incomplete")
    input_ids = {item.input_id for item in inputs.snapshot_binding.inputs}
    if any(dataset_id not in input_ids for dataset_id in required_dataset_ids):
        raise research_execution_error("runtime_dataset_input_binding_missing")
    if inputs.instrument_rules.input_evidence != by_kind["instrument_rules"][0]:
        raise research_execution_error("instrument_rules_evidence_drift")
    if not set(inputs.instrument_rules.source_snapshot_ids).issubset(
        inputs.snapshot_binding.source_snapshot_ids
    ):
        raise research_execution_error("instrument_rules_source_snapshot_drift")
    return inputs
