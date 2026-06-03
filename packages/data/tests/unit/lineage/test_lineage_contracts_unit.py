from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import assert_type

import pytest
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.lineage.contracts import (
    DataLineageReader,
    DataLineageRecorder,
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)


def test_lineage_refs_are_frozen_and_use_product_neutral_roles() -> None:
    asset = DataAssetRef(dataset_id="bars", namespace="market")
    input_ref = LineageInputRef(asset=asset)
    output_ref = LineageOutputRef(asset=asset)

    assert input_ref.role == "input"
    assert output_ref.role == "output"
    with pytest.raises(FrozenInstanceError):
        input_ref.role = "feature-source"  # type: ignore[misc]


def test_lineage_event_is_frozen_and_uses_tuple_relationships() -> None:
    input_asset = DataAssetRef(dataset_id="raw_bars", namespace="market")
    output_asset = DataAssetRef(dataset_id="clean_bars", namespace="market")
    event = LineageEvent(
        run_id="run-1",
        operation="normalize",
        inputs=(LineageInputRef(asset=input_asset),),
        outputs=(LineageOutputRef(asset=output_asset),),
        timestamp=datetime(2026, 5, 6, tzinfo=UTC),
    )

    assert event.inputs == (LineageInputRef(asset=input_asset),)
    assert event.outputs == (LineageOutputRef(asset=output_asset),)
    with pytest.raises(FrozenInstanceError):
        event.operation = "rewrite"  # type: ignore[misc]


def test_lineage_protocols_accept_structural_in_memory_fake() -> None:
    class InMemoryLineage:
        def __init__(self) -> None:
            self._events: list[LineageEvent] = []

        def record_event(self, event: LineageEvent) -> None:
            self._events.append(event)

        def list_events_for_asset(
            self,
            asset: DataAssetRef,
        ) -> tuple[LineageEvent, ...]:
            return tuple(
                event
                for event in self._events
                if any(ref.asset == asset for ref in event.inputs)
                or any(ref.asset == asset for ref in event.outputs)
            )

        def list_events_for_run(self, run_id: str) -> tuple[LineageEvent, ...]:
            return tuple(event for event in self._events if event.run_id == run_id)

    raw_asset = DataAssetRef(dataset_id="raw_bars", namespace="market")
    clean_asset = DataAssetRef(dataset_id="clean_bars", namespace="market")
    event = LineageEvent(
        run_id="run-1",
        operation="normalize",
        inputs=(LineageInputRef(asset=raw_asset),),
        outputs=(LineageOutputRef(asset=clean_asset),),
        timestamp=datetime(2026, 5, 6, tzinfo=UTC),
    )
    lineage = InMemoryLineage()

    assert isinstance(lineage, DataLineageRecorder)
    assert isinstance(lineage, DataLineageReader)
    recorder: DataLineageRecorder = lineage
    reader: DataLineageReader = lineage
    assert_type(recorder, DataLineageRecorder)
    assert_type(reader, DataLineageReader)

    recorder.record_event(event)

    assert reader.list_events_for_asset(raw_asset) == (event,)
    assert reader.list_events_for_asset(clean_asset) == (event,)
    assert reader.list_events_for_run("run-1") == (event,)
    assert reader.list_events_for_run("run-2") == ()
    assert (
        reader.list_events_for_asset(
            DataAssetRef(dataset_id="unrelated", namespace="market"),
        )
        == ()
    )


def test_lineage_contracts_have_canonical_modules() -> None:
    expected_module = "ditto_data.lineage.contracts"

    assert LineageInputRef.__module__ == expected_module
    assert LineageOutputRef.__module__ == expected_module
    assert LineageEvent.__module__ == expected_module
    assert DataLineageRecorder.__module__ == expected_module
    assert DataLineageReader.__module__ == expected_module
