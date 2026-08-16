"""Approval-gated, leakage-safe Campaign access to one sealed holdout result."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import NoReturn, Protocol, cast

from ditto_application.exceptions import AppProcessError
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.processes.experiments.holdout import (
    ClaimHoldoutCandidateRequest,
    HoldoutClaimReceipt,
)
from ditto_application.processes.experiments.scheduler_store import SchedulerLease

__all__ = [
    "AgentCampaignHoldoutProcess",
    "AgentCampaignHoldoutRequest",
    "AgentCampaignHoldoutResult",
    "CampaignHoldoutAggregateReader",
    "CampaignHoldoutAggregateRecord",
    "CampaignHoldoutApprovalCheck",
    "CampaignHoldoutApprovalVerifier",
    "CampaignHoldoutClaimPort",
    "CampaignHoldoutSignature",
    "CampaignHoldoutSigner",
    "VerifiedCampaignHoldoutApproval",
]

_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{128}")
_THRESHOLD_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{0,63}")
_TOOL_NAME = "campaign_holdout_evaluate"


def _error(reason: str, **details: object) -> NoReturn:
    raise AppProcessError(
        "Campaign holdout evaluation is invalid",
        details={"code": "CAMPAIGN_HOLDOUT_INVALID", "reason": reason, **details},
    )


def _text(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _error("campaign_holdout_text_invalid", field=field_name)
    return value


def _hash(value: object, field_name: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _error("campaign_holdout_hash_invalid", field=field_name)
    return value


def _utc(value: object, field_name: str) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _error("campaign_holdout_time_must_be_utc", field=field_name)
    return value


def _utc_text(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _threshold_ids(values: object) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        _error("campaign_holdout_thresholds_invalid")
    resolved = tuple(cast("Sequence[object]", values))
    if not resolved:
        _error("campaign_holdout_thresholds_invalid")
    for value in resolved:
        if type(value) is not str or _THRESHOLD_PATTERN.fullmatch(value) is None:
            _error("campaign_holdout_threshold_invalid")
    normalized = tuple(sorted(cast("tuple[str, ...]", resolved)))
    if len(normalized) != len(set(normalized)):
        _error("campaign_holdout_thresholds_invalid")
    return normalized


def _threshold_outcomes(values: object) -> Mapping[str, bool]:
    if not isinstance(values, Mapping) or not values:
        _error("campaign_holdout_threshold_invalid")
    normalized: dict[str, bool] = {}
    for raw_key, raw_value in cast("Mapping[object, object]", values).items():
        if (
            type(raw_key) is not str
            or _THRESHOLD_PATTERN.fullmatch(raw_key) is None
            or type(raw_value) is not bool
        ):
            _error("campaign_holdout_threshold_invalid")
        normalized[raw_key] = raw_value
    return MappingProxyType(dict(sorted(normalized.items())))


def _claim_request_hash(request: ClaimHoldoutCandidateRequest) -> str:
    return canonical_request_hash(
        {
            "schema_version": 1,
            "kind": "ditto_campaign_holdout_claim_request",
            "experiment_id": request.experiment_id,
            "candidate_id": request.candidate_id,
            "expected_revision": request.expected_revision,
            "expected_selection_evidence_hash": (
                request.expected_selection_evidence_hash
            ),
            "operator_confirmation": request.operator_confirmation,
            "selection_reason": {
                "code": request.selection_reason.code,
                "summary": request.selection_reason.summary,
            },
            "occurred_at": _utc_text(request.occurred_at),
            "selection_id": request.selection_id,
            "expected_candidate_evidence_content_hash": (
                request.expected_candidate_evidence_content_hash
            ),
        }
    )


@dataclass(frozen=True, slots=True)
class AgentCampaignHoldoutRequest:
    """Host request for one independently approved sealed evaluation."""

    claim: ClaimHoldoutCandidateRequest
    run_id: str
    episode_id: str
    call_id: str
    expected_threshold_ids: Sequence[str]

    def __post_init__(self) -> None:
        """Bind approval to one candidate claim and preregistered threshold set."""
        if type(self.claim) is not ClaimHoldoutCandidateRequest:
            _error("campaign_holdout_claim_request_invalid")
        run_id = _text(self.run_id, "run_id")
        episode_id = _text(self.episode_id, "episode_id")
        _text(self.call_id, "call_id")
        if episode_id != f"episode-{run_id}":
            _error("campaign_holdout_episode_identity_invalid")
        object.__setattr__(
            self,
            "expected_threshold_ids",
            _threshold_ids(self.expected_threshold_ids),
        )

    def approval_arguments(self) -> Mapping[str, object]:
        """Return the non-holdout-data action body requiring human approval."""
        return MappingProxyType(
            {
                "claim_request_hash": _claim_request_hash(self.claim),
                "expected_threshold_ids": tuple(self.expected_threshold_ids),
            }
        )


@dataclass(frozen=True, slots=True)
class CampaignHoldoutApprovalCheck:
    """Exact tool call independently presented to the approval authority."""

    run_id: str
    episode_id: str
    call_id: str
    arguments: Mapping[str, object]
    tool_name: str = _TOOL_NAME
    action_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Canonicalize the action before an approval can be issued."""
        _text(self.run_id, "run_id")
        _text(self.episode_id, "episode_id")
        _text(self.call_id, "call_id")
        if self.tool_name != _TOOL_NAME:
            _error("campaign_holdout_approval_invalid")
        arguments = dict(self.arguments)
        claim_hash = _hash(arguments.get("claim_request_hash"), "claim_request_hash")
        threshold_ids = _threshold_ids(arguments.get("expected_threshold_ids"))
        if set(arguments) != {"claim_request_hash", "expected_threshold_ids"}:
            _error("campaign_holdout_approval_invalid")
        frozen = MappingProxyType(
            {
                "claim_request_hash": claim_hash,
                "expected_threshold_ids": threshold_ids,
            }
        )
        object.__setattr__(self, "arguments", frozen)
        object.__setattr__(
            self,
            "action_hash",
            canonical_request_hash(self.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return the exact independently approved action."""
        return {
            "schema_version": 1,
            "kind": "ditto_campaign_holdout_approval_check",
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
        }


@dataclass(frozen=True, slots=True)
class VerifiedCampaignHoldoutApproval:
    """Self-verifying independent approval for one exact holdout action."""

    approval_id: str
    run_id: str
    episode_id: str
    call_id: str
    tool_name: str
    action_hash: str
    operator_id: str
    approved_at: datetime
    approved: bool
    verification_hash: str

    def __post_init__(self) -> None:
        """Validate representation without trusting issuer integrity."""
        for field_name in (
            "approval_id",
            "run_id",
            "episode_id",
            "call_id",
            "operator_id",
        ):
            _text(getattr(self, field_name), field_name)
        if self.tool_name != _TOOL_NAME:
            _error("campaign_holdout_approval_invalid")
        _hash(self.action_hash, "action_hash")
        _utc(self.approved_at, "approved_at")
        if type(self.approved) is not bool:
            _error("campaign_holdout_approval_invalid")
        _hash(self.verification_hash, "verification_hash")

    @classmethod
    def issue(
        cls,
        *,
        check: CampaignHoldoutApprovalCheck,
        approval_id: str,
        action_hash: str,
        operator_id: str,
        approved_at: datetime,
        approved: bool,
    ) -> VerifiedCampaignHoldoutApproval:
        """Issue a proof binding the independent decision to the exact action."""
        if type(check) is not CampaignHoldoutApprovalCheck:
            _error("campaign_holdout_approval_invalid")
        proof = cls(
            approval_id=approval_id,
            run_id=check.run_id,
            episode_id=check.episode_id,
            call_id=check.call_id,
            tool_name=check.tool_name,
            action_hash=action_hash,
            operator_id=operator_id,
            approved_at=approved_at,
            approved=approved,
            verification_hash="0" * 64,
        )
        return replace(
            proof,
            verification_hash=canonical_request_hash(proof.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return every field covered by the integrity hash."""
        return {
            "schema_version": 1,
            "kind": "ditto_verified_campaign_holdout_approval",
            "approval_id": self.approval_id,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "action_hash": self.action_hash,
            "operator_id": self.operator_id,
            "approved_at": _utc_text(self.approved_at),
            "approved": self.approved,
        }

    def matches(self, check: CampaignHoldoutApprovalCheck) -> bool:
        """Verify integrity and exact call identity."""
        return (
            canonical_request_hash(self.canonical_payload()) == self.verification_hash
            and self.run_id == check.run_id
            and self.episode_id == check.episode_id
            and self.call_id == check.call_id
            and self.tool_name == check.tool_name
            and self.action_hash == check.action_hash
        )


class CampaignHoldoutApprovalVerifier(Protocol):
    """Independent human-approval authority."""

    def verify(
        self, check: CampaignHoldoutApprovalCheck
    ) -> VerifiedCampaignHoldoutApproval:
        """Return an independently verified decision for the exact action."""
        ...


class CampaignHoldoutClaimPort(Protocol):
    """Existing append-only one-shot holdout claim authority."""

    def claim_candidate(
        self,
        request: ClaimHoldoutCandidateRequest,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> HoldoutClaimReceipt:
        """Atomically create or replay one append-only holdout claim."""
        ...


@dataclass(frozen=True, slots=True)
class CampaignHoldoutAggregateRecord:
    """Trusted internal aggregate; never serialized into Agent context directly."""

    claim_id: str
    experiment_id: str
    candidate_id: str
    aggregate_passed: bool
    threshold_outcomes: Mapping[str, bool]
    evidence_hash: str
    aggregate_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Reject numeric metrics and inconsistent threshold aggregation."""
        _text(self.claim_id, "claim_id")
        _text(self.experiment_id, "experiment_id")
        _text(self.candidate_id, "candidate_id")
        if type(self.aggregate_passed) is not bool:
            _error("campaign_holdout_aggregate_invalid")
        outcomes = _threshold_outcomes(self.threshold_outcomes)
        object.__setattr__(self, "threshold_outcomes", outcomes)
        if self.aggregate_passed is not all(outcomes.values()):
            _error("campaign_holdout_aggregate_inconsistent")
        evidence_hash = _hash(self.evidence_hash, "evidence_hash")
        object.__setattr__(
            self,
            "aggregate_hash",
            canonical_request_hash(
                {
                    "schema_version": 1,
                    "kind": "ditto_campaign_holdout_safe_aggregate",
                    "claim_id": self.claim_id,
                    "experiment_id": self.experiment_id,
                    "candidate_id": self.candidate_id,
                    "aggregate_passed": self.aggregate_passed,
                    "threshold_outcomes": dict(outcomes),
                    "evidence_hash": evidence_hash,
                }
            ),
        )


class CampaignHoldoutAggregateReader(Protocol):
    """Trusted reader producing only preregistered aggregate predicates."""

    def read_aggregate(self, claim_id: str) -> CampaignHoldoutAggregateRecord:
        """Read the committed safe aggregate for one exact claim."""
        ...


@dataclass(frozen=True, slots=True)
class CampaignHoldoutSignature:
    """Detached signature over one exact safe aggregate hash."""

    algorithm: str
    key_id: str
    payload_hash: str
    signature_hex: str

    def __post_init__(self) -> None:
        """Require the production signature contract at the port boundary."""
        if self.algorithm != "ed25519":
            _error("campaign_holdout_signature_invalid")
        _text(self.key_id, "key_id")
        _hash(self.payload_hash, "payload_hash")
        if (
            type(self.signature_hex) is not str
            or _SIGNATURE_PATTERN.fullmatch(self.signature_hex) is None
        ):
            _error("campaign_holdout_signature_invalid")


class CampaignHoldoutSigner(Protocol):
    """Trusted host signing boundary for aggregate evidence."""

    def sign(self, aggregate_hash: str) -> CampaignHoldoutSignature:
        """Sign the exact safe aggregate content hash."""
        ...


@dataclass(frozen=True, slots=True)
class AgentCampaignHoldoutResult:
    """The complete and deliberately narrow Agent-visible holdout result."""

    aggregate_passed: bool
    threshold_outcomes: Mapping[str, bool]
    evidence_hash: str
    aggregate_hash: str
    signature: CampaignHoldoutSignature

    def __post_init__(self) -> None:
        """Preserve the leakage-safe result surface after orchestration."""
        if type(self.aggregate_passed) is not bool:
            _error("campaign_holdout_aggregate_invalid")
        outcomes = _threshold_outcomes(self.threshold_outcomes)
        object.__setattr__(self, "threshold_outcomes", outcomes)
        if self.aggregate_passed is not all(outcomes.values()):
            _error("campaign_holdout_aggregate_inconsistent")
        _hash(self.evidence_hash, "evidence_hash")
        _hash(self.aggregate_hash, "aggregate_hash")
        if type(self.signature) is not CampaignHoldoutSignature:
            _error("campaign_holdout_signature_invalid")
        if self.signature.payload_hash != self.aggregate_hash:
            _error("campaign_holdout_signature_mismatch")

    def to_agent_payload(self) -> dict[str, object]:
        """Serialize only signed aggregate predicates and content hashes."""
        return {
            "aggregate_passed": self.aggregate_passed,
            "threshold_outcomes": dict(self.threshold_outcomes),
            "evidence_hash": self.evidence_hash,
            "aggregate_hash": self.aggregate_hash,
            "signature": {
                "algorithm": self.signature.algorithm,
                "key_id": self.signature.key_id,
                "signature_hex": self.signature.signature_hex,
            },
        }


class AgentCampaignHoldoutProcess:
    """Approve, atomically claim, read, and sign one sealed holdout aggregate."""

    def __init__(
        self,
        *,
        claim_port: CampaignHoldoutClaimPort,
        aggregate_reader: CampaignHoldoutAggregateReader,
        approval_verifier: CampaignHoldoutApprovalVerifier,
        signer: CampaignHoldoutSigner,
    ) -> None:
        self._claim_port = claim_port
        self._aggregate_reader = aggregate_reader
        self._approval_verifier = approval_verifier
        self._signer = signer

    def evaluate(
        self,
        request: AgentCampaignHoldoutRequest,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> AgentCampaignHoldoutResult:
        """Return a signed boolean aggregate after independent approval."""
        self._validate_authority(request, lease=lease, now_epoch_us=now_epoch_us)
        self._require_approval(request)
        receipt = self._claim(
            request,
            lease=lease,
            now_epoch_us=now_epoch_us,
        )
        aggregate = self._read_aggregate(request, receipt)
        signature = self._sign(aggregate)
        return AgentCampaignHoldoutResult(
            aggregate_passed=aggregate.aggregate_passed,
            threshold_outcomes=aggregate.threshold_outcomes,
            evidence_hash=aggregate.evidence_hash,
            aggregate_hash=aggregate.aggregate_hash,
            signature=signature,
        )

    @staticmethod
    def _validate_authority(
        request: AgentCampaignHoldoutRequest,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> None:
        if type(request) is not AgentCampaignHoldoutRequest:
            _error("campaign_holdout_request_invalid")
        if (
            type(lease) is not SchedulerLease
            or str(lease.experiment_id) != request.claim.experiment_id
            or type(now_epoch_us) is not int
            or now_epoch_us < 0
        ):
            _error("campaign_holdout_claim_authority_required")

    def _require_approval(self, request: AgentCampaignHoldoutRequest) -> None:
        check = CampaignHoldoutApprovalCheck(
            run_id=request.run_id,
            episode_id=request.episode_id,
            call_id=request.call_id,
            arguments=request.approval_arguments(),
        )
        approval = self._approval_verifier.verify(check)
        if type(approval) is not VerifiedCampaignHoldoutApproval:
            _error("campaign_holdout_approval_invalid")
        if not approval.matches(check):
            _error("campaign_holdout_approval_invalid")
        if not approval.approved:
            _error("campaign_holdout_approval_required")
        if approval.approved_at > request.claim.occurred_at:
            _error("campaign_holdout_approval_invalid")

    def _claim(
        self,
        request: AgentCampaignHoldoutRequest,
        *,
        lease: SchedulerLease | None,
        now_epoch_us: int | None,
    ) -> HoldoutClaimReceipt:
        receipt = self._claim_port.claim_candidate(
            request.claim,
            lease=lease,
            now_epoch_us=now_epoch_us,
        )
        if type(receipt) is not HoldoutClaimReceipt:
            _error("campaign_holdout_claim_receipt_invalid")
        if (
            receipt.experiment_id != request.claim.experiment_id
            or receipt.candidate_id != request.claim.candidate_id
            or receipt.selection_evidence_hash
            != request.claim.expected_selection_evidence_hash
        ):
            _error("campaign_holdout_claim_identity_mismatch")
        return receipt

    def _read_aggregate(
        self,
        request: AgentCampaignHoldoutRequest,
        receipt: HoldoutClaimReceipt,
    ) -> CampaignHoldoutAggregateRecord:
        aggregate = self._aggregate_reader.read_aggregate(receipt.claim_id)
        if type(aggregate) is not CampaignHoldoutAggregateRecord:
            _error("campaign_holdout_aggregate_invalid")
        if (
            aggregate.claim_id != receipt.claim_id
            or aggregate.experiment_id != receipt.experiment_id
            or aggregate.candidate_id != receipt.candidate_id
        ):
            _error("campaign_holdout_identity_mismatch")
        if tuple(aggregate.threshold_outcomes) != tuple(request.expected_threshold_ids):
            _error("campaign_holdout_threshold_mismatch")
        return aggregate

    def _sign(
        self,
        aggregate: CampaignHoldoutAggregateRecord,
    ) -> CampaignHoldoutSignature:
        signature = self._signer.sign(aggregate.aggregate_hash)
        if type(signature) is not CampaignHoldoutSignature:
            _error("campaign_holdout_signature_invalid")
        if signature.payload_hash != aggregate.aggregate_hash:
            _error("campaign_holdout_signature_mismatch")
        return signature
