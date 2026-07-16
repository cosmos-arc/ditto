"""ManualSizingService 的 A 股建议数量规则。"""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution import manual_sizing
from ditto_application.processes.execution.manual_sizing import (
    ManualSizingContext,
    ManualSizingRequest,
    ManualSizingService,
)
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
from ditto_application.queries.account import AccountBaselineReadModel
from ditto_execution.models import AccountSnapshotRecord, PositionRecord
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.models import TargetPortfolio


class _AccountBaselineQuery:
    def __init__(self, result: AccountBaselineReadModel | None) -> None:
        self.result = result
        self.calls: list[dict[str, str]] = []

    def get_latest(
        self,
        *,
        account_id: str,
        strategy_id: str,
        signal_date: str,
    ) -> AccountBaselineReadModel | None:
        self.calls.append(
            {
                "account_id": account_id,
                "strategy_id": strategy_id,
                "signal_date": signal_date,
            }
        )
        return self.result


class _MarketQuery:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame
        self.calls: list[dict[str, object]] = []

    def find_bars(self, **kwargs: object) -> pl.DataFrame:
        self.calls.append(kwargs)
        return self.frame


class _PositionReader:
    def __init__(self, positions: dict[int, float]) -> None:
        self._positions = positions

    def get_current_positions(self, strategy_id: str) -> dict[int, float]:
        return dict(self._positions)


def _baseline() -> AccountBaselineReadModel:
    account = AccountSnapshotRecord(
        snapshot_id="baseline-1",
        run_id="manual-paper-a-strategy-a",
        strategy_id="strategy-a",
        account_id="paper-a",
        snapshot_date="2026-02-13",
        cash_available=6_000.0,
        cash_settled=6_000.0,
        cash_frozen=0.0,
        total_value=10_000.0,
        nav=1.0,
        exposure=4_000.0,
    )
    position = PositionRecord(
        snapshot_id="position-1",
        run_id=account.run_id,
        strategy_id=account.strategy_id,
        snapshot_date=account.snapshot_date,
        instrument_id=510300,
        quantity=400,
        available_quantity=300,
        average_cost=9.5,
        market_value=4_000.0,
        unrealized_pnl=200.0,
        realized_pnl=0.0,
        total_fees=1.0,
    )
    return AccountBaselineReadModel(account=account, positions=(position,))


def _request(**overrides: object) -> ManualSizingRequest:
    values: dict[str, object] = {
        "direction": "buy",
        "target_weight": 0.115,
        "nav": 10_000.0,
        "current_quantity": 0,
        "available_quantity": 0,
        "cash_available": 10_000.0,
        "reference_price": 10.0,
        "lot_size": 100,
    }
    values.update(overrides)
    return ManualSizingRequest(**values)  # type: ignore[arg-type]


def test_buy_150_raw_shares_rounds_down_to_one_board_lot() -> None:
    result = ManualSizingService().size(_request(target_weight=0.15, nav=10_000.0))

    assert result.raw_quantity == 150
    assert result.rounded_quantity == 100
    assert result.cash_impact == -1000.0
    assert result.reason == "rounded_down_to_board_lot"


def test_buy_is_capped_by_cash_and_risk_limit() -> None:
    result = ManualSizingService().size(
        _request(
            target_weight=0.8,
            cash_available=2_500.0,
            risk_quantity_limit=150,
        )
    )

    assert result.raw_quantity == 800
    assert result.rounded_quantity == 100
    assert result.reason == "capped_by_cash_and_risk_limit"


def test_buy_below_one_lot_is_reviewable_no_trade() -> None:
    result = ManualSizingService().size(_request(target_weight=0.05))

    assert result.raw_quantity == 50
    assert result.rounded_quantity == 0
    assert result.reason == "below_board_lot"
    assert result.readiness == "review"


