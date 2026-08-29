"""Isolation tests for the approval-gated Campaign holdout bridge."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Lock
from typing import cast

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.agent_campaign_holdout import (
    AgentCampaignHoldoutProcess,
    AgentCampaignHoldoutRequest,
    AgentCampaignHoldoutResult,
    CampaignHoldoutAggregateReader,
    CampaignHoldoutAggregateRecord,
    CampaignHoldoutApprovalCheck,
    CampaignHoldoutApprovalVerifier,
    CampaignHoldoutClaimPort,
    CampaignHoldoutSignature,
    CampaignHoldoutSigner,
    VerifiedCampaignHoldoutApproval,
)
from ditto_application.processes.experiments.holdout import (
    ClaimHoldoutCandidateRequest,
    HoldoutClaimReceipt,
    HoldoutSelectionReason,
)
from ditto_application.processes.experiments.scheduler_store import (
    ExperimentId,
    SchedulerLease,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
NOW = datetime(2026, 8, 16, 8, 0, tzinfo=UTC)


def _claim_request() -> ClaimHoldoutCandidateRequest:
    return ClaimHoldoutCandidateRequest(
        experiment_id="campaign-holdout-1",
        candidate_id="candidate-preselected-1",
        expected_revision=7,
        expected_selection_evidence_hash=HASH_A,
        operator_confirmation="I approve one sealed holdout evaluation.",
        selection_reason=HoldoutSelectionReason(
            code="preselected",
            summary="Chosen from preregistered walk-forward evidence.",
        ),
        occurred_at=NOW,
    )


def _request() -> AgentCampaignHoldoutRequest:
    return AgentCampaignHoldoutRequest(
        claim=_claim_request(),
        run_id="run-holdout-1",
        episode_id="episode-run-holdout-1",
        call_id="call-holdout-1",
        expected_threshold_ids=("constraints", "minimum_evidence"),
    )


def _lease() -> SchedulerLease:
    return SchedulerLease(
        experiment_id=ExperimentId("campaign-holdout-1"),
        owner_token="r5-holdout-operator",
        lease_until_epoch_us=2_000_000,
        acquired_at_epoch_us=1_000_000,
        renewed_at_epoch_us=1_000_000,
        revision=3,
    )


def _receipt() -> HoldoutClaimReceipt:
    return HoldoutClaimReceipt(
        claim_id="holdout-claim-1",
        experiment_id="campaign-holdout-1",
        candidate_id="candidate-preselected-1",
        fold_id="sealed-holdout-fold",
        logical_run_id="logical-holdout-run",
        reproduction_fingerprint=HASH_B,
        claim_payload_hash=HASH_C,
        selection_evidence_hash=HASH_A,
        experiment_revision=8,
        event_id="holdout-claim-event-1",
        occurred_at=NOW,
    )


class _ClaimPort(CampaignHoldoutClaimPort):
    def __init__(self) -> None:
        self._lock = Lock()
        self._receipt: HoldoutClaimReceipt | None = None
        self.calls = 0
        self.new_claims = 0

    def claim_candidate(
        self,
        request: ClaimHoldoutCandidateRequest,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> HoldoutClaimReceipt:
        assert request == _claim_request()
        assert lease == _lease()
        assert now_epoch_us == 1_000_000
        with self._lock:
            self.calls += 1
            if self._receipt is None:
                self._receipt = _receipt()
                self.new_claims += 1
            return self._receipt


class _AggregateReader(CampaignHoldoutAggregateReader):
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls = 0
        self.record = CampaignHoldoutAggregateRecord(
            claim_id="holdout-claim-1",
            experiment_id="campaign-holdout-1",
            candidate_id="candidate-preselected-1",
            aggregate_passed=True,
            threshold_outcomes={
                "constraints": True,
                "minimum_evidence": True,
            },
            evidence_hash=HASH_B,
        )

    def read_aggregate(self, claim_id: str) -> CampaignHoldoutAggregateRecord:
        assert claim_id == "holdout-claim-1"
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise AppProcessError(
                "holdout result is not committed yet",
                details={"code": "HOLDOUT_PENDING", "reason": "holdout_pending"},
            )
        return self.record


class _ApprovalVerifier(CampaignHoldoutApprovalVerifier):
    def __init__(
        self,
        *,
        approved: bool = True,
        wrong_type: bool = False,
        wrong_action_hash: bool = False,
        approved_at: datetime = NOW,
    ) -> None:
        self.approved = approved
        self.wrong_type = wrong_type
        self.wrong_action_hash = wrong_action_hash
        self.approved_at = approved_at
        self.checks: list[CampaignHoldoutApprovalCheck] = []

    def verify(
        self, check: CampaignHoldoutApprovalCheck
    ) -> VerifiedCampaignHoldoutApproval:
        self.checks.append(check)
        if self.wrong_type:
            return cast("VerifiedCampaignHoldoutApproval", object())
        return VerifiedCampaignHoldoutApproval.issue(
            check=check,
            approval_id="independent-holdout-approval-1",
            action_hash=HASH_A if self.wrong_action_hash else check.action_hash,
            operator_id="operator-1",
            approved_at=self.approved_at,
            approved=self.approved,
        )


class _Signer(CampaignHoldoutSigner):
    def __init__(self, *, wrong_hash: bool = False) -> None:
        self.wrong_hash = wrong_hash
        self.hashes: list[str] = []

    def sign(self, aggregate_hash: str) -> CampaignHoldoutSignature:
        self.hashes.append(aggregate_hash)
        return CampaignHoldoutSignature(
            algorithm="ed25519",
            key_id="r5-holdout-test-key",
            payload_hash=HASH_C if self.wrong_hash else aggregate_hash,
            signature_hex="d" * 128,
        )


def _process(
    *,
    claim_port: _ClaimPort | None = None,
    reader: _AggregateReader | None = None,
    verifier: _ApprovalVerifier | None = None,
    signer: _Signer | None = None,
) -> tuple[
    AgentCampaignHoldoutProcess,
    _ClaimPort,
    _AggregateReader,
    _ApprovalVerifier,
    _Signer,
]:
    actual_claim = claim_port or _ClaimPort()
    actual_reader = reader or _AggregateReader()
    actual_verifier = verifier or _ApprovalVerifier()
    actual_signer = signer or _Signer()
    return (
        AgentCampaignHoldoutProcess(
            claim_port=actual_claim,
            aggregate_reader=actual_reader,
            approval_verifier=actual_verifier,
            signer=actual_signer,
        ),
        actual_claim,
        actual_reader,
        actual_verifier,
        actual_signer,
    )


def _evaluate(process: AgentCampaignHoldoutProcess):
    return process.evaluate(
        _request(),
        lease=_lease(),
        now_epoch_us=1_000_000,
    )


def _reason(exc_info: pytest.ExceptionInfo[AppProcessError]) -> str:
    return str(exc_info.value.details["reason"])


def test_returns_only_signed_aggregate_thresholds_and_evidence_hash() -> None:
    process, claim_port, _reader, verifier, signer = _process()

    result = _evaluate(process)
    payload = result.to_agent_payload()

    assert payload == {
        "aggregate_passed": True,
        "threshold_outcomes": {
            "constraints": True,
            "minimum_evidence": True,
        },
        "evidence_hash": HASH_B,
        "aggregate_hash": signer.hashes[0],
        "signature": {
            "algorithm": "ed25519",
            "key_id": "r5-holdout-test-key",
            "signature_hex": "d" * 128,
        },
    }
    forbidden = {
        "candidate",
        "claim",
        "date",
        "experiment",
        "feature",
        "fold",
        "metric",
        "period",
        "window",
    }
    assert not any(term in repr(payload).lower() for term in forbidden)
    assert claim_port.new_claims == 1
    assert verifier.checks[0].tool_name == "campaign_holdout_evaluate"
    assert "holdout_window" not in verifier.checks[0].arguments
    assert "campaign_authorization" not in verifier.checks[0].arguments


def test_independent_approval_is_required_before_holdout_claim() -> None:
    verifier = _ApprovalVerifier(approved=False)
    process, claim_port, reader, _verifier, signer = _process(verifier=verifier)

    with pytest.raises(AppProcessError) as exc_info:
        _evaluate(process)

    assert _reason(exc_info) == "campaign_holdout_approval_required"
    assert claim_port.calls == 0
    assert reader.calls == 0
    assert signer.hashes == []


def test_other_authority_cannot_replace_holdout_approval() -> None:
    verifier = _ApprovalVerifier(wrong_type=True)
    process, claim_port, _reader, _verifier, _signer = _process(verifier=verifier)

    with pytest.raises(AppProcessError) as exc_info:
        _evaluate(process)

    assert _reason(exc_info) == "campaign_holdout_approval_invalid"
    assert claim_port.calls == 0


@pytest.mark.parametrize(
    "verifier",
    [
        _ApprovalVerifier(wrong_action_hash=True),
        _ApprovalVerifier(approved_at=datetime(2026, 8, 16, 8, 0, 1, tzinfo=UTC)),
    ],
)
def test_approval_must_bind_exact_action_and_precede_claim(
    verifier: _ApprovalVerifier,
) -> None:
    process, claim_port, _reader, _verifier, _signer = _process(verifier=verifier)

    with pytest.raises(AppProcessError) as exc_info:
        _evaluate(process)

    assert _reason(exc_info) == "campaign_holdout_approval_invalid"
    assert claim_port.calls == 0


def test_approval_arguments_are_deeply_immutable() -> None:
    check = CampaignHoldoutApprovalCheck(
        run_id=_request().run_id,
        episode_id=_request().episode_id,
        call_id=_request().call_id,
        arguments=_request().approval_arguments(),
    )

    assert isinstance(check.arguments["expected_threshold_ids"], tuple)


def test_crash_after_atomic_claim_replays_without_second_consumption() -> None:
    claim_port = _ClaimPort()
    reader = _AggregateReader(fail_first=True)
    process, _claim, _reader, _verifier, _signer = _process(
        claim_port=claim_port,
        reader=reader,
    )

    with pytest.raises(AppProcessError) as exc_info:
        _evaluate(process)
    recovered = _evaluate(process)

    assert _reason(exc_info) == "holdout_pending"
    assert recovered.aggregate_passed is True
    assert claim_port.calls == 2
    assert claim_port.new_claims == 1


def test_concurrent_replay_has_one_append_only_holdout_consumption() -> None:
    claim_port = _ClaimPort()
    process, _claim, _reader, _verifier, _signer = _process(claim_port=claim_port)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _item: _evaluate(process), range(2)))

    assert results[0] == results[1]
    assert claim_port.calls == 2
    assert claim_port.new_claims == 1


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        (
            replace(
                _AggregateReader().record,
                candidate_id="candidate-other",
            ),
            "campaign_holdout_identity_mismatch",
        ),
        (
            replace(
                _AggregateReader().record,
                threshold_outcomes={"constraints": True},
            ),
            "campaign_holdout_threshold_mismatch",
        ),
    ],
)
def test_aggregate_identity_and_preregistered_thresholds_fail_closed(
    record: CampaignHoldoutAggregateRecord,
    reason: str,
) -> None:
    reader = _AggregateReader()
    reader.record = record
    process, _claim, _reader, _verifier, _signer = _process(reader=reader)

    with pytest.raises(AppProcessError) as exc_info:
        _evaluate(process)

    assert _reason(exc_info) == reason


def test_numeric_or_inconsistent_threshold_result_is_rejected() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        CampaignHoldoutAggregateRecord(
            claim_id="holdout-claim-1",
            experiment_id="campaign-holdout-1",
            candidate_id="candidate-preselected-1",
            aggregate_passed=True,
            threshold_outcomes=cast("Mapping[str, bool]", {"constraints": 1.234}),
            evidence_hash=HASH_B,
        )

    assert _reason(exc_info) == "campaign_holdout_threshold_invalid"

    with pytest.raises(AppProcessError) as exc_info:
        replace(_AggregateReader().record, aggregate_passed=False)

    assert _reason(exc_info) == "campaign_holdout_aggregate_inconsistent"


def test_signature_must_bind_exact_safe_aggregate_hash() -> None:
    process, _claim, _reader, _verifier, _signer = _process(
        signer=_Signer(wrong_hash=True)
    )

    with pytest.raises(AppProcessError) as exc_info:
        _evaluate(process)

    assert _reason(exc_info) == "campaign_holdout_signature_mismatch"


def test_exported_result_rejects_signature_for_another_aggregate() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        AgentCampaignHoldoutResult(
            aggregate_passed=True,
            threshold_outcomes={"constraints": True},
            evidence_hash=HASH_B,
            aggregate_hash=HASH_A,
            signature=CampaignHoldoutSignature(
                algorithm="ed25519",
                key_id="r5-holdout-test-key",
                payload_hash=HASH_C,
                signature_hex="d" * 128,
            ),
        )

    assert _reason(exc_info) == "campaign_holdout_signature_mismatch"
