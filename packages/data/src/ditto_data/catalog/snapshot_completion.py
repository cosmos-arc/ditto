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
    """
    An interval alone cannot attest another revision's payload.

    Committed payload evidence carries the exact snapshot identity; an intent
    only proves byte-level intent and stays deliberately conservative.
    """
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
            or (
                checkpoint.payload_id.startswith(f"payload:{snapshot.checksum}:")
                and checkpoint.payload_id.endswith(f":{snapshot.snapshot_id}")
            )
        )
    )


def snapshot_completed(
    snapshot: ProviderSnapshot, lifecycle: PartitionLifecycleReader
) -> bool:
    """The COMPLETE row itself pins the exact snapshot identity it attests."""
    return any(
        checkpoint_matches_snapshot(checkpoint, snapshot)
        and checkpoint.complete_evidence_id == snapshot.snapshot_id
        for checkpoint in lifecycle.list_complete(dataset_id=snapshot.dataset_id)
    )


def canonical_write_identity(snapshot: ProviderSnapshot) -> tuple[str, int] | None:
    """Canonical output attested by the same completed ingestion as the payload."""
    metadata = dict(snapshot.response_metadata)
    checksum = metadata.get("canonical_checksum")
    rows = metadata.get("canonical_row_count", "")
    if not checksum or not rows.isdecimal():
        return None
    return checksum, int(rows)
