"""
Unit tests for backtest trigger endpoint logic.

Tests request → command → response mapping and error handling.
Route handler is wrapped by Dishka @inject, so we test mapping
logic directly without the DI container.
"""

from __future__ import annotations

import pytest
from ditto_application.commands.backtest import BacktestRunCommand, BacktestRunResult
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_apps.api.errors import BadRequestError
from ditto_apps.models.backtest import (
    BacktestRunTriggerResponse,
    CreateBacktestRunRequest,
)
from pydantic import ValidationError


class TestCreateBacktestRunRequest:
    """Tests for request model validation."""

    def test_default_values(self) -> None:
        """默认 initial_cash=1M, parameter_overrides=[]."""
        body = CreateBacktestRunRequest(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
        assert body.initial_cash == 1_000_000.0
        assert body.parameter_overrides == []

    def test_custom_values(self) -> None:
        """自定义 initial_cash 和 parameter_overrides."""
        body = CreateBacktestRunRequest(
            strategy_id="my-strategy",
            start_date="2025-01-01",
            end_date="2025-06-30",
            initial_cash=500_000.0,
            parameter_overrides=["key1=val1", "key2=val2"],
        )
        assert body.initial_cash == 500_000.0
        assert body.parameter_overrides == ["key1=val1", "key2=val2"]

    def test_empty_strategy_id_rejected(self) -> None:
        """空 strategy_id 被拒绝."""
        with pytest.raises(ValidationError):
            CreateBacktestRunRequest(
                strategy_id="",
                start_date="2025-01-01",
                end_date="2025-01-31",
            )

    def test_zero_initial_cash_rejected(self) -> None:
        """initial_cash=0 被拒绝."""
        with pytest.raises(ValidationError):
            CreateBacktestRunRequest(
                strategy_id="test",
                start_date="2025-01-01",
                end_date="2025-01-31",
                initial_cash=0.0,
            )


class TestBodyToCommandMapping:
    """Tests for request body → BacktestRunCommand mapping."""

    def test_basic_mapping(self) -> None:
        """基本字段映射."""
        body = CreateBacktestRunRequest(
            strategy_id="momentum-etf",
            start_date="2025-01-01",
            end_date="2025-03-31",
        )
        command = BacktestRunCommand(
            strategy_id=body.strategy_id,
            start_date=body.start_date,
            end_date=body.end_date,
            initial_cash=body.initial_cash,
            parameter_overrides=tuple(body.parameter_overrides),
        )
        assert command.strategy_id == "momentum-etf"
        assert command.start_date == "2025-01-01"
        assert command.end_date == "2025-03-31"
        assert command.initial_cash == 1_000_000.0
        assert command.parameter_overrides == ()

    def test_list_to_tuple_overrides(self) -> None:
        """parameter_overrides list → tuple 转换."""
        body = CreateBacktestRunRequest(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            parameter_overrides=["a=1", "b=2"],
        )
        command = BacktestRunCommand(
            strategy_id=body.strategy_id,
            start_date=body.start_date,
            end_date=body.end_date,
            initial_cash=body.initial_cash,
            parameter_overrides=tuple(body.parameter_overrides),
        )
        assert command.parameter_overrides == ("a=1", "b=2")


class TestResultToResponseMapping:
    """Tests for BacktestRunResult → BacktestRunTriggerResponse mapping."""

    def test_basic_mapping(self) -> None:
        """基本字段映射."""
        result = BacktestRunResult(
            run_id="abc12345",
            strategy_id="momentum-etf",
            status="pending",
        )
        response = BacktestRunTriggerResponse(
            run_id=result.run_id,
            strategy_id=result.strategy_id,
            status=result.status,
        )
        assert response.run_id == "abc12345"
        assert response.strategy_id == "momentum-etf"
        assert response.status == "pending"


class TestErrorHandlerMapping:
    """Tests for ValueError → BadRequestError(400) mapping."""

    def test_strategy_not_found(self) -> None:
        """Strategy not found → 400."""
        exc = AppCommandError("Strategy not found: missing")
        api_exc = BadRequestError(str(exc))
        assert api_exc.status_code == 400
        assert "Strategy not found" in api_exc.message

    def test_invalid_dates(self) -> None:
        """Invalid dates → 400."""
        exc = AppCommandError(
            "日期范围无效: start_date=2025-06-30 > end_date=2025-01-01"
        )
        api_exc = BadRequestError(str(exc))
        assert api_exc.status_code == 400
        assert "日期范围无效" in api_exc.message

    def test_factor_compile_failure(self) -> None:
        """Factor compile failure → 400."""
        exc = AppProcessError("编译失败 (signal_0): bad expr")
        api_exc = BadRequestError(str(exc))
        assert api_exc.status_code == 400
        assert "编译失败" in api_exc.message


class TestBuildFlowParams:
    """Tests for build_flow_params helper — result → flow 参数映射."""

    def test_basic_params_without_cost_config(self) -> None:
        """无 cost_config 时构建基本 flow 参数."""
        from ditto_application.commands.backtest import (
            BacktestRunCommand,
            BacktestRunResult,
        )
        from ditto_apps.api.routes.backtest import build_flow_params

        command = BacktestRunCommand(
            strategy_id="momentum-etf",
            start_date="2025-01-01",
            end_date="2025-03-31",
        )
        result = BacktestRunResult(
            run_id="abc12345",
            strategy_id="momentum-etf",
            status="pending",
        )
        params = build_flow_params(command, result)

        assert params["run_id"] == "abc12345"
        assert params["strategy_id"] == "momentum-etf"
        assert params["start_date"] == "2025-01-01"
        assert params["end_date"] == "2025-03-31"
        assert params["initial_cash"] == 1_000_000.0
        assert params["parameter_overrides"] == ()
        assert "cost_config" not in params

    def test_params_with_cost_config(self) -> None:
        """有 cost_config 时包含 cost_config dict."""

        from ditto_application.commands.backtest import (
            BacktestRunCommand,
            BacktestRunResult,
            CostConfig,
        )
        from ditto_apps.api.routes.backtest import build_flow_params

        cost_cfg = CostConfig(commission_rate=0.0005, commission_min=10.0)
        command = BacktestRunCommand(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            cost_config=cost_cfg,
        )
        result = BacktestRunResult(
            run_id="run-cost",
            strategy_id="test",
            status="pending",
            cost_config=cost_cfg,
        )
        params = build_flow_params(command, result)

        assert "cost_config" in params
        cost_dict = params["cost_config"]
        assert isinstance(cost_dict, dict)
        assert cost_dict["commission_rate"] == 0.0005
        assert cost_dict["commission_min"] == 10.0

    def test_params_with_parameter_overrides(self) -> None:
        """parameter_overrides 正确传递."""
        from ditto_application.commands.backtest import (
            BacktestRunCommand,
            BacktestRunResult,
        )
        from ditto_apps.api.routes.backtest import build_flow_params

        command = BacktestRunCommand(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            parameter_overrides=("key1=val1", "key2=val2"),
        )
        result = BacktestRunResult(
            run_id="run-ovr",
            strategy_id="test",
            status="pending",
        )
        params = build_flow_params(command, result)

        assert params["parameter_overrides"] == ("key1=val1", "key2=val2")


class TestRaiseBusinessErrorBacktest:
    """Tests for raise_business_error — backtest 路由使用 default_conflict=True."""

    def test_not_found_raises_404(self) -> None:
        """'not found' 错误映射为 404."""
        from ditto_apps.api.errors import NotFoundError, raise_business_error

        exc = AppCommandError("Run not found: missing")
        with pytest.raises(NotFoundError) as exc_info:
            raise_business_error(exc, default_conflict=True)
        assert exc_info.value.status_code == 404

    def test_generic_error_raises_409(self) -> None:
        """非 not found 错误默认映射为 409（backtest 特有行为）。"""
        from ditto_apps.api.errors import ConflictError, raise_business_error

        exc = AppCommandError("Some other error")
        with pytest.raises(ConflictError) as exc_info:
            raise_business_error(exc, default_conflict=True)
        assert exc_info.value.status_code == 409

    def test_case_insensitive_matching(self) -> None:
        """大小写不敏感匹配 'Not Found'."""
        from ditto_apps.api.errors import NotFoundError, raise_business_error

        exc = AppCommandError("Run Not Found: xyz")
        with pytest.raises(NotFoundError) as exc_info:
            raise_business_error(exc, default_conflict=True)
        assert exc_info.value.status_code == 404


class TestRunBacktestFlow:
    """Tests for run_backtest_flow_sync bypasses Prefect engine."""

    def test_calls_flow_fn_not_flow_object(self) -> None:
        """run_backtest_flow_sync 通过 .fn 调用 raw function，避免 Prefect engine."""
        from unittest.mock import MagicMock, patch

        from ditto_apps.api.routes.backtest import run_backtest_flow_sync

        mock_fn = MagicMock(return_value=None)
        mock_flow = MagicMock()
        mock_flow.fn = mock_fn
        # 不设置 .func — Prefect 3.x 没有 .func 属性

        params: dict[str, object] = {
            "run_id": "test-run",
            "strategy_id": "strat-1",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        }

        with patch(
            "ditto_apps.api.routes.backtest_run_routes.run_backtest_flow",
            mock_flow,
        ):
            run_backtest_flow_sync(params)

        # 应调用 .fn 而非直接调用 flow 对象
        mock_fn.assert_called_once_with(**params)
        # flow 对象本身不应被直接调用
        mock_flow.assert_not_called()

    def test_on_failure_receives_exception_message(self) -> None:
        """on_failure 回调应收到包含实际异常信息的字符串，而非泛化消息."""
        from unittest.mock import MagicMock, patch

        from ditto_apps.api.routes.backtest import run_backtest_flow_sync

        original_error = RuntimeError("strategy compilation failed: bad alpha expr")
        mock_fn = MagicMock(side_effect=original_error)
        mock_flow = MagicMock()
        mock_flow.fn = mock_fn

        params: dict[str, object] = {
            "run_id": "fail-run",
            "strategy_id": "strat-1",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        }

        failure_callback = MagicMock()
        with patch(
            "ditto_apps.api.routes.backtest_run_routes.run_backtest_flow",
            mock_flow,
        ):
            run_backtest_flow_sync(params, on_failure=failure_callback)

        # on_failure 应被调用，且消息包含实际异常文本
        failure_callback.assert_called_once()
        call_args = failure_callback.call_args
        assert call_args[0][0] == "fail-run"
        error_msg = call_args[0][1]
        # 必须包含原始异常文本，而非仅有 "Flow execution failed"
        assert "strategy compilation failed: bad alpha expr" in error_msg
