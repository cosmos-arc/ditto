"""PaperTradingRuntime 单元测试 — 订单执行最小冒烟测试."""

from __future__ import annotations

from unittest.mock import Mock

from ditto_application.processes.execution.paper_trading_process import (
    PaperTradingRuntime,
)
from ditto_execution.broker.contracts import BrokerGateway
from ditto_execution.broker.gateways.paper import PaperBrokerGateway
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.orders.trigger import OrderTrigger
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting import FillEvent
from ditto_portfolio.accounting.account import Account, AccountView
from ditto_portfolio.accounting.cash import CashBook

IID = InstrumentId(600519)


def _make_order(
    direction: OrderSide,
    quantity: int = 100,
    price: float = 10.0,
    instrument_id: InstrumentId = IID,
) -> Order:
    """构建测试用 Order."""
    return Order(
        client_id=ClientOrderId.generate(),
        instrument_id=instrument_id,
        order_type=OrderType.LIMIT,
        direction=direction,
        quantity=quantity,
        price=price,
    )


def _make_runtime(
    initial_cash: float = 100_000.0,
) -> tuple[PaperBrokerGateway, Account, PaperTradingRuntime]:
    """构建测试用 PaperTradingRuntime 及其依赖."""
    cash = CashBook(
        available=initial_cash,
        settled=initial_cash,
        frozen=0.0,
    )
    gateway = PaperBrokerGateway(initial_cash=initial_cash)
    account = Account(cash=cash)
    runtime = PaperTradingRuntime(gateway=gateway, account=account)
    return gateway, account, runtime


class TestPaperTradingRuntimeConstruction:
    """PaperTradingRuntime 构造."""

    def test_constructs_with_gateway_and_account(self) -> None:
        """接受 PaperBrokerGateway 和 Account."""
        _, _, runtime = _make_runtime()
        assert runtime is not None


class TestPaperTradingRuntimeExecuteOrder:
    """execute_order 完整路径：gateway -> fill -> account."""

    def test_buy_order_reduces_cash(self) -> None:
        """BUY 订单应减少账户现金."""
        initial_cash = 100_000.0
        _, account, runtime = _make_runtime(initial_cash)
        runtime.execute_order(_make_order(OrderSide.BUY, quantity=100, price=10.0))

        # 现金应减少: 100 * 10.0 = 1000.0
        view = account.get_view()
        assert view.cash.available == initial_cash - 1000.0

    def test_buy_order_creates_position(self) -> None:
        """BUY 订单应创建持仓."""
        _, account, runtime = _make_runtime()
        runtime.execute_order(_make_order(OrderSide.BUY))

        # 持仓应存在
        view = account.get_view()
        assert IID in view.positions
        assert view.positions[IID].quantity == 100
        assert view.positions[IID].average_cost == 10.0

    def test_buy_order_returns_ticket_with_filled_status(self) -> None:
        """execute_order 应返回 FILLED 状态的 ticket."""
        _, _, runtime = _make_runtime()

        ticket = runtime.execute_order(_make_order(OrderSide.BUY))

        assert isinstance(ticket, OrderTicket)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 100
        assert ticket.filled_price == 10.0

    def test_sell_order_increases_cash(self) -> None:
        """SELL 订单应增加账户现金."""
        initial_cash = 50_000.0
        _, account, runtime = _make_runtime(initial_cash)

        # 先买入
        runtime.execute_order(_make_order(OrderSide.BUY, quantity=200, price=10.0))
        # 再卖出
        runtime.execute_order(_make_order(OrderSide.SELL, quantity=100, price=12.0))

        view = account.get_view()
        # 买入后现金: 50000 - 200*10 = 48000
        # 卖出后现金: 48000 + 100*12 = 49200
        assert view.cash.available == initial_cash - 2000.0 + 1200.0

    def test_account_view_snapshot_after_fills(self) -> None:
        """多次成交后 AccountView 应反映正确的 cash/position/exposure."""
        _, account, runtime = _make_runtime()

        runtime.execute_order(_make_order(OrderSide.BUY, quantity=100, price=10.0))

        view: AccountView = account.get_view()

        # 现金: 100000 - 1000 = 99000
        assert view.cash.available == 99_000.0
        # 持仓数量和成本
        assert IID in view.positions
        pos = view.positions[IID]
        assert pos.quantity == 100
        assert pos.average_cost == 10.0
        assert pos.market_value == 1000.0
        # exposure = sum(market_value) = 1000
        assert view.exposure == 1000.0
        # total_value = cash.total + exposure = 99000 + 1000 = 100000
        assert view.total_value == 100_000.0

    def test_runtime_does_not_contain_gateway_logic(self) -> None:
        """PaperTradingRuntime 应是纯编排 — 不应自己实现撮合/成交逻辑."""
        import inspect

        source = inspect.getsource(PaperTradingRuntime)
        # 不应包含成交撮合关键词
        assert "slippage" not in source
        assert "matching" not in source
        assert "fee_calc" not in source


