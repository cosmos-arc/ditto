"""Tests for portfolio state projection — AccountProjector / FillProjector."""

from __future__ import annotations

from datetime import datetime

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.fills import FillEvent
from ditto_portfolio.projection import AccountProjector, PortfolioStateSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INSTRUMENT: InstrumentId = InstrumentId(600000)


def _make_fill(
    instrument_id: InstrumentId = InstrumentId(600_000),
    direction: OrderSide = OrderSide.BUY,
    filled_quantity: int = 100,
    fill_price: float = 10.0,
    fee: float = 5.0,
    slippage: float = 0.0,
    fill_id: str = "f1",
    order_id: str = "o1",
    event_time: datetime = datetime(2024, 1, 15, 15, 0),
) -> FillEvent:
    """创建测试用 FillEvent。"""
    return FillEvent(
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=instrument_id,
        direction=direction,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=slippage,
        event_time=event_time,
        cumulative_quantity=filled_quantity,
        leaves_quantity=0,
    )


# ---------------------------------------------------------------------------
# TestAccountProjector
# ---------------------------------------------------------------------------


class TestAccountProjectorEmptyFills:
    """空 fill 流场景。"""

    def test_empty_fills_produces_empty_snapshot(self) -> None:
        """AccountProjector 无成交 → 空 positions + 零 CashBook。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=0.0, settled=0.0, frozen=0.0),
        )
        snapshot = projector.project([])

        assert isinstance(snapshot, PortfolioStateSnapshot)
        assert snapshot.positions == {}
        assert snapshot.cash.available == 0.0
        assert snapshot.cash.settled == 0.0
        assert snapshot.cash.frozen == 0.0


class TestAccountProjectorBuyFill:
    """BUY fill 投影场景。"""

    def test_single_buy_fill_produces_position(self) -> None:
        """单次 BUY → 产生正确 quantity / average_cost 的 Position。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        snapshot = projector.project([fill])

        assert _INSTRUMENT in snapshot.positions
        pos = snapshot.positions[_INSTRUMENT]
        assert pos.quantity == 100
        assert pos.average_cost == pytest.approx(10.0)
        assert pos.total_fees == pytest.approx(5.0)

    def test_cash_decreases_on_buy(self) -> None:
        """BUY fill → cash.available 减少 price * qty + fee。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        snapshot = projector.project([fill])

        expected_available = 100_000.0 - 10.0 * 100 - 5.0
        assert snapshot.cash.available == pytest.approx(expected_available)
        assert snapshot.cash.frozen == 0.0


class TestAccountProjectorSellFill:
    """SELL fill 投影场景。"""

    def test_sell_fill_reduces_position(self) -> None:
        """BUY 后 SELL → 持仓减少或清空。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        # 卖出一半
        sell_fill = _make_fill(
            fill_id="f2",
            order_id="o2",
            direction=OrderSide.SELL,
            filled_quantity=50,
            fill_price=12.0,
            fee=3.0,
        )

        # AccountProjector 使用 Account 内部累加，需要先让 BUY 的持仓
        # available_quantity 可卖（模拟 T+0 解冻）无法通过 projector 接口操作，
        # 所以直接验证 SELL 后持仓数量减少
        snapshot = projector.project([buy_fill, sell_fill])

        pos = snapshot.positions[_INSTRUMENT]
        assert pos.quantity == 50
        # realized_pnl = (12.0 - 10.0) * 50 = 100
        assert pos.realized_pnl == pytest.approx(100.0)

    def test_sell_fill_removes_position_on_full_exit(self) -> None:
        """BUY 后全部 SELL → 持仓被完全移除。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        sell_fill = _make_fill(
            fill_id="f2",
            order_id="o2",
            direction=OrderSide.SELL,
            filled_quantity=100,
            fill_price=12.0,
            fee=3.0,
        )
        snapshot = projector.project([buy_fill, sell_fill])

        assert _INSTRUMENT not in snapshot.positions

    def test_cash_increases_on_sell(self) -> None:
        """SELL fill → cash.available 增加 price * qty - fee。"""
        projector = AccountProjector(
            initial_cash=CashBook(available=100_000.0, settled=100_000.0, frozen=0.0),
        )
        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        sell_fill = _make_fill(
            fill_id="f2",
            order_id="o2",
            direction=OrderSide.SELL,
            filled_quantity=100,
            fill_price=12.0,
            fee=3.0,
        )
        snapshot = projector.project([buy_fill, sell_fill])

        # BUY: 100_000 - 10*100 - 5 = 98_995
        # SELL: 98_995 + 12*100 - 3 = 100_192
        expected_available = 100_000.0 - 10.0 * 100 - 5.0 + 12.0 * 100 - 3.0
        assert snapshot.cash.available == pytest.approx(expected_available)


class TestAccountProjectorParity:
    """in-memory 引擎与账本重建引擎的端态一致性（#680/#684 批B）。

    旧 parity 测试对 Account 手动 apply_fill 与 projector（内部同样走
    Account）互拍＝套套逻辑；改为对 AccountLedgerRebuilder 断真不变量：
    同一组成交在全部交收完成后（as_of ≥ 一切 settlement_date），两引擎
    的持仓数量与 available/settled 现金必须一致。available_quantity 不在
    断言内——两引擎的 T+0 解冻模型不同（in-memory 外部回调 vs rebuilder
    按 settlement_date<=as_of）。
    """

    def test_end_state_cash_and_quantity_match_ledger_rebuilder(self) -> None:
        from datetime import UTC
        from decimal import Decimal

        from ditto_portfolio.account_ledger import (
            AccountDefinition,
            AccountEventDraft,
            AccountEventSource,
            AccountEventType,
            AccountKind,
            create_account_event,
        )
        from ditto_portfolio.account_projection import AccountLedgerRebuilder

        initial_cash = CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)
        fills = [
            _make_fill(
                fill_id="f1",
                order_id="o1",
                filled_quantity=200,
                fill_price=10.0,
                fee=5.0,
            ),
            _make_fill(
                fill_id="f2",
                order_id="o2",
                instrument_id=InstrumentId(600_001),
                filled_quantity=300,
                fill_price=8.0,
                fee=4.0,
            ),
            _make_fill(
                fill_id="f3",
                order_id="o3",
                direction=OrderSide.SELL,
                filled_quantity=100,
                fill_price=11.0,
                fee=3.0,
            ),
        ]

        # 路径 A: in-memory 引擎（projector 与手动 apply_fill 同源同果）
        projector = AccountProjector(initial_cash=initial_cash)
        snapshot = projector.project(fills)

        # 路径 B: Decimal 账本全量重建（DEPOSIT 锚定初始现金）
        account = AccountDefinition(
            account_id="paper-parity",
            kind=AccountKind.PAPER,
            name="Parity",
            opened_at=datetime(2026, 1, 5, tzinfo=UTC),
        )
        now = datetime(2026, 1, 6, 9, 30, tzinfo=UTC)
        drafts = [
            AccountEventDraft(
                event_type=AccountEventType.DEPOSIT,
                event_id="e0",
                trade_date="2026-01-05",
                settlement_date="2026-01-05",
                recorded_at=now,
                idempotency_key="k0",
                actor="test",
                source=AccountEventSource.PAPER_ENGINE,
                gross_amount=Decimal("100000"),
            ),
        ]
        for fill in fills:
            is_buy = fill.direction == OrderSide.BUY
            drafts.append(
                AccountEventDraft(
                    event_type=(
                        AccountEventType.BUY if is_buy else AccountEventType.SELL
                    ),
                    event_id=f"e-{fill.fill_id}",
                    trade_date="2026-01-05",
                    settlement_date="2026-01-05",
                    recorded_at=now,
                    idempotency_key=f"k-{fill.fill_id}",
                    actor="test",
                    source=AccountEventSource.PAPER_ENGINE,
                    instrument_id=fill.instrument_id,
                    quantity=Decimal(fill.filled_quantity),
                    price=Decimal(str(fill.fill_price)),
                    gross_amount=Decimal(str(fill.fill_price * fill.filled_quantity)),
                    fees=Decimal(str(fill.fee)),
                ),
            )
        events = [
            create_account_event(account=account, draft=draft) for draft in drafts
        ]
        rebuilt = AccountLedgerRebuilder().rebuild(
            account=account, events=events, as_of="2026-01-06"
        )

        # 持仓数量一致
        assert {pos.instrument_id: pos.quantity for pos in rebuilt.positions} == {
            iid: pos.quantity for iid, pos in snapshot.positions.items()
        }

        # 端态现金一致（#680 口径：BUY 全额当日占 settled，端态两引擎相等）
        assert float(rebuilt.cash.available) == pytest.approx(snapshot.cash.available)
        assert float(rebuilt.cash.settled) == pytest.approx(snapshot.cash.settled)


class TestAccountProjectorIdempotency:
    """project() 多次调用不应累积状态。"""

    def test_repeated_project_resets_state(self) -> None:
        """同一 projector 调用 project() 两次，第二次结果应独立于第一次。"""
        initial_cash = CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)
        projector = AccountProjector(initial_cash=initial_cash)

        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        projector.project([buy_fill])

        # 第二次调用 — 同样的 fill，应产生相同结果
        snapshot2 = projector.project([buy_fill])
        pos = snapshot2.positions[_INSTRUMENT]
        assert pos.quantity == 100
        assert pos.total_fees == pytest.approx(5.0)

    def test_repeated_project_empty_resets_to_initial(self) -> None:
        """先 project 有 fill，再 project 空 → 应回到初始状态。"""
        initial_cash = CashBook(available=100_000.0, settled=100_000.0, frozen=0.0)
        projector = AccountProjector(initial_cash=initial_cash)

        buy_fill = _make_fill(filled_quantity=100, fill_price=10.0, fee=5.0)
        projector.project([buy_fill])

        snapshot2 = projector.project([])
        assert snapshot2.positions == {}
        assert snapshot2.cash == initial_cash