def test_sell_uses_available_quantity_and_allows_odd_lot() -> None:
    result = ManualSizingService().size(
        _request(
            direction="sell",
            target_weight=0.0,
            current_quantity=250,
            available_quantity=150,
        )
    )

    assert result.raw_quantity == 250
    assert result.rounded_quantity == 150
    assert result.cash_impact == 1500.0
    assert result.reason == "t_plus1_available_quantity_cap"


def test_manual_sizing_delegates_to_simple_execution_planner() -> None:
    planner = MagicMock(wraps=SimpleExecutionPlanner())

    result = ManualSizingService(planner=planner).size(
        _request(target_weight=0.15, nav=10_000.0)
    )

    planner.plan.assert_called_once()
    assert result.direction == "buy"
    assert result.rounded_quantity == 100


def test_planner_reverses_stale_baseline_buy_hint_to_exact_sell_quantity() -> None:
    result = ManualSizingService().size(
        _request(
            direction="buy",
            target_weight=0.5,
            nav=10_000.0,
            current_quantity=100,
            available_quantity=100,
            reference_price=80.0,
        )
    )

    assert result.direction == "sell"
    assert result.raw_quantity == 38
    assert result.rounded_quantity == 38
    assert result.reason == "sell_quantity_available"


def test_planner_clears_complete_position_with_odd_lot() -> None:
    result = ManualSizingService().size(
        _request(
            direction="buy",
            target_weight=0.0,
            current_quantity=250,
            available_quantity=250,
        )
    )

    assert result.direction == "sell"
    assert result.raw_quantity == 250
    assert result.rounded_quantity == 250


@pytest.mark.parametrize(
    ("overrides", "expected_direction", "expected_quantity", "expected_reason"),
    [
        (
            {"target_weight": 0.2, "at_price_limit": True, "is_limit_up": True},
            "buy",
            0,
            "limit_up_no_buy",
        ),
        (
            {"target_weight": 0.2, "at_price_limit": True, "is_limit_down": True},
            "buy",
            200,
            "exact_board_lot",
        ),
        (
            {
                "target_weight": 0.0,
                "current_quantity": 200,
                "available_quantity": 200,
                "at_price_limit": True,
                "is_limit_down": True,
            },
            "sell",
            0,
            "limit_down_no_sell",
        ),
        (
            {
                "target_weight": 0.0,
                "current_quantity": 200,
                "available_quantity": 200,
                "at_price_limit": True,
                "is_limit_up": True,
            },
            "sell",
            200,
            "sell_quantity_available",
        ),
    ],
)
def test_price_limit_enforcement_is_directional(
    overrides: dict[str, object],
    expected_direction: str,
    expected_quantity: int,
    expected_reason: str,
) -> None:
    result = ManualSizingService().size(_request(**overrides))

    assert result.direction == expected_direction
    assert result.rounded_quantity == expected_quantity
    assert result.reason == expected_reason


def test_planner_risk_lock_blocks_reentry() -> None:
    result = ManualSizingService().size(
        _request(target_weight=0.5, is_risk_locked=True)
    )

    assert result.direction == "buy"
    assert result.rounded_quantity == 0
    assert result.reason == "risk_locked"
    assert result.readiness == "blocked"


def test_cash_cap_reserves_minimum_commission() -> None:
    blocked = ManualSizingService().size(
        _request(target_weight=0.1, cash_available=1_004.99)
    )
    affordable = ManualSizingService().size(
        _request(target_weight=0.1, cash_available=1_005.0)
    )

    assert blocked.rounded_quantity == 0
    assert blocked.reason == "capped_by_cash"
    assert blocked.cash_required == 0.0
    assert affordable.rounded_quantity == 100
    assert affordable.cash_required == 1_005.0


