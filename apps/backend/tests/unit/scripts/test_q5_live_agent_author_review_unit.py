"""Exact-approval boundary for the Q5 Agent Author review lane."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import orjson
import pytest
from ditto_application.agent_authoring_contracts import AgentAuthoringApprovalVerifier
from ditto_application.commands.agent_authoring import AgentAuthoringCommandFacade
from ditto_application.commands.strategy import (
    CreateStrategyCommand,
    UpdateStrategyCommand,
)
from ditto_application.commands.strategy_governance import SubmitReviewCommand
from ditto_application.contracts import StrategySpecInfo, StrategyVersionStateInfo
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_apps.scripts.q5_live_agent_author_review import (
    approved_review_request,
    build_review_proposal,
    execute_governed_review,
)

_STRATEGY_ID = "agent_etf_518880_rotation"
_SPEC_HASH = "49e7e79197e5a645b79b44cf09b22205ffa73e430558aa70386572a87994c33c"
_EXPERIMENT_ID = "r3-live-etf-agent-author-etf-context-933d21313ceb59d117d3ac06"
_DECISION_TIME = "2026-09-01T16:21:00Z"
_MARKET_ID = (
    "market-regime:sha256:"
    "a99b2576dc18a56a6cee0647b3516dab44c060a147c94fcadb80ec3734f22a77"
)
_TECHNICAL_ID = (
    "technical-analysis:sha256:"
    "7fd63a1af43abd5647da648c866f1abdb8c471d26c653356fd998ede1a83c028"
)
_MARKET_HASH = "387116ab36ebfe0be555cdcc01f162d28c283343bda04f623db89379f780c3c3"
_TECHNICAL_HASH = "c4990645727dad34d10fba34f42e79ee7207118ca8b9f8142d44cb556e1d303f"
_MARKET_SNAPSHOTS = (
    "snapshot:tushare:global_index_daily:sha256:market-global",
    "snapshot:tushare:index_daily:sha256:market-index",
    "snapshot:tushare:stock_daily:sha256:market-stock",
)
_TECHNICAL_SNAPSHOTS = ("snapshot:tushare:etf_daily:sha256:technical-etf",)
_HARD_GATES = (
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
)


def _record(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


def _author_proposal() -> dict[str, object]:
    return {
        "schema": "ditto.q5-live-agent-author-proposal.v1",
        "passed": True,
        "production_eligible": False,
        "holdout_excluded": True,
        "proposal": {
            "strategy_id": _STRATEGY_ID,
            "canonical_hash": _SPEC_HASH,
            "publishable": False,
        },
        "exact_save_request": {
            "arguments_hash": (
                "1b7608964ee37e211c729e969da0ae44d2822cdfc81049409107186fa9b7f12d"
            )
        },
        "egress": {
            "payload": {
                "lineage": {
                    "selection_run_id": "selection-run:sha256:selection",
                    "research_case_id": "research-case:sha256:case",
                    "market_context_feature_set_id": _MARKET_ID,
                    "technical_snapshot_id": _TECHNICAL_ID,
                },
                "market_context": {
                    "source_snapshot_ids": list(_MARKET_SNAPSHOTS),
                },
                "technical": {
                    "source_snapshot_ids": list(_TECHNICAL_SNAPSHOTS),
                },
                "temporal_boundary": {
                    "as_of": _DECISION_TIME,
                    "knowledge_cutoff": _DECISION_TIME,
                    "publication_cutoff": _DECISION_TIME,
                },
            }
        },
    }


def _save_receipt() -> dict[str, object]:
    return {
        "schema": "ditto.q5-live-agent-author-save.v1",
        "passed": True,
        "request_hash": (
            "1b7608964ee37e211c729e969da0ae44d2822cdfc81049409107186fa9b7f12d"
        ),
        "approval_status": "approved",
        "run_status": "completed",
        "provider_calls": 0,
        "publishable": False,
        "strategy": {
            "strategy_id": _STRATEGY_ID,
            "version": 1,
            "state": "draft",
        },
    }


def _context_ref(
    *, kind: str, context_id: str, content_hash: str, snapshots: tuple[str, ...]
) -> dict[str, object]:
    return {
        "context_kind": kind,
        "context_id": context_id,
        "content_hash": content_hash,
        "as_of": _DECISION_TIME,
        "knowledge_cutoff": _DECISION_TIME,
        "publication_cutoff": _DECISION_TIME,
        "source_snapshot_ids": list(snapshots),
    }


def _planning_document() -> dict[str, object]:
    return {
        "experiment_id": _EXPERIMENT_ID,
        "strategy": {
            "strategy_id": _STRATEGY_ID,
            "version": 1,
            "spec_hash": _SPEC_HASH,
            "spec_json": {"strategy_id": _STRATEGY_ID},
        },
        "snapshot": {
            "snapshot_id": "r3-live-etf-snapshot",
            "manifest_hash": "7" * 64,
        },
        "context_input_refs": [
            _context_ref(
                kind="market_context",
                context_id=_MARKET_ID,
                content_hash=_MARKET_HASH,
                snapshots=_MARKET_SNAPSHOTS,
            ),
            _context_ref(
                kind="technical_analysis",
                context_id=_TECHNICAL_ID,
                content_hash=_TECHNICAL_HASH,
                snapshots=_TECHNICAL_SNAPSHOTS,
            ),
        ],
    }


def _review_packet() -> tuple[dict[str, object], bytes, str]:
    packet = {
        "schema_version": 3,
        "resolved_spec_hash": _SPEC_HASH,
        "holdout_claim_id": "holdout:exact-claim",
        "gate_evaluations": [
            *(
                {"rule_id": rule_id, "layer": "hard", "outcome": "pass"}
                for rule_id in _HARD_GATES
            ),
            {
                "rule_id": "r2_live_gate",
                "layer": "evidence",
                "outcome": "not_evaluated",
                "observed": {"reason_code": "r2_live_evidence_unavailable"},
            },
        ],
    }
    raw = orjson.dumps(packet, option=orjson.OPT_SORT_KEYS)
    return packet, raw, hashlib.sha256(raw).hexdigest()


def _lane_result(bundle_hash: str, planning_hash: str) -> dict[str, object]:
    return {
        "schema": "ditto.r3-live-golden-lane.v1",
        "status": "completed",
        "lane": "etf",
        "purpose": "agent-author-etf-context",
        "experiment_id": _EXPERIMENT_ID,
        "eligible_month_count": 136,
        "strategy_id": _STRATEGY_ID,
        "candidate_version": 1,
        "strategy_spec_hash": _SPEC_HASH,
        "snapshot_manifest_hash": "7" * 64,
        "planning_document_hash": planning_hash,
        "review_bundle_hash": bundle_hash,
        "holdout_claim_id": "holdout:exact-claim",
        "holdout_duplicate_blocked": True,
        "r2_live_gate": "not_evaluated",
    }


def _proposal_inputs() -> tuple[dict[str, object], dict[str, object]]:
    planning = _planning_document()
    planning_hash = hashlib.sha256(
        orjson.dumps(planning, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    packet, packet_bytes, bundle_hash = _review_packet()
    proposal = build_review_proposal(
        author_proposal=_author_proposal(),
        save_receipt=_save_receipt(),
        lane_result=_lane_result(bundle_hash, planning_hash),
        planning_document=planning,
        review_packet=packet,
        review_packet_bytes=packet_bytes,
        generated_at=datetime(2026, 9, 2, 5, 51, tzinfo=UTC),
    )
    return proposal, planning


def test_review_proposal_binds_exact_completed_research_and_safe_action() -> None:
    proposal, _ = _proposal_inputs()
    request = _record(proposal["exact_submit_review_request"])
    arguments = _record(request["arguments"])
    research = _record(proposal["research"])

    assert request["arguments_hash"] == canonical_request_hash(arguments)
    assert arguments == {
        "strategy_id": _STRATEGY_ID,
        "version": 1,
        "bundle_hash": research["review_bundle_hash"],
        "reason": (
            f"Submit completed Q5 Agent Author experiment {_EXPERIMENT_ID} to "
            "review; no publish or trade authority."
        ),
    }
    assert research["hard_gate_pass_count"] == 10
    assert proposal["safety"] == {
        "provider_calls": 0,
        "publishes_strategy": False,
        "activates_strategy": False,
        "creates_trade": False,
        "target_state": "review",
    }


@pytest.mark.pit
def test_review_proposal_rejects_future_context_sentinel() -> None:
    planning = _planning_document()
    context_refs = planning["context_input_refs"]
    assert isinstance(context_refs, list)
    _record(context_refs[0])["knowledge_cutoff"] = "2026-09-02T00:00:00Z"
    planning_hash = hashlib.sha256(
        orjson.dumps(planning, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    packet, packet_bytes, bundle_hash = _review_packet()

    with pytest.raises(ValueError, match="PIT"):
        build_review_proposal(
            author_proposal=_author_proposal(),
            save_receipt=_save_receipt(),
            lane_result=_lane_result(bundle_hash, planning_hash),
            planning_document=planning,
            review_packet=packet,
            review_packet_bytes=packet_bytes,
            generated_at=datetime(2026, 9, 2, 5, 51, tzinfo=UTC),
        )


def test_exact_review_rejects_a_different_operator_approval_hash() -> None:
    proposal, _ = _proposal_inputs()

    with pytest.raises(ValueError, match="approval hash"):
        approved_review_request(proposal, approved_request_hash="f" * 64)


def test_exact_review_rejects_lineage_tamper_after_proposal() -> None:
    proposal, _ = _proposal_inputs()
    request = cast("dict[str, object]", proposal["exact_submit_review_request"])
    lineage = cast("dict[str, object]", proposal["lineage"])
    lineage["selection_run_id"] = "selection-run:sha256:tampered"

    with pytest.raises(ValueError, match="evidence binding"):
        approved_review_request(
            proposal,
            approved_request_hash=cast("str", request["approval_hash"]),
        )


class _SubmitHandler:
    def __init__(self) -> None:
        self.calls: list[SubmitReviewCommand] = []

    def handle(self, command: SubmitReviewCommand) -> StrategyVersionStateInfo:
        self.calls.append(command)
        return StrategyVersionStateInfo(
            strategy_id=_STRATEGY_ID,
            version=1,
            state="review",
            review_outcome="pending",
        )


class _UnexpectedCreateHandler:
    def handle(self, command: CreateStrategyCommand) -> StrategySpecInfo:
        del command
        raise AssertionError("exact-review acceptance must not create")


class _UnexpectedUpdateHandler:
    def handle(self, command: UpdateStrategyCommand) -> StrategySpecInfo:
        del command
        raise AssertionError("exact-review acceptance must not update")


def test_governed_review_revalidates_approval_and_only_submits_review(
    tmp_path: Path,
) -> None:
    proposal, _ = _proposal_inputs()
    request = cast("dict[str, object]", proposal["exact_submit_review_request"])
    approved = approved_review_request(
        proposal,
        approved_request_hash=cast("str", request["approval_hash"]),
    )
    submit = _SubmitHandler()

    def facade_factory(
        verifier: AgentAuthoringApprovalVerifier,
    ) -> AgentAuthoringCommandFacade:
        return AgentAuthoringCommandFacade(
            approval_verifier=verifier,
            create_handler=_UnexpectedCreateHandler(),
            update_handler=_UnexpectedUpdateHandler(),
            submit_review_handler=submit,
        )

    result = asyncio.run(
        execute_governed_review(
            approved,
            agent_data_root=tmp_path,
            facade_factory=facade_factory,
            operator_id="workspace-user",
            clock=lambda: datetime(2026, 9, 2, 6, 0, tzinfo=UTC),
        )
    )

    assert len(submit.calls) == 1
    command = submit.calls[0]
    assert command.strategy_id == _STRATEGY_ID
    assert command.version == 1
    assert command.bundle_hash == approved.bundle_hash
    assert result["passed"] is True
    assert result["provider_calls"] == 0
    assert result["agent_tool_call_count"] == 1
    assert result["strategy"] == {
        "strategy_id": _STRATEGY_ID,
        "version": 1,
        "state": "review",
        "review_outcome": "pending",
    }
    assert result["publishable"] is False
