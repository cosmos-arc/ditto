from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from ditto_agent.contracts.approval import (
    ActionBudget,
    ApprovalAction,
    ApprovalRequest,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.runtime.codec import canonical_bytes, canonical_sha256


def _context(
    *,
    knowledge_cutoff: datetime | None = None,
    source_snapshot_id: str = "snapshot-20260812",
) -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 12, 7, 0, tzinfo=UTC),
            knowledge_cutoff=knowledge_cutoff
            or datetime(2026, 8, 12, 6, 55, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 12, 6, 50, tzinfo=UTC),
            source_snapshot_id=source_snapshot_id,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH", "510500.SH"),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _approval(
    *,
    parameters: Mapping[str, object] | None = None,
    subject_identity: str = "strategy-draft-001",
    required_authority: str = "strategy_author",
    authority_hash: str = "a" * 64,
    temporal_context: TemporalToolContext | None = None,
    budget: ActionBudget | None = None,
    expires_at: datetime | None = None,
) -> ApprovalRequest:
    return ApprovalRequest.issue(
        request_id="approval-001",
        run_id="run-001",
        action=ApprovalAction(
            action_kind="formal_author_write",
            tool_name="strategy_draft_save",
            parameters=parameters or {"name": "café", "window": 20},
            subject_identity=subject_identity,
            required_authority=required_authority,
            authority_hash=authority_hash,
            temporal_context=temporal_context or _context(),
            budget=budget
            or ActionBudget(
                max_tool_calls=1,
                max_output_bytes=65_536,
                max_model_tokens=4_096,
                max_model_spend_usd=Decimal("0.25"),
            ),
            expires_at=expires_at or datetime(2026, 8, 12, 8, 0, tzinfo=UTC),
        ),
    )


def test_canonical_bytes_are_stable_across_order_unicode_time_and_numbers() -> None:
    local = timezone(timedelta(hours=8))
    first = {
        "z": -0.0,
        "nested": {"b": 1.0, "a": "cafe\N{COMBINING ACUTE ACCENT}"},
        "at": datetime(2026, 8, 12, 15, 0, tzinfo=local),
    }
    second = {
        "at": datetime(2026, 8, 12, 7, 0, tzinfo=UTC),
        "nested": {"a": "café", "b": 1},
        "z": 0,
    }

    expected = (
        b'{"at":"2026-08-12T07:00:00.000000Z","nested":{"a":"caf\xc3\xa9","b":1},"z":0}'
    )
    assert canonical_bytes(first) == expected
    assert canonical_bytes(second) == expected
    assert canonical_sha256(first) == canonical_sha256(second)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "bad"}, {"x"}])
def test_canonical_codec_rejects_ambiguous_or_unsupported_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_bytes(value)


def test_canonical_codec_rejects_unicode_key_collisions() -> None:
    with pytest.raises(ValueError, match="collide"):
        canonical_bytes({"café": 1, "cafe\N{COMBINING ACUTE ACCENT}": 2})


def test_action_hash_covers_authority_pit_snapshot_budget_expiry_and_subject() -> None:
    baseline = _approval()
    changed = (
        _approval(parameters={"window": 21, "name": "café"}),
        _approval(subject_identity="strategy-draft-002"),
        _approval(required_authority="strategy_reviewer"),
        _approval(authority_hash="b" * 64),
        _approval(
            temporal_context=_context(
                knowledge_cutoff=datetime(2026, 8, 12, 6, 54, tzinfo=UTC)
            )
        ),
        _approval(temporal_context=_context(source_snapshot_id="snapshot-20260811")),
        _approval(
            budget=ActionBudget(
                max_tool_calls=2,
                max_output_bytes=65_536,
                max_model_tokens=4_096,
                max_model_spend_usd=Decimal("0.25"),
            )
        ),
        _approval(expires_at=datetime(2026, 8, 12, 8, 1, tzinfo=UTC)),
    )

    assert baseline.verify_action_hash()
    assert all(item.action_hash != baseline.action_hash for item in changed)
    assert not replace(baseline, action_hash="0" * 64).verify_action_hash()


def test_approval_restore_rejects_tampered_hash() -> None:
    approval = _approval()

    with pytest.raises(ValueError, match="action_hash"):
        ApprovalRequest.restore(
            request_id=approval.request_id,
            run_id=approval.run_id,
            action=approval.action,
            action_hash="0" * 64,
        )
