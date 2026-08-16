"""Governed Agent authoring commands over existing strategy mutations."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol, cast

import orjson

from ditto_application.agent_authoring_contracts import (
    AUTHOR_SAVE_STRATEGY_DRAFT,
    AUTHOR_SUBMIT_STRATEGY_REVIEW,
    AgentAuthoringApprovalCheck,
    AgentAuthoringApprovalVerifier,
    AgentAuthoringCommandReceipt,
    AgentSaveStrategyDraftCommand,
    AgentSubmitStrategyReviewCommand,
    VerifiedAgentAuthoringApproval,
)
from ditto_application.commands.strategy import (
    CreateStrategyCommand,
    UpdateStrategyCommand,
)
from ditto_application.commands.strategy_governance import SubmitReviewCommand
from ditto_application.contracts import StrategySpecInfo, StrategyVersionStateInfo
from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    build_mutation_idempotency,
    canonical_request_hash,
    canonical_resource_id,
)

_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_PROVENANCE_KIND = "ditto_agent_authoring_provenance"


def _error(code: str, reason: str, message: str) -> AppCommandError:
    return AppCommandError(message, details={"code": code, "reason": reason})


def _text(value: str, *, field: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized != normalized.strip():
        raise _error(
            "AGENT_AUTHORING_REQUEST_INVALID",
            "agent_authoring_request_invalid",
            f"{field} must be a non-empty canonical string",
        )
    return normalized


def _hash(value: str, *, field: str) -> str:
    if _HASH_PATTERN.fullmatch(value) is None:
        raise _error(
            "AGENT_AUTHORING_REQUEST_INVALID",
            "agent_authoring_request_invalid",
            f"{field} must be a lowercase sha256 digest",
        )
    return value


def _positive(value: int, *, field: str) -> int:
    if type(value) is not int or value < 1:
        raise _error(
            "AGENT_AUTHORING_REQUEST_INVALID",
            "agent_authoring_request_invalid",
            f"{field} must be a positive integer",
        )
    return value


def _utc_text(approved_at: datetime) -> str:
    return (
        approved_at.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        raw = cast("Mapping[object, object]", value)
        return {str(key): _plain_json(item) for key, item in raw.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return [_plain_json(item) for item in sequence]
    return value


def _frozen_mapping(value: Mapping[str, object], *, field: str) -> Mapping[str, object]:
    try:
        canonical_request_hash(value)
        decoded: object = orjson.loads(
            orjson.dumps(_plain_json(value), option=orjson.OPT_SORT_KEYS)
        )
    except (AppCommandError, orjson.JSONEncodeError) as exc:
        raise _error(
            "AGENT_AUTHORING_REQUEST_INVALID",
            "agent_authoring_request_invalid",
            f"{field} must be canonical JSON",
        ) from exc
    if not isinstance(decoded, dict):
        raise _error(
            "AGENT_AUTHORING_REQUEST_INVALID",
            "agent_authoring_request_invalid",
            f"{field} must be a JSON object",
        )
    raw = cast("dict[object, object]", decoded)
    if not all(type(key) is str for key in raw):
        raise _error(
            "AGENT_AUTHORING_REQUEST_INVALID",
            "agent_authoring_request_invalid",
            f"{field} must have string keys",
        )
    return MappingProxyType(cast("dict[str, object]", raw))


class _CreateHandler(Protocol):
    def handle(self, command: CreateStrategyCommand) -> StrategySpecInfo: ...


class _UpdateHandler(Protocol):
    def handle(self, command: UpdateStrategyCommand) -> StrategySpecInfo: ...


class _SubmitHandler(Protocol):
    def handle(self, command: SubmitReviewCommand) -> StrategyVersionStateInfo: ...


class AgentAuthoringCommandFacade:
    """Verify HITL, delegate existing commands, and expose immutable receipts."""

    def __init__(
        self,
        *,
        approval_verifier: AgentAuthoringApprovalVerifier,
        create_handler: _CreateHandler,
        update_handler: _UpdateHandler,
        submit_review_handler: _SubmitHandler,
    ) -> None:
        self._approval_verifier = approval_verifier
        self._create = create_handler
        self._update = update_handler
        self._submit = submit_review_handler

    def _approved(
        self,
        *,
        run_id: str,
        episode_id: str,
        call_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
    ) -> tuple[AgentAuthoringApprovalCheck, VerifiedAgentAuthoringApproval]:
        try:
            check = AgentAuthoringApprovalCheck(
                run_id=run_id,
                episode_id=episode_id,
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
            )
            proof = self._approval_verifier.verify(check)
        except AppCommandError:
            raise
        except (TypeError, ValueError) as exc:
            raise _error(
                "AGENT_AUTHORING_APPROVAL_INVALID",
                "agent_authoring_approval_invalid",
                "Agent authoring approval is invalid",
            ) from exc
        if not proof.verify_integrity() or not proof.matches(check):
            raise _error(
                "AGENT_AUTHORING_APPROVAL_INVALID",
                "agent_authoring_approval_invalid",
                "Agent authoring approval is invalid",
            )
        if not proof.approved:
            raise _error(
                "AGENT_AUTHORING_APPROVAL_REQUIRED",
                "agent_authoring_approval_required",
                "Agent authoring write requires operator approval",
            )
        return check, proof

    @staticmethod
    def _identity(
        *,
        operation_id: str,
        resource_id: str,
        check: AgentAuthoringApprovalCheck,
        proof: VerifiedAgentAuthoringApproval,
    ) -> MutationIdempotency:
        return build_mutation_idempotency(
            operation_id=operation_id,
            resource_id=resource_id,
            raw_key=proof.action_hash,
            request_payload={
                "schema_version": 1,
                "kind": "ditto_agent_authoring_command",
                "check": check.canonical_payload(),
                "approval": proof.canonical_payload(),
            },
        )

    @staticmethod
    def _reason(
        proof: VerifiedAgentAuthoringApproval,
        identity: MutationIdempotency,
    ) -> str:
        return orjson.dumps(
            {
                "schema_version": 1,
                "kind": _PROVENANCE_KIND,
                "approval_id": proof.approval_id,
                "action_hash": proof.action_hash,
                "operator_id": proof.operator_id,
                "approved_at": _utc_text(proof.approved_at),
                "run_id": proof.run_id,
                "episode_id": proof.episode_id,
                "call_id": proof.call_id,
                "audit_identity": proof.audit_identity,
                "mutation_request_hash": identity.request_hash,
            },
            option=orjson.OPT_SORT_KEYS,
        ).decode()

    @staticmethod
    def _receipt(
        *,
        identity: MutationIdempotency,
        proof: VerifiedAgentAuthoringApproval,
        result_identity: str,
        result: Mapping[str, object],
    ) -> AgentAuthoringCommandReceipt:
        try:
            return AgentAuthoringCommandReceipt.issue(
                identity=identity,
                approval=proof,
                result_identity=result_identity,
                result=result,
            )
        except (TypeError, ValueError) as exc:
            raise _error(
                "AGENT_AUTHORING_RECEIPT_INVALID",
                "agent_authoring_receipt_invalid",
                "Agent authoring command returned an invalid receipt",
            ) from exc

    def save_strategy_draft(
        self,
        command: AgentSaveStrategyDraftCommand,
    ) -> AgentAuthoringCommandReceipt:
        """Verify and save a new or exact-base-derived strategy draft."""
        arguments: dict[str, object] = {
            "strategy_id": _text(command.strategy_id, field="strategy_id"),
            "name": _text(command.name, field="name"),
            "spec_json": _frozen_mapping(command.spec_json, field="spec_json"),
            "base_version": (
                None
                if command.base_version is None
                else _positive(command.base_version, field="base_version")
            ),
            "tags": tuple(_text(item, field="tag") for item in command.tags),
        }
        check, proof = self._approved(
            run_id=command.run_id,
            episode_id=command.episode_id,
            call_id=command.call_id,
            tool_name=AUTHOR_SAVE_STRATEGY_DRAFT,
            arguments=arguments,
        )
        operation_id = (
            "strategies_create_strategy"
            if command.base_version is None
            else "strategies_update_strategy"
        )
        resource_id = canonical_resource_id(
            "strategy", {"strategy_id": arguments["strategy_id"]}
        )
        identity = self._identity(
            operation_id=operation_id,
            resource_id=resource_id,
            check=check,
            proof=proof,
        )
        strategy_id = cast("str", arguments["strategy_id"])
        name = cast("str", arguments["name"])
        spec_json = dict(cast("Mapping[str, object]", arguments["spec_json"]))
        tags = cast("tuple[str, ...]", arguments["tags"])
        actor = f"agent:{proof.operator_id}"
        reason = self._reason(proof, identity)
        if command.base_version is None:
            info = self._create.handle(
                CreateStrategyCommand(
                    strategy_id=strategy_id,
                    name=name,
                    spec_json=spec_json,
                    tags=tags,
                    idempotency=identity,
                    actor=actor,
                    reason=reason,
                )
            )
        else:
            info = self._update.handle(
                UpdateStrategyCommand(
                    strategy_id=strategy_id,
                    name=name,
                    spec_json=spec_json,
                    version=cast("int", arguments["base_version"]),
                    tags=tags,
                    idempotency=identity,
                    actor=actor,
                    reason=reason,
                )
            )
        result = {
            "strategy_id": info.strategy_id,
            "version": info.version,
            "state": info.status,
        }
        return self._receipt(
            identity=identity,
            proof=proof,
            result_identity=f"{info.strategy_id}@{info.version}",
            result=result,
        )

    def submit_strategy_review(
        self,
        command: AgentSubmitStrategyReviewCommand,
    ) -> AgentAuthoringCommandReceipt:
        """Verify and submit one exact draft to the existing review gate."""
        arguments: dict[str, object] = {
            "strategy_id": _text(command.strategy_id, field="strategy_id"),
            "version": _positive(command.version, field="version"),
            "bundle_hash": _hash(command.bundle_hash, field="bundle_hash"),
            "reason": _text(command.reason, field="reason"),
        }
        check, proof = self._approved(
            run_id=command.run_id,
            episode_id=command.episode_id,
            call_id=command.call_id,
            tool_name=AUTHOR_SUBMIT_STRATEGY_REVIEW,
            arguments=arguments,
        )
        resource_id = canonical_resource_id(
            "strategy_version",
            {
                "strategy_id": arguments["strategy_id"],
                "version": arguments["version"],
            },
        )
        identity = self._identity(
            operation_id="strategies_submit_strategy_review",
            resource_id=resource_id,
            check=check,
            proof=proof,
        )
        info = self._submit.handle(
            SubmitReviewCommand(
                strategy_id=cast("str", arguments["strategy_id"]),
                version=cast("int", arguments["version"]),
                bundle_hash=cast("str", arguments["bundle_hash"]),
                actor=f"agent:{proof.operator_id}",
                reason=self._reason(proof, identity),
                idempotency=identity,
            )
        )
        result = {
            "strategy_id": info.strategy_id,
            "version": info.version,
            "state": info.state,
            "review_outcome": info.review_outcome,
        }
        return self._receipt(
            identity=identity,
            proof=proof,
            result_identity=f"{info.strategy_id}@{info.version}",
            result=result,
        )


__all__ = ["AgentAuthoringCommandFacade"]
