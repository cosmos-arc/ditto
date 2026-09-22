"""Pure time-weighted return contract tests over valuations and external flows."""

from decimal import Decimal

import pytest
from ditto_portfolio.account_ledger import FlowPosition
from ditto_portfolio.account_returns import (
    RETURN_METHOD_VERSION,
    ExternalFlow,
    ExternalFlowKind,
    ReturnReasonCode,
    ValuationObservation,
    compute_return_series,
)
from ditto_portfolio.errors import PortfolioError

D = Decimal


def _obs(pairs: tuple[tuple[str, str], ...]) -> tuple[ValuationObservation, ...]:
    return tuple(
        ValuationObservation(on_date=on_date, total_value=D(value))
        for on_date, value in pairs
    )


def _flow(
    on_date: str,
    amount: str,
    position: FlowPosition | None = FlowPosition.START_OF_DAY,
) -> ExternalFlow:
    return ExternalFlow(
        on_date=on_date,
        amount=D(amount),
        position=position,
        kind=ExternalFlowKind.CASH,
    )


def test_deposit_with_no_price_change_yields_zero_return() -> None:
    """100 -> deposit 100 -> 200 must be exactly 0% (spec hand-computed case)."""
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "200"))),
        flows=(_flow("2026-03-03", "100", FlowPosition.START_OF_DAY),),
    )
    assert series.method == RETURN_METHOD_VERSION
    assert series.points[1].period_return == D("0")
    assert series.segments[0].linked_return == D("0")


def test_two_ten_percent_subperiods_link_to_twenty_one_percent() -> None:
    """100 -> 110 -> deposit 100 -> 231 links 10% and 10% into 21%."""
    series = compute_return_series(
        observations=_obs(
            (("2026-03-02", "100"), ("2026-03-03", "110"), ("2026-03-04", "231"))
        ),
        flows=(_flow("2026-03-04", "100", FlowPosition.START_OF_DAY),),
    )
    assert series.points[1].period_return == D("0.1")
    assert series.points[2].period_return == D("0.1")
    assert series.segments[0].linked_return == D("0.21")


def test_end_of_day_flow_is_removed_from_period_end_value() -> None:
    """A closing-day deposit must not inflate the last leg's ending value."""
    series = compute_return_series(
        observations=_obs(
            (("2026-03-02", "100"), ("2026-03-03", "110"), ("2026-03-04", "220"))
        ),
        flows=(_flow("2026-03-04", "110", FlowPosition.END_OF_DAY),),
    )
    assert series.points[1].period_return == D("0.1")
    # 220 - 110 = 110 economic close over the 110 base => 0%, not +100%.
    assert series.points[2].period_return == D("0")
    assert series.segments[0].linked_return == D("0.1")


def test_opening_day_flow_joins_the_denominator_of_the_first_leg() -> None:
    """期初流先加入分母: the flow sits before the day's price movement."""
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "210"))),
        flows=(_flow("2026-03-03", "100", FlowPosition.START_OF_DAY),),
    )
    assert series.points[1].period_return == D("0.05")


def test_fee_is_not_an_external_flow_so_cash_drop_is_a_loss() -> None:
    """100 -> fee 1 -> 99 is -1%; fees never appear as flows here."""
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "99"))),
        flows=(),
    )
    assert series.points[1].period_return == D("-0.01")


def test_ex_dividend_position_drop_without_flow_is_zero_return() -> None:
    """Position 100 -> 95 plus 5 dividend cash inside the ledger value is 0%."""
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "100"))),
        flows=(),
    )
    assert series.points[1].period_return == D("0")


def test_withdrawal_of_everything_closes_segment_without_minus_hundred() -> None:
    """A full redemption's final leg is the pre-flow return, never -100%."""
    series = compute_return_series(
        observations=_obs(
            (("2026-03-02", "100"), ("2026-03-03", "110"), ("2026-03-04", "0"))
        ),
        flows=(_flow("2026-03-04", "-110", FlowPosition.END_OF_DAY),),
    )
    assert series.points[2].period_return == D("0")
    assert series.points[2].total_value == D("0")
    assert series.points[2].segment_id == 0
    assert series.segments[0].closed_reason == "full_withdrawal"
    assert series.segments[0].linked_return == D("0.1")


def test_loss_to_zero_records_minus_hundred_percent_and_closes() -> None:
    series = compute_return_series(
        observations=_obs(
            (("2026-03-02", "100"), ("2026-03-03", "50"), ("2026-03-04", "0"))
        ),
        flows=(),
    )
    assert series.points[2].period_return == D("-1")
    assert series.segments[0].linked_return == D("-1")
    assert series.segments[0].closed_reason == "loss_to_zero"


def test_redeposit_after_loss_to_zero_starts_a_new_segment() -> None:
    """New capital after a wipeout must not chain onto the dead segment."""
    series = compute_return_series(
        observations=_obs(
            (
                ("2026-03-02", "100"),
                ("2026-03-03", "0"),
                ("2026-03-04", "120"),
                ("2026-03-05", "132"),
            )
        ),
        flows=(_flow("2026-03-04", "120", FlowPosition.START_OF_DAY),),
    )
    assert [segment.segment_id for segment in series.segments] == [0, 1]
    assert series.segments[0].linked_return == D("-1")
    assert series.segments[1].start_date == "2026-03-04"
    assert series.segments[1].linked_return == D("0.1")
    assert series.points[2].segment_id == 1
    assert series.points[2].period_return is None


