"""Immutable per-action and autonomous-campaign authorization contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import (
    freeze_json,
    nonnegative_decimal,
    normalized_text,
    normalized_unique_tuple,
    positive_int,
    sha256_hex,
    utc_datetime,
)
from ditto_agent.contracts.temporal import TemporalToolContext

_FORBIDDEN_CAMPAIGN_TOOL_TOKENS = (
    "broker",
    "holdout",
    "order",
    "publish",
    "trade",
)


def _is_forbidden_campaign_tool(tool: str) -> bool:
    capability_tokens = frozenset(re.split(r"[^a-z0-9]+", tool.lower()))
    return any(token in capability_tokens for token in _FORBIDDEN_CAMPAIGN_TOOL_TOKENS)


@dataclass(frozen=True, slots=True)
class ActionBudget:
    """Maximum resource use authorized for one proposed action."""

    max_tool_calls: int
    max_output_bytes: int
    max_model_tokens: int
    max_model_spend_usd: Decimal

    def __post_init__(self) -> None:
        """Validate positive resource limits and a finite spend ceiling."""
        positive_int(self.max_tool_calls, field="max_tool_calls")
        positive_int(self.max_output_bytes, field="max_output_bytes")
        positive_int(self.max_model_tokens, field="max_model_tokens")
        nonnegative_decimal(self.max_model_spend_usd, field="max_model_spend_usd")


@dataclass(frozen=True, slots=True)
class ApprovalAction:
    """Complete immutable action subject authenticated by an approval hash."""

    action_kind: str
    tool_name: str
    parameters: Mapping[str, object]
    subject_identity: str
    required_authority: str
    authority_hash: str
    temporal_context: TemporalToolContext
    budget: ActionBudget
    expires_at: datetime

    def __post_init__(self) -> None:
        """Normalize and validate every safety-sensitive action field."""
        for field_name in (
            "action_kind",
            "tool_name",
            "subject_identity",
            "required_authority",
        ):
            object.__setattr__(
                self,
                field_name,
                normalized_text(getattr(self, field_name), field=field_name),
            )
        frozen = freeze_json(self.parameters, field="parameters")
        if not isinstance(frozen, Mapping):
            raise TypeError("parameters must be a mapping")
        object.__setattr__(self, "parameters", frozen)
        object.__setattr__(
            self,
            "authority_hash",
            sha256_hex(self.authority_hash, field="authority_hash"),
        )
        expires = utc_datetime(self.expires_at, field="expires_at")
        if expires <= self.temporal_context.decision_time:
            raise ValueError("expires_at must be after the temporal decision_time")
        object.__setattr__(self, "expires_at", expires)

    def canonical_payload(self) -> dict[str, object]:
        """Return every normalized action field authenticated by approval."""
        return {
            "action_kind": self.action_kind,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "subject_identity": self.subject_identity,
            "required_authority": self.required_authority,
            "authority_hash": self.authority_hash,
            "temporal_context": self.temporal_context.canonical_payload(),
            "budget": self.budget,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Canonical per-action approval identity bound to every safety input."""

    request_id: str
    run_id: str
    action: ApprovalAction
    action_hash: str

    def __post_init__(self) -> None:
        """Normalize identities without silently trusting the stored hash."""
        object.__setattr__(
            self,
            "request_id",
            normalized_text(self.request_id, field="request_id"),
        )
        object.__setattr__(
            self,
            "run_id",
            normalized_text(self.run_id, field="run_id"),
        )
        object.__setattr__(
            self, "action_hash", sha256_hex(self.action_hash, field="action_hash")
        )

    @classmethod
    def issue(
        cls,
        *,
        request_id: str,
        run_id: str,
        action: ApprovalAction,
    ) -> ApprovalRequest:
        """Issue a normalized request and derive its canonical action hash."""
        request = cls(
            request_id=request_id,
            run_id=run_id,
            action=action,
            action_hash="0" * 64,
        )
        return replace(request, action_hash=canonical_sha256(request.action_payload()))

    @classmethod
    def restore(
        cls,
        *,
        request_id: str,
        run_id: str,
        action: ApprovalAction,
        action_hash: str,
    ) -> ApprovalRequest:
        """Restore persisted state only when its canonical action hash matches."""
        request = cls(
            request_id=request_id,
            run_id=run_id,
            action=action,
            action_hash=action_hash,
        )
        if not request.verify_action_hash():
            raise ValueError("action_hash does not match the canonical action payload")
        return request

    def action_payload(self) -> dict[str, object]:
        """Return the complete canonical hash subject without the hash itself."""
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            **self.action.canonical_payload(),
        }

    def verify_action_hash(self) -> bool:
        """Verify the stored action hash against normalized immutable fields."""
        return canonical_sha256(self.action_payload()) == self.action_hash

    @property
    def action_kind(self) -> str:
        """Return the authenticated action kind."""
        return self.action.action_kind

    @property
    def tool_name(self) -> str:
        """Return the authenticated tool name."""
        return self.action.tool_name

    @property
    def parameters(self) -> Mapping[str, object]:
        """Return the deeply frozen authenticated parameters."""
        return self.action.parameters

    @property
    def subject_identity(self) -> str:
        """Return the identity acted upon by the request."""
        return self.action.subject_identity

    @property
    def required_authority(self) -> str:
        """Return the authority required for execution."""
        return self.action.required_authority

    @property
    def authority_hash(self) -> str:
        """Return the authority snapshot bound to the request."""
        return self.action.authority_hash

    @property
    def temporal_context(self) -> TemporalToolContext:
        """Return the PIT context bound to the request."""
        return self.action.temporal_context

    @property
    def budget(self) -> ActionBudget:
        """Return the resource ceiling bound to the request."""
        return self.action.budget

    @property
    def expires_at(self) -> datetime:
        """Return the normalized approval expiry."""
        return self.action.expires_at