def _make_stub_gateway(order: Order) -> Mock:
    """构建满足 BrokerGateway Protocol 的 Mock stub."""
    from datetime import UTC, datetime

    gateway = Mock(spec=BrokerGateway)
    fill_price = order.price if order.price is not None else 0.0
    ticket = OrderTicket(order=order, status=OrderStatus.SUBMITTED).with_fill(
        quantity=order.quantity,
        price=fill_price,
        event=OrderEvent(
            client_id=order.client_id,
            trigger=OrderTrigger.FILL,
            status=OrderStatus.FILLED,
            fill_price=fill_price,
            fill_quantity=order.quantity,
        ),
    )
    gateway.submit_order.return_value = ticket
    fill = FillEvent(
        fill_id="stub-fill-001",
        order_id=order.order_id,
        instrument_id=order.instrument_id,
        direction=order.direction,
        filled_quantity=order.quantity,
        fill_price=fill_price,
        fee=0.0,
        slippage=0.0,
        event_time=datetime.now(tz=UTC),
        cumulative_quantity=order.quantity,
        leaves_quantity=0,
    )
    gateway.query_fills.return_value = (fill,)
    return gateway


class TestPaperTradingRuntimeAcceptsBrokerGatewayProtocol:
    """PaperTradingRuntime 必须接受任何 BrokerGateway Protocol 实现者."""

    def test_constructs_with_mock_gateway(self) -> None:
        """接受满足 BrokerGateway Protocol 的 Mock 对象."""
        order = _make_order(OrderSide.BUY)
        gateway = _make_stub_gateway(order)
        cash = CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)
        account = Account(cash=cash)

        runtime = PaperTradingRuntime(gateway=gateway, account=account)
        assert runtime is not None

    def test_execute_order_with_mock_gateway(self) -> None:
        """通过 Mock gateway 执行订单应正常返回 ticket 并应用成交."""
        order = _make_order(OrderSide.BUY, quantity=100, price=10.0)
        gateway = _make_stub_gateway(order)
        cash = CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)
        account = Account(cash=cash)
        runtime = PaperTradingRuntime(gateway=gateway, account=account)

        ticket = runtime.execute_order(order)

        assert isinstance(ticket, OrderTicket)
        assert ticket.status == OrderStatus.FILLED
        assert ticket.filled_quantity == 100
        gateway.submit_order.assert_called_once_with(order)
        gateway.query_fills.assert_called_once_with(order.order_id)

    def test_mock_gateway_reduces_cash(self) -> None:
        """Mock gateway 成交应正确减少账户现金."""
        order = _make_order(OrderSide.BUY, quantity=100, price=10.0)
        gateway = _make_stub_gateway(order)
        initial_cash = 100_000.0
        cash = CashBook(available=initial_cash, settled=initial_cash, frozen=0.0)
        account = Account(cash=cash)
        runtime = PaperTradingRuntime(gateway=gateway, account=account)

        runtime.execute_order(order)

        view = account.get_view()
        assert view.cash.available == initial_cash - 1000.0

    def test_paper_broker_gateway_satisfies_protocol(self) -> None:
        """PaperBrokerGateway 应满足 BrokerGateway Protocol."""
        gateway = PaperBrokerGateway(initial_cash=100_000.0)
        assert isinstance(gateway, BrokerGateway)
