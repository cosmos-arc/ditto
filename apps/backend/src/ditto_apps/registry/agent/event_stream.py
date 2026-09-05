"""Authenticate stored Agent event chains before presenting stream suffixes."""

from ditto_agent.runtime.episode import episode_event_hash
from ditto_agent.runtime.service import AgentEventView, AgentRuntimeUnavailable
from ditto_agent.storage.sqlite.records import StoredRunEvent


def _event_view(event: StoredRunEvent) -> AgentEventView:
    return AgentEventView(
        event_id=event.event_id,
        run_id=event.run_id,
        run_sequence=event.run_sequence,
        event_type=event.event_type,
        payload_hash=event.payload_hash,
        occurred_at=event.occurred_at,
        prev_hash=event.prev_hash,
        event_hash=event.event_hash,
    )


def validated_event_views(
    events: tuple[StoredRunEvent, ...],
    *,
    run_id: str,
) -> tuple[AgentEventView, ...]:
    """Authenticate the complete target stream before exposing any suffix."""
    views = tuple(_event_view(event) for event in events)
    previous_id = 0
    previous_hash: str | None = None
    for expected_sequence, event in enumerate(views, start=1):
        expected_hash = episode_event_hash(
            event_id=event.event_id,
            run_id=event.run_id,
            run_sequence=event.run_sequence,
            event_type=event.event_type,
            payload_hash=event.payload_hash,
            occurred_at=event.occurred_at,
            prev_hash=event.prev_hash,
        )
        if (
            event.run_id != run_id
            or event.run_sequence != expected_sequence
            or event.event_id <= previous_id
            or event.prev_hash != previous_hash
            or event.event_hash != expected_hash
        ):
            raise AgentRuntimeUnavailable("agent_event_stream_invalid")
        previous_id = event.event_id
        previous_hash = event.event_hash
    return views
