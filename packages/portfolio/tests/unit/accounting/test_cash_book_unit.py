"""Tests for CashBook frozen dataclass (R6)."""

from dataclasses import FrozenInstanceError

import pytest


class TestCashBook:
    def test_create_cash_book(self) -> None:
        from ditto_portfolio.accounting.cash import CashBook

        cash = CashBook(available=90000.0, settled=85000.0, frozen=10000.0)
        assert cash.available == 90000.0
        assert cash.settled == 85000.0
        assert cash.frozen == 10000.0

    def test_cash_book_is_frozen(self) -> None:
        from ditto_portfolio.accounting.cash import CashBook

        cash = CashBook(available=100000.0, settled=100000.0, frozen=0.0)
        with pytest.raises(FrozenInstanceError):
            cash.available = 50000.0  # type: ignore[misc]

    def test_total_cash_property(self) -> None:
        from ditto_portfolio.accounting.cash import CashBook

        cash = CashBook(available=90000.0, settled=85000.0, frozen=10000.0)
        assert cash.total == 100000.0  # available + frozen

    def test_create_replacement_after_fill(self) -> None:
        from ditto_portfolio.accounting.cash import CashBook

        original = CashBook(available=100000.0, settled=100000.0, frozen=0.0)
        fee = 5.0
        # 模拟成交后扣除手续费
        updated = CashBook(
            available=original.available - fee,
            settled=original.settled,
            frozen=original.frozen,
        )
        assert updated.available == pytest.approx(99995.0)
        assert original.available == 100000.0  # 原实例不变