def test_missing_price_and_market_blocks_produce_no_fake_quantity() -> None:
    service = ManualSizingService()

    missing = service.size(_request(reference_price=None))
    suspended = service.size(_request(is_suspended=True))
    limit_up = service.size(_request(at_price_limit=True))

    assert (missing.rounded_quantity, missing.reason, missing.readiness) == (
        0,
        "missing_reference_price",
        "blocked",
    )
    assert suspended.reason == "suspended"
    assert suspended.readiness == "blocked"
    assert limit_up.reason == "price_limit"
    assert limit_up.readiness == "review"


def test_identical_input_is_deterministic() -> None:
    service = ManualSizingService()
    request = _request(target_weight=0.3)

    assert service.size(request) == service.size(request)


def test_signal_snapshot_writes_suggested_quantity_only_with_current_context() -> None:
    reader = _PositionReader({})
    target = TargetPortfolio(
        trade_date="2026-03-20",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(510300): 0.15},
    )
    process = SignalSnapshotProcess(
        position_reader=reader,
        sizing_service=ManualSizingService(),
    )

    intent = process.generate_intents(
        strategy_id="strategy-1",
        signal_date="2026-03-20",
        target=target,
        sizing_contexts={
            510300: ManualSizingContext(
                nav=10_000.0,
                current_quantity=0,
                available_quantity=0,
                cash_available=10_000.0,
                reference_price=10.0,
            )
        },
    )[0]

    assert intent.quantity == 100
    assert intent.raw_quantity == 150
    assert intent.rounded_quantity == 100
    assert intent.lot_size == 100
    assert intent.reference_price == 10.0
    assert intent.cash_impact == -1_000.0
    assert intent.sizing_reason == "rounded_down_to_board_lot"
    assert intent.sizing_readiness == "ready"


def test_signal_snapshot_keeps_blocked_sizing_evidence_when_price_is_missing() -> None:
    process = SignalSnapshotProcess(
        position_reader=_PositionReader({}),
        sizing_service=ManualSizingService(),
    )
    target = TargetPortfolio(
        trade_date="2026-03-20",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(510300): 0.15},
    )

    intent = process.generate_intents(
        strategy_id="strategy-1",
        signal_date="2026-03-20",
        target=target,
        sizing_contexts={
            510300: ManualSizingContext(
                nav=10_000.0,
                current_quantity=0,
                available_quantity=0,
                cash_available=10_000.0,
                reference_price=None,
                current_weight=0.0,
            )
        },
    )[0]

    assert intent.quantity == 0
    assert intent.raw_quantity == 0
    assert intent.rounded_quantity == 0
    assert intent.lot_size == 100
    assert intent.reference_price is None
    assert intent.cash_impact == 0.0
    assert intent.sizing_reason == "missing_reference_price"
    assert intent.sizing_readiness == "blocked"


def test_signal_snapshot_caps_aggregate_buys_by_account_cash() -> None:
    process = SignalSnapshotProcess(
        position_reader=_PositionReader({}),
        sizing_service=ManualSizingService(),
    )
    target = TargetPortfolio(
        trade_date="2026-03-20",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(1): 0.3, InstrumentId(2): 0.3},
    )
    contexts = {
        instrument_id: ManualSizingContext(
            nav=10_000.0,
            current_quantity=0,
            available_quantity=0,
            cash_available=4_000.0,
            reference_price=10.0,
            current_weight=0.0,
        )
        for instrument_id in (1, 2)
    }

    intents = process.generate_intents(
        strategy_id="strategy-1",
        signal_date="2026-03-20",
        target=target,
        sizing_contexts=contexts,
    )

    # 首笔 300 股占用 3,000 元 + 5 元最低佣金，剩余 995 元不足第二手。
    assert [intent.rounded_quantity for intent in intents] == [300, 0]
    assert sum(-(intent.cash_impact or 0.0) for intent in intents) == 3_000.0
    assert intents[1].sizing_reason == "capped_by_cash"


