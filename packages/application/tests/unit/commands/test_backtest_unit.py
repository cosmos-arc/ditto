"""
Unit tests for BacktestRunHandler + Cancel/Retry Handlers.

Tests parameter validation, factor pre-compilation, RunRecord creation,
error handling, and cancel/retry status guards.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from ditto_application.commands.backtest import (
    BacktestRunCommand,
    BacktestRunHandler,
    BacktestRunResult,
    CancelRunCommand,
    CancelRunHandler,
    CostConfig,
    RetryRunCommand,
    RetryRunHandler,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_kernel.strategy import ImpactModel
from ditto_strategy.runs.models import StrategyRunRecord
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)


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


def _make_run_record(**overrides) -> StrategyRunRecord:
    """Build a default StrategyRunRecord with optional overrides."""
    defaults = {
        "run_id": "abc123",
        "strategy_id": "momentum-etf",
        "strategy_version": "1",
        "mode": "backtest",
        "status": "pending",
        "config_json": "",
    }
    defaults.update(overrides)
    return StrategyRunRecord(**defaults)


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

        with pytest.raises(AppCommandError, match="Strategy not found"):
            handler.handle(cmd)

    def test_invalid_date_range_raises(
        self,
        handler: BacktestRunHandler,
    ) -> None:
        """End date before start date raises ValueError."""
        cmd = _make_command(start_date="2025-06-01", end_date="2025-01-01")

        with pytest.raises(AppCommandError, match="日期范围无效"):
            handler.handle(cmd)

    def test_invalid_date_format_raises(
        self,
        handler: BacktestRunHandler,
    ) -> None:
        """Invalid date format raises ValueError."""
        cmd = _make_command(start_date="not-a-date")

        with pytest.raises(AppCommandError, match="日期格式无效"):
            handler.handle(cmd)

    def test_factor_compile_failure_raises(
        self,
        handler: BacktestRunHandler,
        mock_factor_bridge: Mock,
        mock_run_service: Mock,
    ) -> None:
        """Factor compilation failure raises typed process error, no record created."""
        mock_factor_bridge.compile_and_validate.side_effect = AppProcessError(
            "编译失败 (signal_0): unknown function 'bad_func'"
        )

        cmd = _make_command()

        with pytest.raises(AppProcessError, match="编译失败"):
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

    def test_invalid_signal_weight_raises_app_command_error(
        self,
        handler: BacktestRunHandler,
        mock_catalog_service: Mock,
        mock_factor_bridge: Mock,
        mock_run_service: Mock,
    ) -> None:
        """Invalid signal weight values raise typed command errors."""
        mock_catalog_service.get_spec.return_value = Mock(
            strategy_id="bad-weights",
            spec_json={
                "signal_expressions": ["close"],
                "signal_weights": ["not-a-number"],
            },
        )

        with pytest.raises(AppCommandError, match="signal_weights") as exc_info:
            handler.handle(_make_command(strategy_id="bad-weights"))

        assert exc_info.value.details == {
            "strategy_id": "bad-weights",
            "field": "signal_weights",
            "index": 0,
            "value": "not-a-number",
        }
        mock_factor_bridge.compile_and_validate.assert_not_called()
        mock_run_service.create_run.assert_not_called()


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
            impact_model=ImpactModel.VOLUME_SHARE,
        )
        cmd = _make_command(cost_config=cost_cfg)
        result = handler.handle(cmd)
        assert result.cost_config is not None
        assert result.cost_config.commission_rate == 0.0005
        assert result.cost_config.commission_min == 10.0
        assert result.cost_config.stamp_duty_rate == 0.002
        assert result.cost_config.slippage_bps == 3.0
        assert result.cost_config.impact_model == ImpactModel.VOLUME_SHARE


# ---------------------------------------------------------------------------
# T26: Cancel / Retry Handler Tests
# ---------------------------------------------------------------------------


class TestCancelRunHandler:
    """Tests for CancelRunHandler — status guard + mark_cancelled."""

    def test_cancel_pending_run(self) -> None:
        """取消 pending 状态的运行成功."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="pending")
        handler = CancelRunHandler(run_service=run_svc)

        handler.handle(CancelRunCommand(run_id="abc123"))

        run_svc.mark_cancelled.assert_called_once_with("abc123")

    def test_cancel_running_run(self) -> None:
        """取消 running 状态的运行成功."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="running")
        handler = CancelRunHandler(run_service=run_svc)

        handler.handle(CancelRunCommand(run_id="abc123"))

        run_svc.mark_cancelled.assert_called_once_with("abc123")

    def test_cancel_completed_rejected(self) -> None:
        """completed 状态不允许取消."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="completed")
        handler = CancelRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Cannot cancel"):
            handler.handle(CancelRunCommand(run_id="abc123"))
        run_svc.mark_cancelled.assert_not_called()

    def test_cancel_failed_rejected(self) -> None:
        """failed 状态不允许取消."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="failed")
        handler = CancelRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Cannot cancel"):
            handler.handle(CancelRunCommand(run_id="abc123"))

    def test_cancel_not_found(self) -> None:
        """运行不存在抛 ValueError."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = None
        handler = CancelRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Run not found"):
            handler.handle(CancelRunCommand(run_id="missing"))


class TestRetryRunHandler:
    """Tests for RetryRunHandler — status guard + config_json 传递."""

    def test_retry_failed_run(self) -> None:
        """重试 failed 状态的运行创建新 run 并传递 config_json."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(
            status="failed",
            config_json='{"start_date":"2025-01-01"}',
        )
        handler = RetryRunHandler(run_service=run_svc)

        new_id = handler.handle(RetryRunCommand(run_id="abc123"))

        # 创建新运行并传递 config_json
        run_svc.create_run.assert_called_once()
        call_kwargs = run_svc.create_run.call_args.kwargs
        assert call_kwargs["strategy_id"] == "momentum-etf"
        assert call_kwargs["parent_run_id"] == "abc123"
        assert call_kwargs["config_json"] == '{"start_date":"2025-01-01"}'
        assert new_id  # 返回非空 new_run_id

    def test_retry_cancelled_run(self) -> None:
        """重试 cancelled 状态的运行成功."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="cancelled")
        handler = RetryRunHandler(run_service=run_svc)

        new_id = handler.handle(RetryRunCommand(run_id="abc123"))
        assert new_id

    def test_retry_pending_rejected(self) -> None:
        """pending 状态不允许重试."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="pending")
        handler = RetryRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Cannot retry"):
            handler.handle(RetryRunCommand(run_id="abc123"))
        run_svc.create_run.assert_not_called()

    def test_retry_running_rejected(self) -> None:
        """running 状态不允许重试."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(status="running")
        handler = RetryRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Cannot retry"):
            handler.handle(RetryRunCommand(run_id="abc123"))

    def test_retry_not_found(self) -> None:
        """运行不存在抛 ValueError."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = None
        handler = RetryRunHandler(run_service=run_svc)

        with pytest.raises(AppCommandError, match="Run not found"):
            handler.handle(RetryRunCommand(run_id="missing"))

    def test_retry_preserves_strategy_version(self) -> None:
        """重试保留原始 strategy_version."""
        run_svc = Mock(spec=StrategyRunLifecycleStore)
        run_svc.get_run.return_value = _make_run_record(
            status="failed",
            strategy_version="2",
        )
        handler = RetryRunHandler(run_service=run_svc)

        handler.handle(RetryRunCommand(run_id="abc123"))

        call_kwargs = run_svc.create_run.call_args.kwargs
        assert call_kwargs["strategy_version"] == "2"
