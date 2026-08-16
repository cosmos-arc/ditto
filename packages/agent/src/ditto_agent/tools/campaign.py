"""Campaign-authorized candidate proposal tool with host-injected authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ditto_application.agent_campaign_contracts import (
    CAMPAIGN_PROPOSE_CANDIDATE,
    AutonomousCampaignCommandPort,
    CampaignCandidateProposalCommand,
    CampaignCandidateReceipt,
)

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import normalized_text
from ditto_agent.contracts.approval import CampaignAuthorization
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.tools._common import Arguments, function_spec

_TEXT = {"type": "string", "minLength": 1}
_NULLABLE_HASH = {
    "type": ["string", "null"],
    "pattern": "^[0-9a-f]{64}$",
}
_HASHES = {
    "type": "array",
    "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "minItems": 1,
    "uniqueItems": True,
}


@dataclass(frozen=True, slots=True)
class CampaignToolExecutionContext:
    """Trusted Campaign and model-call identities injected by the host."""

    campaign_id: str
    run_id: str
    episode_id: str
    call_id: str

    def __post_init__(self) -> None:
        """Normalize identities and bind the episode to its run."""
        for field in ("campaign_id", "run_id", "episode_id", "call_id"):
            object.__setattr__(
                self,
                field,
                normalized_text(getattr(self, field), field=field),
            )
        if self.episode_id != f"episode-{self.run_id}":
            raise ValueError("episode_id must be bound to run_id")


def _validate_authority(
    *,
    authorization: CampaignAuthorization,
    context: TemporalToolContext,
) -> None:
    if type(authorization) is not CampaignAuthorization:
        raise ValueError("authorization must be CampaignAuthorization")
    if not authorization.verify_authorization_hash():
        raise ValueError("campaign authorization hash mismatch")
    if CAMPAIGN_PROPOSE_CANDIDATE not in authorization.allowed_tools:
        raise ValueError("candidate proposal tool is not campaign-authorized")
    if context.campaign_authorization_id != authorization.authorization_id:
        raise ValueError("campaign authorization context mismatch")
    if context.campaign_authority_hash != authorization.authority_hash:
        raise ValueError("campaign authority context mismatch")
    if context.source_snapshot_id != authorization.source_snapshot_id:
        raise ValueError("campaign source snapshot context mismatch")
    if (
        not authorization.authorized_at
        <= context.decision_time
        <= authorization.expires_at
    ):
        raise ValueError("campaign authorization is not active")


def _seal_receipt(
    *,
    receipt: CampaignCandidateReceipt,
    context: TemporalToolContext,
    execution: CampaignToolExecutionContext,
) -> EvidenceEnvelope:
    if not receipt.verify_integrity():
        raise ValueError("application campaign receipt hash mismatch")
    result: Mapping[str, object] = {
        "schema_version": 1,
        "kind": "agent_campaign_candidate_receipt",
        "receipt_hash": receipt.receipt_hash,
        "receipt": receipt.canonical_payload(),
    }
    evidence_hash = canonical_sha256(
        {
            "tool_name": CAMPAIGN_PROPOSE_CANDIDATE,
            "receipt_hash": receipt.receipt_hash,
            "temporal_context": context.canonical_payload(),
        }
    )
    return EvidenceEnvelope.seal(
        evidence_id=f"evidence-{evidence_hash}",
        tool_name=CAMPAIGN_PROPOSE_CANDIDATE,
        result=result,
        artifact_refs=(f"campaign-receipt:sha256:{receipt.receipt_hash}",),
        temporal_context=context,
        lineage=(
            f"campaign:{execution.campaign_id}",
            f"agent-run:{execution.run_id}",
            f"agent-episode:{execution.episode_id}",
            f"application-event:{receipt.event_id}",
        ),
    )


class CampaignProposalTool:
    """Submit model candidate content under immutable host Campaign authority."""

    spec = function_spec(
        name=CAMPAIGN_PROPOSE_CANDIDATE,
        description=(
            "Propose one candidate inside the authorized Campaign search axis; "
            "the host owns scheduling, evaluation, budgets, and stopping."
        ),
        properties={
            "parent_candidate_id": _TEXT,
            "parameters": {"type": "object"},
            "factor_code_hash": _NULLABLE_HASH,
            "model_code_hash": _NULLABLE_HASH,
            "data_requirement_hashes": _HASHES,
        },
        required=(
            "parent_candidate_id",
            "parameters",
            "factor_code_hash",
            "model_code_hash",
            "data_requirement_hashes",
        ),
    )

    def __init__(self, *, commands: AutonomousCampaignCommandPort) -> None:
        self._commands = commands

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
        authorization: CampaignAuthorization,
        execution: CampaignToolExecutionContext,
    ) -> EvidenceEnvelope:
        """Inject verified authority and delegate an exact proposal to Application."""
        _validate_authority(authorization=authorization, context=context)
        parsed = Arguments(
            arguments,
            required=(
                "parent_candidate_id",
                "parameters",
                "factor_code_hash",
                "model_code_hash",
                "data_requirement_hashes",
            ),
        )
        receipt = self._commands.propose_candidate(
            CampaignCandidateProposalCommand(
                campaign_id=execution.campaign_id,
                authorization_id=authorization.authorization_id,
                authorization_hash=authorization.authorization_hash,
                authority_hash=authorization.authority_hash,
                run_id=execution.run_id,
                episode_id=execution.episode_id,
                call_id=execution.call_id,
                parent_candidate_id=parsed.text("parent_candidate_id"),
                parameters=parsed.mapping("parameters"),
                factor_code_hash=parsed.optional_text("factor_code_hash"),
                model_code_hash=parsed.optional_text("model_code_hash"),
                data_requirement_hashes=parsed.text_tuple("data_requirement_hashes"),
            ),
            occurred_at=context.decision_time,
        )
        if receipt.campaign_id != execution.campaign_id:
            raise ValueError("application campaign receipt identity mismatch")
        return _seal_receipt(
            receipt=receipt,
            context=context,
            execution=execution,
        )


__all__ = ["CampaignProposalTool", "CampaignToolExecutionContext"]
