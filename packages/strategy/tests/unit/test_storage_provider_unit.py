"""Strategy storage provider unit tests."""

from __future__ import annotations

from pathlib import Path

from ditto_platform.foundation import SQLitePool
from ditto_strategy.di.storage import StrategyStorageProvider


def _make_legacy_strategy_run_table(pool: SQLitePool) -> None:
    conn = pool.get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS strategy_run (
            run_id            TEXT PRIMARY KEY,
            strategy_id       TEXT NOT NULL,
            strategy_version  TEXT NOT NULL DEFAULT '',
            mode              TEXT NOT NULL DEFAULT 'backtest',
            status            TEXT NOT NULL DEFAULT 'pending',
            started_at        TEXT NOT NULL DEFAULT '',
            completed_at      TEXT NOT NULL DEFAULT '',
            error_message     TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO strategy_run (run_id, strategy_id, status)
        VALUES ('legacy-run', 'stock-selection', 'completed');
        """
    )
    pool.commit()


def test_strategy_run_provider_migrates_legacy_run_schema(tmp_path: Path) -> None:
    """Provider-built run services should be safe on existing metadata DBs."""
    pool = SQLitePool(str(tmp_path / "metadata.sqlite"))
    try:
        _make_legacy_strategy_run_table(pool)
        provider = StrategyStorageProvider()

        reader = provider.strategy_run_reader(pool)
        writer = provider.strategy_run_writer(pool)
        service = provider.strategy_run_service(reader, writer)

        runs = service.list_runs()

        assert [run.run_id for run in runs] == ["legacy-run"]
        assert runs[0].parent_run_id == ""
    finally:
        pool.close()
