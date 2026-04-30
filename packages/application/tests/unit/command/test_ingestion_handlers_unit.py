"""IngestDateHandler 单元测试 — Command Handler 委托测试."""

from datetime import date
from unittest.mock import create_autospec

from ditto_application.contracts import IngestDateCommand
from ditto_application.process.ingestion.coordinator import IngestionCoordinator
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

        from ditto_application.command.ingestion import IngestDateHandler

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

        from ditto_application.command.ingestion import IngestDateHandler

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

        from ditto_application.command.ingestion import IngestDateHandler

        handler = IngestDateHandler(coordinator)
        cmd = IngestDateCommand(dataset="test", trade_date=date(2025, 6, 15))

        handler.handle(cmd)

        coordinator.ingest_date.assert_called_once_with(
            "test", "2025-06-15", force=False
        )

    def test_handle_propagates_coordinator_error(self) -> None:
        """Handler 传播 coordinator 抛出的异常."""
        import pytest

        coordinator = create_autospec(IngestionCoordinator, instance=True)
        coordinator.ingest_date.side_effect = ValueError("不支持的数据集: bad")

        from ditto_application.command.ingestion import IngestDateHandler

        handler = IngestDateHandler(coordinator)
        cmd = IngestDateCommand(dataset="bad", trade_date=date(2025, 1, 1))

        with pytest.raises(ValueError, match="不支持的数据集"):
            handler.handle(cmd)

    def test_satisfies_command_handler_protocol(self) -> None:
        """IngestDateHandler 满足 CommandHandler Protocol."""
        from ditto_application.command.protocols import CommandHandler

        coordinator = create_autospec(IngestionCoordinator, instance=True)

        from ditto_application.command.ingestion import IngestDateHandler

        handler = IngestDateHandler(coordinator)
        assert isinstance(handler, CommandHandler)
