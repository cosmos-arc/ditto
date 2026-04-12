"""
OverrideFeeModel + build_fee_model 工厂单元测试.

测试用例:
1. build_fee_model(None) 返回 AShareFeeModel
2. OverrideFeeModel 使用自定义费率计算
3. 买卖方向差异 — 卖出有印花税，买入无
4. Protocol 兼容性 — OverrideFeeModel 满足 FeeModel Protocol
5. min_commission 生效 — 小额交易使用 min_commission 而非 rate*amount
"""

from __future__ import annotations

import dataclasses

import pytest
from ditto_app.command.backtest import CostConfig
from ditto_app.process.execution.fee_override import (
    OverrideFeeModel,
    build_fee_model,
)
from ditto_engine.accounting.order_book import Order
from ditto_engine.execution.reality.fee import AShareFeeModel
from ditto_engine.execution.rules import FeeSchedule
from ditto_kernel.enums import OrderSide
from ditto_kernel.identity import InstrumentId

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_INSTRUMENT_ID = InstrumentId(510300)


def _make_fee_schedule(**overrides) -> FeeSchedule:
    """构造默认 FeeSchedule（A 股标准费率）."""
    defaults = {
        "instrument_id": _INSTRUMENT_ID,
        "as_of_date": "2025-01-15",
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "stamp_duty_rate": 0.001,
        "transfer_fee_rate": 0.00001,
    }
    defaults.update(overrides)
    return FeeSchedule(**defaults)


def _make_order(
    direction: OrderSide = OrderSide.BUY,
    quantity: int = 1000,
) -> Order:
    """构造测试用 Order."""
    return Order(
        order_id="test-001",
        instrument_id=_INSTRUMENT_ID,
        order_type="market",  # type: ignore[arg-type]
        direction=direction,
        quantity=quantity,
    )


_DEFAULT_SCHEDULE = _make_fee_schedule()


# ---------------------------------------------------------------------------
# Test: build_fee_model(None) 返回 AShareFeeModel
# ---------------------------------------------------------------------------


class TestBuildFeeModelDefault:
    """build_fee_model(None) 返回 AShareFeeModel 实例."""

    def test_returns_ashare_fee_model(self) -> None:
        """无 CostConfig 时返回 AShareFeeModel."""
        model = build_fee_model(None)
        assert isinstance(model, AShareFeeModel)

    def test_ashare_fee_model_has_required_methods(self) -> None:
        """AShareFeeModel 满足 FeeModel Protocol 签名."""
        model = build_fee_model(None)
        assert callable(model.calculate)
        assert callable(model.estimate)


# ---------------------------------------------------------------------------
# Test: OverrideFeeModel 使用自定义费率计算
# ---------------------------------------------------------------------------


class TestOverrideFeeModelCustomRates:
    """OverrideFeeModel 使用 CostConfig 自定义费率."""

    def test_calculate_with_custom_commission_rate(self) -> None:
        """自定义 commission_rate 覆盖 FeeSchedule 中的值."""
        cost_config = CostConfig(
            commission_rate=0.001,  # 10x 正常费率
            commission_min=5.0,
            stamp_duty_rate=0.001,
        )
        model = build_fee_model(cost_config)
        assert isinstance(model, OverrideFeeModel)

        order = _make_order(direction=OrderSide.BUY, quantity=10000)
        # amount = 10.0 * 10000 = 100,000
        # commission = max(5.0, 100,000 * 0.001) = 100.0
        # transfer = 100,000 * 0.00001 = 1.0
        # stamp = 0 (BUY)
        # total = 101.0
        result = model.calculate(
            order,
            fill_price=10.0,
            fill_quantity=10000,
            fee_schedule=_DEFAULT_SCHEDULE,
        )
        assert result == pytest.approx(101.0)

    def test_calculate_with_custom_stamp_duty(self) -> None:
        """自定义 stamp_duty_rate 覆盖 FeeSchedule 中的值."""
        cost_config = CostConfig(
            commission_rate=0.0003,
            commission_min=5.0,
            stamp_duty_rate=0.005,  # 5x 正常印花税
        )
        model = build_fee_model(cost_config)

        order = _make_order(direction=OrderSide.SELL, quantity=10000)
        # amount = 10.0 * 10000 = 100,000
        # commission = max(5.0, 100,000 * 0.0003) = 30.0
        # stamp = 100,000 * 0.005 = 500.0
        # transfer = 100,000 * 0.00001 = 1.0
        # total = 531.0
        result = model.calculate(
            order,
            fill_price=10.0,
            fill_quantity=10000,
            fee_schedule=_DEFAULT_SCHEDULE,
        )
        assert result == pytest.approx(531.0)

    def test_estimate_uses_custom_rates(self) -> None:
        """estimate 同样使用自定义费率."""
        cost_config = CostConfig(
            commission_rate=0.0005,
            commission_min=5.0,
            stamp_duty_rate=0.001,
        )
        model = build_fee_model(cost_config)

        order = _make_order(direction=OrderSide.BUY, quantity=10000)
        # amount = 10.0 * 10000 = 100,000
        # commission = max(5.0, 100,000 * 0.0005) = 50.0
        # transfer = 100,000 * 0.00001 = 1.0
        # stamp = 0 (BUY)
        # total = 51.0
        result = model.estimate(
            order,
            estimated_price=10.0,
            fee_schedule=_DEFAULT_SCHEDULE,
        )
        assert result == pytest.approx(51.0)


