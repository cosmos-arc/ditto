"""Tests for Account / AccountView."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from ditto_core.accounting.cash import CashBook
from ditto_core.accounting.position import Position


class TestAccount:
    def test_create_account_with_initial_cash(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        assert account.cash.available == 1000000.0
        assert account.positions == {}

    def test_account_is_mutable(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        # Account 本身不是 frozen — 可以修改 positions
        account.positions["159915.SZ"] = Position(
            instrument_id="159915.SZ",
            quantity=100,
            available_quantity=0,
            average_cost=0.452,
            market_value=45.2,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        assert "159915.SZ" in account.positions

    def test_get_view_returns_frozen_snapshot(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        account.positions["159915.SZ"] = Position(
            instrument_id="159915.SZ",
            quantity=100,
            available_quantity=0,
            average_cost=0.452,
            market_value=45.2,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = account.get_view()
        assert view.nav == pytest.approx(1000045.2)
        assert view.total_value == pytest.approx(1000045.2)
        # view 是 frozen — 修改 Account 不影响已有 view
        account.positions["510300.SH"] = Position(
            instrument_id="510300.SH",
            quantity=200,
            available_quantity=0,
            average_cost=4.0,
            market_value=820.0,
            unrealized_pnl=20.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        assert "510300.SH" not in view.positions


class TestAccountView:
    def test_view_is_frozen(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        view = account.get_view()
        with pytest.raises(FrozenInstanceError):
            view.nav = 0.0  # type: ignore[misc]

    def test_view_positions_readonly(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        account.positions["159915.SZ"] = Position(
            instrument_id="159915.SZ",
            quantity=100,
            available_quantity=0,
            average_cost=0.452,
            market_value=45.2,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
        view = account.get_view()
        # positions 通过 MappingProxyType 暴露，不可写
        with pytest.raises(TypeError):
            view.positions["NEW"] = Position(  # type: ignore[index]
                instrument_id="NEW",
                quantity=1,
                available_quantity=1,
                average_cost=1.0,
                market_value=1.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                total_fees=0.0,
            )

    def test_view_order_book_readonly(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=1000000.0, settled=1000000.0, frozen=0.0),
        )
        view = account.get_view()
        assert view.order_book.get("NONEXISTENT") is None