def test_signal_snapshot_prefers_account_baseline_weight_from_sizing_context() -> None:
    reader = _PositionReader({510300: 1.0})
    target = TargetPortfolio(
        trade_date="2026-02-13",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(510300): 0.4},
    )
    process = SignalSnapshotProcess(
        position_reader=reader,
        sizing_service=ManualSizingService(),
    )

    intents = process.generate_intents(
        strategy_id="strategy-1",
        signal_date="2026-02-13",
        target=target,
        sizing_contexts={
            510300: ManualSizingContext(
                nav=10_000.0,
                current_quantity=400,
                available_quantity=300,
                cash_available=6_000.0,
                reference_price=10.0,
                current_weight=0.4,
            )
        },
    )

    assert intents == []


def test_signal_snapshot_uses_planner_side_after_d_close_revaluation() -> None:
    """旧基线权重提示买入时，planner 仍应按 D 收盘价生成正确卖单。"""
    process = SignalSnapshotProcess(
        position_reader=_PositionReader({510300: 0.1}),
        sizing_service=ManualSizingService(),
    )
    target = TargetPortfolio(
        trade_date="2026-02-13",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(510300): 0.5},
    )

    intent = process.generate_intents(
        strategy_id="strategy-1",
        signal_date="2026-02-13",
        target=target,
        sizing_contexts={
            510300: ManualSizingContext(
                nav=10_000.0,
                current_quantity=100,
                available_quantity=100,
                cash_available=9_000.0,
                reference_price=80.0,
                current_weight=0.1,
            )
        },
    )[0]

    assert intent.current_weight == pytest.approx(0.8)
    assert intent.delta_weight == pytest.approx(-0.3)
    assert intent.direction == "sell"
    assert intent.quantity == 38


def test_signal_snapshot_excludes_positions_outside_explicit_account_context() -> None:
    process = SignalSnapshotProcess(
        position_reader=_PositionReader({999999: 0.5}),
        sizing_service=ManualSizingService(),
    )
    target = TargetPortfolio(
        trade_date="2026-02-13",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(510300): 0.1},
    )

    intents = process.generate_intents(
        strategy_id="strategy-1",
        signal_date="2026-02-13",
        target=target,
        sizing_contexts={
            510300: ManualSizingContext(
                nav=10_000.0,
                current_quantity=0,
                available_quantity=0,
                cash_available=10_000.0,
                reference_price=10.0,
                current_weight=0.0,
            )
        },
    )

    assert [intent.instrument_id for intent in intents] == [510300]


def test_signal_snapshot_sized_path_does_not_read_legacy_positions() -> None:
    reader = MagicMock(spec=["get_current_positions"])
    reader.get_current_positions.side_effect = RuntimeError("legacy reader unavailable")
    process = SignalSnapshotProcess(
        position_reader=reader,
        sizing_service=ManualSizingService(),
    )
    target = TargetPortfolio(
        trade_date="2026-02-13",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(510300): 0.1},
    )

    intents = process.generate_intents(
        strategy_id="strategy-1",
        signal_date="2026-02-13",
        target=target,
        sizing_contexts={
            510300: ManualSizingContext(
                nav=10_000.0,
                current_quantity=0,
                available_quantity=0,
                cash_available=10_000.0,
                reference_price=10.0,
                current_weight=0.0,
            )
        },
    )

    reader.get_current_positions.assert_not_called()
    assert [(intent.direction, intent.quantity) for intent in intents] == [("buy", 100)]


def test_signal_snapshot_authoritative_contexts_fail_closed_without_sizer() -> None:
    reader = MagicMock(spec=["get_current_positions"])
    reader.get_current_positions.side_effect = RuntimeError("legacy reader called")
    process = SignalSnapshotProcess(position_reader=reader)
    target = TargetPortfolio(
        trade_date="2026-02-13",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(510300): 0.1},
    )

    with pytest.raises(AppProcessError, match="sizing service is required"):
        process.generate_intents(
            strategy_id="strategy-1",
            signal_date="2026-02-13",
            target=target,
            sizing_contexts={
                510300: ManualSizingContext(
                    nav=10_000.0,
                    current_quantity=0,
                    available_quantity=0,
                    cash_available=10_000.0,
                    reference_price=10.0,
                )
            },
        )

    reader.get_current_positions.assert_not_called()


