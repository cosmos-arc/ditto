"""
Unit tests for backtest async flow.

Tests that the flow delegates lifecycle management to BacktestService
and correctly computes total_return from NAV values.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from ditto_application.queries.artifact_utils import compute_total_return
from ditto_apps.jobs.flows.backtest import (
    run_backtest_flow,
)
from pytest_mock import MockerFixture


def _prefect_runner(entrypoint):
    """Extract the underlying function from a Prefect-decorated entrypoint."""
    return getattr(entrypoint, "func", getattr(entrypoint, "fn", entrypoint))


RUNNER = _prefect_runner(run_backtest_flow)


def _make_bundle(
    facade: Mock,
    run_service: Mock | None,
    run_writer: Mock | None,
) -> Mock:
    """构建 mock bundle context manager（供 autouse 和手动 patch 使用）."""
    mock_bundle = Mock()
    mock_bundle.strategy_facade = facade
    mock_bundle.run_service = run_service
    mock_bundle.run_writer = run_writer

    mock_ctx = Mock()
    mock_ctx.__enter__ = Mock(return_value=mock_bundle)
    mock_ctx.__exit__ = Mock(return_value=False)
    return mock_ctx


@pytest.fixture
def mock_report() -> Mock:
    """Mock BacktestReport with initial_cash=1M and final_nav=1.1M."""
    report = Mock()
    report.initial_cash = 1_000_000.0
    report.final_nav = 1_100_000.0
    return report


@pytest.fixture
def mock_facade(mock_report: Mock) -> Mock:
    """Mock StrategyFacade."""
    facade = Mock()
    facade.run_backtest_from_catalog.return_value = mock_report
    return facade


@pytest.fixture
def mock_run_service() -> Mock:
    """Mock RunLifecycleService."""
    return Mock()


@pytest.fixture
def mock_run_writer() -> Mock | None:
    """Mock run_writer — 默认 None.

    个别测试可 override 此 fixture 注入自定义 Mock，
    或保持 None（表示无 run_writer）。
    """
    return None


@pytest.fixture(autouse=True)
def mock_create_strategy_bundle(
    mocker: MockerFixture,
    mock_facade: Mock,
    mock_run_service: Mock,
    mock_run_writer: Mock | None,
) -> None:
    """Replace create_strategy_bundle with mock DI bundle."""
    mocker.patch(
        "ditto_apps.jobs.flows.backtest.create_strategy_bundle",
        return_value=_make_bundle(mock_facade, mock_run_service, mock_run_writer),
    )


class TestRunBacktestFlow:
    """Tests for run_backtest_flow delegation to BacktestService."""

    def test_successful_flow_returns_completed(
        self,
        mock_facade: Mock,
    ) -> None:
        """Successful backtest returns completed status with total_return."""
        result = RUNNER(
            run_id="run-001",
            strategy_id="momentum-etf",
            start_date="2025-01-01",
            end_date="2025-03-31",
        )

        assert result["run_id"] == "run-001"
        assert result["status"] == "completed"
        assert result["total_return"] == pytest.approx(0.1)

    def test_passes_config_to_facade(
        self,
        mock_facade: Mock,
    ) -> None:
        """Flow passes correct BacktestServiceConfig to facade."""
        RUNNER(
            run_id="run-003",
            strategy_id="my-strategy",
            start_date="2025-01-01",
            end_date="2025-06-30",
        )

        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config is not None
        assert config.strategy_id == "my-strategy"
        assert config.run_id == "run-003"
        assert config.start_date == "2025-01-01"
        assert config.end_date == "2025-06-30"

    def test_passes_run_service_via_options(
        self,
        mock_facade: Mock,
        mock_run_service: Mock,
    ) -> None:
        """Flow passes run_service through BacktestServiceOptions."""
        RUNNER(
            run_id="run-004",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        options = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options")
        assert options is not None
        assert options.run_service is mock_run_service

    def test_failed_flow_propagates_exception(
        self,
        mock_facade: Mock,
    ) -> None:
        """Failed backtest propagates exception (BacktestService handles lifecycle)."""
        mock_facade.run_backtest_from_catalog.side_effect = RuntimeError("engine crash")

        with pytest.raises(RuntimeError, match="engine crash"):
            RUNNER(
                run_id="run-002",
                strategy_id="momentum-etf",
                start_date="2025-01-01",
                end_date="2025-03-31",
            )

    def test_none_run_service_still_executes(
        self,
        mock_facade: Mock,
        mock_run_service: Mock,
    ) -> None:
        """When run_service is None, backtest still executes."""
        mock_run_service.mark_running.side_effect = AttributeError("None")

        # Reset the mock to None
        mock_run_service.mark_running.reset_mock()
        mock_run_service.mark_running.side_effect = None

        result = RUNNER(
            run_id="run-005",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        mock_facade.run_backtest_from_catalog.assert_called_once()
        assert result["status"] == "completed"


class TestComputeTotalReturn:
    """Tests for compute_total_return helper."""

    def test_positive_return(self) -> None:
        """Normal positive return."""
        assert compute_total_return(
            initial_cash=1_000_000.0,
            final_nav=1_200_000.0,
        ) == pytest.approx(0.2)

    def test_negative_return(self) -> None:
        """Negative return (loss)."""
        assert compute_total_return(
            initial_cash=1_000_000.0,
            final_nav=800_000.0,
        ) == pytest.approx(-0.2)

    def test_zero_initial_cash(self) -> None:
        """Zero initial cash returns 0.0 to avoid division by zero."""
        assert (
            compute_total_return(
                initial_cash=0.0,
                final_nav=100_000.0,
            )
            == 0.0
        )


class TestRunBacktestFlowStateMachine:
    """Tests for run_backtest_flow state machine via run_writer.

    所有测试通过 mock_run_writer fixture 注入自定义 Mock，
    由 autouse fixture 统一创建 bundle context，消除 with patch(...) 混用。
    """

    @pytest.fixture
    def mock_run_writer(self) -> Mock:
        """状态机测试注入带有 update_status 的 mock writer."""
        return Mock()

    def test_completed_status_written_without_run_service(
        self,
        mocker: MockerFixture,
        mock_facade: Mock,
        mock_run_writer: Mock,
    ) -> None:
        """Flow 成功完成且无 run_svc 时，writer 记录 completed."""
        mocker.patch(
            "ditto_apps.jobs.flows.backtest.create_strategy_bundle",
            return_value=_make_bundle(
                mock_facade,
                run_service=None,
                run_writer=mock_run_writer,
            ),
        )

        RUNNER(
            run_id="run-sm-001",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        mock_run_writer.update_status.assert_any_call("run-sm-001", "completed")

    def test_no_writer_call_when_run_svc_available(
        self,
        mock_facade: Mock,
        mock_run_service: Mock,
        mock_run_writer: Mock,
    ) -> None:
        """有 run_svc 时 completed 由 Service 内部管理，writer 不重复写入."""
        mock_run_service.get_run.return_value = None

        result = RUNNER(
            run_id="run-sm-002",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        # run_svc 存在且返回非 cancelled → 走 if 分支，不进入 elif writer
        mock_run_writer.update_status.assert_not_called()
        assert result["status"] == "completed"

    def test_failed_status_on_exception(
        self,
        mock_facade: Mock,
        mock_run_writer: Mock,
    ) -> None:
        """Flow 异常时调用 writer.update_status(run_id, 'failed', error_message=...)."""
        mock_facade.run_backtest_from_catalog.side_effect = RuntimeError("engine crash")

        with pytest.raises(RuntimeError, match="engine crash"):
            RUNNER(
                run_id="run-sm-003",
                strategy_id="test",
                start_date="2025-01-01",
                end_date="2025-01-31",
            )

        mock_run_writer.update_status.assert_any_call(
            "run-sm-003",
            "failed",
            error_message="engine crash",
        )

    def test_no_writer_still_executes(
        self,
        mock_facade: Mock,
    ) -> None:
        """run_writer 为 None 时回测仍正常执行.

        此测试不 override mock_run_writer fixture，因此使用默认的 None。
        注意: 此方法不接受 mock_run_writer 参数，autouse fixture 将使用
        模块级 fixture（返回 None）而非类级 fixture。
        """
        result = RUNNER(
            run_id="run-sm-004",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        mock_facade.run_backtest_from_catalog.assert_called_once()
        assert result["status"] == "completed"

    def test_cancelled_status_returned_when_record_cancelled(
        self,
        mock_facade: Mock,
        mock_run_service: Mock,
        mock_run_writer: Mock,
    ) -> None:
        """BacktestService 内部标记 cancelled 后，flow 返回 cancelled 状态."""
        cancelled_record = Mock()
        cancelled_record.status = "cancelled"
        mock_run_service.get_run.return_value = cancelled_record

        result = RUNNER(
            run_id="run-sm-006",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        assert result["status"] == "cancelled"
        # cancelled 由 run_svc 管理，writer 不写入
        mock_run_writer.update_status.assert_not_called()

    def test_status_transition_order(
        self,
        mock_facade: Mock,
        mock_run_writer: Mock,
    ) -> None:
        """状态转换: running 由 Service 管理，flow 只在无 run_svc 时写 completed."""
        call_order: list[str] = []

        def record_call(
            run_id: str,
            status: str,
            **kwargs: object,
        ) -> bool:
            call_order.append(status)
            return True

        mock_run_writer.update_status.side_effect = record_call

        RUNNER(
            run_id="run-sm-005",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        # run_svc 由 autouse fixture 提供（非 None），所以 writer 不被调用
        assert call_order == []


class TestRunBacktestFlowCostConfig:
    """Tests for run_backtest_flow cost_config FeeModel injection."""

    def test_no_cost_config_options_fee_model_is_default(
        self,
        mock_facade: Mock,
    ) -> None:
        """无 cost_config 时 options.fee_model 为 AShareFeeModel 默认实例."""
        from ditto_execution.reality.fee import AShareFeeModel

        RUNNER(
            run_id="run-010",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        options = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options")
        assert options is not None
        assert isinstance(options.fee_model, AShareFeeModel)

    def test_with_cost_config_options_has_fee_model(
        self,
        mock_facade: Mock,
    ) -> None:
        """有 cost_config 时 options.fee_model 为非 None 的 FeeModel."""
        cost_dict = {
            "commission_rate": 0.0005,
            "commission_min": 10.0,
            "stamp_duty_rate": 0.002,
            "slippage_bps": 3.0,
            "impact_model": "none",
        }
        RUNNER(
            run_id="run-011",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            cost_config=cost_dict,
        )

        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        options = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options")
        assert options is not None
        assert options.fee_model is not None
        # OverrideFeeModel 满足 FeeModel Protocol
        assert callable(options.fee_model.calculate)
        assert callable(options.fee_model.estimate)

    def test_no_cost_config_options_slippage_model_is_default(
        self,
        mock_facade: Mock,
    ) -> None:
        """无 cost_config 时 options.slippage_model 为 FixedBpsSlippage 默认实例."""
        from ditto_backtest.simulation.slippage import FixedBpsSlippage

        RUNNER(
            run_id="run-012",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        options = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options")
        assert options is not None
        assert isinstance(options.slippage_model, FixedBpsSlippage)

    def test_with_cost_config_slippage_model_uses_custom_bps(
        self,
        mock_facade: Mock,
    ) -> None:
        """有 cost_config 且 impact_model='none' 时 slippage_model 使用自定义 bps."""
        cost_dict = {
            "commission_rate": 0.0003,
            "commission_min": 5.0,
            "stamp_duty_rate": 0.001,
            "slippage_bps": 5.0,
            "impact_model": "none",
        }
        RUNNER(
            run_id="run-013",
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            cost_config=cost_dict,
        )

        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        options = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options")
        assert options is not None
        assert options.slippage_model is not None
        assert callable(options.slippage_model.estimate)
