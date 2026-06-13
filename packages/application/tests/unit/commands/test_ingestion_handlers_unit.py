"""IngestDateHandler 单元测试 — Command Handler 委托测试."""

from datetime import date
from unittest.mock import create_autospec

from ditto_application.contracts import IngestDateCommand
from ditto_application.processes.ingestion.coordinator import IngestionCoordinator
from ditto_data.models.ingestion import IngestionResult


class TestIngestDateHandler:
    """IngestDateHandler — 单日入库 Command Handler."""

    def test_handle_delegates_to_coordinator(self) -> None:
        """Handler 将 command 参数委托给 coordinator.ingest_date."""
        # Arrange
        coordinator = create_autospec(IngestionCoordinator, instance=True)
        expected = IngestionResult(
            dataset="test",
            trade_date="2025-01-01",
            status="success",
            row_count=100,
        )
        coordinator.ingest_date.return_value = expected

        from ditto_application.commands.ingestion import IngestDateHandler

        handler = IngestDateHandler(coordinator)
        cmd = IngestDateCommand(dataset="test", trade_date=date(2025, 1, 1), force=True)

        # Act
        result = handler.handle(cmd)

        # Assert
        assert result == expected
        coordinator.ingest_date.assert_called_once_with(
            "test", "2025-01-01", force=True
        )

    def test_handle_default_force_false(self) -> None:
        """force 默认为 False，传递给 coordinator."""
        coordinator = create_autospec(IngestionCoordinator, instance=True)
        coordinator.ingest_date.return_value = IngestionResult(
            dataset="test",
            trade_date="2025-01-01",
            status="success",
            row_count=0,
        )

        from ditto_application.commands.ingestion import IngestDateHandler

        handler = IngestDateHandler(coordinator)
        cmd = IngestDateCommand(dataset="test", trade_date=date(2025, 1, 1))

        handler.handle(cmd)

        coordinator.ingest_date.assert_called_once_with(
            "test", "2025-01-01", force=False
        )

    def test_handle_converts_date_to_isoformat(self) -> None:
        """Handler 将 date 对象转换为 ISO 格式字符串."""
        coordinator = create_autospec(IngestionCoordinator, instance=True)
        coordinator.ingest_date.return_value = IngestionResult(
            dataset="test",
            trade_date="2025-06-15",
            status="success",
        )

        from ditto_application.commands.ingestion import IngestDateHandler

        handler = IngestDateHandler(coordinator)
        cmd = IngestDateCommand(dataset="test", trade_date=date(2025, 6, 15))

        handler.handle(cmd)

        coordinator.ingest_date.assert_called_once_with(
            "test", "2025-06-15", force=False
        )

    def test_handle_maps_coordinator_error(self) -> None:
        """Handler 将 coordinator 领域错误映射为 AppCommandError."""
        import pytest
        from ditto_application.exceptions import AppCommandError, AppProcessError

        coordinator = create_autospec(IngestionCoordinator, instance=True)
        coordinator.ingest_date.side_effect = AppProcessError("不支持的数据集: bad")

        from ditto_application.commands.ingestion import IngestDateHandler

        handler = IngestDateHandler(coordinator)
        cmd = IngestDateCommand(dataset="bad", trade_date=date(2025, 1, 1))

        with pytest.raises(AppCommandError, match="不支持的数据集") as exc_info:
            handler.handle(cmd)

        assert exc_info.value.details == {
            "command": "ingest_date",
            "dataset": "bad",
            "trade_date": "2025-01-01",
            "force": False,
        }

    def test_handle_preserves_process_error_details(self) -> None:
        """Handler 映射 process error 时应保留底层结构化诊断上下文."""
        import pytest
        from ditto_application.exceptions import AppCommandError, AppProcessError

        coordinator = create_autospec(IngestionCoordinator, instance=True)
        coordinator.ingest_date.side_effect = AppProcessError(
            "Data source 'fred' does not support dataset stock_daily",
            field="source_name",
            value="fred",
            dataset="stock_daily",
            supported=["tushare"],
            operation="ingest_date",
            selection_date="2026-06-01",
        )

        from ditto_application.commands.ingestion import IngestDateHandler

        handler = IngestDateHandler(coordinator)
        cmd = IngestDateCommand(
            dataset="stock_daily",
            trade_date=date(2026, 6, 1),
            force=True,
        )

        with pytest.raises(AppCommandError, match="does not support dataset") as exc:
            handler.handle(cmd)

        assert exc.value.details == {
            "field": "source_name",
            "value": "fred",
            "dataset": "stock_daily",
            "supported": ["tushare"],
            "operation": "ingest_date",
            "selection_date": "2026-06-01",
            "command": "ingest_date",
            "trade_date": "2026-06-01",
            "force": True,
        }

    def test_satisfies_command_handler_protocol(self) -> None:
        """IngestDateHandler 满足 CommandHandler Protocol."""
        from ditto_application.commands.protocols import CommandHandler

        coordinator = create_autospec(IngestionCoordinator, instance=True)

        from ditto_application.commands.ingestion import IngestDateHandler

        handler = IngestDateHandler(coordinator)
        assert isinstance(handler, CommandHandler)
