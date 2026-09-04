"""Backtest lineage must preserve exact replay input provenance."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_application.processes.execution.backtest_lineage import (
    record_backtest_lineage,
)
from ditto_application.processes.execution.backtest_process_types import (
    BacktestLineageConfig,
)
from ditto_backtest.context_inputs import ContextInputKind, ReplayContextInputRef
from ditto_backtest.manifest import InputRef, RunManifest, RunMode
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.parameters import canonical_parameter_hash


def _manifest(
    *,
    created_at: str = "2026-07-23T00:00:00Z",
    context_input_refs: tuple[ReplayContextInputRef, ...] = (),
) -> RunManifest:
    return RunManifest(
        run_id="run-1",
        strategy_id="strategy-1",
        strategy_version="1",
        mode=RunMode.BACKTEST,
        created_at=created_at,
        spec_hash="a" * 64,
        base_spec_hash="b" * 64,
        parameter_hash=canonical_parameter_hash(()),
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
        input_ref_details=(
            InputRef(
                instrument_id=InstrumentId(510300),
                data_hash="sha256:" + "c" * 64,
                date_range=("2026-01-01", "2026-03-31"),
                source="tushare",
                source_snapshot_id="source-snapshot-1",
            ),
        ),
        context_input_refs=context_input_refs,
    )


def _config() -> BacktestLineageConfig:
    return BacktestLineageConfig(
        strategy_id="strategy-1",
        strategy_version="1",
        start_date="2026-01-01",
        end_date="2026-03-31",
    )


def test_lineage_market_asset_preserves_source_snapshot_identity() -> None:
    recorder = MagicMock()

    record_backtest_lineage(
        recorder=recorder,
        run_id="run-1",
        config=_config(),
        manifest=_manifest(),
    )

    event = recorder.record_event.call_args.args[0]
    market_asset = event.inputs[1].asset
    assert "source_snapshot_id=source-snapshot-1" in market_asset.partition_keys


def test_lineage_preserves_exact_product_context_identity() -> None:
    recorder = MagicMock()
    context_ref = ReplayContextInputRef(
        context_kind=ContextInputKind.MARKET_CONTEXT,
        context_id="market-context-2026-03-31",
        content_hash="d" * 64,
        as_of="2026-03-31T07:00:00Z",
        knowledge_cutoff="2026-03-31T06:30:00Z",
        publication_cutoff="2026-03-31T06:00:00Z",
        source_snapshot_ids=("macro-snapshot-1", "breadth-snapshot-1"),
    )

    record_backtest_lineage(
        recorder=recorder,
        run_id="run-1",
        config=_config(),
        manifest=_manifest(context_input_refs=(context_ref,)),
    )

    event = recorder.record_event.call_args.args[0]
    context_input = event.inputs[2]
    assert context_input.role == "market_context"
    assert context_input.asset.dataset_id == "market-context-2026-03-31"
    assert context_input.asset.namespace == "backtest_context_input"
    assert context_input.asset.partition_keys == (
        "content_hash=" + "d" * 64,
        "as_of=2026-03-31T07:00:00Z",
        "knowledge_cutoff=2026-03-31T06:30:00Z",
        "publication_cutoff=2026-03-31T06:00:00Z",
        "source_snapshot_id=breadth-snapshot-1",
        "source_snapshot_id=macro-snapshot-1",
    )


@pytest.mark.parametrize("created_at", ["", "not-a-timestamp"])
def test_invalid_manifest_timestamp_does_not_mint_current_time_lineage(
    created_at: str,
) -> None:
    recorder = MagicMock()

    record_backtest_lineage(
        recorder=recorder,
        run_id="run-1",
        config=_config(),
        manifest=_manifest(created_at=created_at),
    )

    recorder.record_event.assert_not_called()
