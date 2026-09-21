"""Bind durable ingestion evidence to exact provider content."""

from ditto_data.catalog.source_snapshot import ProviderSnapshot
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleReader,
    PartitionLifecycleStatus,
)


def checkpoint_matches_snapshot(
    checkpoint: PartitionCheckpoint, snapshot: ProviderSnapshot
) -> bool:
    """An interval alone cannot attest another revision's payload."""
    return (
        checkpoint.dataset_id == snapshot.dataset_id
        and checkpoint.source == snapshot.source
        and checkpoint.request_start == snapshot.request_start
        and checkpoint.request_end == snapshot.request_end
        and checkpoint.payload_id is not None
        and (
            (
                checkpoint.status is not PartitionLifecycleStatus.COMPLETE
                and checkpoint.payload_id == f"intent:{snapshot.checksum}"
            )
            or checkpoint.payload_id.startswith(f"payload:{snapshot.checksum}:")
        )
    )


def snapshot_completed(
    snapshot: ProviderSnapshot, lifecycle: PartitionLifecycleReader
) -> bool:
    """The terminal event pins schema and request identity as well as payload bytes."""
    return any(
        checkpoint_matches_snapshot(checkpoint, snapshot)
        and any(
            event.to_status is PartitionLifecycleStatus.COMPLETE
            and event.evidence_id == snapshot.snapshot_id
            for event in lifecycle.list_events(checkpoint.chunk_id)
        )
        for checkpoint in lifecycle.list_complete(dataset_id=snapshot.dataset_id)
    )
