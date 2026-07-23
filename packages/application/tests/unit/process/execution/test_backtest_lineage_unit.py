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
from ditto_backtest.manifest import InputRef, RunManifest, RunMode
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.parameters import canonical_parameter_hash


def _manifest(*, created_at: str = "2026-07-23T00:00:00Z") -> RunManifest:
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
