# pyright: reportPrivateUsage=false
"""Fail-closed boundaries for the Q5 Agent Author review handoff."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import orjson
import pytest
from apps.backend.tests.unit.scripts import (
    test_q5_live_agent_author_review_unit as fixtures,
)
from ditto_application.agent_authoring_contracts import (
    AgentAuthoringApprovalVerifier,
)
from ditto_application.commands.agent_authoring import AgentAuthoringCommandFacade
from ditto_apps.scripts import q5_live_agent_author_review as subject
from ditto_apps.scripts.q5_live_agent_author_review_execution import (
    AgentAuthoringFacadeFactory,
    ApprovedReviewRequest,
)

pytestmark = pytest.mark.pit


def _record(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(type(key) is str for key in value)
    return cast("dict[str, object]", value)


def _records(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [_record(item) for item in value]


@dataclass(slots=True)
class _BuildInputs:
    author: dict[str, object]
    save: dict[str, object]
    lane: dict[str, object]
    planning: dict[str, object]
    packet: dict[str, object]
    packet_bytes: bytes

    def sync_planning(self) -> None:
        compact = orjson.dumps(self.planning, option=orjson.OPT_SORT_KEYS)
        self.lane["planning_document_hash"] = hashlib.sha256(compact).hexdigest()

    def sync_packet(self) -> None:
        self.packet_bytes = orjson.dumps(self.packet, option=orjson.OPT_SORT_KEYS)
        self.lane["review_bundle_hash"] = hashlib.sha256(self.packet_bytes).hexdigest()

    def build(self) -> dict[str, object]:
        return subject.build_review_proposal(
            author_proposal=self.author,
            save_receipt=self.save,
            lane_result=self.lane,
            planning_document=self.planning,
            review_packet=self.packet,
            review_packet_bytes=self.packet_bytes,
            generated_at=fixtures.datetime(2026, 9, 2, 5, 51, tzinfo=fixtures.UTC),
        )


def _inputs() -> _BuildInputs:
    planning = fixtures._planning_document()
    planning_bytes = orjson.dumps(planning, option=orjson.OPT_SORT_KEYS)
    packet, packet_bytes, bundle_hash = fixtures._review_packet()
    return _BuildInputs(
        author=fixtures._author_proposal(),
        save=fixtures._save_receipt(),
        lane=fixtures._lane_result(
            bundle_hash,
            hashlib.sha256(planning_bytes).hexdigest(),
        ),
        planning=planning,
        packet=packet,
        packet_bytes=packet_bytes,
    )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("proposal_not_mapping", "author proposal must be an object"),
        ("proposal_non_string_key", "author proposal must have string keys"),
        ("unsafe_author", "not a safe passing proposal"),
        ("strategy_identity", "strategy identity drifted"),
        ("save_request_identity", "save approval identity drifted"),
        ("save_receipt", "save receipt is not eligible"),
    ],
)
def test_build_rejects_untrusted_author_and_save_evidence(
    case: str,
    message: str,
) -> None:
    inputs = _inputs()
    if case == "proposal_not_mapping":
        inputs.author["proposal"] = None
    elif case == "proposal_non_string_key":
        inputs.author["proposal"] = {1: "not-a-string-key"}
    elif case == "unsafe_author":
        inputs.author["passed"] = False
    elif case == "strategy_identity":
        _record(inputs.author["proposal"])["canonical_hash"] = "f" * 64
    elif case == "save_request_identity":
        _record(inputs.author["exact_save_request"])["arguments_hash"] = "f" * 64
    else:
        inputs.save["run_status"] = "failed"

    with pytest.raises(ValueError, match=message):
        inputs.build()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("sequence", "context_input_refs must be a sequence"),
        ("text", "must be a non-empty canonical string"),
        ("hash", "must be a lowercase sha256 digest"),
        ("positive", "must be a positive integer"),
        ("snapshot_set", "must be non-empty and unique"),
        ("timestamp", "must be an RFC3339 timestamp"),
        ("naive_timestamp", "must be timezone aware"),
    ],
)
def test_build_rejects_noncanonical_context_values(
    case: str,
    message: str,
) -> None:
    inputs = _inputs()
    payload = _record(_record(inputs.author["egress"])["payload"])
    if case == "sequence":
        inputs.planning["context_input_refs"] = "not-a-sequence"
        inputs.sync_planning()
    elif case == "text":
        _record(payload["lineage"])["market_context_feature_set_id"] = " "
    elif case == "hash":
        refs = _records(inputs.planning["context_input_refs"])
        refs[0]["content_hash"] = "not-a-sha256"
        inputs.sync_planning()
    elif case == "positive":
        inputs.lane["eligible_month_count"] = 0
    elif case == "snapshot_set":
        market = _record(payload["market_context"])
        market["source_snapshot_ids"] = ["snapshot:duplicate", "snapshot:duplicate"]
    elif case == "timestamp":
        _record(payload["temporal_boundary"])["as_of"] = "not-a-timestamp"
    else:
        _record(payload["temporal_boundary"])["as_of"] = "2026-09-01T16:21:00"

    with pytest.raises(ValueError, match=message):
        inputs.build()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("author_future_cutoff", "Author PIT temporal boundary is invalid"),
        ("planning_hash", "planning document hash drifted"),
        ("planning_identity", "planning identity drifted"),
        ("incomplete_context", "PIT context set is incomplete"),
        ("duplicate_context", "PIT context kind is duplicated"),
        ("lineage_drift", "PIT context lineage drifted"),
        ("lane_ineligible", "research lane is not review eligible"),
    ],
)
def test_build_rejects_future_or_drifted_research_evidence(
    case: str,
    message: str,
) -> None:
    inputs = _inputs()
    if case == "author_future_cutoff":
        payload = _record(_record(inputs.author["egress"])["payload"])
        temporal = _record(payload["temporal_boundary"])
        temporal["knowledge_cutoff"] = "2026-09-02T00:00:00Z"
    elif case == "planning_hash":
        inputs.lane["planning_document_hash"] = "f" * 64
    elif case == "planning_identity":
        _record(inputs.planning["strategy"])["version"] = 2
        inputs.sync_planning()
    elif case == "incomplete_context":
        inputs.planning["context_input_refs"] = _records(
            inputs.planning["context_input_refs"]
        )[:1]
        inputs.sync_planning()
    elif case == "duplicate_context":
        refs = _records(inputs.planning["context_input_refs"])
        refs[1]["context_kind"] = refs[0]["context_kind"]
        inputs.sync_planning()
    elif case == "lineage_drift":
        refs = _records(inputs.planning["context_input_refs"])
        refs[0]["context_id"] = "market-regime:sha256:drifted"
        inputs.sync_planning()
    else:
        inputs.lane["status"] = "failed"

    with pytest.raises(ValueError, match=message):
        inputs.build()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("invalid_json", "packet is not valid JSON"),
        ("payload_bytes_differ", "bytes and payload differ"),
        ("bundle_hash", "bundle hash drifted"),
        ("packet_identity", "packet identity drifted"),
        ("blocking_hard_gate", "blocking hard gate"),
        ("invalid_r2", "invalid R2 evidence status"),
    ],
)
def test_build_rejects_untrusted_review_packet(
    case: str,
    message: str,
) -> None:
    inputs = _inputs()
    if case == "invalid_json":
        inputs.packet_bytes = b"{"
    elif case == "payload_bytes_differ":
        inputs.packet_bytes = orjson.dumps({"different": True})
    elif case == "bundle_hash":
        inputs.lane["review_bundle_hash"] = "f" * 64
    elif case == "packet_identity":
        inputs.packet["resolved_spec_hash"] = "f" * 64
        inputs.sync_packet()
    elif case == "blocking_hard_gate":
        evaluations = _records(inputs.packet["gate_evaluations"])
        evaluations[0]["outcome"] = "fail"
        inputs.sync_packet()
    else:
        evaluations = _records(inputs.packet["gate_evaluations"])
        r2 = next(item for item in evaluations if item["rule_id"] == "r2_live_gate")
        r2["outcome"] = "fail"
        inputs.sync_packet()

    with pytest.raises(ValueError, match=message):
        inputs.build()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("proposal_boundary", "proposal boundary is invalid"),
        ("arguments", "arguments are invalid"),
        ("evidence", "evidence is no longer eligible"),
        ("future_cutoff", "PIT boundary is invalid"),
    ],
)
def test_approval_revalidates_every_bound_identity(
    case: str,
    message: str,
) -> None:
    proposal, _ = fixtures._proposal_inputs()
    request = _record(proposal["exact_submit_review_request"])
    approved_hash = cast("str", request["approval_hash"])
    if case == "proposal_boundary":
        proposal["status"] = "approved"
    elif case == "arguments":
        _record(request["arguments"])["reason"] = "submit something else"
    elif case == "evidence":
        _record(proposal["research"])["status"] = "failed"
    else:
        _record(proposal["temporal_boundary"])["knowledge_cutoff"] = (
            "2026-09-02T00:00:00Z"
        )

    with pytest.raises(ValueError, match=message):
        subject.approved_review_request(
            proposal,
            approved_request_hash=approved_hash,
        )


def test_cli_rejects_existing_output_before_loading_or_executing(
    tmp_path: Path,
) -> None:
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_bytes(b"{}")
    data_root = tmp_path / "state"
    data_root.mkdir()
    output_path = tmp_path / "existing.json"
    output_path.write_bytes(b"do-not-overwrite")

    with pytest.raises(FileExistsError) as exc_info:
        subject.main(
            [
                "--proposal",
                str(proposal_path),
                "--approved-request-hash",
                "f" * 64,
                "--data-root",
                str(data_root),
                "--output",
                str(output_path),
            ]
        )

    assert exc_info.value.filename is None
    assert output_path.read_bytes() == b"do-not-overwrite"


class _Container:
    def __init__(self) -> None:
        self.requests: list[type[object]] = []
        self.closed = False

    def get(self, dependency: type[object]) -> object:
        self.requests.append(dependency)
        return object()

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("previous_state_root", [None, "/existing/state"])
def test_cli_scopes_state_root_and_restores_the_previous_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    previous_state_root: str | None,
) -> None:
    proposal, _ = fixtures._proposal_inputs()
    request = _record(proposal["exact_submit_review_request"])
    approved_hash = cast("str", request["approval_hash"])
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_bytes(orjson.dumps(proposal, option=orjson.OPT_SORT_KEYS))
    data_root = tmp_path / "state"
    data_root.mkdir()
    output_path = tmp_path / "nested" / "result.json"
    if previous_state_root is None:
        monkeypatch.delenv("DITTO_STATE_ROOT", raising=False)
    else:
        monkeypatch.setenv("DITTO_STATE_ROOT", previous_state_root)
    container = _Container()
    execution_observed = False

    def _make_container() -> _Container:
        assert os.environ["DITTO_STATE_ROOT"] == str(data_root)
        return container

    async def _execute(
        approved: ApprovedReviewRequest,
        *,
        agent_data_root: Path,
        facade_factory: AgentAuthoringFacadeFactory,
        operator_id: str,
    ) -> dict[str, object]:
        nonlocal execution_observed
        execution_observed = True
        assert approved.request_hash == approved_hash
        assert agent_data_root == data_root
        assert operator_id == "boundary-operator"
        facade = facade_factory(cast("AgentAuthoringApprovalVerifier", object()))
        assert isinstance(facade, AgentAuthoringCommandFacade)
        return {"passed": True, "provider_calls": 0, "target_state": "review"}

    monkeypatch.setattr(subject, "make_app_container", _make_container)
    monkeypatch.setattr(subject, "execute_governed_review", _execute)

    assert (
        subject.main(
            [
                "--proposal",
                str(proposal_path),
                "--approved-request-hash",
                approved_hash,
                "--operator-id",
                "boundary-operator",
                "--data-root",
                str(data_root),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    assert execution_observed is True
    assert container.closed is True
    assert len(container.requests) == 3
    assert os.environ.get("DITTO_STATE_ROOT") == previous_state_root
    assert orjson.loads(output_path.read_bytes()) == {
        "passed": True,
        "provider_calls": 0,
        "target_state": "review",
    }
