"""App Command DTO 单元测试."""

from datetime import date

import pytest
from ditto_application.command import (
    BackfillRangeCommand,
    CommandHandler,
    IngestRangeCommand,
)
from ditto_application.contracts import IngestDateCommand


class TestIngestDateCommand:
    def test_creation(self) -> None:
        cmd = IngestDateCommand(dataset="cn_stock_bar", trade_date=date(2024, 1, 15))
        assert cmd.dataset == "cn_stock_bar"
        assert cmd.trade_date == date(2024, 1, 15)
        assert cmd.force is False

    def test_creation_with_force(self) -> None:
        cmd = IngestDateCommand(dataset="test", trade_date=date(2024, 1, 1), force=True)
        assert cmd.force is True

    def test_frozen(self) -> None:
        cmd = IngestDateCommand(dataset="test", trade_date=date(2024, 1, 1))
        with pytest.raises(AttributeError):
            cmd.dataset = "changed"  # type: ignore[misc]


class TestIngestRangeCommand:
    def test_creation(self) -> None:
        cmd = IngestRangeCommand(
            dataset="cn_stock_bar",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        assert cmd.dataset == "cn_stock_bar"
        assert cmd.start_date == date(2024, 1, 1)
        assert cmd.end_date == date(2024, 1, 31)
        assert cmd.force is False
        assert cmd.parallel == 4

    def test_frozen(self) -> None:
        cmd = IngestRangeCommand(
            dataset="test", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)
        )
        with pytest.raises(AttributeError):
            cmd.dataset = "changed"  # type: ignore[misc]


class TestBackfillRangeCommand:
    def test_creation(self) -> None:
        cmd = BackfillRangeCommand(
            dataset="cn_stock_bar",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        assert cmd.parallel == 4

    def test_custom_parallel(self) -> None:
        cmd = BackfillRangeCommand(
            dataset="test",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            parallel=8,
        )
        assert cmd.parallel == 8


class TestCommandHandlerProtocol:
    def test_custom_handler_satisfies_protocol(self) -> None:
        """自定义 handler 应满足 CommandHandler Protocol."""

        class FakeHandler:
            def handle(self, command: IngestDateCommand) -> str:
                return f"processed {command.dataset}"

        handler: CommandHandler[IngestDateCommand] = FakeHandler()
        result = handler.handle(
            IngestDateCommand(dataset="test", trade_date=date(2024, 1, 1))
        )
        assert result == "processed test"

    def test_protocol_runtime_check(self) -> None:
        """CommandHandler 应通过 runtime_check."""

        class FakeHandler:
            def handle(self, command: object) -> object:
                return None

        assert isinstance(FakeHandler(), CommandHandler)