@pytest.mark.parametrize("sizing_contexts", [None, {}])
def test_signal_snapshot_empty_or_absent_contexts_use_legacy_compatibility(
    sizing_contexts: dict[int, ManualSizingContext] | None,
) -> None:
    reader = MagicMock(spec=["get_current_positions"])
    reader.get_current_positions.return_value = {510300: 0.1}
    process = SignalSnapshotProcess(position_reader=reader)
    target = TargetPortfolio(
        trade_date="2026-02-13",
        strategy_id="strategy-1",
        run_id="run-1",
        positions={InstrumentId(510300): 0.2},
    )

    intent = process.generate_intents(
        strategy_id="strategy-1",
        signal_date="2026-02-13",
        target=target,
        sizing_contexts=sizing_contexts,
    )[0]

    reader.get_current_positions.assert_called_once_with("strategy-1")
    assert (intent.current_weight, intent.direction) == (0.1, "buy")


def test_a_share_trade_date_resolver_skips_weekend_and_exchange_holiday() -> None:
    resolver = manual_sizing.AShareTradeDateResolver(
        trading_days=(
            "2026-02-13",
            "2026-02-24",
            "2026-02-25",
        )
    )

    dates = resolver.resolve(
        signal_date="2026-02-13",
        decision_date="2026-02-13",
    )

    assert dates.decision_date == "2026-02-13"
    assert dates.intended_trade_date == "2026-02-24"
    with pytest.raises(AppProcessError, match="intended_trade_date"):
        resolver.validate(
            signal_date="2026-02-13",
            decision_date="2026-02-13",
            intended_trade_date="2026-02-16",
        )


def test_context_builder_uses_explicit_account_baseline_and_exact_close() -> None:
    account_query = _AccountBaselineQuery(_baseline())
    market_query = _MarketQuery(
        pl.DataFrame(
            {
                "instrument_id": [510300, 159915],
                "trade_date": ["2026-02-13", "2026-02-13"],
                "close": [10.0, 5.0],
            }
        )
    )
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=account_query,
        market_query=market_query,
    )

    sizing = builder.build(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-02-13",
        instrument_ids=(159915,),
    )
    contexts = sizing.contexts

    assert sizing.account_id == "paper-a"
    assert sizing.sleeve_id == "manual-paper-a-strategy-a"
    assert contexts[510300] == ManualSizingContext(
        nav=10_000.0,
        current_quantity=400,
        available_quantity=300,
        cash_available=6_000.0,
        reference_price=10.0,
        tradability_reason="tradability_unverified",
        current_weight=0.4,
    )
    assert contexts[159915] == ManualSizingContext(
        nav=10_000.0,
        current_quantity=0,
        available_quantity=0,
        cash_available=6_000.0,
        reference_price=5.0,
        tradability_reason="tradability_unverified",
        current_weight=0.0,
    )
    assert account_query.calls == [
        {
            "account_id": "paper-a",
            "strategy_id": "strategy-a",
            "signal_date": "2026-02-13",
        }
    ]
    assert market_query.calls == [
        {
            "instrument_ids": [159915, 510300],
            "start": "2026-02-13",
            "end": "2026-02-13",
            "allow_experimental_data": False,
        }
    ]


