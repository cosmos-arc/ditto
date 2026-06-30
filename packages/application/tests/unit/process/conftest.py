"""质量巡检测试共享 Fixtures — 从 quality 子包复用."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.quality.quality_types import DQResult


@pytest.fixture
def mock_statistical_engine() -> MagicMock:
    """Mock QualityEngine configured for statistical checks.

    使用 check_statistical 方法（区别于 mock_quality_engine 的 check 方法）。
    """
    engine = MagicMock()
    result = DQResult(
        dataset="stock_daily",
        passed=True,
        issues=[],
    )
    engine.check_statistical.return_value = result
    return engine


@pytest.fixture
def mock_market_service() -> MagicMock:
    """Mock MarketService."""
    service = MagicMock()
    service.find_bars.return_value = pl.DataFrame()
    return service


@pytest.fixture
def mock_metadata_service() -> MagicMock:
    """Mock MetadataService."""
    service = MagicMock()
    service.calendar.list_calendar_range.return_value = pl.DataFrame()
    return service
