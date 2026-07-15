"""Daily decision cockpit query facade tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_application.execution_dto import ActualPositionSnapshot, TradeIntent
from ditto_application.queries.deviation import (
    SignalDeviationItem,
    SignalDeviationReport,
)
from ditto_application.queries.portfolio_actual import PnlSummary


def _intent(
    *,
    intent_id: str = "intent-1",
    signal_date: str = "2024-01-15",
    instrument_id: int = 510300,
) -> TradeIntent:
    return TradeIntent(
        intent_id=intent_id,
        strategy_id="strat-a",
        signal_date=signal_date,
        instrument_id=instrument_id,
        direction="buy",
        target_weight=0.3,
        current_weight=0.1,
        delta_weight=0.2,
        quantity=1000,
        status="pending",
    )


def _position() -> ActualPositionSnapshot:
    return ActualPositionSnapshot(
        snapshot_id="snap-1",
        strategy_id="strat-a",
        snapshot_date="2024-01-15",
        instrument_id=510300,
        quantity=1000,
        available_quantity=1000,
        average_cost=4.0,
        market_value=4000.0,
        unrealized_pnl=10.0,
        realized_pnl=5.0,
        total_fees=1.0,
    )


def _deviation() -> SignalDeviationReport:
    return SignalDeviationReport(
        strategy_id="strat-a",
        signal_date="2024-01-15",
        total_signals=1,
        filled=1,
        unfilled=0,
        items=(
            SignalDeviationItem(
                instrument_id=510300,
                signal_action="buy",
                signal_weight=0.3,
                actual_weight=0.3,
                deviation_bps=0.0,
                fill_status="filled",
            ),
        ),
    )


def _pnl() -> PnlSummary:
    return PnlSummary(
        total_realized_pnl=5.0,
        total_unrealized_pnl=10.0,
        total_fees=1.0,
        net_pnl=14.0,
    )


def test_infers_latest_signal_date_from_signal_facade() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    signal_facade = MagicMock()
    signal_facade.get_latest_intents.return_value = [
        _intent(intent_id="old", signal_date="2024-01-14"),
        _intent(intent_id="new", signal_date="2024-01-15"),
    ]
    portfolio_facade = MagicMock()
    portfolio_facade.get_position_history.return_value = [_position()]
    portfolio_facade.compute_pnl.return_value = _pnl()
    deviation_facade = MagicMock()
    deviation_facade.get_deviation.return_value = _deviation()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
    ).get_report(strategy_id="strat-a")

    assert report.trade_date == "2024-01-15"
    signal_facade.get_latest_intents.assert_called_once_with("strat-a")
    portfolio_facade.get_position_history.assert_called_once_with(
        "strat-a",
        snapshot_date="2024-01-15",
    )
    deviation_facade.get_deviation.assert_called_once_with(
        strategy_id="strat-a",
        signal_date="2024-01-15",
    )


def test_returns_ready_report_with_daily_artifacts() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [_intent()]
    portfolio_facade = MagicMock()
    portfolio_facade.get_position_history.return_value = [_position()]
    portfolio_facade.compute_pnl.return_value = _pnl()
    deviation_facade = MagicMock()
    deviation_facade.get_deviation.return_value = _deviation()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
    ).get_report(strategy_id="strat-a", trade_date="2024-01-15")

    assert report.readiness_status == "ready"
    assert report.readiness_reasons == ()
    assert report.signal_intents == (_intent(),)
    assert report.positions == (_position(),)
    assert report.deviation == _deviation()
    assert report.pnl == _pnl()


def test_marks_review_when_positions_are_missing() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    signal_facade = MagicMock()
    signal_facade.get_intents_by_date.return_value = [_intent()]
    portfolio_facade = MagicMock()
    portfolio_facade.get_position_history.return_value = []
    portfolio_facade.compute_pnl.return_value = _pnl()
    deviation_facade = MagicMock()
    deviation_facade.get_deviation.return_value = _deviation()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
    ).get_report(strategy_id="strat-a", trade_date="2024-01-15")

    assert report.readiness_status == "review"
    assert report.readiness_reasons == ("positions unavailable for trade date",)


def test_returns_structured_blocked_report_when_no_signals_exist() -> None:
    from ditto_application.queries.daily_decision import DailyDecisionQueryFacade

    signal_facade = MagicMock()
    signal_facade.get_latest_intents.return_value = []
    portfolio_facade = MagicMock()
    deviation_facade = MagicMock()

    report = DailyDecisionQueryFacade(
        signal_facade=signal_facade,
        portfolio_facade=portfolio_facade,
        deviation_facade=deviation_facade,
    ).get_report(strategy_id="strat-a")

    assert report.strategy_id == "strat-a"
    assert report.trade_date is None
    assert report.readiness_status == "blocked"
    assert report.readiness_reasons == ("no signal intents available",)
    assert report.signal_intents == ()
    assert report.positions == ()
    assert report.deviation is None
    assert report.pnl is None
    portfolio_facade.get_position_history.assert_not_called()
    deviation_facade.get_deviation.assert_not_called()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"unresolved_conflict": True}, ("blocked", ("RERUN_CONFLICT",))),
        ({"run_outcome": "failed"}, ("blocked", ("RUN_FAILED",))),
        ({"package_exists": False}, ("blocked", ("PACKAGE_MISSING",))),
        ({"data_ready": False}, ("blocked", ("DATA_BLOCKED",))),
        (
            {"account_ready": False},
            ("blocked", ("ACCOUNT_BASELINE_MISSING",)),
        ),
        ({"no_rebalance": True}, ("review", ("NO_REBALANCE",))),
        ({"risk_warning": True}, ("review", ("RISK_WARNING",))),
        ({"date_mismatch": True}, ("review", ("DATE_MISMATCH",))),
        ({}, ("ready", ())),
    ],
)
def test_v2_readiness_truth_table(
    overrides: dict[str, object],
    expected: tuple[str, tuple[str, ...]],
) -> None:
    from ditto_application.queries.daily_decision import (
        ReadinessFacts,
        evaluate_readiness,
    )

    facts = ReadinessFacts(**overrides)  # type: ignore[arg-type]

    assert evaluate_readiness(facts) == expected
