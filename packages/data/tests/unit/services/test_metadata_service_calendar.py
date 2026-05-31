"""Tests for MetadataService calendar methods — update_half_days and enrich_calendar."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.services.metadata.calendar import compute_calendar_enrichment
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.tushare.transformer import TushareExchangeTransformer


@pytest.fixture
def mock_dependencies() -> dict[str, MagicMock]:
    """创建 MetadataService 的 mock 依赖."""
    return {
        "instrument_reader": MagicMock(),
        "instrument_writer": MagicMock(),
        "name_history_reader": MagicMock(),
        "name_history_writer": MagicMock(),
        "calendar_reader": MagicMock(),
        "calendar_writer": MagicMock(),
        "industry_reader": MagicMock(),
        "industry_writer": MagicMock(),
        "industry_mapping_reader": MagicMock(),
        "industry_mapping_writer": MagicMock(),
        "universe_reader": MagicMock(),
        "universe_writer": MagicMock(),
        "rebalance_reader": MagicMock(),
        "rebalance_writer": MagicMock(),
        "instrument_id_allocator": MagicMock(),
        "index_composition_reader": MagicMock(),
    }


@pytest.fixture
def exchange_transformers() -> ExchangeTransformers:
    """创建 ExchangeTransformers 实例."""
    return ExchangeTransformers(
        tushare=TushareExchangeTransformer(),
        tdx=MagicMock(),
    )


@pytest.fixture
def service(
    mock_dependencies: dict[str, MagicMock],
    exchange_transformers: ExchangeTransformers,
) -> MetadataService:
    """创建 MetadataService 实例."""
    return MetadataService(
        instrument_reader=mock_dependencies["instrument_reader"],
        instrument_writer=mock_dependencies["instrument_writer"],
        name_history_reader=mock_dependencies["name_history_reader"],
        name_history_writer=mock_dependencies["name_history_writer"],
        calendar_reader=mock_dependencies["calendar_reader"],
        calendar_writer=mock_dependencies["calendar_writer"],
        industry_reader=mock_dependencies["industry_reader"],
        industry_writer=mock_dependencies["industry_writer"],
        industry_mapping_reader=mock_dependencies["industry_mapping_reader"],
        industry_mapping_writer=mock_dependencies["industry_mapping_writer"],
        universe_reader=mock_dependencies["universe_reader"],
        universe_writer=mock_dependencies["universe_writer"],
        rebalance_reader=mock_dependencies["rebalance_reader"],
        rebalance_writer=mock_dependencies["rebalance_writer"],
        instrument_id_allocator=mock_dependencies["instrument_id_allocator"],
        index_composition_reader=mock_dependencies["index_composition_reader"],
        exchange_transformers=exchange_transformers,
    )


# ============ compute_calendar_enrichment 纯函数测试 ============


class TestComputeCalendarEnrichment:
    """Tests for the compute_calendar_enrichment pure function."""

    def test_empty_input_returns_empty(self) -> None:
        """空列表应返回空结果."""
        result = compute_calendar_enrichment([])
        assert result == []

    def test_single_trading_day(self) -> None:
        """单个交易日应正确处理边界."""
        days = [
            {"trade_date": "2024-01-02", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert len(result) == 1
        assert result[0]["trade_date"] == "2024-01-02"
        assert result[0]["is_open"] is True
        assert result[0]["prev_trade_date"] is None
        assert result[0]["next_trade_date"] is None
        assert result[0]["month"] == 1
        assert result[0]["quarter"] == 1
        assert result[0]["year"] == 2024
        assert result[0]["is_half_day"] is False

    def test_multiple_days_basic(self) -> None:
        """多个交易日应正确计算 prev/next."""
        days = [
            {"trade_date": "2024-01-02", "is_open": True},
            {"trade_date": "2024-01-03", "is_open": True},
            {"trade_date": "2024-01-04", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert len(result) == 3

        assert result[0]["prev_trade_date"] is None
        assert result[0]["next_trade_date"] == "2024-01-03"

        assert result[1]["prev_trade_date"] == "2024-01-02"
        assert result[1]["next_trade_date"] == "2024-01-04"

        assert result[2]["prev_trade_date"] == "2024-01-03"
        assert result[2]["next_trade_date"] is None

    def test_filters_non_open_days(self) -> None:
        """非交易日不应出现在结果中."""
        days = [
            {"trade_date": "2024-01-01", "is_open": False},
            {"trade_date": "2024-01-02", "is_open": True},
            {"trade_date": "2024-01-06", "is_open": False},
        ]
        result = compute_calendar_enrichment(days)
        assert len(result) == 1
        assert result[0]["trade_date"] == "2024-01-02"

    def test_month_end_detection(self) -> None:
        """月末检测: 当前交易日的 month != 下一个交易日的 month."""
        days = [
            {"trade_date": "2024-01-31", "is_open": True},
            {"trade_date": "2024-02-01", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["is_month_end"] is True
        assert result[1]["is_month_end"] is False

    def test_quarter_end_detection(self) -> None:
        """季末检测: 当前交易日的 quarter != 下一个交易日的 quarter."""
        days = [
            {"trade_date": "2024-03-29", "is_open": True},
            {"trade_date": "2024-04-01", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["is_quarter_end"] is True
        assert result[1]["is_quarter_end"] is False

    def test_week_end_detection(self) -> None:
        """周末检测: 当前交易日的 (year, week) != 下一个交易日的 (year, week)."""
        # 2024-01-05 is Friday, ISO week 1
        # 2024-01-08 is Monday, ISO week 2
        days = [
            {"trade_date": "2024-01-05", "is_open": True},
            {"trade_date": "2024-01-08", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["is_week_end"] is True
        assert result[1]["is_week_end"] is False

    def test_year_boundary(self) -> None:
        """跨年边界: 2024-12-31 -> 2025-01-02."""
        days = [
            {"trade_date": "2024-12-31", "is_open": True},
            {"trade_date": "2025-01-02", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["is_month_end"] is True
        assert result[0]["is_quarter_end"] is True
        # 2024-12-31 ISO calendar: (2025, 1, 2) — same week as 2025-01-02
        assert result[0]["is_week_end"] is False
        assert result[0]["next_trade_date"] == "2025-01-02"
        assert result[0]["prev_trade_date"] is None
        assert result[0]["year"] == 2024
        assert result[1]["year"] == 2025
        assert result[1]["prev_trade_date"] == "2024-12-31"

    def test_week_of_year_extraction(self) -> None:
        """week_of_year 应使用 ISO calendar."""
        # 2024-01-08 is Monday, ISO week 2
        days = [
            {"trade_date": "2024-01-08", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        # date(2024, 1, 8).isocalendar() = (2024, 2, 1)
        assert result[0]["week_of_year"] == 2

    def test_default_is_half_day_false(self) -> None:
        """enrichment 结果默认 is_half_day = False."""
        days = [
            {"trade_date": "2024-01-02", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["is_half_day"] is False

    def test_default_exchange_sse(self) -> None:
        """enrichment 结果默认 exchange = 'SSE'."""
        days = [
            {"trade_date": "2024-01-02", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["exchange"] == "SSE"

    def test_custom_exchange_preserved(self) -> None:
        """enrichment 应保留输入中的 exchange 字段."""
        days = [
            {"trade_date": "2024-01-02", "is_open": True, "exchange": "SZSE"},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["exchange"] == "SZSE"

    def test_default_is_special_false(self) -> None:
        """enrichment 结果默认 is_special = False."""
        days = [
            {"trade_date": "2024-01-02", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["is_special"] is False

    def test_is_special_true_preserved(self) -> None:
        """enrichment 应保留输入中的 is_special = True."""
        days = [
            {"trade_date": "2024-09-18", "is_open": True, "is_special": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["is_special"] is True

    def test_sorted_by_trade_date(self) -> None:
        """输入无需排序，函数应按 trade_date 排序后处理."""
        days = [
            {"trade_date": "2024-01-04", "is_open": True},
            {"trade_date": "2024-01-02", "is_open": True},
            {"trade_date": "2024-01-03", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["trade_date"] == "2024-01-02"
        assert result[1]["trade_date"] == "2024-01-03"
        assert result[2]["trade_date"] == "2024-01-04"

    def test_last_trading_day_has_no_period_end_flags(self) -> None:
        """最后一个交易日如果没有下一个交易日，period_end 标记应为 False."""
        days = [
            {"trade_date": "2024-01-02", "is_open": True},
        ]
        result = compute_calendar_enrichment(days)
        assert result[0]["is_week_end"] is False
        assert result[0]["is_month_end"] is False
        assert result[0]["is_quarter_end"] is False


# ============ update_half_days 方法测试 ============


class TestUpdateHalfDays:
    """Tests for MetadataService.update_half_days method."""

    def test_update_half_days_delegates_to_writer(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """update_half_days 应将 is_half_day=True 的记录委托给 calendar_writer."""
        half_days = ["2024-12-31", "2025-01-01"]
        mock_dependencies["calendar_writer"].upsert.return_value = 2

        count = service.calendar.update_half_days(half_days)

        assert count == 2
        mock_dependencies["calendar_writer"].upsert.assert_called_once()
        call_args = mock_dependencies["calendar_writer"].upsert.call_args
        records = call_args[0][0]
        assert len(records) == 2
        assert records[0]["trade_date"] == "2024-12-31"
        assert records[0]["is_half_day"] is True
        assert records[1]["trade_date"] == "2025-01-01"
        assert records[1]["is_half_day"] is True

    def test_update_half_days_empty_list(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """空列表应返回 0 且不调用 writer."""
        count = service.calendar.update_half_days([])
        assert count == 0
        mock_dependencies["calendar_writer"].upsert.assert_not_called()


# ============ enrich_calendar 方法测试 ============


class TestEnrichCalendar:
    """Tests for MetadataService.enrich_calendar method."""

    def test_enrich_calendar_filters_unenriched_rows(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """enrich_calendar 应只处理 prev_trade_date 为 null 的行."""
        mock_dependencies["calendar_reader"].get_range_df.return_value = pl.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-03"],
                "is_open": [True, True],
                "prev_trade_date": [None, "2024-01-02"],
            }
        )
        mock_dependencies["calendar_reader"].offset.return_value = None
        mock_dependencies["calendar_writer"].upsert.return_value = 1

        count = service.calendar.enrich_calendar("2024-01-01", "2024-01-31")

        # Only one row should be enriched (the one with prev_trade_date=None)
        assert count == 1
        mock_dependencies["calendar_writer"].upsert.assert_called_once()
        call_args = mock_dependencies["calendar_writer"].upsert.call_args
        records = call_args[0][0]
        assert len(records) == 1
        assert records[0]["trade_date"] == "2024-01-02"
        assert records[0]["prev_trade_date"] is None
        # offset returned None for both boundaries, and 2024-01-03 is enriched
        # so next_trade_date should still be None (no adjacent boundary)
        assert records[0]["next_trade_date"] is None

    def test_enrich_calendar_all_rows_already_enriched(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """所有行都已丰富时，应返回 0."""
        # prev_trade_date 列全部非 null 表示已丰富
        mock_dependencies["calendar_reader"].get_range_df.return_value = pl.DataFrame(
            {
                "trade_date": ["2024-01-02"],
                "is_open": [True],
                "prev_trade_date": ["2024-01-01"],
            }
        )

        count = service.calendar.enrich_calendar("2024-01-01", "2024-01-31")
        assert count == 0
        mock_dependencies["calendar_writer"].upsert.assert_not_called()


# ============ auto_enrich_calendar 方法测试 ============


class TestAutoEnrichCalendar:
    """Tests for MetadataService.auto_enrich_calendar method."""

    def test_auto_enrich_calendar_calls_enrich_with_full_range(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """auto_enrich_calendar 应自动获取首尾交易日并委托给 enrich_calendar."""
        mock_dependencies[
            "calendar_reader"
        ].get_first_trading_day.return_value = "2024-01-02"
        mock_dependencies[
            "calendar_reader"
        ].get_last_trading_day.return_value = "2024-12-31"
        # enrich_calendar 内部会调用 get_range_df，模拟返回数据
        mock_dependencies["calendar_reader"].get_range_df.return_value = pl.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-03"],
                "is_open": [True, True],
                "prev_trade_date": [None, "2024-01-02"],
            }
        )
        mock_dependencies["calendar_reader"].offset.return_value = None
        mock_dependencies["calendar_writer"].upsert.return_value = 1

        count = service.calendar.auto_enrich_calendar()

        assert count == 1
        mock_dependencies["calendar_reader"].get_first_trading_day.assert_called_once()
        mock_dependencies["calendar_reader"].get_last_trading_day.assert_called_once()
        mock_dependencies["calendar_reader"].get_range_df.assert_called_once_with(
            "2024-01-02", "2024-12-31", only_open=False
        )
        mock_dependencies["calendar_writer"].upsert.assert_called_once()

    def test_auto_enrich_calendar_no_data(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """当日历无数据时，auto_enrich_calendar 应返回 0."""
        mock_dependencies["calendar_reader"].get_first_trading_day.return_value = None
        mock_dependencies["calendar_reader"].get_last_trading_day.return_value = None

        count = service.calendar.auto_enrich_calendar()

        assert count == 0
        mock_dependencies["calendar_reader"].get_range_df.assert_not_called()
        mock_dependencies["calendar_writer"].upsert.assert_not_called()

    def test_auto_enrich_calendar_first_day_none_returns_zero(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """当 get_first_trading_day 返回 None 时应返回 0."""
        mock_dependencies["calendar_reader"].get_first_trading_day.return_value = None
        mock_dependencies[
            "calendar_reader"
        ].get_last_trading_day.return_value = "2024-12-31"

        count = service.calendar.auto_enrich_calendar()

        assert count == 0
        mock_dependencies["calendar_reader"].get_range_df.assert_not_called()

    def test_auto_enrich_calendar_last_day_none_returns_zero(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """当 get_last_trading_day 返回 None 时应返回 0."""
        mock_dependencies[
            "calendar_reader"
        ].get_first_trading_day.return_value = "2024-01-02"
        mock_dependencies["calendar_reader"].get_last_trading_day.return_value = None

        count = service.calendar.auto_enrich_calendar()

        assert count == 0
        mock_dependencies["calendar_reader"].get_range_df.assert_not_called()
