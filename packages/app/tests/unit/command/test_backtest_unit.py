"""
Unit tests for BacktestRunHandler.

Tests parameter validation, factor pre-compilation, RunRecord creation,
and error handling (strategy not found, invalid dates, compile failure).
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from ditto_app.command.backtest import (
    BacktestRunCommand,
    BacktestRunHandler,
    BacktestRunResult,
    CostConfig,
)
from ditto_app.process.execution.strategy_types import RunLifecycleService


@pytest.fixture
def mock_catalog_service() -> Mock:
    """Mock StrategyCatalogService."""
    svc = Mock()
    svc.get_spec.return_value = Mock(
        strategy_id="momentum-etf",
        spec_json={
            "signal_expressions": ["ts_mean(close, 20)"],
            "signal_weights": [1.0],
        },
    )
    return svc


@pytest.fixture
def mock_run_service() -> Mock:
    """Mock RunLifecycleService."""
    return Mock(spec=RunLifecycleService)


@pytest.fixture
def mock_factor_bridge() -> Mock:
    """Mock FactorBridge."""
    bridge = Mock()
    bridge.compile_and_validate.return_value = Mock()  # CompiledExpressions
    return bridge


@pytest.fixture
def handler(
    mock_catalog_service: Mock,
    mock_run_service: Mock,
    mock_factor_bridge: Mock,
) -> BacktestRunHandler:
    """Create handler with mocked dependencies."""
    return BacktestRunHandler(
        catalog_service=mock_catalog_service,
        run_service=mock_run_service,
        factor_bridge=mock_factor_bridge,
    )


def _make_command(**overrides) -> BacktestRunCommand:
    """Build a default valid command with optional overrides."""
    defaults = {
        "strategy_id": "momentum-etf",
        "start_date": "2025-01-01",
        "end_date": "2025-03-31",
        "initial_cash": 1_000_000.0,
        "parameter_overrides": (),
    }
    defaults.update(overrides)
    return BacktestRunCommand(**defaults)


class TestBacktestRunHandler:
    """Tests for BacktestRunHandler.handle()."""

    def test_successful_run_creates_record(
        self,
        handler: BacktestRunHandler,
        mock_run_service: Mock,
        mock_factor_bridge: Mock,
    ) -> None:
        """Successful flow: validate → compile → create record → return result."""
        cmd = _make_command()

        result = handler.handle(cmd)

        # Factor expressions were compiled
        mock_factor_bridge.compile_and_validate.assert_called_once()

        # RunRecord was created with PENDING status
        mock_run_service.create_run.assert_called_once()
        call_kwargs = mock_run_service.create_run.call_args
        assert call_kwargs.kwargs["strategy_id"] == "momentum-etf"
        assert call_kwargs.kwargs["mode"] == "backtest"

        # Result has run_id
        assert isinstance(result, BacktestRunResult)
        assert result.run_id
        assert result.status == "pending"

    def test_strategy_not_found_raises(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
    ) -> None:
        """Strategy not found raises ValueError."""
        mock_catalog_service.get_spec.return_value = None

        cmd = _make_command(strategy_id="nonexistent")

        with pytest.raises(ValueError, match="Strategy not found"):
            handler.handle(cmd)

    def test_invalid_date_range_raises(
        self,
        handler: BacktestRunHandler,
    ) -> None:
        """End date before start date raises ValueError."""
        cmd = _make_command(start_date="2025-06-01", end_date="2025-01-01")

        with pytest.raises(ValueError, match="日期范围无效"):
            handler.handle(cmd)

    def test_invalid_date_format_raises(
        self,
        handler: BacktestRunHandler,
    ) -> None:
        """Invalid date format raises ValueError."""
        cmd = _make_command(start_date="not-a-date")

        with pytest.raises(ValueError, match="日期格式无效"):
            handler.handle(cmd)

    def test_factor_compile_failure_raises(
        self,
        handler: BacktestRunHandler,
        mock_factor_bridge: Mock,
        mock_run_service: Mock,
    ) -> None:
        """Factor compilation failure raises ValueError, no record created."""
        mock_factor_bridge.compile_and_validate.side_effect = ValueError(
            "编译失败 (signal_0): unknown function 'bad_func'"
        )

        cmd = _make_command()

        with pytest.raises(ValueError, match="编译失败"):
            handler.handle(cmd)

        # No RunRecord should be created when compilation fails
        mock_run_service.create_run.assert_not_called()

    def test_parameter_overrides_passed(
        self,
        handler: BacktestRunHandler,
        mock_run_service: Mock,
    ) -> None:
        """Parameter overrides are forwarded to the result."""
        cmd = _make_command(parameter_overrides=("lookback=30",))

        result = handler.handle(cmd)

        assert isinstance(result, BacktestRunResult)

    def test_no_signal_expressions_skips_compile(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
        mock_factor_bridge: Mock,
        mock_run_service: Mock,
    ) -> None:
        """Strategy without signal_expressions skips factor compilation."""
        mock_catalog_service.get_spec.return_value = Mock(
            strategy_id="simple-strategy",
            spec_json={},  # No signal_expressions
        )

        cmd = _make_command(strategy_id="simple-strategy")
        result = handler.handle(cmd)

        mock_factor_bridge.compile_and_validate.assert_not_called()
        assert isinstance(result, BacktestRunResult)


class TestBacktestRunCommand:
    """Tests for BacktestRunCommand DTO."""

    def test_frozen_command(self) -> None:
        """Command is frozen."""
        cmd = _make_command()
        with pytest.raises(AttributeError):
            cmd.strategy_id = "changed"  # type: ignore[misc]

    def test_default_values(self) -> None:
        """Command has correct defaults."""
        cmd = BacktestRunCommand(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-03-31",
        )
        assert cmd.initial_cash == 1_000_000.0
        assert cmd.parameter_overrides == ()
        assert cmd.cost_config is None


class TestBacktestRunResultCostConfig:
    """Tests for BacktestRunResult.cost_config field."""

    def test_result_without_cost_config(self, handler: BacktestRunHandler) -> None:
        """无 cost_config 的命令返回 cost_config=None 的 result."""
        cmd = _make_command()
        result = handler.handle(cmd)
        assert result.cost_config is None

    def test_result_with_cost_config(self, handler: BacktestRunHandler) -> None:
        """有 cost_config 的命令透传到 result."""
        cost_cfg = CostConfig(
            commission_rate=0.0005,
            commission_min=10.0,
            stamp_duty_rate=0.002,
            slippage_bps=3.0,
            impact_model="linear",
        )
        cmd = _make_command(cost_config=cost_cfg)
        result = handler.handle(cmd)
        assert result.cost_config is not None
        assert result.cost_config.commission_rate == 0.0005
        assert result.cost_config.commission_min == 10.0
        assert result.cost_config.stamp_duty_rate == 0.002
        assert result.cost_config.slippage_bps == 3.0
        assert result.cost_config.impact_model == "linear"
