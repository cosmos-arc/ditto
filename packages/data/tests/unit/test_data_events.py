"""ditto_data.events 单元测试."""

from datetime import date, datetime

import pytest
from ditto_data.events import DataIngested, QualityCheckCompleted


class TestDataIngested:
    def test_creation(self) -> None:
        event = DataIngested(
            timestamp=datetime(2024, 1, 15, 18, 0),
            dataset="cn_stock_bar",
            trade_date=date(2024, 1, 15),
            row_count=4500,
        )
        assert event.event_type == "data_ingested"
        assert event.dataset == "cn_stock_bar"
        assert event.trade_date == date(2024, 1, 15)
        assert event.row_count == 4500
        assert event.source == ""
        assert event.payload == {}

    def test_with_source(self) -> None:
        event = DataIngested(
            timestamp=datetime(2024, 1, 15),
            dataset="cn_stock_bar",
            trade_date=date(2024, 1, 15),
            row_count=100,
            source="tushare",
        )
        assert event.source == "tushare"

    def test_frozen(self) -> None:
        event = DataIngested(
            timestamp=datetime(2024, 1, 15),
            dataset="test",
            trade_date=date(2024, 1, 15),
            row_count=0,
        )
        with pytest.raises(AttributeError):
            event.dataset = "changed"  # type: ignore[misc]

    def test_inherits_domain_event(self) -> None:
        from ditto_kernel import DomainEvent

        event = DataIngested(
            timestamp=datetime(2024, 1, 15),
            dataset="test",
            trade_date=date(2024, 1, 15),
            row_count=0,
        )
        assert isinstance(event, DomainEvent)


class TestQualityCheckCompleted:
    def test_passed(self) -> None:
        event = QualityCheckCompleted(
            timestamp=datetime(2024, 1, 15, 18, 30),
            dataset="cn_stock_bar",
            trade_date=date(2024, 1, 15),
            passed=True,
        )
        assert event.event_type == "quality_check_completed"
        assert event.passed is True
        assert event.issues == []

    def test_failed_with_issues(self) -> None:
        event = QualityCheckCompleted(
            timestamp=datetime(2024, 1, 15),
            dataset="cn_stock_bar",
            trade_date=date(2024, 1, 15),
            passed=False,
            issues=["ohlc_inconsistent", "volume_outlier"],
        )
        assert event.passed is False
        assert len(event.issues) == 2
