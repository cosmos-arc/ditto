"""Governed Agent authoring writes only cross application command boundaries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import cast

import orjson
import pytest
from ditto_application.agent_authoring_contracts import (
    AgentAuthoringApprovalCheck,
    AgentSaveStrategyDraftCommand,
    AgentSubmitStrategyReviewCommand,
    VerifiedAgentAuthoringApproval,
)
from ditto_application.commands.agent_authoring import AgentAuthoringCommandFacade
from ditto_application.commands.strategy import (
    CreateStrategyHandler,
    UpdateStrategyHandler,
)
from ditto_application.contracts import StrategySpecInfo, StrategyVersionStateInfo
from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    find_mutation_receipt_in_reasons,
    mutation_event_id,
)
from ditto_platform.foundation import SQLitePool
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
)
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
APPROVED_AT = datetime(2026, 8, 12, 7, 5, tzinfo=UTC)


class _Verifier:
    def __init__(self, *, approved: bool = True, tamper_hash: bool = False) -> None:
        self.approved = approved
        self.tamper_hash = tamper_hash
        self.calls: list[AgentAuthoringApprovalCheck] = []

    def verify(
        self,
        check: AgentAuthoringApprovalCheck,
    ) -> VerifiedAgentAuthoringApproval:
        self.calls.append(check)
        result = VerifiedAgentAuthoringApproval.issue(
            check=check,
            approval_id="approval-001",
            action_hash=HASH_A,
            operator_id="operator-001",
            approved_at=APPROVED_AT,
            approved=self.approved,
        )
        return replace(result, action_hash=HASH_B) if self.tamper_hash else result


class _CreateHandler:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def handle(self, command: object) -> StrategySpecInfo:
        self.calls.append(command)
        return StrategySpecInfo(
            strategy_id="strategy-001",
            name="Momentum",
            spec_json={"strategy_family_id": "strategy-001"},
            version=1,
            status="draft",
            created_at="2026-08-12T07:06:00Z",
            tags=("agent",),
        )


class _UpdateHandler(_CreateHandler):
    pass


class _SubmitHandler:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def handle(self, command: object) -> StrategyVersionStateInfo:
        self.calls.append(command)
        return StrategyVersionStateInfo(
            strategy_id="strategy-001",
            version=1,
            state="review",
            review_outcome="pending",
        )


def _facade(
    *,
    verifier: _Verifier | None = None,
    create: _CreateHandler | None = None,
    update: _UpdateHandler | None = None,
    submit: _SubmitHandler | None = None,
) -> tuple[
    AgentAuthoringCommandFacade,
    _Verifier,
    _CreateHandler,
    _UpdateHandler,
    _SubmitHandler,
]:
    resolved_verifier = verifier or _Verifier()
    resolved_create = create or _CreateHandler()
    resolved_update = update or _UpdateHandler()
    resolved_submit = submit or _SubmitHandler()
    return (
        AgentAuthoringCommandFacade(
            approval_verifier=resolved_verifier,
            create_handler=resolved_create,
            update_handler=resolved_update,
            submit_review_handler=resolved_submit,
        ),
        resolved_verifier,
        resolved_create,
        resolved_update,
        resolved_submit,
    )


def _save_command() -> AgentSaveStrategyDraftCommand:
    return AgentSaveStrategyDraftCommand(
        strategy_id="strategy-001",
        name="Momentum",
        spec_json={"strategy_family_id": "strategy-001"},
        base_version=None,
        tags=("agent",),
        run_id="run-001",
        episode_id="episode-run-001",
        call_id="call-save-001",
    )


def _submit_command() -> AgentSubmitStrategyReviewCommand:
    return AgentSubmitStrategyReviewCommand(
        strategy_id="strategy-001",
        version=1,
        bundle_hash="c" * 64,
        reason="Submit the validated Agent draft for operator review.",
        run_id="run-001",
        episode_id="episode-run-001",
        call_id="call-submit-001",
    )


@pytest.mark.parametrize("invalid", [True, 1.5])
def test_non_integral_versions_fail_before_approval_or_mutation(
    invalid: object,
) -> None:
    facade, verifier, create, update, submit = _facade()

    with pytest.raises(AppCommandError, match="positive integer"):
        facade.save_strategy_draft(
            replace(_save_command(), base_version=cast("int", invalid))
        )
    with pytest.raises(AppCommandError, match="positive integer"):
        facade.submit_strategy_review(
            replace(_submit_command(), version=cast("int", invalid))
        )

    assert verifier.calls == []
    assert create.calls == []
    assert update.calls == []
    assert submit.calls == []


def test_approval_proof_rejects_non_boolean_decision() -> None:
    check = AgentAuthoringApprovalCheck(
        run_id="run-001",
        episode_id="episode-run-001",
        call_id="call-save-001",
        tool_name="author_save_strategy_draft",
        arguments={"strategy_id": "strategy-001"},
    )

    with pytest.raises(TypeError, match="approved"):
        VerifiedAgentAuthoringApproval.issue(
            check=check,
            approval_id="approval-001",
            action_hash=HASH_A,
            operator_id="operator-001",
            approved_at=APPROVED_AT,
            approved=cast("bool", 1),
        )


@pytest.mark.parametrize(
    ("verifier", "code"),
    [
        (_Verifier(approved=False), "AGENT_AUTHORING_APPROVAL_REQUIRED"),
        (_Verifier(tamper_hash=True), "AGENT_AUTHORING_APPROVAL_INVALID"),
    ],
)
def test_unapproved_or_hash_mismatched_write_fails_before_mutation(
    verifier: _Verifier,
    code: str,
) -> None:
    facade, _, create, _, _ = _facade(verifier=verifier)

    with pytest.raises(AppCommandError) as exc_info:
        facade.save_strategy_draft(_save_command())

    assert exc_info.value.details["code"] == code
    assert create.calls == []


def test_save_draft_mints_exact_mutation_receipt_and_audit_provenance() -> None:
    facade, verifier, create, update, _ = _facade()

    receipt = facade.save_strategy_draft(_save_command())

    assert receipt.verify_integrity()
    assert receipt.operation_id == "strategies_create_strategy"
    assert receipt.result_identity == "strategy-001@1"
    assert receipt.run_id == "run-001"
    assert receipt.episode_id == "episode-run-001"
    assert receipt.approval_id == "approval-001"
    assert receipt.action_hash == HASH_A
    assert receipt.operator_id == "operator-001"
    assert receipt.audit_identity == "agent-approval:approval-001"
    assert receipt.audit_event_id
    assert receipt.request_hash
    assert receipt.key_hash
    assert len(verifier.calls) == 1
    assert update.calls == []

    delegated = create.calls[0]
    assert delegated.idempotency is not None
    assert delegated.idempotency.operation_id == "strategies_create_strategy"
    assert mutation_event_id(delegated.idempotency) == receipt.audit_event_id
    assert delegated.actor == "agent:operator-001"
    reason = orjson.loads(delegated.reason)
    assert reason["approval_id"] == "approval-001"
    assert reason["run_id"] == "run-001"
    assert reason["episode_id"] == "episode-run-001"
    assert reason["audit_identity"] == "agent-approval:approval-001"


def test_submit_review_uses_existing_governance_command_without_publish_authority() -> (
    None
):
    facade, _, create, update, submit = _facade()

    receipt = facade.submit_strategy_review(_submit_command())

    assert receipt.verify_integrity()
    assert receipt.operation_id == "strategies_submit_strategy_review"
    assert receipt.result == {
        "strategy_id": "strategy-001",
        "version": 1,
        "state": "review",
        "review_outcome": "pending",
    }
    assert create.calls == []
    assert update.calls == []
    delegated = submit.calls[0]
    assert delegated.idempotency is not None
    assert delegated.idempotency.operation_id == "strategies_submit_strategy_review"
    assert delegated.actor == "agent:operator-001"
    assert "approval-001" in delegated.reason


class _IdempotentCreateHandler(_CreateHandler):
    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()
        self._events: set[str] = set()
        self.side_effects = 0

    def handle(self, command: object) -> StrategySpecInfo:
        assert command.idempotency is not None
        event_id = mutation_event_id(command.idempotency)
        with self._lock:
            self.calls.append(command)
            if event_id not in self._events:
                self._events.add(event_id)
                self.side_effects += 1
        return StrategySpecInfo(
            strategy_id="strategy-001",
            name="Momentum",
            spec_json={"strategy_family_id": "strategy-001"},
            version=1,
            status="draft",
            created_at="2026-08-12T07:06:00Z",
            tags=("agent",),
        )


def test_duplicate_and_concurrent_submit_replay_one_mutation_identity() -> None:
    create = _IdempotentCreateHandler()
    facade, _, _, _, _ = _facade(create=create)

    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = tuple(
            pool.map(
                lambda _: facade.save_strategy_draft(_save_command()),
                range(16),
            )
        )

    assert create.side_effects == 1
    assert len({item.receipt_hash for item in receipts}) == 1
    assert len({item.audit_event_id for item in receipts}) == 1
    assert all(item.verify_integrity() for item in receipts)


def test_real_governance_store_concurrent_replay_has_one_effect_and_durable_receipt(
    tmp_path: Path,
) -> None:
    pool = SQLitePool(str(tmp_path / "strategy.sqlite"))
    spec_writer = SQLiteStrategySpecWriter(pool)
    spec_writer.init_schema()
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()
    governance = GovernanceService(store)
    catalog = StrategyCatalogService(
        reader=SQLiteStrategySpecReader(pool),
        writer=spec_writer,
    )
    facade = AgentAuthoringCommandFacade(
        approval_verifier=_Verifier(),
        create_handler=CreateStrategyHandler(governance),
        update_handler=UpdateStrategyHandler(catalog, governance),
        submit_review_handler=_SubmitHandler(),
    )
    strategy_id, seed = next(iter(SEED_STRATEGY_SPECS.items()))
    command = replace(
        _save_command(),
        strategy_id=strategy_id,
        name=seed.name,
        spec_json=orjson.loads(orjson.dumps(asdict(seed))),
        tags=seed.tags,
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = tuple(
            executor.map(lambda _: facade.save_strategy_draft(command), range(16))
        )

    assert len(store.list_versions(strategy_id)) == 1
    assert len({item.receipt_hash for item in receipts}) == 1
    receipt = receipts[0]
    event = store.get_decision_event(receipt.audit_event_id)
    assert event is not None
    assert event.actor == "agent:operator-001"
    wrapper = orjson.loads(event.reason)
    provenance = orjson.loads(wrapper["human_reason"])
    assert provenance["approval_id"] == "approval-001"
    assert provenance["run_id"] == "run-001"
    assert provenance["episode_id"] == "episode-run-001"
    assert provenance["audit_identity"] == "agent-approval:approval-001"
    identity = MutationIdempotency(
        operation_id=receipt.operation_id,
        resource_id=receipt.resource_id,
        key_hash=receipt.key_hash,
        request_hash=receipt.request_hash,
    )
    durable = find_mutation_receipt_in_reasons((event.reason,), identity)
    assert durable is not None
    assert durable["strategy_id"] == strategy_id
    assert durable["version"] == 1
    pool.close_all()
