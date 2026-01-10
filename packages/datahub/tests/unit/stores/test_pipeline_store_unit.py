"""Tests for PipelineStore."""

from datetime import datetime

import pytest
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.pipeline_store import PipelineStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.mark.pit
class TestPipelineStore:
    """Tests for PipelineStore.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    def setup_method(self) -> None:
        """Set up test database."""
        # Create in-memory database for testing
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = PipelineStore(self.client)

    def test_pipeline_store_init(self) -> None:
        """Test PipelineStore initialization."""
        assert self.store._client is not None

    def test_insert_run_basic(self) -> None:
        """Test basic pipeline run insertion."""
        self.store.insert_run(
            run_id="test-run-1",
            task_name="test_task",
            dataset_id="test_dataset",
        )

        # Verify run was inserted
        run = self.store.get_run("test-run-1")
        assert run is not None
        assert run["run_id"] == "test-run-1"
        assert run["task_name"] == "test_task"
        assert run["dataset_id"] == "test_dataset"
        assert run["status"] == "running"

    def test_insert_run_with_all_fields(self) -> None:
        """Test pipeline run insertion with all optional fields."""
        started_at = datetime(2024, 1, 1, 10, 0, 0)
        finished_at = datetime(2024, 1, 1, 11, 0, 0)

        self.store.insert_run(
            run_id="test-run-2",
            task_name="test_task",
            dataset_id="test_dataset",
            year=2024,
            rows_read=1000,
            rows_written=950,
            status="completed",
            dq_passed=True,
            dq_fail_count=0,
            dq_warn_count=5,
            started_at=started_at,
            finished_at=finished_at,
        )

        # Verify all fields were inserted
        run = self.store.get_run("test-run-2")
        assert run is not None
        assert run["year"] == 2024
        assert run["rows_read"] == 1000
        assert run["rows_written"] == 950
        assert run["status"] == "completed"
        assert run["dq_passed"] is True
        assert run["dq_fail_count"] == 0
        assert run["dq_warn_count"] == 5
        assert run["duration_sec"] == 3600.0

    def test_insert_run_with_error(self) -> None:
        """Test pipeline run insertion with error."""
        self.store.insert_run(
            run_id="test-run-3",
            task_name="test_task",
            dataset_id="test_dataset",
            status="failed",
            error_message="Test error",
        )

        run = self.store.get_run("test-run-3")
        assert run is not None
        assert run["status"] == "failed"
        assert run["error_message"] == "Test error"

    def test_update_run_status(self) -> None:
        """Test updating pipeline run status."""
        # First insert a run
        self.store.insert_run(
            run_id="test-run-4",
            task_name="test_task",
            dataset_id="test_dataset",
        )

        # Update status
        self.store.update_run("test-run-4", status="completed")

        # Verify update
        run = self.store.get_run("test-run-4")
        assert run is not None
        assert run["status"] == "completed"

    def test_update_run_with_finished_at(self) -> None:
        """Test updating run with finished_at calculates duration."""
        started_at = datetime(2024, 1, 1, 10, 0, 0)
        finished_at = datetime(2024, 1, 1, 10, 30, 0)

        # Insert with started_at
        self.store.insert_run(
            run_id="test-run-5",
            task_name="test_task",
            dataset_id="test_dataset",
            started_at=started_at,
        )

        # Update with finished_at
        self.store.update_run("test-run-5", finished_at=finished_at)

        # Verify duration was calculated
        run = self.store.get_run("test-run-5")
        assert run is not None
        # finished_at is stored as ISO format string in database
        assert run["finished_at"] == "2024-01-01 10:30:00"
        assert run["duration_sec"] == 1800.0

    def test_update_run_multiple_fields(self) -> None:
        """Test updating multiple fields at once."""
        self.store.insert_run(
            run_id="test-run-6",
            task_name="test_task",
            dataset_id="test_dataset",
        )

        # Update multiple fields
        self.store.update_run(
            "test-run-6",
            status="completed",
            rows_read=100,
            rows_written=95,
            dq_passed=True,
            dq_fail_count=0,
            dq_warn_count=1,
        )

        # Verify all updates
        run = self.store.get_run("test-run-6")
        assert run is not None
        assert run["status"] == "completed"
        assert run["rows_read"] == 100
        assert run["rows_written"] == 95
        assert run["dq_passed"] is True
        assert run["dq_fail_count"] == 0
        assert run["dq_warn_count"] == 1

    def test_update_run_invalid_column(self) -> None:
        """Test updating with invalid column raises error."""
        self.store.insert_run(
            run_id="test-run-7",
            task_name="test_task",
            dataset_id="test_dataset",
        )

        # Try to update a non-allowed column (by manipulating ALLOWED_COLUMNS)
        original_columns = PipelineStore.ALLOWED_COLUMNS
        PipelineStore.ALLOWED_COLUMNS = frozenset(["status"])  # Restrict to only status

        try:
            # This should raise ValueError because "rows_read" is not in ALLOWED_COLUMNS
            with pytest.raises(ValueError, match="Invalid column"):
                self.store.update_run("test-run-7", rows_read=100)
        finally:
            # Restore original ALLOWED_COLUMNS
            PipelineStore.ALLOWED_COLUMNS = original_columns

    def test_get_run_not_found(self) -> None:
        """Test getting non-existent run returns None."""
        run = self.store.get_run("nonexistent")
        assert run is None

    def test_list_runs_all(self) -> None:
        """Test listing all runs."""
        # Insert multiple runs
        for i in range(3):
            self.store.insert_run(
                run_id=f"run-{i}",
                task_name="test_task",
                dataset_id="test_dataset",
            )

        # List all runs
        runs = self.store.list_runs()
        assert len(runs) == 3

    def test_list_runs_with_dataset_filter(self) -> None:
        """Test listing runs filtered by dataset_id."""
        # Insert runs for different datasets
        self.store.insert_run("run-1", "task1", "dataset_a")
        self.store.insert_run("run-2", "task2", "dataset_b")
        self.store.insert_run("run-3", "task3", "dataset_a")

        # Filter by dataset
        runs = self.store.list_runs(dataset_id="dataset_a")
        assert len(runs) == 2
        assert all(r["dataset_id"] == "dataset_a" for r in runs)

    def test_list_runs_with_status_filter(self) -> None:
        """Test listing runs filtered by status."""
        self.store.insert_run("run-1", "task1", "dataset_a", status="running")
        self.store.insert_run("run-2", "task2", "dataset_b", status="completed")
        self.store.insert_run("run-3", "task3", "dataset_a", status="completed")

        # Filter by status
        runs = self.store.list_runs(status="completed")
        assert len(runs) == 2
        assert all(r["status"] == "completed" for r in runs)

    def test_list_runs_with_limit(self) -> None:
        """Test listing runs with limit."""
        # Insert 5 runs
        for i in range(5):
            self.store.insert_run(f"run-{i}", "task", "dataset")

        # List with limit
        runs = self.store.list_runs(limit=3)
        assert len(runs) == 3

    def test_get_latest_run(self) -> None:
        """Test getting latest run for dataset."""
        # Insert runs for same dataset
        self.store.insert_run("run-1", "task1", "dataset_a", year=2024)
        self.store.insert_run("run-2", "task2", "dataset_a", year=2024)
        self.store.insert_run("run-3", "task3", "dataset_a", year=2023)

        # Get latest (should be run-2 as it was inserted last for 2024)
        latest = self.store.get_latest_run("dataset_a", year=2024)
        assert latest is not None
        assert latest["run_id"] == "run-2"

    def test_get_latest_run_no_year_filter(self) -> None:
        """Test getting latest run without year filter."""
        self.store.insert_run("run-1", "task1", "dataset_a")
        self.store.insert_run("run-2", "task2", "dataset_a")

        latest = self.store.get_latest_run("dataset_a")
        assert latest is not None
        assert latest["run_id"] == "run-2"

    def test_get_latest_run_not_found(self) -> None:
        """Test getting latest run for non-existent dataset."""
        latest = self.store.get_latest_run("nonexistent")
        assert latest is None

    def test_count_runs_all(self) -> None:
        """Test counting all runs."""
        for i in range(3):
            self.store.insert_run(f"run-{i}", "task", "dataset")

        count = self.store.count_runs()
        assert count == 3

    def test_count_runs_with_dataset_filter(self) -> None:
        """Test counting runs filtered by dataset."""
        self.store.insert_run("run-1", "task1", "dataset_a")
        self.store.insert_run("run-2", "task2", "dataset_b")
        self.store.insert_run("run-3", "task3", "dataset_a")

        count = self.store.count_runs(dataset_id="dataset_a")
        assert count == 2

    def test_count_runs_with_status_filter(self) -> None:
        """Test counting runs filtered by status."""
        self.store.insert_run("run-1", "task1", "dataset_a", status="running")
        self.store.insert_run("run-2", "task2", "dataset_b", status="completed")
        self.store.insert_run("run-3", "task3", "dataset_a", status="completed")

        count = self.store.count_runs(status="completed")
        assert count == 2

    def test_count_runs_no_filters(self) -> None:
        """Test counting runs without filters returns all."""
        self.store.insert_run("run-1", "task1", "dataset_a")
        self.store.insert_run("run-2", "task2", "dataset_b")

        count = self.store.count_runs()
        assert count == 2

    def test_delete_run_existing(self) -> None:
        """Test deleting existing run."""
        self.store.insert_run("run-1", "task", "dataset")

        # Delete the run
        result = self.store.delete_run("run-1")
        assert result is True

        # Verify it's deleted
        run = self.store.get_run("run-1")
        assert run is None

    def test_delete_run_not_found(self) -> None:
        """Test deleting non-existent run returns False."""
        result = self.store.delete_run("nonexistent")
        assert result is False

    def test_insert_dq_issue(self) -> None:
        """Test inserting DQ issue."""
        self.store.insert_dq_issue(
            run_id="test-run",
            dataset_id="test_dataset",
            rule_name="test_rule",
            severity="error",
            message="Test DQ issue",
        )

        # Verify DQ issue was inserted
        issues = self.store.list_dq_issues(run_id="test-run")
        assert len(issues) == 1
        assert issues[0]["rule_name"] == "test_rule"
        assert issues[0]["severity"] == "error"

    def test_insert_dq_issue_with_context(self) -> None:
        """Test inserting DQ issue with context fields."""
        self.store.insert_dq_issue(
            run_id="test-run",
            dataset_id="test_dataset",
            rule_name="test_rule",
            severity="warning",
            year=2024,
            sid=1000001,
            trade_date="2024-01-01",
        )

        issues = self.store.list_dq_issues(run_id="test-run")
        assert len(issues) == 1
        assert issues[0]["year"] == 2024
        assert issues[0]["sid"] == 1000001
        assert issues[0]["trade_date"] == "2024-01-01"

    def test_list_dq_issues_with_filters(self) -> None:
        """Test listing DQ issues with filters."""
        # Insert multiple DQ issues
        self.store.insert_dq_issue("run-1", "dataset_a", "rule1", "error")
        self.store.insert_dq_issue("run-2", "dataset_b", "rule2", "warning")
        self.store.insert_dq_issue("run-1", "dataset_a", "rule3", "error")

        # Filter by run_id
        issues = self.store.list_dq_issues(run_id="run-1")
        assert len(issues) == 2

        # Filter by severity
        issues = self.store.list_dq_issues(severity="error")
        assert len(issues) == 2

        # Filter by dataset_id
        issues = self.store.list_dq_issues(dataset_id="dataset_a")
        assert len(issues) == 2

    def test_count_dq_issues(self) -> None:
        """Test counting DQ issues."""
        # Insert DQ issues
        self.store.insert_dq_issue("run-1", "dataset_a", "rule1", "error")
        self.store.insert_dq_issue("run-2", "dataset_b", "rule2", "warning")
        self.store.insert_dq_issue("run-1", "dataset_a", "rule3", "error")

        # Count all
        count = self.store.count_dq_issues()
        assert count == 3

        # Count with filter
        count = self.store.count_dq_issues(run_id="run-1")
        assert count == 2

        count = self.store.count_dq_issues(severity="error")
        assert count == 2

    def test_dq_passed_default_to_completed_status(self) -> None:
        """Test that dq_passed defaults to True when status is 'completed'."""
        self.store.insert_run(
            run_id="test-run",
            task_name="test_task",
            dataset_id="test_dataset",
            status="completed",
        )

        run = self.store.get_run("test-run")
        assert run is not None
        assert run["dq_passed"] is True

    def test_dq_passed_explicit_none(self) -> None:
        """Test explicit None for dq_passed when status is not completed."""
        self.store.insert_run(
            run_id="test-run",
            task_name="test_task",
            dataset_id="test_dataset",
            status="running",
            dq_passed=None,
        )

        run = self.store.get_run("test-run")
        assert run is not None
        # When status is not "completed" and dq_passed is None, it should be False
        assert run["dq_passed"] is False

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass
