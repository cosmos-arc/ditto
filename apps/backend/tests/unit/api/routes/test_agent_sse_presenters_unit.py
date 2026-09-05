"""Fail-closed SSE presenter invariants at the HTTP boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ditto_agent.runtime.episode import episode_event_hash
from ditto_agent.runtime.service import AgentEventView
from ditto_application.agent_campaign_runtime import (
    CampaignEventView,
    CampaignStatus,
)
from ditto_apps.api.routes.agent_presenters import (
    encode_agent_sse,
    encode_campaign_sse,
)

_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _run_event(
    *,
    event_id: int,
    run_sequence: int,
    prev_hash: str | None,
    occurred_at: datetime | None = None,
) -> AgentEventView:
    event_type = "run_started" if run_sequence == 1 else "provider_attempt"
    event_time = occurred_at or _NOW + timedelta(seconds=run_sequence)
    event_hash = episode_event_hash(
        event_id=event_id,
        run_id="run-1",
        run_sequence=run_sequence,
        event_type=event_type,
        payload_hash=_HASH_A,
        occurred_at=event_time,
        prev_hash=prev_hash,
    )
    return AgentEventView(
        event_id=event_id,
        run_id="run-1",
        run_sequence=run_sequence,
        event_type=event_type,
        payload_hash=_HASH_A,
        occurred_at=event_time,
        prev_hash=prev_hash,
        event_hash=event_hash,
    )


def _campaign_event(
    *,
    event_id: int,
    previous_status: CampaignStatus | None,
    status: CampaignStatus,
    event_type: str | None = None,
    occurred_at: datetime | None = None,
) -> CampaignEventView:
    return CampaignEventView(
        event_id=event_id,
        durable_event_id=f"campaign-event-{event_id}",
        campaign_id="campaign-1",
        event_type=(
            event_type
            if event_type is not None
            else "campaign_created"
            if event_id == 1
            else "campaign_authorized"
        ),
        previous_status=previous_status,
        status=status,
        payload_hash=_HASH_A,
        occurred_at=occurred_at or _NOW + timedelta(seconds=event_id),
    )


def test_run_sse_rejects_a_non_contiguous_hash_chain() -> None:
    first = _run_event(
        event_id=7,
        run_sequence=1,
        prev_hash=None,
    )
    skipped = _run_event(
        event_id=11,
        run_sequence=3,
        prev_hash=_HASH_C,
    )

    with pytest.raises(ValueError, match=r"run_sequence|prev_hash"):
        encode_agent_sse((first, skipped))


def test_campaign_sse_rejects_a_broken_status_predecessor() -> None:
    created = _campaign_event(
        event_id=1,
        previous_status=None,
        status=CampaignStatus.DRAFT,
    )
    authorized = _campaign_event(
        event_id=2,
        previous_status=CampaignStatus.RUNNING,
        status=CampaignStatus.AUTHORIZED,
    )

    with pytest.raises(ValueError, match="previous_status"):
        encode_campaign_sse((created, authorized))


def test_run_sse_accepts_a_hash_valid_persisted_clock_regression() -> None:
    first = _run_event(
        event_id=7,
        run_sequence=1,
        prev_hash=None,
        occurred_at=_NOW + timedelta(seconds=2),
    )
    second = _run_event(
        event_id=8,
        run_sequence=2,
        prev_hash=first.event_hash,
        occurred_at=_NOW + timedelta(seconds=1),
    )

    payload = encode_agent_sse((first, second))

    assert payload.count(b"data: ") == 2


def test_campaign_sse_accepts_a_persisted_clock_regression() -> None:
    created = _campaign_event(
        event_id=1,
        previous_status=None,
        status=CampaignStatus.DRAFT,
        occurred_at=_NOW + timedelta(seconds=2),
    )
    authorized = _campaign_event(
        event_id=2,
        previous_status=CampaignStatus.DRAFT,
        status=CampaignStatus.AUTHORIZED,
        occurred_at=_NOW + timedelta(seconds=1),
    )

    payload = encode_campaign_sse((created, authorized))

    assert payload.count(b"data: ") == 2


def test_campaign_sse_accepts_a_post_terminal_race_receipt() -> None:
    created = _campaign_event(
        event_id=1,
        previous_status=None,
        status=CampaignStatus.DRAFT,
    )
    completed = _campaign_event(
        event_id=2,
        previous_status=CampaignStatus.DRAFT,
        status=CampaignStatus.COMPLETED,
        event_type="campaign_completed",
    )
    late_receipt = _campaign_event(
        event_id=3,
        previous_status=CampaignStatus.COMPLETED,
        status=CampaignStatus.COMPLETED,
        event_type="candidate_dispatched",
    )

    payload = encode_campaign_sse((created, completed, late_receipt))

    assert b"event: campaign_completed\n" in payload
    assert b"event: candidate_dispatched\n" in payload


def test_sse_rejects_unknown_schema_versions_before_serialization() -> None:
    event = AgentEventView(
        event_id=1,
        run_id="run-1",
        run_sequence=1,
        event_type="run_queued",
        payload_hash=_HASH_A,
        occurred_at=_NOW,
        prev_hash=None,
        event_hash=_HASH_B,
        schema_version=2,
    )

    with pytest.raises(ValueError, match="schema_version"):
        encode_agent_sse((event,))
