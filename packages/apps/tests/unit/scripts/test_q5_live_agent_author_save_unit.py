"""Exact-approval boundary for the Q5 Agent Author save lane."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from typing import cast

import orjson
import pytest
from ditto_agent._canonical import canonical_bytes
from ditto_application.commands.agent_authoring import AgentAuthoringCommandFacade
from ditto_application.commands.strategy import CreateStrategyCommand
from ditto_application.contracts import StrategySpecInfo
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_apps.scripts.q5_live_agent_author import _AUTHOR_SPEC_TEMPLATE
from ditto_apps.scripts.q5_live_agent_author_save import (
    approved_save_request,
    execute_governed_save,
)


def _proposal() -> dict[str, object]:
    spec = deepcopy(_AUTHOR_SPEC_TEMPLATE)
    arguments = {
        "strategy_id": "agent_etf_518880_rotation",
        "name": "518880 黄金 ETF 证据绑定策略",
        "spec_json": spec,
        "base_version": None,
        "tags": ["agent-authored", "etf", "gold", "q5"],
    }
    return {
        "schema": "ditto.q5-live-agent-author-proposal.v1",
        "status": "passed",
        "passed": True,
        "holdout_excluded": True,
        "run_id": "run-q5-author-proposal",
        "episode_manifest_hash": "a" * 64,
        "episode_replay_identity": "b" * 64,
        "episode_verified": True,
        "egress": {
            "payload": {
                "lineage": {
                    "selection_run_id": "selection-run:sha256:selection",
                    "research_case_id": "research-case:sha256:case",
                    "market_context_feature_set_id": "market-regime:sha256:market",
                    "technical_snapshot_id": "technical-analysis:sha256:technical",
                },
                "technical": {
                    "instrument_id": 2_001_724,
                    "instrument_name": "华安易富黄金ETF",
                    "last_visible_bar_at": "2026-07-31T07:00:00Z",
                    "source_snapshot_ids": [
                        "snapshot:tushare:etf_daily:sha256:technical"
                    ],
                },
            }
        },
        "proposal": {
            "strategy_id": "agent_etf_518880_rotation",
            "spec_json": spec,
            "canonical_hash": (
                "2d677219fd4ae439f55ccddffcc512fb2965122f78901311d79ae8884d8a0965"
            ),
            "publishable": False,
        },
        "exact_save_request": {
            "tool_name": "author_save_strategy_draft",
            "arguments": arguments,
            "arguments_hash": canonical_request_hash(arguments),
            "requires_exact_approval": True,
            "status": "pending_operator_approval",
        },
    }


def test_exact_save_rejects_a_different_operator_approval_hash() -> None:
    with pytest.raises(ValueError, match="approval hash"):
        approved_save_request(_proposal(), approved_request_hash="f" * 64)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"holdout_excluded": False}),
        lambda payload: payload["proposal"].update({"publishable": True}),
        lambda payload: payload["exact_save_request"].update(
            {"tool_name": "author_submit_strategy_review"}
        ),
        lambda payload: payload["exact_save_request"].update(
            {"arguments_hash": "c" * 64}
        ),
    ],
)
def test_exact_save_revalidates_the_frozen_proposal_before_any_write(
    mutation: object,
) -> None:
    proposal = _proposal()
    assert callable(mutation)
    mutation(proposal)

    with pytest.raises(ValueError):
        approved_save_request(
            proposal,
            approved_request_hash=canonical_request_hash(
                proposal["exact_save_request"]["arguments"]
            ),
        )


def test_exact_save_returns_only_the_approved_host_frozen_arguments() -> None:
    proposal = _proposal()
    request_hash = proposal["exact_save_request"]["arguments_hash"]

    approved = approved_save_request(
        proposal,
        approved_request_hash=request_hash,
    )

    assert approved.request_hash == request_hash
    assert approved.arguments["strategy_id"] == "agent_etf_518880_rotation"
    assert approved.arguments["base_version"] is None
    assert approved.arguments["tags"] == (
        "agent-authored",
        "etf",
        "gold",
        "q5",
    )
    assert approved.selection_run_id == "selection-run:sha256:selection"
    assert approved.technical_snapshot_id == ("technical-analysis:sha256:technical")
    assert approved.instrument_code == "518880.SH"


def test_exact_save_accepts_verified_v1_prewrite_hash_after_artifact_roundtrip() -> (
    None
):
    proposal = _proposal()
    request_hash = proposal["exact_save_request"]["arguments_hash"]
    persisted = orjson.loads(canonical_bytes(proposal))

    approved = approved_save_request(
        persisted,
        approved_request_hash=request_hash,
    )

    assert approved.request_hash == request_hash
    spec = approved.arguments["spec_json"]
    assert spec["constraints"][0]["params"]["max_weight"] == 1.0
    assert spec["execution"]["cost_model"]["slippage_bps"] == 5.0


class _CreateHandler:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def handle(self, command: object) -> StrategySpecInfo:
        self.calls.append(command)
        return StrategySpecInfo(
            strategy_id="agent_etf_518880_rotation",
            name="518880 黄金 ETF 证据绑定策略",
            spec_json=deepcopy(_AUTHOR_SPEC_TEMPLATE),
            version=1,
            status="draft",
            created_at="2026-09-02T03:20:00Z",
            tags=("agent-authored", "etf", "gold", "q5"),
        )


class _UnexpectedHandler:
    def handle(self, command: object) -> object:
        del command
        raise AssertionError("exact-save acceptance must not update or submit review")


def test_governed_save_revalidates_durable_approval_at_the_write_boundary(
    tmp_path: object,
) -> None:
    proposal = _proposal()
    request_hash = proposal["exact_save_request"]["arguments_hash"]
    approved = approved_save_request(
        proposal,
        approved_request_hash=request_hash,
    )
    create = _CreateHandler()

    def facade_factory(verifier: object) -> AgentAuthoringCommandFacade:
        return AgentAuthoringCommandFacade(
            approval_verifier=verifier,
            create_handler=create,
            update_handler=_UnexpectedHandler(),
            submit_review_handler=_UnexpectedHandler(),
        )

    result = asyncio.run(
        execute_governed_save(
            approved,
            agent_data_root=tmp_path,
            facade_factory=facade_factory,
            operator_id="workspace-user",
            clock=lambda: datetime(2026, 9, 2, 3, 20, tzinfo=UTC),
        )
    )

    assert len(create.calls) == 1
    assert result["passed"] is True
    assert result["approval_status"] == "approved"
    assert result["run_status"] == "completed"
    assert result["request_hash"] == request_hash
    assert result["strategy"] == {
        "strategy_id": "agent_etf_518880_rotation",
        "version": 1,
        "state": "draft",
    }
    assert result["receipt_hash"]
    assert result["approval_action_hash"]
    command = cast("CreateStrategyCommand", create.calls[0])
    assert type(command.spec_json["constraints"][0]["params"]["max_weight"]) is float
    assert type(command.spec_json["execution"]["cost_model"]["slippage_bps"]) is float
