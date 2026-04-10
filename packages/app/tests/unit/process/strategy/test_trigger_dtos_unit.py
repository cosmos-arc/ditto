"""Trigger DTO 定义测试."""

from datetime import date

import pytest
from ditto_app.process.execution.strategy_types import (
    BacktestTrigger,
    StrategySliceTrigger,
)


class TestBacktestTrigger:
    def test_creation(self) -> None:
        t = BacktestTrigger(
            strategy_id="strat_1",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
        )
        assert t.strategy_id == "strat_1"
        assert t.start_date == date(2025, 1, 1)
        assert t.end_date == date(2025, 3, 31)

    def test_frozen(self) -> None:
        t = BacktestTrigger(
            strategy_id="strat_1",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
        )
        with pytest.raises(AttributeError):
            t.strategy_id = "new_id"  # type: ignore[misc]


class TestStrategySliceTrigger:
    def test_creation(self) -> None:
        t = StrategySliceTrigger(
            strategy_id="strat_1",
            trade_date=date(2025, 1, 15),
        )
        assert t.strategy_id == "strat_1"
        assert t.trade_date == date(2025, 1, 15)

    def test_frozen(self) -> None:
        t = StrategySliceTrigger(
            strategy_id="strat_1",
            trade_date=date(2025, 1, 15),
        )
        with pytest.raises(AttributeError):
            t.strategy_id = "new_id"  # type: ignore[misc]
