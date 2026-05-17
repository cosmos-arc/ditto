"""IngestRangeProcess + BackfillRangeProcess 单元测试 — Process Manager 编排测试."""

from datetime import date
from unittest.mock import create_autospec

import pytest
from ditto_application.commands.ingestion import IngestDateHandler
from ditto_application.contracts import IngestDateCommand
from ditto_application.processes.ingestion.backfill_manager import BackfillManager
from ditto_data.models.ingestion import BackfillResult, IngestionResult
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    init,
    reset_for_testing,
)


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性."""
    reset_for_testing()
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=True,
        verbose_logging=False,
        tracing_enabled=True,
        tracing_sample_rate=1.0,
        metrics_enabled=True,
    )
    init(config, force=True)
    yield
    reset_for_testing()


class TestIngestRangeProcess:
    """IngestRangeProcess — 日期范围摄取 Process Manager."""

    def test_run_iterates_dates(self) -> None:
        """Range process 对范围内每个日期调用 handler."""
        handler = create_autospec(IngestDateHandler, instance=True)
        handler.handle.return_value = IngestionResult(
            dataset="test",
            trade_date="2025-01-01",
            status="success",
            row_count=10,
        )

        from ditto_application.processes.ingestion.range_process import (
            IngestRangeProcess,
            IngestRangeTrigger,
        )

        process = IngestRangeProcess(handler)
        trigger = IngestRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 3),
        )

        process.run(trigger)

        assert handler.handle.call_count == 3

    def test_run_passes_correct_commands(self) -> None:
        """Range process 传递正确的 IngestDateCommand 给 handler."""
        handler = create_autospec(IngestDateHandler, instance=True)
        handler.handle.return_value = IngestionResult(
            dataset="test",
            trade_date="2025-01-01",
            status="success",
        )

        from ditto_application.processes.ingestion.range_process import (
            IngestRangeProcess,
            IngestRangeTrigger,
        )

        process = IngestRangeProcess(handler)
        trigger = IngestRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
            force=True,
        )

        process.run(trigger)

        # 验证两次调用参数
        calls = handler.handle.call_args_list
        assert len(calls) == 2

        cmd1 = calls[0][0][0]
        assert isinstance(cmd1, IngestDateCommand)
        assert cmd1.dataset == "test"
        assert cmd1.trade_date == date(2025, 1, 1)
        assert cmd1.force is True

        cmd2 = calls[1][0][0]
        assert isinstance(cmd2, IngestDateCommand)
        assert cmd2.trade_date == date(2025, 1, 2)
        assert cmd2.force is True

    def test_run_single_date(self) -> None:
        """单日范围只调用一次 handler."""
        handler = create_autospec(IngestDateHandler, instance=True)
        handler.handle.return_value = IngestionResult(
            dataset="test",
            trade_date="2025-01-01",
            status="success",
        )

        from ditto_application.processes.ingestion.range_process import (
            IngestRangeProcess,
            IngestRangeTrigger,
        )

        process = IngestRangeProcess(handler)
        trigger = IngestRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 1),
        )

        process.run(trigger)

        assert handler.handle.call_count == 1

    def test_run_returns_results(self) -> None:
        """Range process 收集并返回所有结果."""
        handler = create_autospec(IngestDateHandler, instance=True)
        handler.handle.side_effect = [
            IngestionResult(
                dataset="test",
                trade_date="2025-01-01",
                status="success",
                row_count=10,
            ),
            IngestionResult(
                dataset="test",
                trade_date="2025-01-02",
                status="skipped",
            ),
        ]

        from ditto_application.processes.ingestion.range_process import (
            IngestRangeProcess,
            IngestRangeTrigger,
        )

        process = IngestRangeProcess(handler)
        trigger = IngestRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 2),
        )

        results = process.run(trigger)

        assert len(results) == 2
        assert results[0].status == "success"
        assert results[1].status == "skipped"


class TestBackfillRangeProcess:
    """BackfillRangeProcess — 缺失数据回填 Process Manager."""

    def test_run_delegates_to_backfill_manager(self) -> None:
        """BackfillRangeProcess 委托给 BackfillManager.backfill_range."""
        manager = create_autospec(BackfillManager, instance=True)
        expected = BackfillResult(
            dataset="test",
            total_dates=3,
            success_count=3,
            skipped_count=0,
            failed_count=0,
            results=(),
        )
        manager.backfill_range.return_value = expected

        from ditto_application.processes.ingestion.range_process import (
            BackfillRangeProcess,
            BackfillRangeTrigger,
        )

        process = BackfillRangeProcess(manager)
        trigger = BackfillRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            parallel=4,
        )

        result = process.run(trigger)

        assert result == expected
        manager.backfill_range.assert_called_once_with(
            dataset="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            parallel=4,
        )

    def test_run_default_parallel(self) -> None:
        """parallel 默认为 4."""
        manager = create_autospec(BackfillManager, instance=True)
        manager.backfill_range.return_value = BackfillResult(
            dataset="test",
            total_dates=0,
            success_count=0,
            skipped_count=0,
            failed_count=0,
            results=(),
        )

        from ditto_application.processes.ingestion.range_process import (
            BackfillRangeProcess,
            BackfillRangeTrigger,
        )

        process = BackfillRangeProcess(manager)
        trigger = BackfillRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        process.run(trigger)

        manager.backfill_range.assert_called_once_with(
            dataset="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            parallel=4,
        )

    def test_run_propagates_manager_error(self) -> None:
        """BackfillRangeProcess 传播 manager 抛出的异常."""
        manager = create_autospec(BackfillManager, instance=True)
        manager.backfill_range.side_effect = ValueError("dataset not found")

        from ditto_application.processes.ingestion.range_process import (
            BackfillRangeProcess,
            BackfillRangeTrigger,
        )

        process = BackfillRangeProcess(manager)
        trigger = BackfillRangeTrigger(
            dataset="bad",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        with pytest.raises(ValueError, match="dataset not found"):
            process.run(trigger)


class TestIngestRangeTrigger:
    """IngestRangeTrigger DTO 测试."""

    def test_creation(self) -> None:
        """基本创建测试."""
        from ditto_application.processes.ingestion.range_process import (
            IngestRangeTrigger,
        )

        trigger = IngestRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert trigger.dataset == "test"
        assert trigger.start_date == date(2025, 1, 1)
        assert trigger.end_date == date(2025, 1, 31)
        assert trigger.force is False
        assert trigger.parallel == 4

    def test_frozen(self) -> None:
        """Trigger 是 frozen dataclass."""
        from ditto_application.processes.ingestion.range_process import (
            IngestRangeTrigger,
        )

        trigger = IngestRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        try:
            trigger.dataset = "changed"  # type: ignore[misc]
        except AttributeError:
            pass
        else:
            raise AssertionError("Expected AttributeError for frozen dataclass")


class TestBackfillRangeTrigger:
    """BackfillRangeTrigger DTO 测试."""

    def test_creation(self) -> None:
        """基本创建测试."""
        from ditto_application.processes.ingestion.range_process import (
            BackfillRangeTrigger,
        )

        trigger = BackfillRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert trigger.parallel == 4

    def test_custom_parallel(self) -> None:
        """自定义并行度."""
        from ditto_application.processes.ingestion.range_process import (
            BackfillRangeTrigger,
        )

        trigger = BackfillRangeTrigger(
            dataset="test",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            parallel=8,
        )
        assert trigger.parallel == 8
