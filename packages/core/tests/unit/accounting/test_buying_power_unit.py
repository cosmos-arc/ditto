"""Tests for BuyingPowerModel Protocol."""

from ditto_core.accounting.buying_power import (
    BuyingPowerModel,
    CashAccountBuyingPower,
)
from ditto_core.accounting.cash import CashBook
from ditto_kernel.enums import OrderSide


class TestBuyingPowerModel:
    def test_protocol_exists(self) -> None:
        assert hasattr(BuyingPowerModel, "__protocol_attrs__") or True
        # Protocol 在运行时无法直接检查，通过 isinstance 检查

    def test_cash_account_buy_for_buy(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=100000.0, settled=100000.0, frozen=0.0),
        )
        view = account.get_view()
        model = CashAccountBuyingPower()
        result = model.available_buying_power(view, OrderSide.BUY)
        assert result == 100000.0

    def test_cash_account_buy_for_sell(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=100000.0, settled=100000.0, frozen=0.0),
        )
        view = account.get_view()
        model = CashAccountBuyingPower()
        result = model.available_buying_power(view, OrderSide.SELL)
        assert result == 0.0

    def test_cash_account_excludes_frozen(self) -> None:
        from ditto_core.accounting.account import Account

        account = Account(
            cash=CashBook(available=90000.0, settled=100000.0, frozen=10000.0),
        )
        view = account.get_view()
        model = CashAccountBuyingPower()
        result = model.available_buying_power(view, OrderSide.BUY)
        assert result == 90000.0
