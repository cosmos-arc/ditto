"""SQLite persistence tests for immutable industry-rotation snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ditto_platform.foundation import SQLitePool
from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationIndustryInput,
    IndustryRotationInputBundle,
    IndustryRotationSnapshot,
)
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.storage.sqlite.industry_rotation_store import (
    SQLiteIndustryRotationStore,
)


def _snapshot() -> IndustryRotationSnapshot:
    as_of = datetime(2026, 8, 31, 7, tzinfo=UTC)
    return IndustryRotationService().run(
        IndustryRotationInputBundle(
            as_of=as_of,
            knowledge_cutoff=as_of,
            publication_cutoff=as_of,
            source_snapshot_ids=("market-a",),
            market_context_feature_set_id="market-context:sha256:abc",
            membership_version="sw-l1:2026-08-31",
            algorithm_version="industry-rotation-v1",
            industries=(
                IndustryRotationIndustryInput(
                    industry_id="801010",
                    industry_name="Agriculture",
                    relative_strength_5d=0.5,
                    relative_strength_20d=0.5,
                    relative_strength_60d=0.5,
                    advancing_count=6,
                    declining_count=4,
                    member_count=10,
                    trend_score=0.5,
                    fundamental_score=0.5,
                    regime_alignment_score=0.5,
                ),
            ),
        )
    )


def test_store_round_trips_exact_snapshot_and_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    pool = SQLitePool(str(tmp_path / "strategy.db"))
    store = SQLiteIndustryRotationStore(pool)
    store.init_schema()
    snapshot = _snapshot()

    store.save_rotation(snapshot)
    store.save_rotation(snapshot)

    assert store.get_rotation(snapshot.snapshot_id) == snapshot
    assert (
        pool.get_connection()
        .execute("SELECT COUNT(*) FROM industry_rotation_snapshot")
        .fetchone()[0]
        == 1
    )
    pool.close_all()
