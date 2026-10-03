"""Real ingestion, immutable reads, snapshot readiness and failure recovery."""

from dataclasses import replace
from datetime import UTC, date, datetime

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.processes.ingestion.post_ingest import (
    RequestWindow,
    process_fetched_data,
)
from ditto_application.queries.provider_snapshot import (
    ProviderSnapshotQuery,
    SnapshotReplayRequest,
)
from ditto_application.queries.snapshot_readiness import (
    FieldRequirement,
    SnapshotReadinessQuery,
)
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.ingestion.partition_state import PartitionLifecycleStatus
from packages.application.tests.integration.test_ingestion_evidence_recovery import (
    _bars,
    _pipeline,
)


@pytest.mark.integration
@pytest.mark.pit
def test_delayed_revision_replay_and_failed_completion_recovery(tmp_path, monkeypatch):
    observed = datetime(2026, 7, 17, 10, tzinfo=UTC)
    cutoff = datetime(2026, 7, 18, 9, tzinfo=UTC)
    with _pipeline(
        tmp_path, "stock_daily", display="allowed", snapshot_now=lambda: observed
    ) as runtime:
        ports = runtime.ports
        reader = ProviderSnapshotQuery(
            SnapshotReadService(
                ports.snapshot_reader,
                FilesystemProviderPayloadStore(tmp_path),
                ports.lifecycle_reader,
            ),
            SnapshotReadinessQuery(ports.snapshot_reader, ports.lifecycle_reader),
        )

        def ingest(frame, force=False):
            return process_fetched_data(
                frame,
                "stock_daily",
                "2026-07-16",
                force,
                ctx=runtime.context,
                request_window=RequestWindow(None, "2026-07-17"),
                chunk_id="replay",
            )

        original = _bars()
        assert ingest(original).status == "success"
        first = ports.snapshot_reader.list_snapshots()[0]
        request = SnapshotReplayRequest(
            fields=(FieldRequirement("stock_daily", "close", first.snapshot_id),),
            instrument_ids=(1000001,),
            required_from=date(2026, 7, 16),
            required_to=date(2026, 7, 17),
            knowledge_cutoff=cutoff,
        )
        assert reader.replay(request).frames[first.snapshot_id].equals(original)
        _fail_next_completion(monkeypatch, ports.lifecycle_writer)
        future = original.with_columns(pl.lit(999.0).alias("close"))
        assert ingest(future, True).status == "failed"
        second = next(
            item for item in ports.snapshot_reader.list_snapshots() if item != first
        )
        assert (
            ports.snapshot_reader.get_predecessor(second.snapshot_id)
            == first.snapshot_id
        )
        with pytest.raises(AppQueryError, match="COMPLETE"):
            reader.read_for_audit(second.snapshot_id)
        # The unfinished revision is registered but never consumable, while the
        # retained predecessor still replays its exact recorded bytes.
        revised_request = replace(
            request,
            fields=(FieldRequirement("stock_daily", "close", second.snapshot_id),),
        )
        with pytest.raises(AppQueryError, match="snapshot replay data is incomplete"):
            reader.replay(revised_request)
        assert reader.replay(request).frames[first.snapshot_id].equals(original)
        assert ingest(future, True).status == "success"
        assert reader.read_for_audit(second.snapshot_id).frame.equals(future)
        assert reader.replay(revised_request).frames[second.snapshot_id].equals(future)
        events = ports.lifecycle_reader.list_complete()
        assert ingest(future).status == "success"
        assert ports.lifecycle_reader.list_complete() == events
        assert len(ports.snapshot_reader.list_snapshots()) == 2

        # The readiness scope is fail closed: absent identities and request
        # windows the snapshot never covered are never replayed.
        absent_request = replace(
            request,
            fields=(FieldRequirement("stock_daily", "close", "snapshot:absent"),),
        )
        with pytest.raises(AppQueryError, match="snapshot replay data is incomplete"):
            reader.replay(absent_request)
        uncovered_request = replace(request, required_from=date(2026, 7, 1))
        with pytest.raises(AppQueryError, match="snapshot replay data is incomplete"):
            reader.replay(uncovered_request)


def _fail_next_completion(monkeypatch, writer):
    advance = writer.advance_partition
    fail = True

    def fail_complete(chunk_id, stage, **kwargs):
        nonlocal fail
        if fail and stage is PartitionLifecycleStatus.COMPLETE:
            fail = False
            raise OSError("injected COMPLETE persistence failure")
        return advance(chunk_id, stage, **kwargs)

    monkeypatch.setattr(writer, "advance_partition", fail_complete)


@pytest.mark.integration
@pytest.mark.pit
def test_schema_version_bump_sharing_artifact_still_replays_exact_bytes(tmp_path):
    with _pipeline(tmp_path, "stock_daily", display="allowed") as runtime:
        ports = runtime.ports
        original = _bars()
        assert (
            process_fetched_data(
                original,
                "stock_daily",
                "2026-07-16",
                False,
                ctx=runtime.context,
                request_window=RequestWindow(None, "2026-07-17"),
                chunk_id="aliased",
            ).status
            == "success"
        )
        first = ports.snapshot_reader.list_snapshots()[0]
        reader = ProviderSnapshotQuery(
            SnapshotReadService(
                ports.snapshot_reader,
                FilesystemProviderPayloadStore(tmp_path),
                ports.lifecycle_reader,
            ),
            SnapshotReadinessQuery(ports.snapshot_reader, ports.lifecycle_reader),
        )
        assert reader.read_for_audit(first.snapshot_id).frame.equals(original)

        # An unchanged-physical-schema version bump legitimately shares the
        # checksum-addressed artifact; replay must keep returning the exact
        # bytes rather than treating the shared checksum as ambiguous.
        ports.snapshot_writer.append_snapshot(
            ProviderSnapshot.create(
                ProviderSnapshotDraft(
                    dataset_id=first.dataset_id,
                    source=first.source,
                    request_start=first.request_start,
                    request_end=first.request_end,
                    schema_version="market.stock_daily.v2",
                    checksum=first.checksum,
                    canonical_asset=first.canonical_asset,
                    request_parameters_hash=first.request_parameters_hash,
                    response_metadata=first.response_metadata,
                    license_record_id=first.license_record_id,
                    row_count=first.row_count,
                    payload_uri=first.payload_uri,
                    payload_retained=first.payload_retained,
                    created_at=first.created_at,
                )
            )
        )

        assert reader.read_for_audit(first.snapshot_id).frame.equals(original)
