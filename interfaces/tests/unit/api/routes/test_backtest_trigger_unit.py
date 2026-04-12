"""
Unit tests for backtest trigger endpoint logic.

Tests request → command → response mapping and error handling.
Route handler is wrapped by Dishka @inject, so we test mapping
logic directly without the DI container.
"""

from __future__ import annotations

import pytest
from ditto_app.command.backtest import BacktestRunCommand, BacktestRunResult
from ditto_interfaces.models.backtest import (
    BacktestRunTriggerResponse,
    CreateBacktestRunRequest,
)
from fastapi import HTTPException
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
    """Tests for ValueError → HTTPException(400) mapping."""

    def test_strategy_not_found(self) -> None:
        """Strategy not found → 400."""
        exc = ValueError("Strategy not found: missing")
        http_exc = HTTPException(status_code=400, detail=str(exc))
        assert http_exc.status_code == 400
        assert "Strategy not found" in http_exc.detail

    def test_invalid_dates(self) -> None:
        """Invalid dates → 400."""
        exc = ValueError("日期范围无效: start_date=2025-06-30 > end_date=2025-01-01")
        http_exc = HTTPException(status_code=400, detail=str(exc))
        assert http_exc.status_code == 400
        assert "日期范围无效" in http_exc.detail

    def test_factor_compile_failure(self) -> None:
        """Factor compile failure → 400."""
        exc = ValueError("编译失败 (signal_0): bad expr")
        http_exc = HTTPException(status_code=400, detail=str(exc))
        assert http_exc.status_code == 400
        assert "编译失败" in http_exc.detail


class TestBuildFlowParams:
    """Tests for _build_flow_params helper — result → flow 参数映射."""

    def test_basic_params_without_cost_config(self) -> None:
        """无 cost_config 时构建基本 flow 参数."""
        from ditto_app.command.backtest import BacktestRunCommand, BacktestRunResult
        from ditto_interfaces.api.routes.backtest import _build_flow_params

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
        params = _build_flow_params(command, result)

        assert params["run_id"] == "abc12345"
        assert params["strategy_id"] == "momentum-etf"
        assert params["start_date"] == "2025-01-01"
        assert params["end_date"] == "2025-03-31"
        assert params["initial_cash"] == 1_000_000.0
        assert params["parameter_overrides"] == ()
        assert "cost_config" not in params

    def test_params_with_cost_config(self) -> None:
        """有 cost_config 时包含 cost_config dict."""

        from ditto_app.command.backtest import (
            BacktestRunCommand,
            BacktestRunResult,
            CostConfig,
        )
        from ditto_interfaces.api.routes.backtest import _build_flow_params

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
        params = _build_flow_params(command, result)

        assert "cost_config" in params
        cost_dict = params["cost_config"]
        assert cost_dict["commission_rate"] == 0.0005
        assert cost_dict["commission_min"] == 10.0

    def test_params_with_parameter_overrides(self) -> None:
        """parameter_overrides 正确传递."""
        from ditto_app.command.backtest import BacktestRunCommand, BacktestRunResult
        from ditto_interfaces.api.routes.backtest import _build_flow_params

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
        params = _build_flow_params(command, result)

        assert params["parameter_overrides"] == ("key1=val1", "key2=val2")
