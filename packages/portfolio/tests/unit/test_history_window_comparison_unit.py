"""Pure common-window comparison contract tests over per-leg return series."""

from decimal import Decimal

from ditto_portfolio.history_window_comparison import (
    COMMON_WINDOW_POLICY_VERSION,
    WindowLeg,
    WindowLegPoint,
    compare_common_windows,
)

D = Decimal


def _leg(kind: str, points: tuple[tuple[str, str | None, str | None, int | None], ...]):
    """Build one leg from (date, value, period_return, segment_id) rows."""
    return WindowLeg(
        kind=kind,
        points=tuple(
            WindowLegPoint(
                on_date=date,
                total_value=D("0") if value is None else D(value),
                period_return=None if ret is None else D(ret),
                segment_id=segment,
            )
            for date, value, ret, segment in points
        ),
    )


def _values(run, index: int, kind: str) -> Decimal:
    return run.points[index].growth[kind]


def test_policy_version_is_pinned() -> None:
    assert COMMON_WINDOW_POLICY_VERSION == "common-window-twr-v1"


def test_common_window_normalizes_each_leg_to_one_at_first_common_date() -> None:
    model = _leg(
        "model",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
        ),
    )
    paper = _leg(
        "paper",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "99", "-0.01", 0),
            ("2026-03-04", "108.90", "0.1", 0),
        ),
    )
    manual = _leg(
        "manual",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "100", "0", 0),
            ("2026-03-04", "101", "0.01", 0),
        ),
    )

    result = compare_common_windows((model, paper, manual))

    assert result.status == "comparable"
    assert result.empty_reason is None
    assert len(result.runs) == 1
    run = result.runs[0]
    assert (run.start_date, run.end_date) == ("2026-03-02", "2026-03-04")
    assert len(run.points) == 3
    for kind in ("model", "paper", "manual"):
        assert _values(run, 0, kind) == D("1")
    assert _values(run, 1, "model") == D("1.1")
    assert _values(run, 1, "paper") == D("0.99")
    assert _values(run, 1, "manual") == D("1")
    assert _values(run, 2, "model") == D("1.21")
    assert _values(run, 2, "paper") == D("1.089")
    assert _values(run, 2, "manual") == D("1.01")
    assert run.window_returns == {
        "model": D("1.21") - D("1"),
        "paper": D("1.089") - D("1"),
        "manual": D("1.01") - D("1"),
    }
    assert run.points[2].assets == {
        "model": D("121"),
        "paper": D("108.90"),
        "manual": D("101"),
    }


def test_external_flow_returns_still_link_exactly() -> None:
    # Manual 100→110→deposit 100→231 keeps both sub-legs at +10% (#249 hand
    # example): the deposit day carries an external flow, period return 0.1.
    model = _leg(
        "model",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "231", "0.1", 0),
        ),
    )
    paper = _leg(
        "paper",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "231", "0.1", 0),
        ),
    )
    manual = _leg(
        "manual",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "231", "0.1", 0),
        ),
    )

    run = compare_common_windows((model, paper, manual)).runs[0]

    assert _values(run, 2, "model") == D("1.21")
    assert run.window_returns == {
        "model": D("0.21"),
        "paper": D("0.21"),
        "manual": D("0.21"),
    }


def test_gap_day_in_one_leg_breaks_the_common_run() -> None:
    model = _leg(
        "model",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
            ("2026-03-05", "133.10", "0.1", 0),
        ),
    )
    paper = _leg(
        "paper",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            # 03-04 has no visible price: a gap row keeps a None segment.
            ("2026-03-04", None, None, None),
            ("2026-03-05", "133.10", None, 1),
        ),
    )
    manual = _leg(
        "manual",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
            ("2026-03-05", "133.10", "0.1", 0),
        ),
    )

    result = compare_common_windows((model, paper, manual))

    assert result.status == "comparable"
    assert [run.end_date for run in result.runs] == ["2026-03-03", "2026-03-05"]
    assert result.runs[0].window_returns == {
        "model": D("0.1"),
        "paper": D("0.1"),
        "manual": D("0.1"),
    }
    # The second run re-anchors to 1 at its own start; it never links across
    # the gap.
    assert _values(result.runs[1], 0, "paper") == D("1")


def test_refunding_new_segment_in_one_leg_breaks_the_common_run() -> None:
    # Paper depletes to zero (segment 0 closes) and re-funds on 03-04 with a
    # new segment: no cross-segment geometric linking even though every day
    # has a value.
    model = _leg(
        "model",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
        ),
    )
    paper = _leg(
        "paper",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "50", None, 1),
        ),
    )
    manual = _leg(
        "manual",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
        ),
    )

    result = compare_common_windows((model, paper, manual))

    assert [run.end_date for run in result.runs] == ["2026-03-03", "2026-03-04"]
    assert result.runs[1].points[0].assets["paper"] == D("50")


