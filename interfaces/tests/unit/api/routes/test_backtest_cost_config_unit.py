"""
Unit tests for CostConfig API model + parameter pass-through.

Tests:
1. CostConfigRequest default values (A-share standard rates)
2. CostConfigRequest custom overrides
3. CostConfigRequest parameter validation
4. CreateBacktestRunRequest with optional cost_config
5. Body → Command cost_config mapping
"""

from __future__ import annotations

import pytest
from ditto_app.command.backtest import BacktestRunCommand, CostConfig
from ditto_interfaces.models.backtest import (
    CostConfigRequest,
    CreateBacktestRunRequest,
)
from pydantic import ValidationError


class TestCostConfigRequestDefaults:
    """Tests for CostConfigRequest default values (A-share standard rates)."""

    def test_default_commission_rate(self) -> None:
        """默认佣金费率 = 万三."""
        cfg = CostConfigRequest()
        assert cfg.commission_rate == 0.0003

    def test_default_commission_min(self) -> None:
        """默认最低佣金 = 5.0 元."""
        cfg = CostConfigRequest()
        assert cfg.commission_min == 5.0

    def test_default_stamp_duty_rate(self) -> None:
        """默认印花税税率 = 千一 (卖出)."""
        cfg = CostConfigRequest()
        assert cfg.stamp_duty_rate == 0.001

    def test_default_slippage_bps(self) -> None:
        """默认滑点 = 1.0 bps."""
        cfg = CostConfigRequest()
        assert cfg.slippage_bps == 1.0

    def test_default_impact_model(self) -> None:
        """默认冲击成本模型 = none."""
        cfg = CostConfigRequest()
        assert cfg.impact_model == "none"


class TestCostConfigRequestCustom:
    """Tests for CostConfigRequest custom overrides."""

    def test_custom_all_fields(self) -> None:
        """自定义所有字段."""
        cfg = CostConfigRequest(
            commission_rate=0.0005,
            commission_min=10.0,
            stamp_duty_rate=0.002,
            slippage_bps=3.0,
            impact_model="linear",
        )
        assert cfg.commission_rate == 0.0005
        assert cfg.commission_min == 10.0
        assert cfg.stamp_duty_rate == 0.002
        assert cfg.slippage_bps == 3.0
        assert cfg.impact_model == "linear"

    def test_partial_override_keeps_defaults(self) -> None:
        """只覆盖部分字段，其余保持默认."""
        cfg = CostConfigRequest(slippage_bps=5.0)
        assert cfg.commission_rate == 0.0003
        assert cfg.commission_min == 5.0
        assert cfg.stamp_duty_rate == 0.001
        assert cfg.slippage_bps == 5.0
        assert cfg.impact_model == "none"

    def test_extra_fields_ignored(self) -> None:
        """extra="ignore" 忽略多余字段."""
        cfg = CostConfigRequest(unknown_field="value")  # type: ignore[call-arg]
        assert cfg.commission_rate == 0.0003


class TestCostConfigRequestValidation:
    """Tests for CostConfigRequest parameter validation."""

    def test_negative_commission_rate_rejected(self) -> None:
        """负佣金费率被拒绝."""
        with pytest.raises(ValidationError):
            CostConfigRequest(commission_rate=-0.001)

    def test_negative_commission_min_rejected(self) -> None:
        """负最低佣金被拒绝."""
        with pytest.raises(ValidationError):
            CostConfigRequest(commission_min=-1.0)

    def test_negative_stamp_duty_rate_rejected(self) -> None:
        """负印花税税率被拒绝."""
        with pytest.raises(ValidationError):
            CostConfigRequest(stamp_duty_rate=-0.001)

    def test_negative_slippage_bps_rejected(self) -> None:
        """负滑点被拒绝."""
        with pytest.raises(ValidationError):
            CostConfigRequest(slippage_bps=-1.0)

    def test_zero_values_allowed(self) -> None:
        """零值合法（表示无费用/无滑点）."""
        cfg = CostConfigRequest(
            commission_rate=0.0,
            commission_min=0.0,
            stamp_duty_rate=0.0,
            slippage_bps=0.0,
        )
        assert cfg.commission_rate == 0.0
        assert cfg.commission_min == 0.0
        assert cfg.stamp_duty_rate == 0.0
        assert cfg.slippage_bps == 0.0


class TestCreateBacktestRunWithCostConfig:
    """Tests for CreateBacktestRunRequest with optional cost_config."""

    def test_request_without_cost_config(self) -> None:
        """请求不含 cost_config 时为 None."""
        body = CreateBacktestRunRequest(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
        assert body.cost_config is None

    def test_request_with_cost_config(self) -> None:
        """请求含 cost_config 时正确解析."""
        body = CreateBacktestRunRequest(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            cost_config=CostConfigRequest(slippage_bps=5.0),
        )
        assert body.cost_config is not None
        assert body.cost_config.slippage_bps == 5.0

    def test_request_with_default_cost_config(self) -> None:
        """请求含默认 cost_config."""
        body = CreateBacktestRunRequest(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            cost_config=CostConfigRequest(),
        )
        assert body.cost_config is not None
        assert body.cost_config.commission_rate == 0.0003
        assert body.cost_config.commission_min == 5.0
        assert body.cost_config.stamp_duty_rate == 0.001
        assert body.cost_config.slippage_bps == 1.0
        assert body.cost_config.impact_model == "none"


class TestCostConfigMapping:
    """Tests for cost_config request → command mapping."""

    def test_cost_config_to_command_none(self) -> None:
        """cost_config=None → command.cost_config=None."""
        body = CreateBacktestRunRequest(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
        )
        command = BacktestRunCommand(
            strategy_id=body.strategy_id,
            start_date=body.start_date,
            end_date=body.end_date,
            initial_cash=body.initial_cash,
            parameter_overrides=tuple(body.parameter_overrides),
            cost_config=None,
        )
        assert command.cost_config is None

    def test_cost_config_to_command_custom(self) -> None:
        """cost_config 自定义值正确透传到 command."""
        body = CreateBacktestRunRequest(
            strategy_id="test",
            start_date="2025-01-01",
            end_date="2025-01-31",
            cost_config=CostConfigRequest(
                commission_rate=0.0005,
                commission_min=10.0,
                stamp_duty_rate=0.002,
                slippage_bps=3.0,
                impact_model="linear",
            ),
        )
        cost_cfg = body.cost_config
        assert cost_cfg is not None
        # 模拟 route 层转换: CostConfigRequest → CostConfig
        command = BacktestRunCommand(
            strategy_id=body.strategy_id,
            start_date=body.start_date,
            end_date=body.end_date,
            initial_cash=body.initial_cash,
            parameter_overrides=tuple(body.parameter_overrides),
            cost_config=CostConfig(
                commission_rate=cost_cfg.commission_rate,
                commission_min=cost_cfg.commission_min,
                stamp_duty_rate=cost_cfg.stamp_duty_rate,
                slippage_bps=cost_cfg.slippage_bps,
                impact_model=cost_cfg.impact_model,
            ),
        )
        assert command.cost_config is not None
        assert command.cost_config.commission_rate == 0.0005
        assert command.cost_config.commission_min == 10.0
        assert command.cost_config.stamp_duty_rate == 0.002
        assert command.cost_config.slippage_bps == 3.0
        assert command.cost_config.impact_model == "linear"