def test_valuation_gap_breaks_linking_and_starts_a_new_segment() -> None:
    observations = (
        *_obs((("2026-03-02", "100"), ("2026-03-03", "110"))),
        ValuationObservation(
            on_date="2026-03-05", total_value=D("120"), gap_before=True
        ),
    )
    series = compute_return_series(observations=observations, flows=())
    assert [segment.segment_id for segment in series.segments] == [0, 1]
    assert series.segments[0].end_date == "2026-03-03"
    assert series.segments[0].closed_reason == "valuation_gap"
    assert series.segments[1].start_date == "2026-03-05"
    assert series.points[2].period_return is None


def test_unknown_flow_timing_fails_the_leg_closed_with_reason() -> None:
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "220"))),
        flows=(_flow("2026-03-03", "100", None),),
    )
    assert series.points[1].period_return is None
    assert series.points[1].cumulative_return is None
    codes = {reason.code for reason in series.points[1].reasons}
    assert codes == {ReturnReasonCode.TIMING_UNKNOWN}
    assert series.segments[0].linked_return is None


def test_intraday_flow_without_boundary_valuations_fails_closed() -> None:
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "220"))),
        flows=(_flow("2026-03-03", "100", FlowPosition.INTRADAY),),
    )
    codes = {reason.code for reason in series.points[1].reasons}
    assert codes == {ReturnReasonCode.CASH_FLOW_VALUATION_MISSING}
    assert series.points[1].period_return is None


def test_security_transfer_fails_only_its_own_leg() -> None:
    series = compute_return_series(
        observations=_obs(
            (
                ("2026-03-02", "100"),
                ("2026-03-03", "150"),
                ("2026-03-04", "165"),
            )
        ),
        flows=(
            ExternalFlow(
                on_date="2026-03-03",
                amount=D("0"),
                position=None,
                kind=ExternalFlowKind.SECURITY_TRANSFER,
            ),
        ),
    )
    codes = {reason.code for reason in series.points[1].reasons}
    assert codes == {ReturnReasonCode.SECURITY_TRANSFER_UNSUPPORTED}
    assert series.points[1].period_return is None
    assert series.points[2].period_return == D("0.1")
    assert series.segments[0].linked_return is None


def test_negative_equity_is_reported_not_linkable() -> None:
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "-20"))),
        flows=(),
    )
    codes = {reason.code for reason in series.points[1].reasons}
    assert ReturnReasonCode.NEGATIVE_EQUITY_UNSUPPORTED in codes
    assert series.points[1].period_return is None
    assert series.segments[0].closed_reason == "negative_equity"


def test_single_point_segment_reports_no_interval_return() -> None:
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"),)),
        flows=(),
    )
    assert len(series.points) == 1
    assert series.points[0].total_value == D("100")
    assert series.points[0].period_return is None
    assert series.points[0].cumulative_return == D("0")
    assert series.segments[0].linked_return is None
    codes = {reason.code for reason in series.segments[0].reasons}
    assert ReturnReasonCode.SINGLE_POINT_SEGMENT in codes


def test_empty_observations_yield_an_empty_series() -> None:
    series = compute_return_series(observations=(), flows=())
    assert series.points == ()
    assert series.segments == ()


def test_first_observation_absorbs_its_flows_into_the_segment_base() -> None:
    """Flows on the range's first valuation date only move the base to 1."""
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "110"))),
        flows=(_flow("2026-03-02", "100", FlowPosition.START_OF_DAY),),
    )
    assert series.points[0].period_return is None
    assert series.points[1].period_return == D("0.1")


def test_duplicate_or_unsorted_observations_fail_closed() -> None:
    with pytest.raises(PortfolioError):
        compute_return_series(
            observations=_obs((("2026-03-02", "100"), ("2026-03-02", "110"))),
            flows=(),
        )
    with pytest.raises(PortfolioError):
        compute_return_series(
            observations=_obs((("2026-03-03", "100"), ("2026-03-02", "110"))),
            flows=(),
        )


def test_flow_outside_observation_window_is_ignored() -> None:
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "110"))),
        flows=(_flow("2026-03-10", "500", FlowPosition.START_OF_DAY),),
    )
    assert series.points[1].period_return == D("0.1")
    assert series.segments[0].linked_return == D("0.1")


def test_netted_same_position_flows_on_one_date_use_one_leg() -> None:
    series = compute_return_series(
        observations=_obs((("2026-03-02", "100"), ("2026-03-03", "180"))),
        flows=(
            _flow("2026-03-03", "100", FlowPosition.START_OF_DAY),
            _flow("2026-03-03", "-30", FlowPosition.START_OF_DAY),
        ),
    )
    # base 100 + 70 = 170, end 180 => ~5.88%.
    assert series.points[1].period_return == D("180") / D("170") - D("1")
    assert series.segments[0].linked_return == series.points[1].period_return
