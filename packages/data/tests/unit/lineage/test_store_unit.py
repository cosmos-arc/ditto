"""Unit tests for in-memory data lineage store."""

from __future__ import annotations

from datetime import UTC, datetime

from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.lineage.contracts import (
    DataLineageReader,
    DataLineageRecorder,
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)
from ditto_data.lineage.store import InMemoryDataLineage


def _event(
    run_id: str,
    *,
    input_asset: DataAssetRef,
    output_asset: DataAssetRef,
    timestamp: datetime,
) -> LineageEvent:
    return LineageEvent(
        run_id=run_id,
        operation="materialize",
        inputs=(LineageInputRef(asset=input_asset),),
        outputs=(LineageOutputRef(asset=output_asset),),
        timestamp=timestamp,
    )


class TestInMemoryDataLineageRecordAndList:
    def test_records_and_lists_events_for_input_or_output_asset(self) -> None:
        raw = DataAssetRef(dataset_id="raw_bars", namespace="market")
        clean = DataAssetRef(dataset_id="clean_bars", namespace="market")
        features = DataAssetRef(dataset_id="alpha_inputs", namespace="features")
        lineage = InMemoryDataLineage()
        event_1 = _event(
            "run-1",
            input_asset=raw,
            output_asset=clean,
            timestamp=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        )
        event_2 = _event(
            "run-2",
            input_asset=clean,
            output_asset=features,
            timestamp=datetime(2026, 6, 1, 9, 1, tzinfo=UTC),
        )

        lineage.record_event(event_1)
        lineage.record_event(event_2)

        assert lineage.list_events_for_asset(raw) == (event_1,)
        assert lineage.list_events_for_asset(clean) == (event_1, event_2)
        assert lineage.list_events_for_asset(features) == (event_2,)
        assert (
            lineage.list_events_for_asset(
                DataAssetRef(dataset_id="unrelated", namespace="market"),
            )
            == ()
        )

    def test_preserves_append_order_for_replay_audit(self) -> None:
        raw = DataAssetRef(dataset_id="raw_bars", namespace="market")
        clean = DataAssetRef(dataset_id="clean_bars", namespace="market")
        lineage = InMemoryDataLineage()
        event_1 = _event(
            "run-1",
            input_asset=raw,
            output_asset=clean,
            timestamp=datetime(2026, 6, 1, 9, 1, tzinfo=UTC),
        )
        event_2 = _event(
            "run-2",
            input_asset=raw,
            output_asset=clean,
            timestamp=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        )

        lineage.record_event(event_1)
        lineage.record_event(event_2)

        assert lineage.list_events_for_asset(raw) == (event_1, event_2)

    def test_lists_events_for_run_in_append_order(self) -> None:
        raw = DataAssetRef(dataset_id="raw_bars", namespace="market")
        clean = DataAssetRef(dataset_id="clean_bars", namespace="market")
        features = DataAssetRef(dataset_id="alpha_inputs", namespace="features")
        lineage = InMemoryDataLineage()
        event_1 = _event(
            "run-1",
            input_asset=raw,
            output_asset=clean,
            timestamp=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        )
        event_2 = _event(
            "run-2",
            input_asset=clean,
            output_asset=features,
            timestamp=datetime(2026, 6, 1, 9, 1, tzinfo=UTC),
        )
        event_3 = _event(
            "run-1",
            input_asset=clean,
            output_asset=features,
            timestamp=datetime(2026, 6, 1, 9, 2, tzinfo=UTC),
        )

        lineage.record_event(event_1)
        lineage.record_event(event_2)
        lineage.record_event(event_3)

        assert lineage.list_events_for_run("run-1") == (event_1, event_3)
        assert lineage.list_events_for_run("missing") == ()


class TestInMemoryDataLineageProtocols:
    def test_satisfies_lineage_reader_and_recorder_protocols(self) -> None:
        lineage = InMemoryDataLineage()

        assert isinstance(lineage, DataLineageReader)
        assert isinstance(lineage, DataLineageRecorder)
