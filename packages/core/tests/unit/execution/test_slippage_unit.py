"""SlippageModel unit tests — FixedBpsSlippage + VolumeShareSlippage."""

from datetime import datetime

import pytest
from ditto_core.accounting.order_book import Order, OrderDirection
from ditto_core.execution.reality.market import MarketSnapshot
from ditto_core.execution.reality.slippage import FixedBpsSlippage, VolumeShareSlippage
from ditto_core.execution.rules import InstrumentDefinition

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _order(
    direction: OrderDirection = OrderDirection.BUY,
    quantity: int = 100,
    instrument_id: str = "ETF-001",
) -> Order:
    return Order(
        order_id="ORD-001",
        instrument_id=instrument_id,
        order_type="market",
        direction=direction,
        quantity=quantity,
        price=None,
        created_at=datetime(2026, 3, 1),
    )


def _market_snapshot(
    close: float = 10.0,
    avg_volume_20d: float | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-03-01",
        instrument_id="ETF-001",
        open=10.0,
        high=10.5,
        low=9.5,
        close=close,
        prev_close=9.8,
        volume=1_000_000,
        amount=10_000_000,
        avg_volume_20d=avg_volume_20d,
    )


_DEFINITION = InstrumentDefinition(
    instrument_id="ETF-001",
    asset_class="etf",
    exchange="XSHE",
    currency="CNY",
    tick_size=0.001,
    lot_size=100,
    multiplier=1.0,
    board_segment="main",
    lifecycle_state="normal",
)


# ---------------------------------------------------------------------------
# FixedBpsSlippage
# ---------------------------------------------------------------------------


class TestFixedBpsSlippage:
    def test_default_bps(self) -> None:
        model = FixedBpsSlippage()
        assert model.bps == pytest.approx(2.0)

    def test_buy_slippage_positive(self) -> None:
        model = FixedBpsSlippage(bps=2.0)
        slippage = model.estimate(_order(), _market_snapshot(close=10.0), _DEFINITION)
        assert slippage == pytest.approx(0.002)

    def test_sell_slippage_negative(self) -> None:
        model = FixedBpsSlippage(bps=2.0)
        slippage = model.estimate(
            _order(direction=OrderDirection.SELL),
            _market_snapshot(close=10.0),
            _DEFINITION,
        )
        assert slippage == pytest.approx(-0.002)

    def test_custom_bps(self) -> None:
        model = FixedBpsSlippage(bps=5.0)
        slippage = model.estimate(_order(), _market_snapshot(close=100.0), _DEFINITION)
        assert slippage == pytest.approx(0.05)

    def test_frozen(self) -> None:
        model = FixedBpsSlippage(bps=3.0)
        with pytest.raises(AttributeError):
            model.bps = 10.0  # type: ignore[misc]

    def test_zero_price(self) -> None:
        model = FixedBpsSlippage(bps=2.0)
        slippage = model.estimate(_order(), _market_snapshot(close=0.0), _DEFINITION)
        assert slippage == pytest.approx(0.0)

    def test_large_price(self) -> None:
        model = FixedBpsSlippage(bps=1.0)
        slippage = model.estimate(
            _order(), _market_snapshot(close=10_000.0), _DEFINITION
        )
        assert slippage == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# VolumeShareSlippage
# ---------------------------------------------------------------------------


class TestVolumeShareSlippage:
    def test_default_params(self) -> None:
        model = VolumeShareSlippage()
        assert model.base_bps == pytest.approx(2.0)
        assert model.impact_factor == pytest.approx(0.5)

    def test_small_order_near_base_bps(self) -> None:
        """小单: trade_amount=1000, avg_daily=10_000_000, share=0.0001 → bps≈2.0。"""
        model = VolumeShareSlippage(base_bps=2.0, impact_factor=0.5)
        slippage = model.estimate(
            _order(quantity=100),
            _market_snapshot(close=10.0, avg_volume_20d=1_000_000),
            _DEFINITION,
        )
        # bps = 2.0 + 0.5 * (1000/10_000_000) = 2.0 + 0.00005 ≈ 2.0
        expected = 10.0 * 2.00005 / 10_000
        assert slippage == pytest.approx(expected)

    def test_large_order_increased_slippage(self) -> None:
        """大单: trade_amount=1_000_000, avg_daily=10_000_000, share=0.1 → bps=2.05。"""
        model = VolumeShareSlippage(base_bps=2.0, impact_factor=0.5)
        slippage = model.estimate(
            _order(quantity=100_000),
            _market_snapshot(close=10.0, avg_volume_20d=1_000_000),
            _DEFINITION,
        )
        # bps = 2.0 + 0.5 * 0.1 = 2.05
        expected = 10.0 * 2.05 / 10_000
        assert slippage == pytest.approx(expected)

    def test_buy_slippage_positive(self) -> None:
        model = VolumeShareSlippage()
        slippage = model.estimate(
            _order(quantity=100),
            _market_snapshot(close=10.0, avg_volume_20d=1_000_000),
            _DEFINITION,
        )
        assert slippage > 0

    def test_sell_slippage_negative(self) -> None:
        model = VolumeShareSlippage()
        slippage = model.estimate(
            _order(direction=OrderDirection.SELL, quantity=100),
            _market_snapshot(close=10.0, avg_volume_20d=1_000_000),
            _DEFINITION,
        )
        assert slippage < 0

    def test_no_avg_volume_fallback_base_bps(self) -> None:
        """avg_volume_20d=None → fallback base_bps。"""
        model = VolumeShareSlippage(base_bps=3.0, impact_factor=0.5)
        slippage = model.estimate(
            _order(),
            _market_snapshot(close=10.0, avg_volume_20d=None),
            _DEFINITION,
        )
        expected = 10.0 * 3.0 / 10_000
        assert slippage == pytest.approx(expected)

    def test_zero_avg_volume_fallback_base_bps(self) -> None:
        """avg_volume_20d=0 → fallback base_bps。"""
        model = VolumeShareSlippage(base_bps=3.0)
        slippage = model.estimate(
            _order(),
            _market_snapshot(close=10.0, avg_volume_20d=0),
            _DEFINITION,
        )
        expected = 10.0 * 3.0 / 10_000
        assert slippage == pytest.approx(expected)

    def test_zero_close_zero_slippage(self) -> None:
        model = VolumeShareSlippage()
        slippage = model.estimate(
            _order(),
            _market_snapshot(close=0.0, avg_volume_20d=1_000_000),
            _DEFINITION,
        )
        assert slippage == pytest.approx(0.0)

    def test_frozen(self) -> None:
        model = VolumeShareSlippage(base_bps=2.0, impact_factor=0.5)
        with pytest.raises(AttributeError):
            model.base_bps = 10.0  # type: ignore[misc]