def test_context_builder_proves_normal_etf_day_from_trade_and_limit_evidence() -> None:
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=_AccountBaselineQuery(_baseline()),
        market_query=_MarketQuery(
            pl.DataFrame(
                {
                    "instrument_id": [159915],
                    "trade_date": ["2026-02-13"],
                    "close": [5.0],
                    "pre_close": [4.9],
                    "volume": [1_000_000.0],
                    "amount": [5_000_000.0],
                }
            )
        ),
    )
    sizing = builder.build(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-02-13",
        instrument_ids=(159915,),
    )
    process = SignalSnapshotProcess(
        position_reader=_PositionReader({}),
        sizing_service=ManualSizingService(),
    )
    target = TargetPortfolio(
        trade_date="2026-02-13",
        strategy_id="strategy-a",
        run_id="run-1",
        positions={InstrumentId(159915): 0.2},
    )

    intent = process.generate_intents(
        strategy_id="strategy-a",
        signal_date="2026-02-13",
        target=target,
        sizing_contexts=sizing.contexts,
    )[0]

    assert intent.quantity == 400
    assert intent.sizing_readiness == "ready"
    assert intent.sizing_reason == "exact_board_lot"


def test_context_builder_blocks_zero_volume_etf_without_status_flags() -> None:
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=_AccountBaselineQuery(_baseline()),
        market_query=_MarketQuery(
            pl.DataFrame(
                {
                    "instrument_id": [159915],
                    "trade_date": ["2026-02-13"],
                    "close": [5.0],
                    "pre_close": [4.9],
                    "volume": [0.0],
                    "amount": [0.0],
                }
            )
        ),
    )

    context = builder.build(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-02-13",
        instrument_ids=(159915,),
    ).contexts[159915]

    assert context.tradability_reason == "tradability_unverified"


def test_context_builder_fails_closed_for_non_finite_market_values() -> None:
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=_AccountBaselineQuery(_baseline()),
        market_query=_MarketQuery(
            pl.DataFrame(
                {
                    "instrument_id": [159915],
                    "trade_date": ["2026-02-13"],
                    "close": [float("inf")],
                    "pre_close": [float("nan")],
                    "volume": [float("inf")],
                    "amount": [float("nan")],
                }
            )
        ),
    )

    context = builder.build(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-02-13",
        instrument_ids=(159915,),
    ).contexts[159915]

    assert context.reference_price is None
    assert context.is_suspended is False
    assert context.at_price_limit is False
    assert context.tradability_reason == "tradability_unverified"


@pytest.mark.parametrize("close", [4.5, 5.5, 4.0, 6.0])
def test_context_builder_marks_exchange_fund_limit_prices_for_review(
    close: float,
) -> None:
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=_AccountBaselineQuery(_baseline()),
        market_query=_MarketQuery(
            pl.DataFrame(
                {
                    "instrument_id": [159915],
                    "trade_date": ["2026-02-13"],
                    "close": [close],
                    "pre_close": [5.0],
                    "volume": [1_000_000.0],
                    "amount": [5_000_000.0],
                }
            )
        ),
    )

    context = builder.build(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-02-13",
        instrument_ids=(159915,),
    ).contexts[159915]

    assert context.at_price_limit is True
    assert context.tradability_reason is None


def test_context_builder_fails_closed_when_explicit_account_has_no_baseline() -> None:
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=_AccountBaselineQuery(None),
        market_query=_MarketQuery(pl.DataFrame()),
    )

    with pytest.raises(AppProcessError, match="Account baseline missing"):
        builder.build(
            account_id="paper-a",
            strategy_id="strategy-a",
            signal_date="2026-02-13",
            instrument_ids=(510300,),
        )


def test_context_builder_propagates_authoritative_tradability_flags() -> None:
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=_AccountBaselineQuery(_baseline()),
        market_query=_MarketQuery(
            pl.DataFrame(
                {
                    "instrument_id": [510300, 159915],
                    "trade_date": ["2026-02-13", "2026-02-13"],
                    "close": [10.0, 5.0],
                    "is_suspended": [True, False],
                    "is_limit_up": [False, True],
                    "is_limit_down": [False, False],
                }
            )
        ),
    )

    contexts = builder.build(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-02-13",
        instrument_ids=(159915,),
    ).contexts

    assert contexts[510300].is_suspended is True
    assert contexts[510300].at_price_limit is False
    assert contexts[510300].tradability_reason is None
    assert contexts[159915].is_suspended is False
    assert contexts[159915].at_price_limit is True
    assert contexts[159915].is_limit_up is True
    assert contexts[159915].is_limit_down is False
    assert contexts[159915].tradability_reason is None