# ---------------------------------------------------------------------------
# Test: 买卖方向差异
# ---------------------------------------------------------------------------


class TestBuySellDirectionDifference:
    """卖出有印花税，买入无."""

    def test_buy_no_stamp_duty(self) -> None:
        """买入方向无印花税."""
        cost_config = CostConfig(stamp_duty_rate=0.001)
        model = build_fee_model(cost_config)

        order = _make_order(direction=OrderSide.BUY, quantity=10000)
        fee = model.calculate(
            order,
            fill_price=10.0,
            fill_quantity=10000,
            fee_schedule=_DEFAULT_SCHEDULE,
        )

        # BUY: commission + transfer (no stamp)
        assert fee > 0

    def test_sell_includes_stamp_duty(self) -> None:
        """卖出方向包含印花税."""
        cost_config = CostConfig(stamp_duty_rate=0.001)
        model = build_fee_model(cost_config)

        order_buy = _make_order(direction=OrderSide.BUY, quantity=10000)
        order_sell = _make_order(direction=OrderSide.SELL, quantity=10000)

        fee_buy = model.calculate(
            order_buy,
            fill_price=10.0,
            fill_quantity=10000,
            fee_schedule=_DEFAULT_SCHEDULE,
        )
        fee_sell = model.calculate(
            order_sell,
            fill_price=10.0,
            fill_quantity=10000,
            fee_schedule=_DEFAULT_SCHEDULE,
        )

        # 卖出费用应大于买入费用（因为印花税）
        assert fee_sell > fee_buy

        # 印花税差额 = amount * stamp_duty_rate = 100,000 * 0.001 = 100.0
        diff = fee_sell - fee_buy
        assert diff == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Test: Protocol 兼容性
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """OverrideFeeModel 满足 FeeModel Protocol."""

    def test_satisfies_fee_model_protocol(self) -> None:
        """OverrideFeeModel 满足 FeeModel Protocol 签名（calculate + estimate）."""
        cost_config = CostConfig()
        model = build_fee_model(cost_config)
        # structural subtyping: 方法签名匹配 FeeModel Protocol
        assert callable(model.calculate)
        assert callable(model.estimate)

    def test_frozen_dataclass(self) -> None:
        """OverrideFeeModel 是 frozen dataclass."""
        cost_config = CostConfig()
        model = build_fee_model(cost_config)
        assert dataclasses.is_dataclass(model)
        with pytest.raises(AttributeError):
            model._commission_rate = 0.1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: min_commission 生效
# ---------------------------------------------------------------------------


class TestMinCommissionEffect:
    """小额交易使用 min_commission 而非 rate*amount."""

    def test_small_trade_uses_min_commission(self) -> None:
        """小额交易的佣金 = max(min_commission, amount * rate)."""
        cost_config = CostConfig(
            commission_rate=0.0003,
            commission_min=5.0,
            stamp_duty_rate=0.001,
        )
        model = build_fee_model(cost_config)

        # 小额交易: 100 股 * 10.0 = 1,000 元
        # commission = max(5.0, 1000 * 0.0003) = max(5.0, 0.3) = 5.0
        # transfer = 1000 * 0.00001 = 0.01
        # stamp = 0 (BUY)
        # total = 5.01
        order = _make_order(direction=OrderSide.BUY, quantity=100)
        result = model.calculate(
            order,
            fill_price=10.0,
            fill_quantity=100,
            fee_schedule=_DEFAULT_SCHEDULE,
        )
        assert result == pytest.approx(5.01)

    def test_custom_min_commission_overrides(self) -> None:
        """自定义 min_commission 覆盖 FeeSchedule 中的值."""
        cost_config = CostConfig(
            commission_rate=0.0003,
            commission_min=20.0,  # 更高的最低佣金
            stamp_duty_rate=0.001,
        )
        model = build_fee_model(cost_config)

        # 小额交易: 100 股 * 10.0 = 1,000 元
        # commission = max(20.0, 1000 * 0.0003) = max(20.0, 0.3) = 20.0
        # transfer = 1000 * 0.00001 = 0.01
        # stamp = 0 (BUY)
        # total = 20.01
        order = _make_order(direction=OrderSide.BUY, quantity=100)
        result = model.calculate(
            order,
            fill_price=10.0,
            fill_quantity=100,
            fee_schedule=_DEFAULT_SCHEDULE,
        )
        assert result == pytest.approx(20.01)
