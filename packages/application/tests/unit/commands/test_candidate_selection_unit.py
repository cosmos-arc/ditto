"""Candidate preselection command boundary tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_application.commands.candidate_selection import (
    CandidateSelectionCommand,
    CandidateSelectionHandler,
    CandidateSelectionReceipt,
    CandidateSelectionRequest,
)
from ditto_application.mutation_idempotency import (
    build_mutation_idempotency,
    canonical_resource_id,
)

NOW = datetime(2026, 8, 1, 8, tzinfo=UTC)


def _request() -> CandidateSelectionRequest:
    payload = {
        "candidate_id": "candidate-1",
        "comparison_payload_hash": "a" * 64,
        "expected_revision": 4,
        "rationale": "Promote the strongest preregistered candidate.",
    }
    return CandidateSelectionRequest(
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        comparison_payload_hash="a" * 64,
        expected_revision=4,
        rationale=payload["rationale"],
        occurred_at=NOW,
        idempotency=build_mutation_idempotency(
            operation_id="design_research_candidate_selection",
            resource_id=canonical_resource_id(
                "candidate_selection",
                {"experiment_id": "experiment-1"},
            ),
            raw_key="selection-key-1",
            request_payload=payload,
        ),
    )


@dataclass
class _Authority:
    calls: int = 0

    def select_candidate(
        self,
        request: CandidateSelectionRequest,
    ) -> CandidateSelectionReceipt:
        self.calls += 1
        return CandidateSelectionReceipt(
            selection_id="candidate-selection:" + "b" * 64,
            experiment_id=request.experiment_id,
            candidate_id=request.candidate_id,
            comparison_payload_hash=request.comparison_payload_hash,
            candidate_evidence_artifact_id="candidate-evidence-bundle-v1-" + "c" * 64,
            candidate_evidence_content_hash="c" * 64,
            selection_evidence_content_hash="d" * 64,
            experiment_revision=5,
            event_id="status:" + "e" * 64,
            occurred_at=NOW,
        )


def test_handler_returns_committed_server_receipt() -> None:
    authority = _Authority()
    receipt = CandidateSelectionHandler(authority).handle(
        CandidateSelectionCommand(_request())
    )

    assert receipt.selection_id.startswith("candidate-selection:")
    assert receipt.experiment_revision == 5
    assert authority.calls == 1
