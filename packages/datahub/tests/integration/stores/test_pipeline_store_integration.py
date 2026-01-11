"""Tests for PipelineStore."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.pipeline_store import PipelineStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


class TestPipelineStore:
    """Tests for PipelineStore."""

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> SQLitePool:
        """Create temporary database."""
        db_path = tmp_path / "test.db"
        pool = SQLitePool(str(db_path))
        pool.init_schema()
        return pool

    @pytest.fixture
    def pipeline_store(self, temp_db: SQLitePool) -> PipelineStore:
        """Create PipelineStore instance."""
        client = SQLiteClient(temp_db)
        return PipelineStore(client)

    # ============ insert_run tests ============

    def test_insert_run_minimal(self, pipeline_store: PipelineStore) -> None:
        """Test inserting pipeline run with minimal fields."""
        run_id = "test-run-001"

        pipeline_store.insert_run(
            run_id=run_id,
            task_name="update_bars",
            dataset_id="stock_daily",
        )

        result = pipeline_store.get_run(run_id)
        assert result is not None
        assert result["run_id"] == run_id
        assert result["task_name"] == "update_bars"
        assert result["dataset_id"] == "stock_daily"
        assert result["status"] == "running"

    def test_insert_run_full(self, pipeline_store: PipelineStore) -> None:
        """Test inserting pipeline run with all fields."""
        run_id = "test-run-002"
        started = datetime(2024, 1, 15, 10, 0, 0)
        finished = datetime(2024, 1, 15, 10, 5, 30)

        pipeline_store.insert_run(
            run_id=run_id,
            task_name="update_bars",
            dataset_id="stock_daily",
            year=2024,
            rows_read=10000,
            rows_written=9500,
            status="completed",
            error_message=None,
            dq_passed=True,
            dq_fail_count=0,
            dq_warn_count=2,
            started_at=started,
            finished_at=finished,
        )

        result = pipeline_store.get_run(run_id)
        assert result is not None
        assert result["year"] == 2024
        assert result["rows_read"] == 10000
        assert result["rows_written"] == 9500
        assert result["status"] == "completed"
        assert result["dq_passed"] is True
        assert result["dq_fail_count"] == 0
        assert result["dq_warn_count"] == 2
        assert result["duration_sec"] == 330.0

    def test_insert_run_with_error(self, pipeline_store: PipelineStore) -> None:
        """Test inserting failed pipeline run."""
        run_id = "test-run-003"

        pipeline_store.insert_run(
            run_id=run_id,
            task_name="update_bars",
            dataset_id="stock_daily",
            status="failed",
            error_message="Connection timeout",
        )

        result = pipeline_store.get_run(run_id)
        assert result is not None
        assert result["status"] == "failed"
        assert result["error_message"] == "Connection timeout"
        assert result["dq_passed"] is False  # Failed runs default to False

    def test_insert_run_rollback_on_error(
        self, pipeline_store: PipelineStore, mocker
    ) -> None:
        """Test rollback on error during insert."""
        # Insert a valid run first
        pipeline_store.insert_run(
            run_id="test-run-004",
            task_name="update_bars",
            dataset_id="stock_daily",
        )

        # Mock execute to raise exception
        original_execute = pipeline_store._client.execute
        mocker.patch.object(
            pipeline_store._client, "execute", side_effect=Exception("DB error")
        )
        with pytest.raises(Exception, match="DB error"):
            pipeline_store.insert_run(
                run_id="test-run-005",
                task_name="update_bars",
                dataset_id="stock_daily",
            )

        # Restore original execute for verification
        pipeline_store._client.execute = original_execute

        # Original run should still be accessible
        result = pipeline_store.get_run("test-run-004")
        assert result is not None

    # ============ update_run tests ============

    def test_update_run_status(self, pipeline_store: PipelineStore) -> None:
        """Test updating run status."""
        run_id = "test-run-006"
        pipeline_store.insert_run(
            run_id=run_id,
            task_name="update_bars",
            dataset_id="stock_daily",
        )

        pipeline_store.update_run(
            run_id=run_id,
            status="completed",
            rows_written=5000,
        )

        result = pipeline_store.get_run(run_id)
        assert result is not None
        assert result["status"] == "completed"
        assert result["rows_written"] == 5000

    def test_update_run_with_dq_results(self, pipeline_store: PipelineStore) -> None:
        """Test updating run with DQ results."""
        run_id = "test-run-007"
        pipeline_store.insert_run(
            run_id=run_id,
            task_name="update_bars",
            dataset_id="stock_daily",
        )

        pipeline_store.update_run(
            run_id=run_id,
            status="completed",
            dq_passed=False,
            dq_fail_count=5,
            dq_warn_count=10,
        )

        result = pipeline_store.get_run(run_id)
        assert result is not None
        assert result["dq_passed"] is False
        assert result["dq_fail_count"] == 5
        assert result["dq_warn_count"] == 10

    def test_update_run_nonexistent(self, pipeline_store: PipelineStore) -> None:
        """Test updating non-existent run."""
        # Should not raise exception, just no rows affected
        pipeline_store.update_run(
            run_id="nonexistent",
            status="completed",
        )

    # ============ insert_dq_issue tests ============

    def test_insert_dq_issue(self, pipeline_store: PipelineStore) -> None:
        """Test inserting DQ issue."""
        pipeline_store.insert_dq_issue(
            run_id="test-run-008",
            dataset_id="stock_daily",
            year=2024,
            sid=1000001,
            trade_date="2024-01-15",
            rule_name="price_negative",
            severity="error",
            message="Price is negative for sid 1000001",
        )

        issues = pipeline_store.list_dq_issues(run_id="test-run-008")
        assert len(issues) == 1
        assert issues[0]["sid"] == 1000001
        assert issues[0]["rule_name"] == "price_negative"
        assert issues[0]["severity"] == "error"

    def test_insert_multiple_dq_issues(self, pipeline_store: PipelineStore) -> None:
        """Test inserting multiple DQ issues."""
        for i in range(3):
            pipeline_store.insert_dq_issue(
                run_id="test-run-009",
                dataset_id="stock_daily",
                year=2024,
                sid=1000001 + i,
                trade_date="2024-01-15",
                rule_name="price_negative",
                severity="error",
                message=f"Price issue for sid {1000001 + i}",
            )

        issues = pipeline_store.list_dq_issues(run_id="test-run-009")
        assert len(issues) == 3

    def test_insert_dq_issue_minimal(self, pipeline_store: PipelineStore) -> None:
        """Test inserting DQ issue with minimal fields."""
        pipeline_store.insert_dq_issue(
            run_id="test-run-010",
            dataset_id="stock_daily",
            rule_name="missing_data",
            severity="warning",
        )

        issues = pipeline_store.list_dq_issues(run_id="test-run-010")
        assert len(issues) == 1
        assert issues[0]["rule_name"] == "missing_data"
        assert issues[0]["severity"] == "warning"

    # ============ get_run tests ============

    def test_get_run_exists(self, pipeline_store: PipelineStore) -> None:
        """Test getting existing run."""
        run_id = "test-run-011"
        pipeline_store.insert_run(
            run_id=run_id,
            task_name="update_bars",
            dataset_id="stock_daily",
        )

        result = pipeline_store.get_run(run_id)
        assert result is not None
        assert result["run_id"] == run_id

    def test_get_run_not_exists(self, pipeline_store: PipelineStore) -> None:
        """Test getting non-existent run."""
        result = pipeline_store.get_run("nonexistent")
        assert result is None

    # ============ list_runs tests ============

    def test_list_runs_all(self, pipeline_store: PipelineStore) -> None:
        """Test listing all runs."""
        for i in range(5):
            pipeline_store.insert_run(
                run_id=f"test-run-{100 + i}",
                task_name="update_bars",
                dataset_id="stock_daily",
            )

        runs = pipeline_store.list_runs()
        assert len(runs) == 5

    def test_list_runs_by_dataset(self, pipeline_store: PipelineStore) -> None:
        """Test listing runs filtered by dataset."""
        # Insert runs for different datasets
        pipeline_store.insert_run(
            run_id="run-001",
            task_name="update",
            dataset_id="stock_daily",
        )
        pipeline_store.insert_run(
            run_id="run-002",
            task_name="update",
            dataset_id="etf_daily",
        )
        pipeline_store.insert_run(
            run_id="run-003",
            task_name="update",
            dataset_id="stock_daily",
        )

        runs = pipeline_store.list_runs(dataset_id="stock_daily")
        assert len(runs) == 2
        assert all(r["dataset_id"] == "stock_daily" for r in runs)

    def test_list_runs_by_status(self, pipeline_store: PipelineStore) -> None:
        """Test listing runs filtered by status."""
        pipeline_store.insert_run(
            run_id="run-004",
            task_name="update",
            dataset_id="stock_daily",
            status="running",
        )
        pipeline_store.insert_run(
            run_id="run-005",
            task_name="update",
            dataset_id="stock_daily",
            status="completed",
        )

        runs = pipeline_store.list_runs(status="running")
        assert len(runs) == 1
        assert runs[0]["status"] == "running"

    def test_list_runs_with_limit(self, pipeline_store: PipelineStore) -> None:
        """Test listing runs with limit."""
        for i in range(10):
            pipeline_store.insert_run(
                run_id=f"run-{i:03d}",
                task_name="update",
                dataset_id="stock_daily",
            )

        runs = pipeline_store.list_runs(limit=3)
        assert len(runs) == 3

    def test_list_runs_combined_filters(self, pipeline_store: PipelineStore) -> None:
        """Test listing runs with combined filters."""
        pipeline_store.insert_run(
            run_id="run-aa-1",
            task_name="update",
            dataset_id="stock_daily",
            status="completed",
        )
        pipeline_store.insert_run(
            run_id="run-aa-2",
            task_name="update",
            dataset_id="stock_daily",
            status="failed",
        )
        pipeline_store.insert_run(
            run_id="run-bb-1",
            task_name="update",
            dataset_id="etf_daily",
            status="completed",
        )

        runs = pipeline_store.list_runs(
            dataset_id="stock_daily",
            status="completed",
        )
        assert len(runs) == 1
        assert runs[0]["run_id"] == "run-aa-1"

    # ============ list_dq_issues tests ============

    def test_list_dq_issues_by_run(self, pipeline_store: PipelineStore) -> None:
        """Test listing DQ issues by run_id."""
        pipeline_store.insert_dq_issue(
            run_id="run-x",
            dataset_id="stock_daily",
            rule_name="rule1",
            severity="error",
        )
        pipeline_store.insert_dq_issue(
            run_id="run-y",
            dataset_id="stock_daily",
            rule_name="rule2",
            severity="warning",
        )
        pipeline_store.insert_dq_issue(
            run_id="run-x",
            dataset_id="stock_daily",
            rule_name="rule3",
            severity="error",
        )

        issues = pipeline_store.list_dq_issues(run_id="run-x")
        assert len(issues) == 2

    def test_list_dq_issues_by_dataset(self, pipeline_store: PipelineStore) -> None:
        """Test listing DQ issues by dataset_id."""
        pipeline_store.insert_dq_issue(
            run_id="run-001",
            dataset_id="stock_daily",
            rule_name="rule1",
            severity="error",
        )
        pipeline_store.insert_dq_issue(
            run_id="run-002",
            dataset_id="etf_daily",
            rule_name="rule2",
            severity="warning",
        )

        issues = pipeline_store.list_dq_issues(dataset_id="stock_daily")
        assert len(issues) == 1
        assert issues[0]["dataset_id"] == "stock_daily"

    def test_list_dq_issues_by_severity(self, pipeline_store: PipelineStore) -> None:
        """Test listing DQ issues by severity."""
        for i in range(3):
            pipeline_store.insert_dq_issue(
                run_id=f"run-{i}",
                dataset_id="stock_daily",
                rule_name="rule1",
                severity="error",
            )
        for i in range(2):
            pipeline_store.insert_dq_issue(
                run_id=f"run-{i + 3}",
                dataset_id="stock_daily",
                rule_name="rule2",
                severity="warning",
            )

        issues = pipeline_store.list_dq_issues(severity="error")
        assert len(issues) == 3
        assert all(i["severity"] == "error" for i in issues)

    def test_list_dq_issues_with_limit(self, pipeline_store: PipelineStore) -> None:
        """Test listing DQ issues with limit."""
        for i in range(10):
            pipeline_store.insert_dq_issue(
                run_id=f"run-{i}",
                dataset_id="stock_daily",
                rule_name="rule1",
                severity="error",
            )

        issues = pipeline_store.list_dq_issues(limit=5)
        assert len(issues) == 5

    # ============ count_runs tests ============

    def test_count_runs_all(self, pipeline_store: PipelineStore) -> None:
        """Test counting all runs."""
        for i in range(5):
            pipeline_store.insert_run(
                run_id=f"run-count-{i}",
                task_name="update",
                dataset_id="stock_daily",
            )

        count = pipeline_store.count_runs()
        assert count == 5

    def test_count_runs_by_dataset(self, pipeline_store: PipelineStore) -> None:
        """Test counting runs by dataset."""
        pipeline_store.insert_run(
            run_id="run-001",
            task_name="update",
            dataset_id="stock_daily",
        )
        pipeline_store.insert_run(
            run_id="run-002",
            task_name="update",
            dataset_id="etf_daily",
        )
        pipeline_store.insert_run(
            run_id="run-003",
            task_name="update",
            dataset_id="stock_daily",
        )

        count = pipeline_store.count_runs(dataset_id="stock_daily")
        assert count == 2

    def test_count_runs_by_status(self, pipeline_store: PipelineStore) -> None:
        """Test counting runs by status."""
        pipeline_store.insert_run(
            run_id="run-001",
            task_name="update",
            dataset_id="stock_daily",
            status="completed",
        )
        pipeline_store.insert_run(
            run_id="run-002",
            task_name="update",
            dataset_id="stock_daily",
            status="failed",
        )
        pipeline_store.insert_run(
            run_id="run-003",
            task_name="update",
            dataset_id="stock_daily",
            status="completed",
        )

        count = pipeline_store.count_runs(status="completed")
        assert count == 2

    # ============ get_latest_run tests ============

    def test_get_latest_run(self, pipeline_store: PipelineStore) -> None:
        """Test getting latest run for dataset."""
        # Insert in specific order - last inserted is the latest
        pipeline_store.insert_run(
            run_id="run-2024-01-01",
            task_name="update",
            dataset_id="stock_daily",
            year=2024,
        )
        pipeline_store.insert_run(
            run_id="run-2024-01-02",
            task_name="update",
            dataset_id="stock_daily",
            year=2024,
        )
        pipeline_store.insert_run(
            run_id="run-2024-01-03",
            task_name="update",
            dataset_id="stock_daily",
            year=2024,
        )

        latest = pipeline_store.get_latest_run("stock_daily")
        assert latest is not None
        # Should get the one inserted last (by rowid)
        assert latest["run_id"] == "run-2024-01-03"

    def test_get_latest_run_by_year(self, pipeline_store: PipelineStore) -> None:
        """Test getting latest run for dataset and year."""
        pipeline_store.insert_run(
            run_id="run-2023-01",
            task_name="update",
            dataset_id="stock_daily",
            year=2023,
        )
        pipeline_store.insert_run(
            run_id="run-2024-01",
            task_name="update",
            dataset_id="stock_daily",
            year=2024,
        )
        pipeline_store.insert_run(
            run_id="run-2024-02",
            task_name="update",
            dataset_id="stock_daily",
            year=2024,
        )

        latest = pipeline_store.get_latest_run("stock_daily", year=2024)
        assert latest is not None
        assert latest["year"] == 2024
        assert latest["run_id"] == "run-2024-02"

    def test_get_latest_run_no_runs(self, pipeline_store: PipelineStore) -> None:
        """Test getting latest run when no runs exist."""
        latest = pipeline_store.get_latest_run("stock_daily")
        assert latest is None

    # ============ delete_run tests ============

    def test_delete_run(self, pipeline_store: PipelineStore) -> None:
        """Test deleting a run."""
        run_id = "run-delete-001"
        pipeline_store.insert_run(
            run_id=run_id,
            task_name="update",
            dataset_id="stock_daily",
        )

        # Verify it exists
        result = pipeline_store.get_run(run_id)
        assert result is not None

        # Delete
        deleted = pipeline_store.delete_run(run_id)
        assert deleted is True

        # Verify it's gone
        result = pipeline_store.get_run(run_id)
        assert result is None

    def test_delete_run_nonexistent(self, pipeline_store: PipelineStore) -> None:
        """Test deleting non-existent run."""
        deleted = pipeline_store.delete_run("nonexistent")
        assert deleted is False

    # ============ Security/Whitelist tests ============

    def test_update_run_accepts_all_whitelisted_columns(
        self, pipeline_store: PipelineStore
    ) -> None:
        """Test update_run accepts all columns in ALLOWED_COLUMNS.

        Note: update_run() uses explicit parameter definitions, which prevents
        SQL injection via kwargs at the Python level (TypeError is raised before
        the function executes). The ALLOWED_COLUMNS whitelist provides defense
        in depth for the dynamic SQL construction inside the method.
        """
        pipeline_store.insert_run(
            run_id="run-whitelist-002",
            task_name="update",
            dataset_id="stock_daily",
        )

        # All whitelisted columns should be accepted
        pipeline_store.update_run(
            run_id="run-whitelist-002",
            status="completed",
            error_message=None,
            rows_read=1000,
            rows_written=950,
            dq_passed=True,
            dq_fail_count=0,
            dq_warn_count=2,
        )

        result = pipeline_store.get_run("run-whitelist-002")
        assert result is not None
        assert result["status"] == "completed"
        assert result["rows_read"] == 1000
        assert result["dq_passed"] is True
        assert result["dq_fail_count"] == 0
        assert result["dq_warn_count"] == 2
