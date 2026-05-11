"""Unit tests for market_precheck — 涨跌停 / 停牌判断."""

from ditto_execution._planner_types import BlockedOrder, BlockSeverity
from ditto_execution.market_precheck import pre_check
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import MarketSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IID = InstrumentId(1)


def _snap(
    *,
    close: float = 10.0,
    is_suspended: bool = False,
    limit_up: float | None = None,
    limit_down: float | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-01-01",
        instrument_id=_IID,
        open=close - 0.1,
        high=close + 0.1,
        low=close - 0.2,
        close=close,
        prev_close=close - 0.05,
        volume=1000000.0,
        amount=10000000.0,
        is_suspended=is_suspended,
        limit_up=limit_up,
        limit_down=limit_down,
    )


# ---------------------------------------------------------------------------
# pre_check
# ---------------------------------------------------------------------------


class TestPreCheck:
    """Tests for pre_check — 停牌、涨停、跌停判断."""

    def test_no_snapshot_returns_none(self) -> None:
        """market 中无快照 → None（不阻止）。"""
        market: dict[InstrumentId, MarketSnapshot] = {}
        assert pre_check(_IID, diff_qty=100, market=market) is None

    def test_suspended_buy(self) -> None:
        """停牌 + 买入方向 → BLOCK。"""
        market = {_IID: _snap(is_suspended=True)}
        result = pre_check(_IID, diff_qty=100, market=market)
        assert isinstance(result, BlockedOrder)
        assert result.reason == "suspended"
        assert result.severity == BlockSeverity.BLOCK
        assert result.direction.value == "buy"
        assert result.intended_quantity == 100

    def test_suspended_sell(self) -> None:
        """停牌 + 卖出方向 → BLOCK。"""
        market = {_IID: _snap(is_suspended=True)}
        result = pre_check(_IID, diff_qty=-200, market=market)
        assert isinstance(result, BlockedOrder)
        assert result.reason == "suspended"
        assert result.severity == BlockSeverity.BLOCK
        assert result.direction.value == "sell"
        assert result.intended_quantity == 200

    def test_limit_up_blocks_buy(self) -> None:
        """涨停价 >= close → 阻止买入 (DEFER)。"""
        market = {_IID: _snap(close=11.0, limit_up=11.0)}
        result = pre_check(_IID, diff_qty=100, market=market)
        assert isinstance(result, BlockedOrder)
        assert result.reason == "limit_up_no_buy"
        assert result.severity == BlockSeverity.DEFER
        assert result.direction.value == "buy"

    def test_limit_up_above_close_allows_buy(self) -> None:
        """涨停价高于 close → 允许买入。"""
        market = {_IID: _snap(close=10.5, limit_up=11.0)}
        result = pre_check(_IID, diff_qty=100, market=market)
        assert result is None

    def test_no_limit_up_allows_buy(self) -> None:
        """limit_up=None → 允许买入。"""
        market = {_IID: _snap(close=10.0, limit_up=None)}
        result = pre_check(_IID, diff_qty=100, market=market)
        assert result is None

    def test_limit_down_blocks_sell(self) -> None:
        """跌停价 <= close → 阻止卖出 (DEFER)。"""
        market = {_IID: _snap(close=9.0, limit_down=9.0)}
        result = pre_check(_IID, diff_qty=-100, market=market)
        assert isinstance(result, BlockedOrder)
        assert result.reason == "limit_down_no_sell"
        assert result.severity == BlockSeverity.DEFER
        assert result.direction.value == "sell"

    def test_limit_down_below_close_allows_sell(self) -> None:
        """跌停价低于 close → 允许卖出。"""
        market = {_IID: _snap(close=9.5, limit_down=9.0)}
        result = pre_check(_IID, diff_qty=-100, market=market)
        assert result is None

    def test_no_limit_down_allows_sell(self) -> None:
        """limit_down=None → 允许卖出。"""
        market = {_IID: _snap(close=10.0, limit_down=None)}
        result = pre_check(_IID, diff_qty=-100, market=market)
        assert result is None

    def test_normal_market_allows_all(self) -> None:
        """正常市场条件 → 买入和卖出都允许。"""
        market = {_IID: _snap(close=10.0, limit_up=11.0, limit_down=9.0)}
        assert pre_check(_IID, diff_qty=100, market=market) is None
        assert pre_check(_IID, diff_qty=-100, market=market) is None

    def test_zero_diff_qty_no_limit(self) -> None:
        """diff_qty=0 → 不触发涨跌停（不是买入也不是卖出）。"""
        market = {_IID: _snap(close=11.0, limit_up=11.0)}
        # diff_qty=0 → diff_qty > 0 is False, diff_qty < 0 is False
        result = pre_check(_IID, diff_qty=0, market=market)
        assert result is None
