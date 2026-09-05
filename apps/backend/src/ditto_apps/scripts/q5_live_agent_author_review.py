"""Build and execute one exactly approved Q5 Agent Author review submission."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import cast

import orjson
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_application.agent_authoring_contracts import (
    AgentAuthoringApprovalVerifier,
    AgentAuthoringCommandPort,
)
from ditto_application.commands.agent_authoring import AgentAuthoringCommandFacade
from ditto_application.commands.strategy import (
    CreateStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_application.commands.strategy_governance import SubmitReviewHandler
from ditto_application.mutation_idempotency import canonical_request_hash

from ditto_apps.registry.container import make_app_container
from ditto_apps.scripts.q5_live_agent_author_review_execution import (
    AgentAuthoringFacadeFactory,
    ApprovedReviewRequest,
    execute_governed_review,
)

_HASH = re.compile(r"[0-9a-f]{64}")
_EXPECTED_SCHEMA = "ditto.q5-live-agent-author-submit-review-proposal.v1"
_EXPECTED_TOOL = "author_submit_strategy_review"
_EXPECTED_STRATEGY_ID = "agent_etf_518880_rotation"
_EXPECTED_STRATEGY_VERSION = 1
_EXPECTED_REVIEW_PACKET_SCHEMA_VERSION = 3
_MINIMUM_ELIGIBLE_MONTHS = 96
_EXPECTED_SPEC_HASH = "49e7e79197e5a645b79b44cf09b22205ffa73e430558aa70386572a87994c33c"
_EXPECTED_MARKET_HASH = (
    "387116ab36ebfe0be555cdcc01f162d28c283343bda04f623db89379f780c3c3"
)
_EXPECTED_TECHNICAL_HASH = (
    "c4990645727dad34d10fba34f42e79ee7207118ca8b9f8142d44cb556e1d303f"
)
_EXPECTED_SAVE_HASH = "1b7608964ee37e211c729e969da0ae44d2822cdfc81049409107186fa9b7f12d"
_EXPECTED_HARD_GATES = frozenset(
    {
        "certified_snapshot",
        "ninety_six_month_protocol",
        "pit_known_at",
        "split_purge_embargo",
        "reproduction_fingerprint",
        "cost_assumptions",
        "baseline_declared",
        "trial_declaration",
        "holdout_claim",
        "artifact_completeness",
    }
)
_REQUEST_KEYS = frozenset({"strategy_id", "version", "bundle_hash", "reason"})
_SAFETY = {
    "provider_calls": 0,
    "publishes_strategy": False,
    "activates_strategy": False,
    "creates_trade": False,
    "target_state": "review",
}


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    raw = cast("Mapping[object, object]", value)
    if not all(type(key) is str for key in raw):
        raise ValueError(f"{field} must have string keys")
    return cast("Mapping[str, object]", raw)


def _sequence(value: object, *, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a sequence")
    return cast("Sequence[object]", value)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _hash(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return value


def _positive(value: object, *, field: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _text_tuple(value: object, *, field: str) -> tuple[str, ...]:
    result = tuple(_text(item, field=field) for item in _sequence(value, field=field))
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{field} must be non-empty and unique")
    return result


def _timestamp(value: object, *, field: str) -> tuple[str, datetime]:
    text = _text(value, field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone aware")
    utc = parsed.astimezone(UTC)
    return utc.isoformat().replace("+00:00", "Z"), utc


def _author_context(
    author_proposal: Mapping[str, object],
) -> tuple[Mapping[str, object], Mapping[str, object], Mapping[str, object]]:
    if (
        author_proposal.get("schema") != "ditto.q5-live-agent-author-proposal.v1"
        or author_proposal.get("passed") is not True
        or author_proposal.get("production_eligible") is not False
        or author_proposal.get("holdout_excluded") is not True
    ):
        raise ValueError("Q5 Author proposal is not a safe passing proposal")
    proposal = _mapping(author_proposal.get("proposal"), field="author proposal")
    if (
        proposal.get("strategy_id") != _EXPECTED_STRATEGY_ID
        or proposal.get("canonical_hash") != _EXPECTED_SPEC_HASH
        or proposal.get("publishable") is not False
    ):
        raise ValueError("Q5 Author strategy identity drifted")
    save_request = _mapping(
        author_proposal.get("exact_save_request"), field="exact_save_request"
    )
    if save_request.get("arguments_hash") != _EXPECTED_SAVE_HASH:
        raise ValueError("Q5 Author save approval identity drifted")
    egress = _mapping(author_proposal.get("egress"), field="egress")
    payload = _mapping(egress.get("payload"), field="egress.payload")
    return (
        _mapping(payload.get("lineage"), field="egress.payload.lineage"),
        _mapping(
            payload.get("temporal_boundary"), field="egress.payload.temporal_boundary"
        ),
        payload,
    )


def _validate_save_receipt(save_receipt: Mapping[str, object]) -> None:
    strategy = _mapping(save_receipt.get("strategy"), field="save strategy")
    if (
        save_receipt.get("schema") != "ditto.q5-live-agent-author-save.v1"
        or save_receipt.get("passed") is not True
        or save_receipt.get("request_hash") != _EXPECTED_SAVE_HASH
        or save_receipt.get("approval_status") != "approved"
        or save_receipt.get("run_status") != "completed"
        or save_receipt.get("provider_calls") != 0
        or save_receipt.get("publishable") is not False
        or strategy
        != {
            "strategy_id": _EXPECTED_STRATEGY_ID,
            "version": _EXPECTED_STRATEGY_VERSION,
            "state": "draft",
        }
    ):
        raise ValueError("Q5 exact-save receipt is not eligible for review")


def _expected_context_refs(
    *,
    lineage: Mapping[str, object],
    temporal: Mapping[str, object],
    payload: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    timestamps = {
        field: _timestamp(temporal.get(field), field=f"temporal_boundary.{field}")
        for field in ("as_of", "knowledge_cutoff", "publication_cutoff")
    }
    if not (
        timestamps["publication_cutoff"][1]
        <= timestamps["knowledge_cutoff"][1]
        <= timestamps["as_of"][1]
    ):
        raise ValueError("Q5 Author PIT temporal boundary is invalid")
    canonical_times = {field: value[0] for field, value in timestamps.items()}
    market = _mapping(payload.get("market_context"), field="market_context")
    technical = _mapping(payload.get("technical"), field="technical")
    return {
        "market_context": {
            "context_id": _text(
                lineage.get("market_context_feature_set_id"),
                field="market_context_feature_set_id",
            ),
            "content_hash": _EXPECTED_MARKET_HASH,
            **canonical_times,
            "source_snapshot_ids": tuple(
                sorted(
                    _text_tuple(
                        market.get("source_snapshot_ids"),
                        field="market source_snapshot_ids",
                    ),
                    key=str.encode,
                )
            ),
        },
        "technical_analysis": {
            "context_id": _text(
                lineage.get("technical_snapshot_id"), field="technical_snapshot_id"
            ),
            "content_hash": _EXPECTED_TECHNICAL_HASH,
            **canonical_times,
            "source_snapshot_ids": tuple(
                sorted(
                    _text_tuple(
                        technical.get("source_snapshot_ids"),
                        field="technical source_snapshot_ids",
                    ),
                    key=str.encode,
                )
            ),
        },
    }


def _validate_planning(
    *,
    planning_document: Mapping[str, object],
    lane_result: Mapping[str, object],
    expected_refs: Mapping[str, Mapping[str, object]],
) -> None:
    compact = orjson.dumps(planning_document, option=orjson.OPT_SORT_KEYS)
    if hashlib.sha256(compact).hexdigest() != lane_result.get("planning_document_hash"):
        raise ValueError("Q5 review planning document hash drifted")
    strategy = _mapping(planning_document.get("strategy"), field="planning strategy")
    snapshot = _mapping(planning_document.get("snapshot"), field="planning snapshot")
    if (
        planning_document.get("experiment_id") != lane_result.get("experiment_id")
        or strategy.get("strategy_id") != _EXPECTED_STRATEGY_ID
        or strategy.get("version") != _EXPECTED_STRATEGY_VERSION
        or strategy.get("spec_hash") != _EXPECTED_SPEC_HASH
        or snapshot.get("manifest_hash") != lane_result.get("snapshot_manifest_hash")
    ):
        raise ValueError("Q5 review planning identity drifted")
    raw_refs = _sequence(
        planning_document.get("context_input_refs"), field="context_input_refs"
    )
    if len(raw_refs) != len(expected_refs):
        raise ValueError("Q5 review PIT context set is incomplete")
    observed: dict[str, dict[str, object]] = {}
    for index, item in enumerate(raw_refs):
        ref = _mapping(item, field=f"context_input_refs[{index}]")
        kind = _text(ref.get("context_kind"), field="context_kind")
        times = {
            field: _timestamp(ref.get(field), field=f"context_input_refs.{field}")
            for field in ("as_of", "knowledge_cutoff", "publication_cutoff")
        }
        if not (
            times["publication_cutoff"][1]
            <= times["knowledge_cutoff"][1]
            <= times["as_of"][1]
        ):
            raise ValueError("Q5 review PIT cutoff exceeds the decision timestamp")
        if kind in observed:
            raise ValueError("Q5 review PIT context kind is duplicated")
        observed[kind] = {
            "context_id": _text(ref.get("context_id"), field="context_id"),
            "content_hash": _hash(ref.get("content_hash"), field="content_hash"),
            **{field: value[0] for field, value in times.items()},
            "source_snapshot_ids": tuple(
                sorted(
                    _text_tuple(
                        ref.get("source_snapshot_ids"), field="source_snapshot_ids"
                    ),
                    key=str.encode,
                )
            ),
        }
    if observed != expected_refs:
        raise ValueError("Q5 review PIT context lineage drifted")


def _validate_review_packet(
    *,
    review_packet: Mapping[str, object],
    review_packet_bytes: bytes,
    lane_result: Mapping[str, object],
) -> tuple[int, str]:
    try:
        persisted_packet = _mapping(
            orjson.loads(review_packet_bytes), field="persisted review packet"
        )
    except orjson.JSONDecodeError as exc:
        raise ValueError("Q5 review packet is not valid JSON") from exc
    if persisted_packet != review_packet:
        raise ValueError("Q5 review packet bytes and payload differ")
    bundle_hash = hashlib.sha256(review_packet_bytes).hexdigest()
    if bundle_hash != lane_result.get("review_bundle_hash"):
        raise ValueError("Q5 review bundle hash drifted")
    if (
        review_packet.get("schema_version") != _EXPECTED_REVIEW_PACKET_SCHEMA_VERSION
        or review_packet.get("resolved_spec_hash") != _EXPECTED_SPEC_HASH
        or review_packet.get("holdout_claim_id") != lane_result.get("holdout_claim_id")
    ):
        raise ValueError("Q5 review packet identity drifted")
    evaluations = tuple(
        _mapping(item, field="gate_evaluation")
        for item in _sequence(
            review_packet.get("gate_evaluations"), field="gate_evaluations"
        )
    )
    hard = tuple(item for item in evaluations if item.get("layer") == "hard")
    hard_rules = frozenset(
        _text(item.get("rule_id"), field="hard rule_id") for item in hard
    )
    if (
        len(hard_rules) != len(hard)
        or not _EXPECTED_HARD_GATES.issubset(hard_rules)
        or any(item.get("outcome") != "pass" for item in hard)
    ):
        raise ValueError("Q5 review packet has a blocking hard gate")
    r2 = tuple(item for item in evaluations if item.get("rule_id") == "r2_live_gate")
    if len(r2) != 1 or r2[0].get("outcome") not in {"pass", "not_evaluated"}:
        raise ValueError("Q5 review packet has invalid R2 evidence status")
    return len(hard), _text(r2[0].get("outcome"), field="r2_live_gate.outcome")


def _review_evidence_binding_hash(proposal: Mapping[str, object]) -> str:
    """Bind the exact review action to the host-validated PIT evidence."""
    return canonical_sha256(
        {
            "schema": proposal.get("schema"),
            "strategy": _mapping(proposal.get("strategy"), field="strategy"),
            "research": _mapping(proposal.get("research"), field="research"),
            "lineage": _mapping(proposal.get("lineage"), field="lineage"),
            "temporal_boundary": _mapping(
                proposal.get("temporal_boundary"), field="temporal_boundary"
            ),
            "source_snapshot_ids": _text_tuple(
                proposal.get("source_snapshot_ids"), field="source_snapshot_ids"
            ),
        }
    )


def build_review_proposal(
    *,
    author_proposal: Mapping[str, object],
    save_receipt: Mapping[str, object],
    lane_result: Mapping[str, object],
    planning_document: Mapping[str, object],
    review_packet: Mapping[str, object],
    review_packet_bytes: bytes,
    generated_at: datetime,
) -> dict[str, object]:
    """Build one exact submit-review proposal from fully revalidated evidence."""
    lineage, temporal, author_payload = _author_context(author_proposal)
    _validate_save_receipt(save_receipt)
    if (
        lane_result.get("schema") != "ditto.r3-live-golden-lane.v1"
        or lane_result.get("status") != "completed"
        or lane_result.get("lane") != "etf"
        or lane_result.get("strategy_id") != _EXPECTED_STRATEGY_ID
        or lane_result.get("candidate_version") != _EXPECTED_STRATEGY_VERSION
        or lane_result.get("strategy_spec_hash") != _EXPECTED_SPEC_HASH
        or _positive(
            lane_result.get("eligible_month_count"), field="eligible_month_count"
        )
        < _MINIMUM_ELIGIBLE_MONTHS
        or lane_result.get("holdout_duplicate_blocked") is not True
    ):
        raise ValueError("Q5 real research lane is not review eligible")
    expected_refs = _expected_context_refs(
        lineage=lineage,
        temporal=temporal,
        payload=author_payload,
    )
    _validate_planning(
        planning_document=planning_document,
        lane_result=lane_result,
        expected_refs=expected_refs,
    )
    hard_count, r2_outcome = _validate_review_packet(
        review_packet=review_packet,
        review_packet_bytes=review_packet_bytes,
        lane_result=lane_result,
    )
    experiment_id = _text(lane_result.get("experiment_id"), field="experiment_id")
    bundle_hash = _hash(
        lane_result.get("review_bundle_hash"), field="review_bundle_hash"
    )
    reason = (
        f"Submit completed Q5 Agent Author experiment {experiment_id} to review; "
        "no publish or trade authority."
    )
    arguments: dict[str, object] = {
        "strategy_id": _EXPECTED_STRATEGY_ID,
        "version": _EXPECTED_STRATEGY_VERSION,
        "bundle_hash": bundle_hash,
        "reason": reason,
    }
    r2_observed = _mapping(
        next(
            item
            for item in _sequence(
                review_packet.get("gate_evaluations"), field="gate_evaluations"
            )
            if _mapping(item, field="gate_evaluation").get("rule_id") == "r2_live_gate"
        ),
        field="r2_live_gate",
    )
    observed = _mapping(r2_observed.get("observed"), field="r2_live_gate.observed")
    proposal: dict[str, object] = {
        "schema": _EXPECTED_SCHEMA,
        "generated_at": generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "status": "pending_operator_approval",
        "strategy": {
            "strategy_id": _EXPECTED_STRATEGY_ID,
            "version": _EXPECTED_STRATEGY_VERSION,
            "state": "draft",
            "review_outcome": "pending",
            "spec_hash": _EXPECTED_SPEC_HASH,
        },
        "research": {
            "experiment_id": experiment_id,
            "status": "completed",
            "eligible_month_count": lane_result["eligible_month_count"],
            "review_bundle_hash": bundle_hash,
            "holdout_claim_id": _text(
                lane_result.get("holdout_claim_id"), field="holdout_claim_id"
            ),
            "holdout_duplicate_blocked": True,
            "hard_gate_pass_count": hard_count,
            "hard_gate_failure_count": 0,
            "r2_live_gate": {
                "outcome": r2_outcome,
                "reason_code": observed.get("reason_code"),
                "scope": "global_22_product_bundle",
                "is_strategy_review_hard_gate": False,
            },
        },
        "lineage": {
            "selection_run_id": _text(
                lineage.get("selection_run_id"), field="selection_run_id"
            ),
            "research_case_id": _text(
                lineage.get("research_case_id"), field="research_case_id"
            ),
            "market_context_feature_set_id": _text(
                lineage.get("market_context_feature_set_id"),
                field="market_context_feature_set_id",
            ),
            "technical_snapshot_id": _text(
                lineage.get("technical_snapshot_id"), field="technical_snapshot_id"
            ),
            "planning_document_hash": _hash(
                lane_result.get("planning_document_hash"),
                field="planning_document_hash",
            ),
            "snapshot_manifest_hash": _hash(
                lane_result.get("snapshot_manifest_hash"),
                field="snapshot_manifest_hash",
            ),
        },
        "temporal_boundary": dict(temporal),
        "source_snapshot_ids": tuple(
            sorted(
                {
                    snapshot
                    for ref in expected_refs.values()
                    for snapshot in cast("tuple[str, ...]", ref["source_snapshot_ids"])
                },
                key=str.encode,
            )
        ),
    }
    arguments_hash = canonical_request_hash(arguments)
    evidence_binding_hash = _review_evidence_binding_hash(proposal)
    approval_hash = canonical_request_hash(
        {
            "tool_name": _EXPECTED_TOOL,
            "arguments_hash": arguments_hash,
            "evidence_binding_hash": evidence_binding_hash,
        }
    )
    proposal["exact_submit_review_request"] = {
        "tool_name": _EXPECTED_TOOL,
        "arguments": arguments,
        "arguments_hash": arguments_hash,
        "evidence_binding_hash": evidence_binding_hash,
        "approval_hash": approval_hash,
        "requires_exact_approval": True,
        "status": "pending_operator_approval",
    }
    proposal["safety"] = dict(_SAFETY)
    return proposal


def approved_review_request(
    proposal_payload: Mapping[str, object],
    *,
    approved_request_hash: str,
) -> ApprovedReviewRequest:
    """Fail closed unless the operator approved this exact safe review action."""
    approved_hash = _hash(approved_request_hash, field="approval hash")
    if (
        proposal_payload.get("schema") != _EXPECTED_SCHEMA
        or proposal_payload.get("status") != "pending_operator_approval"
        or _mapping(proposal_payload.get("safety"), field="safety") != _SAFETY
    ):
        raise ValueError("Q5 submit-review proposal boundary is invalid")
    strategy = _mapping(proposal_payload.get("strategy"), field="strategy")
    research = _mapping(proposal_payload.get("research"), field="research")
    lineage = _mapping(proposal_payload.get("lineage"), field="lineage")
    temporal = _mapping(
        proposal_payload.get("temporal_boundary"), field="temporal_boundary"
    )
    request = _mapping(
        proposal_payload.get("exact_submit_review_request"),
        field="exact_submit_review_request",
    )
    arguments = _mapping(request.get("arguments"), field="review arguments")
    arguments_hash = _hash(request.get("arguments_hash"), field="arguments_hash")
    evidence_binding_hash = _hash(
        request.get("evidence_binding_hash"), field="evidence_binding_hash"
    )
    stored_approval_hash = _hash(request.get("approval_hash"), field="approval_hash")
    experiment_id = _text(research.get("experiment_id"), field="experiment_id")
    bundle_hash = _hash(research.get("review_bundle_hash"), field="bundle_hash")
    expected_reason = (
        f"Submit completed Q5 Agent Author experiment {experiment_id} to review; "
        "no publish or trade authority."
    )
    if (
        request.get("tool_name") != _EXPECTED_TOOL
        or request.get("requires_exact_approval") is not True
        or request.get("status") != "pending_operator_approval"
        or frozenset(arguments) != _REQUEST_KEYS
        or arguments
        != {
            "strategy_id": _EXPECTED_STRATEGY_ID,
            "version": _EXPECTED_STRATEGY_VERSION,
            "bundle_hash": bundle_hash,
            "reason": expected_reason,
        }
        or canonical_request_hash(arguments) != arguments_hash
    ):
        raise ValueError("Q5 submit-review arguments are invalid")
    if (
        strategy.get("strategy_id") != _EXPECTED_STRATEGY_ID
        or strategy.get("version") != _EXPECTED_STRATEGY_VERSION
        or strategy.get("state") != "draft"
        or strategy.get("review_outcome") != "pending"
        or strategy.get("spec_hash") != _EXPECTED_SPEC_HASH
        or research.get("status") != "completed"
        or research.get("holdout_duplicate_blocked") is not True
        or research.get("hard_gate_failure_count") != 0
    ):
        raise ValueError("Q5 submit-review evidence is no longer eligible")
    timestamps = {
        field: _timestamp(temporal.get(field), field=field)
        for field in ("as_of", "knowledge_cutoff", "publication_cutoff")
    }
    if not (
        timestamps["publication_cutoff"][1]
        <= timestamps["knowledge_cutoff"][1]
        <= timestamps["as_of"][1]
    ):
        raise ValueError("Q5 submit-review PIT boundary is invalid")
    if _review_evidence_binding_hash(proposal_payload) != evidence_binding_hash:
        raise ValueError("Q5 submit-review evidence binding is invalid")
    expected_approval_hash = canonical_request_hash(
        {
            "tool_name": _EXPECTED_TOOL,
            "arguments_hash": arguments_hash,
            "evidence_binding_hash": evidence_binding_hash,
        }
    )
    if (
        stored_approval_hash != expected_approval_hash
        or approved_hash != stored_approval_hash
    ):
        raise ValueError("Q5 submit-review approval hash is invalid")
    return ApprovedReviewRequest(
        arguments=MappingProxyType(dict(arguments)),
        request_hash=stored_approval_hash,
        arguments_hash=arguments_hash,
        bundle_hash=bundle_hash,
        experiment_id=experiment_id,
        spec_hash=_hash(strategy.get("spec_hash"), field="spec_hash"),
        planning_document_hash=_hash(
            lineage.get("planning_document_hash"), field="planning_document_hash"
        ),
        snapshot_manifest_hash=_hash(
            lineage.get("snapshot_manifest_hash"), field="snapshot_manifest_hash"
        ),
        knowledge_cutoff=timestamps["knowledge_cutoff"][0],
        publication_cutoff=timestamps["publication_cutoff"][0],
        source_snapshot_ids=_text_tuple(
            proposal_payload.get("source_snapshot_ids"), field="source_snapshot_ids"
        ),
        selection_run_id=_text(
            lineage.get("selection_run_id"), field="selection_run_id"
        ),
        research_case_id=_text(
            lineage.get("research_case_id"), field="research_case_id"
        ),
        market_context_feature_set_id=_text(
            lineage.get("market_context_feature_set_id"),
            field="market_context_feature_set_id",
        ),
        technical_snapshot_id=_text(
            lineage.get("technical_snapshot_id"), field="technical_snapshot_id"
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--approved-request-hash", required=True)
    parser.add_argument("--operator-id", default="workspace-user")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local-only review submission after exact CLI approval binding."""
    arguments = _parser().parse_args(argv)
    proposal_path = Path(arguments.proposal).resolve(strict=True)
    data_root = Path(arguments.data_root).resolve(strict=True)
    output_path = Path(arguments.output)
    if output_path.exists():
        raise FileExistsError(output_path)
    raw_proposal: object = orjson.loads(proposal_path.read_bytes())
    proposal = _mapping(raw_proposal, field="review proposal artifact")
    approved = approved_review_request(
        proposal,
        approved_request_hash=str(arguments.approved_request_hash),
    )
    previous_state_root = os.environ.get("DITTO_STATE_ROOT")
    os.environ["DITTO_STATE_ROOT"] = str(data_root)
    container = make_app_container()
    try:

        def facade_factory(
            verifier: AgentAuthoringApprovalVerifier,
        ) -> AgentAuthoringCommandPort:
            return AgentAuthoringCommandFacade(
                approval_verifier=verifier,
                create_handler=container.get(CreateStrategyHandler),
                update_handler=container.get(UpdateStrategyHandler),
                submit_review_handler=container.get(SubmitReviewHandler),
            )

        result = asyncio.run(
            execute_governed_review(
                approved,
                agent_data_root=data_root,
                facade_factory=facade_factory,
                operator_id=str(arguments.operator_id),
            )
        )
    finally:
        container.close()
        if previous_state_root is None:
            del os.environ["DITTO_STATE_ROOT"]
        else:
            os.environ["DITTO_STATE_ROOT"] = previous_state_root
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_bytes(result))
    return 0


__all__ = [
    "AgentAuthoringFacadeFactory",
    "ApprovedReviewRequest",
    "approved_review_request",
    "build_review_proposal",
    "execute_governed_review",
    "main",
]


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
