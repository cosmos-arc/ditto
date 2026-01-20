"""Tests for DQ batch tasks."""

import pathlib

import ditto_datahub
import polars as pl
import pytest
from ditto_port.jobs.tasks.dq_batch import (
    dq_batch_check,
    dq_completeness_check,
    get_default_dq_config_path,
)


@pytest.mark.unit
def test_default_config_path_points_to_package():
    """Test default config path points to packages/datahub/config/dq_rules."""
    package_root = pathlib.Path(ditto_datahub.__file__).parent.parent.parent
    expected_path = package_root / "config" / "dq_rules"

    actual_path = get_default_dq_config_path()

    assert actual_path == str(expected_path)
    # Verify the path actually exists on the filesystem
    assert pathlib.Path(actual_path).exists()


@pytest.mark.unit
def test_dq_completeness_check_uses_context(tmp_path, mocker):
    """Test dq_completeness_check uses create_datahub_context."""
    # Arrange
    mock_hub = mocker.MagicMock()
    mock_hub.bars.get.return_value = pl.DataFrame(
        {"sid": [1, 2, 3], "trade_date": ["2024-01-02", "2024-01-02", "2024-01-02"]}
    )

    # Create mock context manager
    mock_context_mgr = mocker.MagicMock()
    mock_context_mgr.__enter__.return_value = mock_hub
    mock_context_mgr.__exit__.return_value = None

    with mocker.patch(
        "ditto_port.jobs.tasks.dq_batch.create_datahub_context",
        return_value=mock_context_mgr,
    ):
        # Act - call .fn to skip Prefect task wrapper
        result = dq_completeness_check.fn(
            trade_date="2024-01-02",
            dataset="test_daily",
            expected_sids=[1, 2, 3],
            market_wide=True,
        )

        # Assert
        assert result["is_complete"] is True
        assert result["actual_count"] == 3


@pytest.mark.unit
def test_dq_completeness_check_passes_market_wide_parameter(tmp_path, mocker):
    """Test dq_completeness_check passes market_wide to bars.get() via BarsQuery."""
    # Arrange
    mock_hub = mocker.MagicMock()
    mock_hub.bars.get.return_value = pl.DataFrame(
        {"sid": [1, 2, 3], "trade_date": ["2024-01-02", "2024-01-02", "2024-01-02"]}
    )

    # Create mock context manager
    mock_context_mgr = mocker.MagicMock()
    mock_context_mgr.__enter__.return_value = mock_hub
    mock_context_mgr.__exit__.return_value = None

    with mocker.patch(
        "ditto_port.jobs.tasks.dq_batch.create_datahub_context",
        return_value=mock_context_mgr,
    ):
        # Act - call .fn to skip Prefect task wrapper
        dq_completeness_check.fn(
            trade_date="2024-01-02",
            dataset="test_daily",
            expected_sids=[1, 2, 3],
            market_wide=True,
        )

        # Assert
        call_kwargs = mock_hub.bars.get.call_args.kwargs
        query = call_kwargs.get("query")
        assert query is not None
        assert query.market_wide is True


@pytest.mark.unit
def test_dq_batch_check_uses_context(tmp_path, mocker):
    """Test dq_batch_check uses create_datahub_context."""
    # Arrange
    mock_hub = mocker.MagicMock()
    mock_hub.calendar.get_last_trading_day.return_value = "2024-01-02"

    # Mock DQEngine to avoid actual DQ checks
    mock_engine = mocker.MagicMock()
    mock_result = mocker.MagicMock()
    mock_result.passed = True
    mock_result.issues = []
    mock_result.alert_count = 0
    mock_engine.check_statistical.return_value = mock_result

    # Create mock context manager
    mock_context_mgr = mocker.MagicMock()
    mock_context_mgr.__enter__.return_value = mock_hub
    mock_context_mgr.__exit__.return_value = None

    with mocker.patch(
        "ditto_port.jobs.tasks.dq_batch.create_datahub_context",
        return_value=mock_context_mgr,
    ):
        with mocker.patch(
            "ditto_port.jobs.tasks.dq_batch.DQEngine", return_value=mock_engine
        ):
            with mocker.patch("ditto_port.jobs.tasks.dq_batch.M"):
                # Act - call .fn to skip Prefect task wrapper
                result = dq_batch_check.fn(
                    trade_date="2024-01-02",
                    datasets=["test_daily"],
                )

                # Assert
                assert result["trade_date"] == "2024-01-02"
                assert result["total_issues"] == 0


@pytest.mark.unit
def test_dq_completeness_check_propagates_exceptions(tmp_path, mocker):
    """Test dq_completeness_check propagates exceptions."""
    # Arrange
    mock_hub = mocker.MagicMock()
    mock_hub.bars.get.side_effect = Exception("Database error")

    # Create mock context manager
    mock_context_mgr = mocker.MagicMock()
    mock_context_mgr.__enter__.return_value = mock_hub
    mock_context_mgr.__exit__.return_value = None

    with mocker.patch(
        "ditto_port.jobs.tasks.dq_batch.create_datahub_context",
        return_value=mock_context_mgr,
    ):
        # Act & Assert - call .fn to skip Prefect task wrapper
        with pytest.raises(Exception, match="Database error"):
            dq_completeness_check.fn(
                trade_date="2024-01-02",
                dataset="test_daily",
            )

        # Context manager handles cleanup