@pytest.mark.parametrize(
    ("instrument_id", "limit_column", "direction", "target_weight"),
    [
        (510300, "is_limit_up", "sell", 0.0),
        (159915, "is_limit_down", "buy", 0.2),
    ],
)
def test_context_builder_keeps_opposite_limit_trade_blocked_when_suspension_unknown(
    instrument_id: int,
    limit_column: str,
    direction: str,
    target_weight: float,
) -> None:
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=_AccountBaselineQuery(_baseline()),
        market_query=_MarketQuery(
            pl.DataFrame(
                {
                    "instrument_id": [instrument_id],
                    "trade_date": ["2026-02-13"],
                    "close": [10.0 if instrument_id == 510300 else 5.0],
                    "is_limit_up": [limit_column == "is_limit_up"],
                    "is_limit_down": [limit_column == "is_limit_down"],
                }
            )
        ),
    )

    context = builder.build(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-02-13",
        instrument_ids=(instrument_id,),
    ).contexts[instrument_id]
    result = ManualSizingService().size(
        _request(
            direction=direction,
            target_weight=target_weight,
            nav=context.nav,
            current_quantity=context.current_quantity,
            available_quantity=context.available_quantity,
            cash_available=context.cash_available,
            reference_price=context.reference_price,
            instrument_id=instrument_id,
            at_price_limit=context.at_price_limit,
            is_limit_up=context.is_limit_up,
            is_limit_down=context.is_limit_down,
            tradability_reason=context.tradability_reason,
        )
    )

    assert context.tradability_reason == "tradability_unverified"
    assert result.direction == direction
    assert (result.rounded_quantity, result.reason, result.readiness) == (
        0,
        "tradability_unverified",
        "blocked",
    )


def test_context_builder_wires_only_explicit_per_instrument_risk_policy() -> None:
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=_AccountBaselineQuery(_baseline()),
        market_query=_MarketQuery(
            pl.DataFrame(
                {
                    "instrument_id": [510300, 159915],
                    "trade_date": ["2026-02-13", "2026-02-13"],
                    "close": [10.0, 5.0],
                    "is_suspended": [False, False],
                    "is_limit_up": [False, False],
                    "is_limit_down": [False, False],
                }
            )
        ),
    )

    contexts = builder.build(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-02-13",
        instrument_ids=(159915,),
        risk_locked_instruments=(159915,),
        risk_quantity_limits={510300: 150},
    ).contexts

    assert contexts[159915].is_risk_locked is True
    # Strategy target constraints (for example max_weight) are not quantity
    # limits.  A cap remains absent unless a typed risk-policy producer supplies it.
    assert contexts[159915].risk_quantity_limit is None
    assert contexts[510300].is_risk_locked is False
    assert contexts[510300].risk_quantity_limit == 150


def test_context_builder_rejects_untyped_risk_quantity_limit() -> None:
    builder = manual_sizing.ManualSizingContextBuilder(
        account_query=_AccountBaselineQuery(_baseline()),
        market_query=_MarketQuery(pl.DataFrame()),
    )
    limits: dict[int, int] = {}
    limits[510300] = 150.5  # type: ignore[assignment]

    with pytest.raises(
        AppProcessError,
        match="risk quantity limits must be non-negative integers",
    ):
        builder.build(
            account_id="paper-a",
            strategy_id="strategy-a",
            signal_date="2026-02-13",
            instrument_ids=(510300,),
            risk_quantity_limits=limits,
        )
