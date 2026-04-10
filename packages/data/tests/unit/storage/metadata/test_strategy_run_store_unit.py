"""Unit tests for SQLiteStrategyRunReader / SQLiteStrategyRunWriter."""

from __future__ import annotations

from pathlib import Path

from ditto_data.models.strategy_run import StrategyRunRecord
from ditto_data.storage.metadata.strategy_run_store import (
    SQLiteStrategyRunReader,
    SQLiteStrategyRunWriter,
)
from ditto_infra.foundation import SQLitePool
from ditto_kernel.enums import RunStatus


def _make_record(
    run_id: str = "run-001",
    strategy_id: str = "momentum-etf",
    strategy_version: str = "2026.03",
    mode: str = "backtest",
    status: str = RunStatus.PENDING,
    started_at: str = "2026-03-24T10:00:00Z",
    completed_at: str = "",
    error_message: str = "",
) -> StrategyRunRecord:
    return StrategyRunRecord(
        run_id=run_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        mode=mode,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        error_message=error_message,
    )


def _make_pool(tmp_path: Path) -> SQLitePool:
    return SQLitePool(str(tmp_path / "strategy-run.db"))


class TestSQLiteStrategyRunStore:
    """Tests for SQLiteStrategyRunReader / SQLiteStrategyRunWriter."""

    def test_init_schema_is_idempotent(self, tmp_path: Path) -> None:
        """重复初始化 schema 不应报错。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            writer.init_schema()
            writer.init_schema()
        finally:
            pool.close()

    def test_save_and_get_roundtrip(self, tmp_path: Path) -> None:
        """保存后可按 run_id 读回完整记录。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            reader = SQLiteStrategyRunReader(pool)
            writer.init_schema()

            record = _make_record()
            writer.save(record)

            result = reader.get("run-001")
            assert result == record
        finally:
            pool.close()

    def test_list_by_strategy_orders_by_started_at_desc(self, tmp_path: Path) -> None:
        """按策略列出时按 started_at 倒序返回。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            reader = SQLiteStrategyRunReader(pool)
            writer.init_schema()
            writer.save(
                _make_record(run_id="run-001", started_at="2026-03-24T10:00:00Z")
            )
            writer.save(
                _make_record(run_id="run-002", started_at="2026-03-24T12:00:00Z")
            )
            writer.save(
                _make_record(
                    run_id="run-003",
                    strategy_id="other-strategy",
                    started_at="2026-03-24T13:00:00Z",
                )
            )

            result = reader.list_by_strategy("momentum-etf")

            assert [record.run_id for record in result] == ["run-002", "run-001"]
        finally:
            pool.close()

    def test_update_status_completed_sets_completed_at(self, tmp_path: Path) -> None:
        """completed 状态写回 completed_at。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            reader = SQLiteStrategyRunReader(pool)
            writer.init_schema()
            writer.save(_make_record())

            updated = writer.update_status("run-001", RunStatus.COMPLETED)

            assert updated is True
            result = reader.get("run-001")
            assert result is not None
            assert result.status == RunStatus.COMPLETED
            assert result.completed_at != ""
            assert result.error_message == ""
        finally:
            pool.close()

    def test_update_status_failed_persists_error_message(self, tmp_path: Path) -> None:
        """failed 状态保留错误信息并写回 completed_at。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            reader = SQLiteStrategyRunReader(pool)
            writer.init_schema()
            writer.save(_make_record())

            updated = writer.update_status(
                "run-001",
                RunStatus.FAILED,
                "engine crash",
            )

            assert updated is True
            result = reader.get("run-001")
            assert result is not None
            assert result.status == RunStatus.FAILED
            assert result.completed_at != ""
            assert result.error_message == "engine crash"
        finally:
            pool.close()

    def test_update_status_missing_returns_false(self, tmp_path: Path) -> None:
        """不存在的 run_id 更新返回 False。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            writer.init_schema()

            updated = writer.update_status("missing-run", RunStatus.COMPLETED)

            assert updated is False
        finally:
            pool.close()
