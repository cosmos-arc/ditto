"""Unit tests for SQLiteStrategyRunReader / SQLiteStrategyRunWriter."""

from __future__ import annotations

from pathlib import Path

from ditto_data.models.strategy_run import StrategyRunRecord
from ditto_data.storage.metadata.strategy_run_store import (
    SQLiteStrategyRunReader,
    SQLiteStrategyRunWriter,
)
from ditto_kernel.strategy import RunStatus
from ditto_platform.foundation import SQLitePool


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

    def test_progress_fields_roundtrip(self, tmp_path: Path) -> None:
        """进度字段保存后可完整读回。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            reader = SQLiteStrategyRunReader(pool)
            writer.init_schema()

            record = StrategyRunRecord(
                run_id="run-prog",
                strategy_id="momentum-etf",
                progress_pct=0.45,
                current_step="scoring",
                completed_days=45,
                total_days=100,
            )
            writer.save(record)

            result = reader.get("run-prog")
            assert result is not None
            assert result.progress_pct == 0.45
            assert result.current_step == "scoring"
            assert result.completed_days == 45
            assert result.total_days == 100
        finally:
            pool.close()

    def test_progress_fields_default_backward_compatible(self, tmp_path: Path) -> None:
        """无进度字段的旧记录默认值为零/空字符串。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            reader = SQLiteStrategyRunReader(pool)
            writer.init_schema()

            record = _make_record()
            writer.save(record)

            result = reader.get("run-001")
            assert result is not None
            assert result.progress_pct == 0.0
            assert result.current_step == ""
            assert result.completed_days == 0
            assert result.total_days == 0
        finally:
            pool.close()

    def test_update_progress(self, tmp_path: Path) -> None:
        """update_progress 更新进度字段。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            reader = SQLiteStrategyRunReader(pool)
            writer.init_schema()

            writer.save(_make_record())
            updated = writer.update_progress(
                "run-001",
                progress_pct=0.75,
                current_step="execution",
                completed_days=75,
                total_days=100,
            )

            assert updated is True
            result = reader.get("run-001")
            assert result is not None
            assert result.progress_pct == 0.75
            assert result.current_step == "execution"
            assert result.completed_days == 75
            assert result.total_days == 100
        finally:
            pool.close()

    def test_update_progress_missing_returns_false(self, tmp_path: Path) -> None:
        """不存在的 run_id 更新进度返回 False。"""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            writer.init_schema()

            updated = writer.update_progress("missing", progress_pct=0.5)

            assert updated is False
        finally:
            pool.close()


class TestSchemaMigration:
    """Tests for idempotent migration framework in init_schema."""

    def test_init_schema_runs_migrations(self, tmp_path: Path) -> None:
        """init_schema 应执行 migration，使新增列可用."""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            writer.init_schema()

            # 验证 migration 列已存在：直接写入包含新字段的记录不应报错
            conn = pool.get_connection()
            # 检查 _MIGRATIONS 中定义的列是否存在
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(strategy_run)").fetchall()
            }
            # 基础列
            assert "run_id" in columns
            assert "strategy_id" in columns
            # migration 新增列应也存在
            assert "config_json" in columns
        finally:
            pool.close()

    def test_init_schema_idempotent_with_migrations(self, tmp_path: Path) -> None:
        """重复调用 init_schema 不应报错（migration 幂等）."""
        pool = _make_pool(tmp_path)
        try:
            writer = SQLiteStrategyRunWriter(pool)
            writer.init_schema()
            writer.init_schema()

            conn = pool.get_connection()
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(strategy_run)").fetchall()
            }
            assert "config_json" in columns
        finally:
            pool.close()

    def test_old_schema_upgraded_can_read_new_fields(self, tmp_path: Path) -> None:
        """旧 schema 升级后可正常读写新字段（含 parent_run_id 迁移）.

        模拟真实旧库场景：表既不含 parent_run_id 也不含 config_json 等
        migration 列，验证 init_schema() 能正确迁移并创建索引。
        """
        pool = _make_pool(tmp_path)
        try:
            # 模拟最早期旧 schema：基础列，不含
            # parent_run_id / config_json / progress 等
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
                """
            )
            pool.commit()

            # 写入一条旧记录
            conn.execute(
                "INSERT INTO strategy_run (run_id, strategy_id, status) "
                "VALUES ('legacy-run', 'test', 'completed')"
            )
            pool.commit()

            # 运行 init_schema（触发 migration + 索引创建）
            writer = SQLiteStrategyRunWriter(pool)
            reader = SQLiteStrategyRunReader(pool)
            writer.init_schema()

            # 旧记录仍可读取，且 migration 新增列有默认值
            result = reader.get("legacy-run")
            assert result is not None
            assert result.run_id == "legacy-run"
            assert result.strategy_id == "test"
            assert result.progress_pct == 0.0
            assert result.parent_run_id == ""
            assert result.config_json == ""

            # 验证索引已正确创建（包括 parent_run_id 索引）
            indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(strategy_run)").fetchall()
            }
            assert "idx_strategy_run_parent_run_id" in indexes

            # parent_run_id 列存在且可用于查询
            conn.execute(
                "INSERT INTO strategy_run "
                "(run_id, strategy_id, status, parent_run_id) "
                "VALUES ('child-run', 'test', 'pending', 'legacy-run')"
            )
            pool.commit()
            children = reader.list_by_parent("legacy-run")
            assert len(children) == 1
            assert children[0].run_id == "child-run"
        finally:
            pool.close()
