"""EngineResult 不可变性与 EngineResultBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from types import MappingProxyType

import orjson
import pytest
from ditto_backtest import result as result_module
from ditto_backtest.audit.state import ExecutionAuditStateSnapshot
from ditto_backtest.manifest_types import RunManifest, RunMode
from ditto_backtest.result import EngineResult, EngineResultBuilder
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.trade_builder import (
    FifoOpenEntrySnapshot,
    FlatToFlatAccumulatorSnapshot,
    TradeBuilderStateSnapshot,
    TradeMatchingMethod,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting import AccountView, CashBook, FillEvent
from ditto_strategy.alpha.context import StrategyContextSnapshot
from ditto_strategy.alpha.models import TargetPortfolio

IID_1 = InstrumentId(1)


def _checkpoint_cls() -> type:
    """Return BacktestCheckpoint once the checkpoint API exists."""
    return result_module.BacktestCheckpoint


def _sample_order(client_order_id: str = "ord-1") -> Order:
    """创建最小 Order 用于测试。"""
    return Order(
        client_id=ClientOrderId(value=client_order_id),
        instrument_id=IID_1,
        order_type=OrderType.MARKET,
        direction=OrderSide.BUY,
        quantity=100,
    )


def _sample_fill() -> FillEvent:
    """创建最小 FillEvent 用于测试。"""
    return FillEvent(
        fill_id="fill-1",
        order_id="ord-1",
        instrument_id=IID_1,
        direction=OrderSide.BUY,
        filled_quantity=100,
        fill_price=10.0,
        fee=0.0,
        slippage=0.0,
        event_time=datetime(2026, 1, 5, tzinfo=UTC),
        cumulative_quantity=100,
        leaves_quantity=0,
    )


def _sample_account_view() -> AccountView:
    """创建最小 AccountView 用于测试。"""
    return AccountView(
        positions=MappingProxyType({}),
        cash=CashBook(available=1_000_000.0, settled=1_000_000.0, frozen=0.0),
        total_value=1_000_000.0,
        nav=1_000_000.0,
        exposure=0.0,
    )


def _complete_audit_state_payload() -> dict[str, object]:
    """Build one canonical audit tree containing every typed record level."""
    return {
        "closed_trades": [
            {
                "direction": "buy",
                "entry_date": "2026-03-01",
                "entry_order_ids": ["order-1"],
                "entry_price": 10.0,
                "exit_date": "2026-03-02",
                "exit_order_ids": ["order-2"],
                "exit_price": 11.0,
                "fees": 2.0,
                "gross_pnl": 100.0,
                "holding_days": 1,
                "instrument_id": 1,
                "net_pnl": 98.0,
                "quantity": 100,
                "return_pct": 0.098,
                "trade_id": "trade-1",
            }
        ],
        "daily_snapshots": [
            {
                "account": {
                    "cash_available": 1_000.0,
                    "cash_frozen": 0.0,
                    "cash_settled": 1_000.0,
                    "exposure": 0.5,
                    "nav": 2_000.0,
                    "positions": [
                        {
                            "available_quantity": 100,
                            "average_cost": 10.0,
                            "instrument_id": 1,
                            "market_value": 1_000.0,
                            "quantity": 100,
                            "realized_pnl": 0.0,
                            "total_fees": 1.0,
                            "unrealized_pnl": 0.0,
                        }
                    ],
                    "total_value": 2_000.0,
                },
                "trade_date": "2026-03-01",
            }
        ],
        "fills": [
            {
                "correlation_id": None,
                "cumulative_quantity": 100,
                "direction": "buy",
                "event_time": "2026-03-01T00:00:00+00:00",
                "fee": 1.0,
                "fill_id": "fill-1",
                "fill_price": 10.0,
                "filled_quantity": 100,
                "instrument_id": 1,
                "leaves_quantity": 0,
                "order_id": "order-1",
                "slippage": 0.0,
            }
        ],
        "pre_trade_log": [
            {
                "check_sequence": ["lot_size"],
                "decision": "accepted",
                "direction": "buy",
                "final_quantity": 100,
                "instrument_id": 1,
                "order_id": "order-1",
                "original_quantity": 100,
                "reason": None,
                "trade_date": "2026-03-01",
            }
        ],
        "risk_log": [
            {
                "action_taken": "alert",
                "current_value": 0.5,
                "detail": "exposure warning",
                "instrument_id": 1,
                "rule_id": "exposure",
                "scope": "instrument",
                "severity": "warning",
                "threshold": 0.4,
                "trade_date": "2026-03-01",
            }
        ],
    }


def _nested_mapping(
    payload: object,
    path: tuple[str | int, ...],
) -> dict[str, object]:
    """Resolve a typed test path and return its mapping target."""
    current = payload
    for component in path:
        if isinstance(component, str):
            assert isinstance(current, dict)
            current = current[component]
        else:
            assert isinstance(current, list)
            current = current[component]
    assert isinstance(current, dict)
    return current


# ---------------------------------------------------------------------------
# EngineResult 不可变性测试
# ---------------------------------------------------------------------------


class TestEngineResultFrozen:
    """EngineResult 必须是不可变的（frozen dataclass）。"""

    def test_frozen_assign_raises(self) -> None:
        """对 frozen field 赋值应抛出 FrozenInstanceError。"""
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        with pytest.raises(FrozenInstanceError):
            result.final_nav = 999.0  # type: ignore[misc]

    def test_frozen_assign_run_id_raises(self) -> None:
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        with pytest.raises(FrozenInstanceError):
            result.run_id = "other"  # type: ignore[misc]

    def test_frozen_assign_cancelled_raises(self) -> None:
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        with pytest.raises(FrozenInstanceError):
            result.cancelled = True  # type: ignore[misc]

    def test_orders_is_tuple(self) -> None:
        """orders 字段必须是 tuple，不可变容器。"""
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            orders=(_sample_order(),),
        )
        assert isinstance(result.orders, tuple)
        assert len(result.orders) == 1

    def test_fills_is_tuple(self) -> None:
        """fills 字段必须是 tuple，不可变容器。"""
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            fills=(_sample_fill(),),
        )
        assert isinstance(result.fills, tuple)
        assert len(result.fills) == 1

    def test_default_orders_is_empty_tuple(self) -> None:
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        assert result.orders == ()

    def test_default_fills_is_empty_tuple(self) -> None:
        result = EngineResult(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
        )
        assert result.fills == ()

    def test_docstring_says_immutable(self) -> None:
        """文档字符串应标记为不可变。"""
        assert EngineResult.__doc__ is not None
        assert "不可变" in EngineResult.__doc__


class TestBacktestCheckpoint:
    """BacktestCheckpoint freezes the recovery boundary."""

    def test_resume_from_next_trade_date(self) -> None:
        checkpoint = _checkpoint_cls()(
            run_id="run-001",
            strategy_id="strategy-a",
            completed_trade_date="2026-03-01",
            resume_from="2026-03-02",
            completed_days=1,
            total_days=3,
            nav=1_000_000.0,
            fill_count=2,
            order_count=2,
        )

        assert checkpoint.resume_from == "2026-03-02"
        assert checkpoint.can_resume is True

    def test_final_checkpoint_has_no_resume_date(self) -> None:
        checkpoint = _checkpoint_cls()(
            run_id="run-001",
            strategy_id="strategy-a",
            completed_trade_date="2026-03-03",
            resume_from=None,
            completed_days=3,
            total_days=3,
            nav=1_001_000.0,
            fill_count=4,
            order_count=4,
        )

        assert checkpoint.can_resume is False

    def test_account_state_hash_survives_integer_zero_exposure_roundtrip(self) -> None:
        """全现金账户的 int 0 exposure 不应导致 JSON/hash round-trip 漂移."""
        snapshot = result_module.BacktestAccountStateSnapshot(
            cash_available=1_000_000.0,
            cash_settled=1_000_000.0,
            cash_frozen=0.0,
            total_value=1_000_000.0,
            nav=1_000_000.0,
            exposure=0,
        )

        restored = result_module.BacktestAccountStateSnapshot.from_json(
            snapshot.to_json(),
        )

        assert restored.state_hash == snapshot.state_hash

    def test_runtime_state_round_trip_preserves_deterministic_resume_state(
        self,
    ) -> None:
        """Runtime JSON must carry every cross-day state owner needed by resume."""
        trade_builder_state = TradeBuilderStateSnapshot(
            method=TradeMatchingMethod.FIFO,
            counter=7,
            fifo_open_entries=(
                FifoOpenEntrySnapshot(
                    trade_id="trade-7",
                    instrument_id=IID_1,
                    direction=OrderSide.BUY,
                    entry_date=date(2026, 3, 1),
                    entry_price=10.0,
                    entry_fee=5.0,
                    original_quantity=200,
                    remaining_quantity=100,
                    entry_order_id="plan-order-8",
                ),
            ),
        )
        snapshot = result_module.BacktestRuntimeStateSnapshot.from_state(
            result_module.BacktestRuntimeStateCapture(
                strategy_context=StrategyContextSnapshot(
                    risk_locked_instruments={
                        IID_1: ("single-loss", "2026-03-10"),
                    },
                    positions={IID_1: 10.25},
                ),
                planner_id_counter=9,
                brokerage_fill_counter=4,
                trade_builder_state=trade_builder_state,
            )
        )

        restored = result_module.BacktestRuntimeStateSnapshot.from_json(
            snapshot.to_json(),
        )

        assert restored == snapshot
        assert restored.to_strategy_context_snapshot() == StrategyContextSnapshot(
            risk_locked_instruments={IID_1: ("single-loss", "2026-03-10")},
            positions={IID_1: 10.25},
        )
        assert restored.state_hash == snapshot.state_hash

    def test_runtime_state_legacy_json_uses_safe_defaults(self) -> None:
        """V1 payloads without deterministic-resume fields remain readable."""
        legacy_json = '{"delayed_signals":[],"pending_orders":[]}'

        restored = result_module.BacktestRuntimeStateSnapshot.from_json(legacy_json)

        assert restored.runtime_state_version is None
        assert restored.is_exact_resume_state is False
        assert restored.planner_id_counter == 0
        assert restored.brokerage_fill_counter == 0
        assert restored.trade_builder_state is None
        assert restored.to_strategy_context_snapshot() == StrategyContextSnapshot(
            risk_locked_instruments={},
            positions={},
        )
        assert restored.to_json() == legacy_json

    def test_runtime_state_from_live_state_attests_complete_v2_payload(self) -> None:
        """Only a live capture may attest all result-determining V2 fields."""
        snapshot = result_module.BacktestRuntimeStateSnapshot.from_state(
            result_module.BacktestRuntimeStateCapture(
                trade_builder_state=TradeBuilderStateSnapshot(
                    method=TradeMatchingMethod.FIFO,
                    counter=0,
                ),
                rebalance_calendar_start="2026-03-01",
                audit_state_json=(
                    '{"closed_trades":[],"daily_snapshots":[],"fills":[],'
                    '"pre_trade_log":[],"risk_log":[]}'
                ),
            )
        )

        assert snapshot.runtime_state_version == 2
        assert snapshot.is_exact_resume_state is True
        assert '"runtime_state_version":2' in snapshot.to_json()
        assert (
            result_module.BacktestRuntimeStateSnapshot.from_json(snapshot.to_json())
            == snapshot
        )

    def test_v2_runtime_requires_nullable_pending_order_fields(self) -> None:
        """V2 cannot silently default an omitted result-affecting nullable field."""
        ticket = OrderTicket(
            order=_sample_order("plan-order-1"),
            status=OrderStatus.SUBMITTED,
        )
        snapshot = result_module.BacktestRuntimeStateSnapshot.from_state(
            result_module.BacktestRuntimeStateCapture(
                pending_tickets=(ticket,),
                planner_id_counter=1,
                trade_builder_state=TradeBuilderStateSnapshot(
                    method=TradeMatchingMethod.FIFO,
                    counter=0,
                ),
                rebalance_calendar_start="2026-03-01",
                audit_state_json=ExecutionAuditStateSnapshot().to_json(),
            )
        )
        payload = snapshot.to_payload()
        pending_orders = payload["pending_orders"]
        assert isinstance(pending_orders, list)
        pending = pending_orders[0]
        assert isinstance(pending, dict)
        del pending["price"]

        with pytest.raises(ValueError, match="missing required fields"):
            result_module.BacktestRuntimeStateSnapshot.from_payload(payload)

    def test_v2_runtime_rejects_non_contiguous_delayed_queue(self) -> None:
        """Delayed queue identity must match its order-sensitive tuple position."""
        payload = {
            "audit_state_json": ExecutionAuditStateSnapshot().to_json(),
            "brokerage_fill_counter": 0,
            "delayed_signals": [
                {
                    "cash_target": 0.0,
                    "positions": [],
                    "queue_index": 1,
                    "run_id": "run-1",
                    "strategy_id": "strategy-1",
                    "trade_date": "2026-03-01",
                }
            ],
            "pending_orders": [],
            "planner_id_counter": 0,
            "rebalance_calendar_start": "2026-03-01",
            "runtime_state_version": 2,
            "strategy_context": {"position_costs": [], "risk_locks": []},
            "trade_builder_state": {
                "counter": 0,
                "fifo_open_entries": [],
                "method": "fifo",
            },
        }

        with pytest.raises(ValueError, match="queue indices must be contiguous"):
            result_module.BacktestRuntimeStateSnapshot.from_payload(payload)

    @pytest.mark.parametrize(
        "location",
        [
            "root",
            "pending_order",
            "delayed_signal",
            "target_weight",
            "strategy_context",
            "risk_lock",
            "position_cost",
            "trade_builder",
            "fifo_entry",
        ],
    )
    def test_v2_runtime_rejects_unknown_fields_at_every_typed_level(
        self,
        location: str,
    ) -> None:
        """Signed V2 JSON cannot carry ignored data that disappears on decode."""
        ticket = OrderTicket(
            order=_sample_order("plan-order-1"),
            status=OrderStatus.SUBMITTED,
        )
        trade_state = TradeBuilderStateSnapshot(
            method=TradeMatchingMethod.FIFO,
            counter=1,
            fifo_open_entries=(
                FifoOpenEntrySnapshot(
                    trade_id="trade-1",
                    instrument_id=IID_1,
                    direction=OrderSide.BUY,
                    entry_date=date(2026, 3, 1),
                    entry_price=10.0,
                    entry_fee=0.0,
                    original_quantity=100,
                    remaining_quantity=100,
                    entry_order_id="plan-order-1",
                ),
            ),
        )
        signal = TargetPortfolio(
            trade_date="2026-03-01",
            strategy_id="strategy-1",
            run_id="run-1",
            positions={IID_1: 0.5},
            cash_target=0.5,
        )
        snapshot = result_module.BacktestRuntimeStateSnapshot.from_state(
            result_module.BacktestRuntimeStateCapture(
                pending_tickets=(ticket,),
                delayed_signals=(signal,),
                strategy_context=StrategyContextSnapshot(
                    risk_locked_instruments={IID_1: ("cooldown", "2026-03-10")},
                    positions={IID_1: 10.0},
                ),
                planner_id_counter=1,
                brokerage_fill_counter=1,
                trade_builder_state=trade_state,
                rebalance_calendar_start="2026-03-01",
                audit_state_json=ExecutionAuditStateSnapshot().to_json(),
            )
        )
        payload = snapshot.to_payload()
        nested: object = payload
        if location == "pending_order":
            nested = payload["pending_orders"]
        elif location in {"delayed_signal", "target_weight"}:
            nested = payload["delayed_signals"]
        elif location in {"strategy_context", "risk_lock", "position_cost"}:
            nested = payload["strategy_context"]
        elif location in {"trade_builder", "fifo_entry"}:
            nested = payload["trade_builder_state"]
        if isinstance(nested, list):
            nested = nested[0]
        if location == "target_weight":
            assert isinstance(nested, dict)
            nested = nested["positions"]
            assert isinstance(nested, list)
            nested = nested[0]
        elif location == "risk_lock":
            assert isinstance(nested, dict)
            nested = nested["risk_locks"]
            assert isinstance(nested, list)
            nested = nested[0]
        elif location == "position_cost":
            assert isinstance(nested, dict)
            nested = nested["position_costs"]
            assert isinstance(nested, list)
            nested = nested[0]
        elif location == "fifo_entry":
            assert isinstance(nested, dict)
            nested = nested["fifo_open_entries"]
            assert isinstance(nested, list)
            nested = nested[0]
        assert isinstance(nested, dict)
        nested["unexpected"] = "tampered"

        with pytest.raises(ValueError, match="unexpected fields"):
            result_module.BacktestRuntimeStateSnapshot.from_payload(payload)

    @pytest.mark.parametrize(
        ("location", "path"),
        [
            ("audit_root", ()),
            ("fill", ("fills", 0)),
            ("daily_snapshot", ("daily_snapshots", 0)),
            ("account", ("daily_snapshots", 0, "account")),
            ("position", ("daily_snapshots", 0, "account", "positions", 0)),
            ("closed_trade", ("closed_trades", 0)),
            ("risk_record", ("risk_log", 0)),
            ("pre_trade_record", ("pre_trade_log", 0)),
        ],
    )
    def test_v2_runtime_rejects_unknown_audit_fields_at_every_typed_level(
        self,
        location: str,
        path: tuple[str | int, ...],
    ) -> None:
        """V2 decode must fail closed before an audit subtree can be hashed."""
        audit_payload = _complete_audit_state_payload()
        _nested_mapping(audit_payload, path)["unexpected"] = location
        audit_state_json = orjson.dumps(
            audit_payload,
            option=orjson.OPT_SORT_KEYS,
        ).decode()
        direct_snapshot = result_module.BacktestRuntimeStateSnapshot.from_state(
            result_module.BacktestRuntimeStateCapture(
                trade_builder_state=TradeBuilderStateSnapshot(
                    method=TradeMatchingMethod.FIFO,
                    counter=0,
                ),
                rebalance_calendar_start="2026-03-01",
                audit_state_json=audit_state_json,
            )
        )
        payload = {
            "audit_state_json": audit_state_json,
            "brokerage_fill_counter": 1,
            "delayed_signals": [],
            "pending_orders": [],
            "planner_id_counter": 0,
            "rebalance_calendar_start": "2026-03-01",
            "runtime_state_version": 2,
            "strategy_context": {"position_costs": [], "risk_locks": []},
            "trade_builder_state": {
                "counter": 0,
                "fifo_open_entries": [],
                "method": "fifo",
            },
        }

        assert direct_snapshot.is_exact_resume_state is False
        with pytest.raises(ValueError, match="canonical"):
            result_module.BacktestRuntimeStateSnapshot.from_payload(payload)

    def test_flat_to_flat_runtime_state_round_trip(self) -> None:
        """Flat-to-flat accumulators retain nullable dates and numeric state."""
        trade_state = TradeBuilderStateSnapshot(
            method=TradeMatchingMethod.FLAT_TO_FLAT,
            counter=3,
            flat_to_flat_accumulators=(
                FlatToFlatAccumulatorSnapshot(
                    instrument_id=IID_1,
                    entry_order_ids=("plan-order-1",),
                    exit_order_ids=(),
                    net_quantity=100,
                    buy_quantity=100,
                    buy_total_cost=1_000.0,
                    buy_fees=5.0,
                    sell_quantity=0,
                    sell_total_proceeds=0.0,
                    sell_fees=0.0,
                    first_entry_date=date(2026, 3, 1),
                    last_entry_date=date(2026, 3, 1),
                    first_exit_date=None,
                    last_exit_date=None,
                ),
            ),
        )
        snapshot = result_module.BacktestRuntimeStateSnapshot.from_state(
            result_module.BacktestRuntimeStateCapture(
                planner_id_counter=1,
                trade_builder_state=trade_state,
                rebalance_calendar_start="2026-03-01",
                audit_state_json=ExecutionAuditStateSnapshot().to_json(),
            )
        )

        restored = result_module.BacktestRuntimeStateSnapshot.from_json(
            snapshot.to_json()
        )

        assert restored.trade_builder_state == trade_state

    def test_versioned_runtime_rejects_noncanonical_audit_json(self) -> None:
        """Hash evidence uses the canonical typed audit representation only."""
        snapshot = result_module.BacktestRuntimeStateSnapshot.from_state(
            result_module.BacktestRuntimeStateCapture(
                trade_builder_state=TradeBuilderStateSnapshot(
                    method=TradeMatchingMethod.FIFO,
                    counter=0,
                ),
                rebalance_calendar_start="2026-03-01",
                audit_state_json='{ "fills": [] }',
            )
        )

        assert snapshot.is_exact_resume_state is False
        with pytest.raises(ValueError, match="runtime state is incomplete"):
            snapshot.to_json()

    def test_runtime_state_preserves_pending_execution_order(self) -> None:
        """Checkpoint arrays must preserve OrderBook insertion/execution order."""
        tickets = tuple(
            OrderTicket(
                order=_sample_order(client_order_id),
                status=OrderStatus.SUBMITTED,
            )
            for client_order_id in ("plan-order-9", "plan-order-10")
        )

        snapshot = result_module.BacktestRuntimeStateSnapshot.from_state(
            result_module.BacktestRuntimeStateCapture(pending_tickets=tickets)
        )

        assert [item.client_order_id for item in snapshot.pending_orders] == [
            "plan-order-9",
            "plan-order-10",
        ]

    def test_runtime_state_preserves_strategy_context_iteration_order(self) -> None:
        """Strategy context mappings can feed order-sensitive pipeline code."""
        snapshot = result_module.BacktestRuntimeStateSnapshot.from_state(
            result_module.BacktestRuntimeStateCapture(
                strategy_context=StrategyContextSnapshot(
                    risk_locked_instruments={
                        InstrumentId(2): ("second", "2026-03-10"),
                        InstrumentId(1): ("first", "2026-03-10"),
                    },
                    positions={InstrumentId(2): 20.0, InstrumentId(1): 10.0},
                ),
            )
        )

        assert [
            item.instrument_id for item in snapshot.strategy_context.risk_locks
        ] == [
            InstrumentId(2),
            InstrumentId(1),
        ]
        assert [
            item.instrument_id for item in snapshot.strategy_context.position_costs
        ] == [InstrumentId(2), InstrumentId(1)]


# ---------------------------------------------------------------------------
# EngineResultBuilder 测试
# ---------------------------------------------------------------------------


class TestEngineResultBuilder:
    """EngineResultBuilder 可变累积 + build() 产出不可变结果。"""

    def test_initial_state_empty(self) -> None:
        builder = EngineResultBuilder()
        assert builder.orders == []
        assert builder.fills == []
        assert builder.skipped == []

    def test_add_order(self) -> None:
        builder = EngineResultBuilder()
        order = _sample_order()
        builder.add_order(order)
        assert len(builder.orders) == 1
        assert builder.orders[0] is order

    def test_add_fill(self) -> None:
        builder = EngineResultBuilder()
        fill = _sample_fill()
        builder.add_fill(fill)
        assert len(builder.fills) == 1
        assert builder.fills[0] is fill

    def test_add_skipped(self) -> None:
        builder = EngineResultBuilder()
        builder.add_skipped("2026-01-05")
        assert builder.skipped == ["2026-01-05"]

    def test_extend_orders(self) -> None:
        builder = EngineResultBuilder()
        orders = [_sample_order(), _sample_order()]
        builder.extend_orders(orders)
        assert len(builder.orders) == 2

    def test_extend_fills(self) -> None:
        builder = EngineResultBuilder()
        fills = [_sample_fill(), _sample_fill()]
        builder.extend_fills(fills)
        assert len(builder.fills) == 2

    def test_build_produces_frozen_result(self) -> None:
        builder = EngineResultBuilder()
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert isinstance(result, EngineResult)
        with pytest.raises(FrozenInstanceError):
            result.final_nav = 0.0  # type: ignore[misc]

    def test_build_orders_as_tuple(self) -> None:
        builder = EngineResultBuilder()
        order = _sample_order()
        builder.add_order(order)
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert result.orders == (order,)

    def test_build_fills_as_tuple(self) -> None:
        builder = EngineResultBuilder()
        fill = _sample_fill()
        builder.add_fill(fill)
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert result.fills == (fill,)

    def test_build_skipped_as_tuple(self) -> None:
        builder = EngineResultBuilder()
        builder.add_skipped("2026-01-05")
        builder.add_skipped("2026-01-06")
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert result.skipped_dates == ("2026-01-05", "2026-01-06")

    def test_build_total_trades_from_fills(self) -> None:
        builder = EngineResultBuilder()
        builder.add_fill(_sample_fill())
        builder.add_fill(_sample_fill())
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        assert result.total_trades == 2

    def test_build_copies_mutable_state(self) -> None:
        """build() 应将 list 转为 tuple，后续 builder 修改不影响已产出的 result。"""
        builder = EngineResultBuilder()
        builder.add_order(_sample_order())
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_000_000.0,
        )
        # 继续往 builder 添加
        builder.add_order(_sample_order())
        # result 不受影响
        assert len(result.orders) == 1

    def test_build_with_all_fields(self) -> None:
        """完整参数 build 测试。"""

        manifest = RunManifest(
            run_id="run-001",
            strategy_id="test-strategy",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-01T00:00:00Z",
            spec_hash="a" * 64,
            base_spec_hash="b" * 64,
            parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
        )
        order = _sample_order()
        fill = _sample_fill()
        checkpoint = _checkpoint_cls()(
            run_id="run-001",
            strategy_id="test-strategy",
            completed_trade_date="2026-01-05",
            resume_from="2026-01-06",
            completed_days=1,
            total_days=2,
            nav=1_050_000.0,
            fill_count=1,
            order_count=1,
        )
        builder = EngineResultBuilder()
        builder.add_order(order)
        builder.add_fill(fill)
        builder.add_skipped("2026-01-05")
        result = builder.build(
            run_id="run-001",
            period=("2026-01-01", "2026-01-31"),
            final_nav=1_050_000.0,
            account_view=None,
            manifest=manifest,
            last_checkpoint=checkpoint,
            cancelled=True,
        )
        assert result.run_id == "run-001"
        assert result.final_nav == 1_050_000.0
        assert result.total_trades == 1
        assert result.orders == (order,)
        assert result.fills == (fill,)
        assert result.skipped_dates == ("2026-01-05",)
        assert result.manifest is manifest
        assert result.last_checkpoint is checkpoint
        assert result.cancelled is True


# ---------------------------------------------------------------------------
# assemble_engine_result 集成测试
# ---------------------------------------------------------------------------


class TestAssembleEngineResult:
    """assemble_engine_result 应返回 frozen EngineResult。"""

    def test_returns_frozen_result(self) -> None:
        from ditto_backtest.engine_steps import (
            EngineResultAssemblyContext,
            assemble_engine_result,
        )

        account_view = _sample_account_view()
        manifest = RunManifest(
            run_id="run-001",
            strategy_id="test-strategy",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-01T00:00:00Z",
            spec_hash="a" * 64,
            base_spec_hash="b" * 64,
            parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
        )
        result = assemble_engine_result(
            EngineResultAssemblyContext(
                run_id="run-001",
                start="2026-01-01",
                end="2026-01-31",
                account_view=account_view,
                manifest=manifest,
                fills=[],
                orders=[],
                skipped=[],
                cancelled=False,
            )
        )
        with pytest.raises(FrozenInstanceError):
            result.final_nav = 0.0  # type: ignore[misc]

    def test_accepts_assembly_context_object(self) -> None:
        from ditto_backtest.engine_steps import (
            EngineResultAssemblyContext,
            assemble_engine_result,
        )

        account_view = _sample_account_view()
        manifest = RunManifest(
            run_id="run-context",
            strategy_id="test-strategy",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-01T00:00:00Z",
            spec_hash="a" * 64,
            base_spec_hash="b" * 64,
            parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
        )
        order = _sample_order()
        fill = _sample_fill()

        result = assemble_engine_result(
            EngineResultAssemblyContext(
                run_id="run-context",
                start="2026-01-01",
                end="2026-01-31",
                account_view=account_view,
                manifest=manifest,
                fills=[fill],
                orders=[order],
                skipped=["2026-01-05"],
                cancelled=True,
            )
        )

        assert result.run_id == "run-context"
        assert result.period == ("2026-01-01", "2026-01-31")
        assert result.final_nav == account_view.nav
        assert result.orders == (order,)
        assert result.fills == (fill,)
        assert result.skipped_dates == ("2026-01-05",)
        assert result.cancelled is True

    def test_orders_and_fills_are_tuples(self) -> None:
        from ditto_backtest.engine_steps import (
            EngineResultAssemblyContext,
            assemble_engine_result,
        )

        order = _sample_order()
        fill = _sample_fill()
        account_view = _sample_account_view()
        manifest = RunManifest(
            run_id="run-001",
            strategy_id="test-strategy",
            strategy_version="1.0",
            mode=RunMode.BACKTEST,
            created_at="2026-01-01T00:00:00Z",
            spec_hash="a" * 64,
            base_spec_hash="b" * 64,
            parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
        )
        result = assemble_engine_result(
            EngineResultAssemblyContext(
                run_id="run-001",
                start="2026-01-01",
                end="2026-01-31",
                account_view=account_view,
                manifest=manifest,
                fills=[fill],
                orders=[order],
                skipped=["2026-01-05"],
                cancelled=False,
            )
        )
        assert isinstance(result.orders, tuple)
        assert isinstance(result.fills, tuple)
        assert result.orders == (order,)
        assert result.fills == (fill,)
        assert result.skipped_dates == ("2026-01-05",)
