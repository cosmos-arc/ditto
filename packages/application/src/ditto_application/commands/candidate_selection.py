"""Durable, idempotent candidate preselection command and event projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, Protocol, cast

from ditto_application.candidate_selection import (
    CandidateSelectionReceipt,
    CandidateSelectionRequest,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.mutation_idempotency import (
    canonical_request_hash,
    find_mutation_receipt,
    mutation_receipt_detail,
    without_validated_mutation_receipt,
)
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CandidateEvidenceReader,
)
from ditto_application.processes.experiments.scheduler_store import (
    CandidateId,
    ExperimentId,
    ExperimentSchedulerStoreProtocol,
    ExperimentStage,
    SchedulerLease,
)

__all__ = [
    "CandidateSelectionCommand",
    "CandidateSelectionHandler",
    "CandidateSelectionProcess",
    "CandidateSelectionReceipt",
    "CandidateSelectionRequest",
]

_SELECTION_REASON_CODE = "candidate_preselected"
_SELECTION_EVIDENCE_KIND = "selection_evidence"


def _error(code: str, reason: str, message: str, **details: object) -> NoReturn:
    raise AppProcessError(
        message,
        details={"code": code, "reason": reason, **details},
    )


@dataclass(frozen=True, slots=True)
class CandidateSelectionCommand:
    """Nominal CQRS wrapper for one validated selection request."""

    request: CandidateSelectionRequest

    def __post_init__(self) -> None:
        """Reject untyped command payloads at the handler boundary."""
        if type(self.request) is not CandidateSelectionRequest:
            raise AppCommandError(
                "candidate selection command is invalid",
                details={"code": "CANDIDATE_NOT_ELIGIBLE"},
            )


class CandidateSelectionAuthority(Protocol):
    """Coordinator-owned lease authority exposed to the command handler."""

    def select_candidate(
        self,
        request: CandidateSelectionRequest,
    ) -> CandidateSelectionReceipt: ...


class CandidateSelectionHandler:
    """Map process failures into command errors without duplicating authority."""

    def __init__(self, process: CandidateSelectionAuthority) -> None:
        self._process = process

    def handle(self, command: CandidateSelectionCommand) -> CandidateSelectionReceipt:
        """Commit or exactly replay one durable candidate selection event."""
        if type(command) is not CandidateSelectionCommand:
            raise AppCommandError(
                "candidate selection command is invalid",
                details={"code": "CANDIDATE_NOT_ELIGIBLE"},
            )
        try:
            return self._process.select_candidate(command.request)
        except AppProcessError as exc:
            raise AppCommandError(str(exc), details=dict(exc.details)) from exc


@dataclass(frozen=True, slots=True)
class CandidateSelectionProcess:
    """Validate current evidence and append one schema-free status event."""

    store: ExperimentSchedulerStoreProtocol
    candidate_evidence_reader: CandidateEvidenceReader

    def replay(
        self,
        request: CandidateSelectionRequest,
    ) -> CandidateSelectionReceipt | None:
        """Return one exact idempotency receipt without consulting moving inputs."""
        events = self.store.list_status_events(ExperimentId(request.experiment_id))
        response = find_mutation_receipt(
            tuple(event.detail for event in events),
            request.idempotency,
        )
        if response is not None:
            return _decode_receipt(response)
        if any(event.reason_code == _SELECTION_REASON_CODE for event in events):
            _error(
                "CANDIDATE_SELECTION_CONFLICT",
                "candidate_selection_conflict",
                "a candidate has already been preselected",
                experiment_id=request.experiment_id,
            )
        return None

    def read_selection(
        self,
        experiment_id: str,
        selection_id: str,
    ) -> CandidateSelectionReceipt | None:
        """Read one persisted selection by immutable ID without caller key access."""
        matches = tuple(
            event
            for event in self.store.list_status_events(ExperimentId(experiment_id))
            if event.reason_code == _SELECTION_REASON_CODE
        )
        if not matches:
            return None
        if len(matches) != 1:
            _error(
                "CANDIDATE_SELECTION_CONFLICT",
                "candidate_selection_event_not_unique",
                "candidate selection event is not unique",
            )
        event = matches[0]
        detail = without_validated_mutation_receipt(event.detail)
        if detail.get("selection_id") != selection_id:
            return None
        try:
            return CandidateSelectionReceipt(
                selection_id=cast("str", detail["selection_id"]),
                experiment_id=experiment_id,
                candidate_id=cast("str", detail["candidate_id"]),
                comparison_payload_hash=cast("str", detail["comparison_payload_hash"]),
                candidate_evidence_artifact_id=cast(
                    "str", detail["candidate_evidence_artifact_id"]
                ),
                candidate_evidence_content_hash=cast(
                    "str", detail["candidate_evidence_content_hash"]
                ),
                selection_evidence_content_hash=cast(
                    "str", detail["selection_evidence_content_hash"]
                ),
                experiment_revision=event.subject_revision,
                event_id=event.event_id,
                occurred_at=event.occurred_at,
            )
        except (KeyError, TypeError, ValueError):
            _error(
                "CANDIDATE_SELECTION_CONFLICT",
                "candidate_selection_event_invalid",
                "candidate selection event is invalid",
            )

    def select(
        self,
        request: CandidateSelectionRequest,
        *,
        lease: SchedulerLease,
        now_epoch_us: int,
    ) -> CandidateSelectionReceipt:
        """Bind current comparison and evidence hashes before the event CAS."""
        replay = self.replay(request)
        if replay is not None:
            return replay
        experiment_id = ExperimentId(request.experiment_id)
        candidate_id = CandidateId(request.candidate_id)
        snapshot = self.store.load_snapshot(experiment_id)
        if (
            snapshot.projection.record.stage is not ExperimentStage.CANDIDATE_SELECTION
            or snapshot.projection.revision != request.expected_revision
        ):
            _error(
                "CANDIDATE_SELECTION_CONFLICT",
                "candidate_selection_revision_conflict",
                "candidate selection revision conflicts with server truth",
                expected_revision=request.expected_revision,
                actual_revision=snapshot.projection.revision,
            )
        loaded = self.candidate_evidence_reader.load_current_bundle(
            request.experiment_id,
            request.candidate_id,
        )
        if loaded is None:
            _error(
                "CANDIDATE_NOT_ELIGIBLE",
                "candidate_evidence_not_found",
                "candidate evidence was not found",
            )
        candidate_record, bundle = loaded
        if (
            bundle.manifest.get("comparison_payload_hash")
            != request.comparison_payload_hash
        ):
            _error(
                "EVIDENCE_STALE",
                "candidate_selection_comparison_stale",
                "candidate comparison evidence is stale",
            )
        selection_records = tuple(
            record
            for record in self.store.list_experiment_artifacts(experiment_id)
            if record.artifact_kind == _SELECTION_EVIDENCE_KIND
            and record.candidate_id is None
        )
        if len(selection_records) != 1:
            _error(
                "CANDIDATE_NOT_ELIGIBLE",
                "selection_evidence_not_unique",
                "selection evidence is unavailable or ambiguous",
            )
        selection_record = selection_records[0]
        selection_id = _selection_id(request)
        revision = request.expected_revision + 1
        event_id = _event_id(request.experiment_id, revision)
        receipt = CandidateSelectionReceipt(
            selection_id=selection_id,
            experiment_id=request.experiment_id,
            candidate_id=request.candidate_id,
            comparison_payload_hash=request.comparison_payload_hash,
            candidate_evidence_artifact_id=candidate_record.artifact_id,
            candidate_evidence_content_hash=str(candidate_record.content_hash),
            selection_evidence_content_hash=str(selection_record.content_hash),
            experiment_revision=revision,
            event_id=event_id,
            occurred_at=request.occurred_at,
        )
        detail = mutation_receipt_detail(
            request.idempotency,
            response=receipt.canonical_response(),
            detail={
                "candidate_evidence_artifact_id": candidate_record.artifact_id,
                "candidate_evidence_content_hash": str(candidate_record.content_hash),
                "candidate_id": request.candidate_id,
                "comparison_payload_hash": request.comparison_payload_hash,
                "rationale": request.rationale,
                "schema_version": 1,
                "selection_evidence_content_hash": str(selection_record.content_hash),
                "selection_id": selection_id,
            },
        )
        projection = self.store.record_candidate_selection(
            experiment_id,
            candidate_id,
            expected_revision=request.expected_revision,
            lease=lease,
            now_epoch_us=now_epoch_us,
            occurred_at=request.occurred_at,
            detail=detail,
        )
        if projection.revision != revision:
            _error(
                "CANDIDATE_SELECTION_CONFLICT",
                "candidate_selection_revision_drift",
                "candidate selection persistence receipt drifted",
            )
        return receipt


def _selection_id(request: CandidateSelectionRequest) -> str:
    identity = canonical_request_hash(
        {
            "candidate_id": request.candidate_id,
            "comparison_payload_hash": request.comparison_payload_hash,
            "experiment_id": request.experiment_id,
            "schema_version": 1,
        }
    )
    return f"candidate-selection:{identity}"


def _event_id(experiment_id: str, revision: int) -> str:
    identity = canonical_request_hash(
        {
            "attempt_id": None,
            "candidate_id": None,
            "experiment_id": experiment_id,
            "fold_id": None,
            "revision": revision,
            "subject_type": "experiment",
        }
    )
    return f"status:{identity}"


def _decode_receipt(value: Mapping[str, object]) -> CandidateSelectionReceipt:
    expected = {
        "candidate_evidence_artifact_id",
        "candidate_evidence_content_hash",
        "candidate_id",
        "comparison_payload_hash",
        "event_id",
        "experiment_id",
        "experiment_revision",
        "occurred_at",
        "selection_evidence_content_hash",
        "selection_id",
    }
    if set(value) != expected:
        _error(
            "CANDIDATE_SELECTION_CONFLICT",
            "candidate_selection_receipt_invalid",
            "candidate selection receipt is invalid",
        )
    try:
        occurred_at = datetime.fromisoformat(cast("str", value["occurred_at"]))
        return CandidateSelectionReceipt(
            selection_id=cast("str", value["selection_id"]),
            experiment_id=cast("str", value["experiment_id"]),
            candidate_id=cast("str", value["candidate_id"]),
            comparison_payload_hash=cast("str", value["comparison_payload_hash"]),
            candidate_evidence_artifact_id=cast(
                "str", value["candidate_evidence_artifact_id"]
            ),
            candidate_evidence_content_hash=cast(
                "str", value["candidate_evidence_content_hash"]
            ),
            selection_evidence_content_hash=cast(
                "str", value["selection_evidence_content_hash"]
            ),
            experiment_revision=cast("int", value["experiment_revision"]),
            event_id=cast("str", value["event_id"]),
            occurred_at=occurred_at,
        )
    except (TypeError, ValueError):
        _error(
            "CANDIDATE_SELECTION_CONFLICT",
            "candidate_selection_receipt_invalid",
            "candidate selection receipt is invalid",
        )
