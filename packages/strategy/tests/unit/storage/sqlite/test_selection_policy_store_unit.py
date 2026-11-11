"""SQLite persistence tests for content-addressed SelectionSpec policy snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_platform.foundation import SQLitePool
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    SelectionConditionOperator,
    SelectionFactorCondition,
    SelectionFactorWeight,
    StockSelectionSpec,
    canonical_spec_hash,
)
from ditto_strategy.storage.sqlite.selection_policy_store import (
    SQLiteSelectionPolicyStore,
)


def _stock_spec() -> StockSelectionSpec:
    return StockSelectionSpec(
        spec_id="stock-core",
        spec_version="1",
        top_k=5,
        min_average_turnover=20_000_000.0,
        min_listing_days=120,
        factor_weights=(
            SelectionFactorWeight("momentum_1m", 0.6),
            SelectionFactorWeight("value_pe", 0.4),
        ),
        filter_groups=(
            (
                SelectionFactorCondition(
                    "momentum_1m", SelectionConditionOperator.GTE, 0.5
                ),
            ),
        ),
    )


def _etf_spec() -> EtfSelectionSpec:
    return EtfSelectionSpec(
        spec_id="etf-core",
        spec_version="2",
        top_k=3,
        min_average_turnover=10_000_000.0,
        min_listing_days=60,
        factor_weights=(SelectionFactorWeight("momentum_1m", 1.0),),
        max_tracking_error=0.02,
    )


def _store(path: Path) -> tuple[SQLiteSelectionPolicyStore, SQLitePool]:
    pool = SQLitePool(str(path))
    store = SQLiteSelectionPolicyStore(pool)
    store.init_schema()
    return store, pool


def test_policy_store_round_trips_stock_policy_with_conditions(
    tmp_path: Path,
) -> None:
    store, pool = _store(tmp_path / "strategy.db")
    spec = _stock_spec()
    spec_hash = canonical_spec_hash(spec)

    store.save_policy(spec)
    loaded = store.policy_by_hash(spec_hash)

    assert loaded == spec
    assert loaded is not None
    assert canonical_spec_hash(loaded) == spec_hash
    pool.close_all()


def test_policy_store_round_trips_etf_policy_with_tracking_error(
    tmp_path: Path,
) -> None:
    store, pool = _store(tmp_path / "strategy.db")
    spec = _etf_spec()
    spec_hash = canonical_spec_hash(spec)

    store.save_policy(spec)

    assert store.policy_by_hash(spec_hash) == spec
    pool.close_all()


def test_policy_store_exact_replay_is_idempotent_and_missing_returns_none(
    tmp_path: Path,
) -> None:
    store, pool = _store(tmp_path / "strategy.db")
    spec = _stock_spec()

    store.save_policy(spec)
    store.save_policy(spec)

    row_count = (
        pool.get_connection()
        .execute("SELECT COUNT(*) FROM selection_policy_snapshot")
        .fetchone()[0]
    )
    assert row_count == 1
    assert store.policy_by_hash("f" * 64) is None
    pool.close_all()


def test_policy_store_survives_reopen_and_rejects_tampered_payload(
    tmp_path: Path,
) -> None:
    database = tmp_path / "strategy.db"
    store, pool = _store(database)
    spec = _stock_spec()
    spec_hash = canonical_spec_hash(spec)
    store.save_policy(spec)
    pool.close_all()

    reopened, reopened_pool = _store(database)
    assert reopened.policy_by_hash(spec_hash) == spec

    connection = reopened_pool.get_connection()
    stored = str(
        connection.execute(
            "SELECT payload_json FROM selection_policy_snapshot WHERE spec_hash = ?",
            (spec_hash,),
        ).fetchone()[0]
    )
    # 保持载荷 schema 合法、只改一个值：内容哈希与键分离，读取必须拒收。
    tampered = stored.replace('"top_k":5', '"top_k":9')
    assert tampered != stored
    connection.execute(
        "UPDATE selection_policy_snapshot SET payload_json = ? WHERE spec_hash = ?",
        (tampered, spec_hash),
    )
    reopened_pool.commit()
    with pytest.raises(StrategySpecError, match="identity"):
        reopened.policy_by_hash(spec_hash)
    reopened_pool.close_all()
