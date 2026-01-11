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


def test_default_config_path_points_to_package():
    """Test default config path points to packages/datahub/config/dq_rules."""
    package_root = pathlib.Path(ditto_datahub.__file__).parent.parent.parent
    expected_path = package_root / "config" / "dq_rules"

    actual_path = get_default_dq_config_path()

    assert actual_path == str(expected_path)
    # Verify the path actually exists on the filesystem
    assert pathlib.Path(actual_path).exists()


def test_dq_completeness_check_closes_hub_connection(tmp_path, mocker):
    """Test dq_completeness_check closes DataHub connection to avoid leaks."""
    # Arrange
    mock_hub = mocker.MagicMock()
    mock_hub.bars.get.return_value = pl.DataFrame(
        {"sid": [1, 2, 3], "trade_date": ["2024-01-02", "2024-01-02", "2024-01-02"]}
    )

    with mocker.patch("ditto_port.jobs.tasks.dq_batch.DataHub", return_value=mock_hub):
        # Act
        result = dq_completeness_check(
            trade_date="2024-01-02",
            dataset="test_daily",
            expected_sids=[1, 2, 3],
            market_wide=True,
        )

        # Assert
        assert result["is_complete"] is True
        assert result["actual_count"] == 3
        mock_hub.close.assert_called_once()


def test_dq_completeness_check_passes_market_wide_parameter(tmp_path, mocker):
    """Test dq_completeness_check passes market_wide to bars.get()."""
    # Arrange
    mock_hub = mocker.MagicMock()
    mock_hub.bars.get.return_value = pl.DataFrame(
        {"sid": [1, 2, 3], "trade_date": ["2024-01-02", "2024-01-02", "2024-01-02"]}
    )

    with mocker.patch("ditto_port.jobs.tasks.dq_batch.DataHub", return_value=mock_hub):
        # Act
        dq_completeness_check(
            trade_date="2024-01-02",
            dataset="test_daily",
            expected_sids=[1, 2, 3],
            market_wide=True,
        )

        # Assert
        call_kwargs = mock_hub.bars.get.call_args.kwargs
        assert call_kwargs.get("market_wide") is True


def test_dq_batch_check_closes_hub_connection(tmp_path, mocker):
    """Test dq_batch_check closes DataHub connection to avoid leaks."""
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

    with mocker.patch("ditto_port.jobs.tasks.dq_batch.DataHub", return_value=mock_hub):
        with mocker.patch(
            "ditto_port.jobs.tasks.dq_batch.DQEngine", return_value=mock_engine
        ):
            with mocker.patch("ditto_port.jobs.tasks.dq_batch.M"):
                # Act
                result = dq_batch_check(
                    trade_date="2024-01-02",
                    datasets=["test_daily"],
                )

                # Assert
                assert result["trade_date"] == "2024-01-02"
                assert result["total_issues"] == 0
                mock_hub.close.assert_called_once()


def test_dq_completeness_check_closes_on_exception(tmp_path, mocker):
    """Test dq_completeness_check closes connection even when exception occurs."""
    # Arrange
    mock_hub = mocker.MagicMock()
    mock_hub.bars.get.side_effect = Exception("Database error")

    with mocker.patch("ditto_port.jobs.tasks.dq_batch.DataHub", return_value=mock_hub):
        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            dq_completeness_check(
                trade_date="2024-01-02",
                dataset="test_daily",
            )

        # Verify close was called despite exception
        mock_hub.close.assert_called_once()