def test_unknown_flow_timing_day_breaks_linking_until_next_segment() -> None:
    # Manual's 03-03 return is timing-unknown (None) inside segment 0; its
    # later per-day returns stay individually valid but the segment link is
    # broken, so the common run cannot extend through it.
    model = _leg(
        "model",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
        ),
    )
    paper = _leg(
        "paper",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
        ),
    )
    manual = _leg(
        "manual",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "120", None, 0),
            ("2026-03-04", "132", "0.1", 0),
        ),
    )

    result = compare_common_windows((model, paper, manual))

    assert [(run.start_date, run.end_date) for run in result.runs] == [
        ("2026-03-02", "2026-03-02"),
        ("2026-03-03", "2026-03-04"),
    ]
    first, second = result.runs
    # A one-point run reports assets only, never a period return.
    assert all(value is None for value in first.window_returns.values())
    # The second run re-anchors at 03-03; the timing break stays behind it.
    assert second.points[0].growth["manual"] == D("1")
    assert second.window_returns["manual"] == D("0.1")


def test_single_common_point_shows_assets_without_returns() -> None:
    model = _leg("model", (("2026-03-02", "100", None, 0),))
    paper = _leg("paper", (("2026-03-02", "250", None, 0),))
    manual = _leg("manual", (("2026-03-02", "1000", None, 0),))

    result = compare_common_windows((model, paper, manual))

    assert result.status == "single_common_point"
    assert result.empty_reason is None
    assert len(result.runs) == 1
    assert len(result.runs[0].points) == 1
    assert result.runs[0].window_returns == {
        "model": None,
        "paper": None,
        "manual": None,
    }
    assert result.runs[0].points[0].assets == {
        "model": D("100"),
        "paper": D("250"),
        "manual": D("1000"),
    }


def test_no_common_valuation_dates_is_explicitly_incomparable() -> None:
    model = _leg("model", (("2026-03-02", "100", None, 0),))
    paper = _leg("paper", (("2026-03-04", "100", None, 0),))
    manual = _leg("manual", (("2026-03-06", "100", None, 0),))

    result = compare_common_windows((model, paper, manual))

    assert result.status == "incomparable"
    assert result.empty_reason == "no_common_valuation_dates"
    assert result.runs == ()


def test_empty_leg_series_is_incomparable_not_an_error() -> None:
    model = _leg("model", ())
    paper = _leg("paper", (("2026-03-02", "100", None, 0),))
    manual = _leg("manual", (("2026-03-02", "100", None, 0),))

    result = compare_common_windows((model, paper, manual))

    assert result.status == "incomparable"
    assert result.empty_reason == "no_common_valuation_dates"


def test_leg_valued_between_common_dates_compounds_into_the_next_stretch() -> None:
    # Manual values 03-03 while the model leg does not trade it: the stretch
    # 03-02→03-04 still links through the manual return chain.
    model = _leg(
        "model",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-04", "121", "0.21", 0),
        ),
    )
    paper = _leg(
        "paper",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "105", "0.05", 0),
            ("2026-03-04", "110.25", "0.05", 0),
        ),
    )
    manual = _leg(
        "manual",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "115.50", "0.05", 0),
        ),
    )

    run = compare_common_windows((model, paper, manual)).runs[0]

    assert (run.start_date, run.end_date) == ("2026-03-02", "2026-03-04")
    assert [point.on_date for point in run.points] == ["2026-03-02", "2026-03-04"]
    assert _values(run, 1, "model") == D("1.21")
    assert _values(run, 1, "paper") == D("1.1025")
    assert _values(run, 1, "manual") == D("1.155")


def test_unlinkable_middle_common_date_splits_into_runs() -> None:
    # Model segment restarts on 03-04 (re-funding) while paper/manual run on;
    # runs split but later common dates still form their own anchored run.
    model = _leg(
        "model",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "200", None, 1),
            ("2026-03-05", "220", "0.1", 1),
        ),
    )
    paper = _leg(
        "paper",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
            ("2026-03-05", "133.10", "0.1", 0),
        ),
    )
    manual = _leg(
        "manual",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
            ("2026-03-05", "133.10", "0.1", 0),
        ),
    )

    result = compare_common_windows((model, paper, manual))

    assert [(run.start_date, run.end_date) for run in result.runs] == [
        ("2026-03-02", "2026-03-03"),
        ("2026-03-04", "2026-03-05"),
    ]
    assert result.runs[1].points[0].growth["paper"] == D("1")
    assert result.runs[1].window_returns["model"] == D("0.1")


def test_isolated_common_point_between_breaks_is_its_own_run() -> None:
    # 03-03 has an unlinkable stretch into it for paper (timing unknown) and
    # 03-04 starts a fresh paper segment; 03-03 alone is a single-point run.
    model = _leg(
        "model",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
        ),
    )
    paper = _leg(
        "paper",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "120", None, 0),
            ("2026-03-04", "150", None, 1),
        ),
    )
    manual = _leg(
        "manual",
        (
            ("2026-03-02", "100", None, 0),
            ("2026-03-03", "110", "0.1", 0),
            ("2026-03-04", "121", "0.1", 0),
        ),
    )

    result = compare_common_windows((model, paper, manual))

    assert [(run.start_date, run.end_date) for run in result.runs] == [
        ("2026-03-02", "2026-03-02"),
        ("2026-03-03", "2026-03-03"),
        ("2026-03-04", "2026-03-04"),
    ]
    # Every run is a single point (paper breaks both stretches), so the whole
    # comparison reports assets only.
    assert result.status == "single_common_point"
    assert all(
        value is None for run in result.runs for value in run.window_returns.values()
    )