@dataclass(frozen=True, slots=True)
class CampaignBudget:
    """Immutable ceiling for every autonomous campaign resource dimension."""

    max_generations: int
    max_unique_candidates: int
    max_fold_runs: int
    max_concurrent_sandboxes: int
    max_wall_time_seconds: int
    max_temporary_storage_bytes: int
    max_model_spend_usd: Decimal

    def __post_init__(self) -> None:
        """Reject missing, zero, negative, or non-finite resource limits."""
        for field_name in (
            "max_generations",
            "max_unique_candidates",
            "max_fold_runs",
            "max_concurrent_sandboxes",
            "max_wall_time_seconds",
            "max_temporary_storage_bytes",
        ):
            positive_int(getattr(self, field_name), field=field_name)
        nonnegative_decimal(self.max_model_spend_usd, field="max_model_spend_usd")


@dataclass(frozen=True, slots=True)
class CampaignGrant:
    """Complete immutable authority and resource grant for one campaign."""

    campaign_manifest_hash: str
    authority_hash: str
    authorized_by: str
    authorized_at: datetime
    expires_at: datetime
    search_axis: str
    allowed_tools: tuple[str, ...]
    source_snapshot_id: str
    budget: CampaignBudget

    def __post_init__(self) -> None:
        """Normalize the grant and reject forbidden campaign capabilities."""
        object.__setattr__(
            self,
            "campaign_manifest_hash",
            sha256_hex(self.campaign_manifest_hash, field="campaign_manifest_hash"),
        )
        object.__setattr__(
            self,
            "authority_hash",
            sha256_hex(self.authority_hash, field="authority_hash"),
        )
        object.__setattr__(
            self,
            "authorized_by",
            normalized_text(self.authorized_by, field="authorized_by"),
        )
        authorized = utc_datetime(self.authorized_at, field="authorized_at")
        expires = utc_datetime(self.expires_at, field="expires_at")
        if expires <= authorized:
            raise ValueError("expires_at must be after authorized_at")
        object.__setattr__(self, "authorized_at", authorized)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(
            self,
            "search_axis",
            normalized_text(self.search_axis, field="search_axis"),
        )
        tools = normalized_unique_tuple(
            self.allowed_tools, field="allowed_tools", sort=True
        )
        if any(_is_forbidden_campaign_tool(tool) for tool in tools):
            raise ValueError("allowed_tools contains a forbidden campaign action")
        object.__setattr__(self, "allowed_tools", tools)
        object.__setattr__(
            self,
            "source_snapshot_id",
            normalized_text(self.source_snapshot_id, field="source_snapshot_id"),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return every normalized campaign grant field."""
        return {
            "campaign_manifest_hash": self.campaign_manifest_hash,
            "authority_hash": self.authority_hash,
            "authorized_by": self.authorized_by,
            "authorized_at": self.authorized_at,
            "expires_at": self.expires_at,
            "search_axis": self.search_axis,
            "allowed_tools": self.allowed_tools,
            "source_snapshot_id": self.source_snapshot_id,
            "budget": self.budget,
        }


@dataclass(frozen=True, slots=True)
class CampaignAuthorization:
    """Operator authorization for one immutable campaign grant."""

    authorization_id: str
    grant: CampaignGrant
    authorization_hash: str

    def __post_init__(self) -> None:
        """Normalize the identity without silently trusting the stored hash."""
        object.__setattr__(
            self,
            "authorization_id",
            normalized_text(self.authorization_id, field="authorization_id"),
        )
        object.__setattr__(
            self,
            "authorization_hash",
            sha256_hex(self.authorization_hash, field="authorization_hash"),
        )

    @classmethod
    def issue(
        cls,
        *,
        authorization_id: str,
        grant: CampaignGrant,
    ) -> CampaignAuthorization:
        """Issue a normalized campaign authorization with an integrity hash."""
        authorization = cls(
            authorization_id=authorization_id,
            grant=grant,
            authorization_hash="0" * 64,
        )
        return replace(
            authorization,
            authorization_hash=canonical_sha256(authorization.authorization_payload()),
        )

    def authorization_payload(self) -> dict[str, object]:
        """Return the normalized grant fields authenticated by the hash."""
        return {
            "authorization_id": self.authorization_id,
            **self.grant.canonical_payload(),
        }

    def verify_authorization_hash(self) -> bool:
        """Verify that no normalized campaign authority field drifted."""
        return canonical_sha256(self.authorization_payload()) == self.authorization_hash

    @property
    def campaign_manifest_hash(self) -> str:
        """Return the authorized campaign manifest identity."""
        return self.grant.campaign_manifest_hash

    @property
    def authority_hash(self) -> str:
        """Return the bound operator authority snapshot."""
        return self.grant.authority_hash

    @property
    def authorized_by(self) -> str:
        """Return the operator identity that issued the grant."""
        return self.grant.authorized_by

    @property
    def authorized_at(self) -> datetime:
        """Return the normalized issue time."""
        return self.grant.authorized_at

    @property
    def expires_at(self) -> datetime:
        """Return the normalized campaign expiry."""
        return self.grant.expires_at

    @property
    def search_axis(self) -> str:
        """Return the one authorized search axis."""
        return self.grant.search_axis

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        """Return the explicitly authorized campaign tools."""
        return self.grant.allowed_tools

    @property
    def source_snapshot_id(self) -> str:
        """Return the source snapshot bound to the grant."""
        return self.grant.source_snapshot_id

    @property
    def budget(self) -> CampaignBudget:
        """Return the immutable campaign resource ceiling."""
        return self.grant.budget


__all__ = [
    "ActionBudget",
    "ApprovalAction",
    "ApprovalRequest",
    "CampaignAuthorization",
    "CampaignBudget",
    "CampaignGrant",
]
