"""SQLite persistence tests for immutable content-addressed SelectionRuns."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLitePool
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.selection.codec import decode_selection_run, encode_selection_run
from ditto_strategy.selection.contracts import (
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    SelectionRun,
    StockSelectionSpec,
)
from ditto_strategy.selection.pipeline import SelectionPipeline
from ditto_strategy.storage.sqlite.selection_run_store import SQLiteSelectionRunStore

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def _run(*, seed: int = 17, as_of: datetime = _AS_OF) -> SelectionRun:
    return SelectionPipeline().run(
        SelectionInputBundle(
            as_of=as_of,
            knowledge_cutoff=as_of,
            publication_cutoff=as_of,
            universe_snapshot_id="universe:sha256:abc",
            industry_rotation_snapshot_id="industry-rotation:sha256:def",
            source_snapshot_ids=("source-a",),
            spec=StockSelectionSpec(
                spec_id="stock-core",
                spec_version="1",
                top_k=1,
                min_average_turnover=20_000_000.0,
                min_listing_days=120,
                factor_weights=(SelectionFactorWeight("momentum", 1.0),),
            ),
            seed=seed,
            instruments=(
                SelectionInstrumentInput(
                    instrument_id=InstrumentId(600000),
                    instrument_name="Pudong Bank",
                    industry_id="801780",
                    factor_values=(SelectionFactorValue("momentum", 0.7),),
                    average_turnover=100_000_000.0,
                    is_st=False,
                    is_suspended=False,
                    listing_days=5000,
                    limit_state=SelectionLimitState.NORMAL,
                    tracking_error=None,
                ),
            ),
        )
    )


def _store(path: Path) -> tuple[SQLiteSelectionRunStore, SQLitePool]:
    pool = SQLitePool(str(path))
    store = SQLiteSelectionRunStore(pool)
    store.init_schema()
    return store, pool


def test_codec_round_trips_exact_run_and_rejects_detached_identity() -> None:
    run = _run()
    encoded = encode_selection_run(run)

    assert run.spec_hash == (
        "d316edad4efbb28470bdc64989d48f4ea73988e4ab2dd7038eb753ccfd921a4c"
    )
    assert run.input_hash == (
        "19f7277101230cc22ed58857e4923ade486f0e71cb9fac5fda196ff07a738daa"
    )
    assert len(encoded) == 777
    assert hashlib.sha256(encoded).hexdigest() == (
        "f597c3dc4a4de15403ea0c8520e8dae5f617190a371b8e6fe988f04b8dff1695"
    )
    assert run.run_id == (
        "selection-run:sha256:"
        "f597c3dc4a4de15403ea0c8520e8dae5f617190a371b8e6fe988f04b8dff1695"
    )
    assert decode_selection_run(encoded, expected_run_id=run.run_id) == run
    with pytest.raises(StrategySpecError, match="identity"):
        decode_selection_run(
            encoded,
            expected_run_id="selection-run:sha256:" + "0" * 64,
        )


def test_store_survives_reopen_and_exact_replay_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "strategy.db"
    store, pool = _store(database)
    run = _run()

    store.save(run)
    store.save(run)
    pool.close_all()
    reopened, reopened_pool = _store(database)

    assert reopened.get(run.run_id) == run
    assert reopened.list_by_spec("stock-core") == [run]
    row_count = (
        reopened_pool.get_connection()
        .execute("SELECT COUNT(*) FROM selection_run")
        .fetchone()[0]
    )
    assert row_count == 1
    reopened_pool.close_all()


def test_list_by_spec_orders_latest_first_and_honors_limit(tmp_path: Path) -> None:
    store, pool = _store(tmp_path / "strategy.db")
    first = _run()
    second = _run(
        seed=18,
        as_of=datetime(2026, 9, 1, 7, 0, tzinfo=UTC),
    )
    store.save(first)
    store.save(second)

    assert store.list_by_spec("stock-core", limit=1) == [second]
    pool.close_all()


def test_store_rejects_tampered_payload_on_exact_read(tmp_path: Path) -> None:
    store, pool = _store(tmp_path / "strategy.db")
    run = _run()
    store.save(run)
    connection = pool.get_connection()
    payload = connection.execute(
        "SELECT payload_json FROM selection_run WHERE run_id = ?",
        (run.run_id,),
    ).fetchone()[0]
    connection.execute(
        "UPDATE selection_run SET payload_json = ? WHERE run_id = ?",
        (payload.replace('"seed":17', '"seed":18'), run.run_id),
    )
    pool.commit()

    with pytest.raises(StrategySpecError, match="identity"):
        store.get(run.run_id)
    pool.close_all()
