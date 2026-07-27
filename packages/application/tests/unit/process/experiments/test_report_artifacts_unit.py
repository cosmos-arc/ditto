"""Unit tests for immutable R3 backtest-report evidence artifacts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from typing import cast

import pytest
from ditto_analysis.experiments import (
    AttemptId,
    BacktestRunId,
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    FoldId,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import _report_evidence as report_evidence
from ditto_backtest.statistics import (
    BacktestReport,
    empty_aggregated_trade_statistics,
    empty_alpha_statistics,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import FillEvent


def _report(*, event_time: datetime | None = None) -> BacktestReport:
    return BacktestReport(
        run_id="run-report-1",
        period=("2026-01-01", "2026-01-02"),
        initial_cash=100_000.0,
        final_nav=101_000.0,
        trade_stats=(),
        portfolio_stats=(),
        aggregated_trade_stats=empty_aggregated_trade_statistics(),
        alpha_stats=empty_alpha_statistics(),
        nav_series=(
            ("2026-01-01", 100_000.0),
            ("2026-01-02", 101_000.0),
        ),
        trade_log=(),
        fill_log=(
            FillEvent(
                fill_id="fill-1",
                order_id="order-1",
                instrument_id=InstrumentId(2_000_001),
                direction=OrderSide.BUY,
                filled_quantity=100,
                fill_price=10.0,
                fee=5.0,
                slippage=0.01,
                event_time=event_time
                if event_time is not None
                else datetime(2026, 1, 2, 9, 31, tzinfo=UTC),
                cumulative_quantity=100,
                leaves_quantity=0,
                correlation_id="correlation-1",
            ),
        ),
    )


def test_real_report_projects_to_schema_v1_without_losing_hash_facts() -> None:
    report = _report()

    evidence = report_evidence.BacktestReportEvidence.from_report(report)

    assert evidence.run_id == report.run_id
    assert evidence.period == report.period
    assert evidence.initial_cash == report.initial_cash
    assert evidence.final_nav == report.final_nav
    assert evidence.nav_series == report.nav_series
    assert len(evidence.fill_log) == 1
    assert evidence.fill_log[0].instrument_id == InstrumentId(2_000_001)
    assert evidence.fill_log[0].direction is OrderSide.BUY
    assert evidence.content_hash == report_evidence.backtest_report_content_hash(report)
    assert evidence.canonical_payload()["artifact_schema"] == {
        "id": "ditto.r3.backtest-report-evidence",
        "version": 1,
    }
    assert evidence.period == (
        date(2026, 1, 1).isoformat(),
        date(2026, 1, 2).isoformat(),
    )


def _payload() -> dict[str, object]:
    return report_evidence.BacktestReportEvidence.from_report(
        _report()
    ).canonical_payload()


def _mutate_schema_id(payload: dict[str, object]) -> None:
    cast("dict[str, object]", payload["artifact_schema"])["id"] = "unknown"


class _SchemaId(str):
    """Prove schema identity requires an exact built-in string."""


def _make_schema_id_str_subclass(payload: dict[str, object]) -> None:
    cast("dict[str, object]", payload["artifact_schema"])["id"] = _SchemaId(
        "ditto.r3.backtest-report-evidence"
    )


def _mutate_schema_version(payload: dict[str, object]) -> None:
    cast("dict[str, object]", payload["artifact_schema"])["version"] = 2


def _add_top_level_field(payload: dict[str, object]) -> None:
    payload["trade_stats"] = []


def _pad_run_id(payload: dict[str, object]) -> None:
    payload["run_id"] = " run-report-1"


def _invert_period(payload: dict[str, object]) -> None:
    payload["period"] = ["2026-01-02", "2026-01-01"]


def _make_period_noncanonical(payload: dict[str, object]) -> None:
    payload["period"] = ["20260101", "2026-01-02"]


def _unsort_nav(payload: dict[str, object]) -> None:
    payload["nav_series"] = [
        ["2026-01-02", 101_000.0],
        ["2026-01-01", 100_000.0],
    ]


def _move_nav_outside_period(payload: dict[str, object]) -> None:
    payload["nav_series"] = [["2025-12-31", 100_000.0]]
    payload["final_nav"] = 100_000.0


def _make_nav_bool(payload: dict[str, object]) -> None:
    cast("list[list[object]]", payload["nav_series"])[0][1] = True


def _make_final_nav_non_finite(payload: dict[str, object]) -> None:
    payload["final_nav"] = float("nan")


def _drift_final_nav_from_series(payload: dict[str, object]) -> None:
    payload["final_nav"] = 100_500.0


def _add_fill_field(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["venue"] = "XSHG"


def _make_fill_direction_invalid(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["direction"] = "hold"


def _make_fill_instrument_invalid(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["instrument_id"] = "020"


def _make_fill_quantity_bool(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["filled_quantity"] = True


def _make_fill_fee_negative(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["fee"] = -0.01


def _make_fill_slippage_non_finite(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["slippage"] = float("inf")


def _make_fill_time_noncanonical(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["event_time"] = (
        "2026-01-02T09:31:00Z"
    )


def _make_fill_time_naive(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["event_time"] = (
        "2026-01-02T09:31:00"
    )


def _make_fill_time_non_utc(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["event_time"] = (
        "2026-01-02T17:31:00+08:00"
    )


def _move_fill_outside_period(payload: dict[str, object]) -> None:
    cast("list[dict[str, object]]", payload["fill_log"])[0]["event_time"] = (
        "2025-12-31T09:31:00+00:00"
    )


def _duplicate_fill(payload: dict[str, object]) -> None:
    fills = cast("list[dict[str, object]]", payload["fill_log"])
    fills.append(dict(fills[0]))


@pytest.mark.parametrize(
    "mutate",
    [
        _mutate_schema_id,
        _make_schema_id_str_subclass,
        _mutate_schema_version,
        _add_top_level_field,
        _pad_run_id,
        _invert_period,
        _make_period_noncanonical,
        _unsort_nav,
        _move_nav_outside_period,
        _make_nav_bool,
        _make_final_nav_non_finite,
        _drift_final_nav_from_series,
        _add_fill_field,
        _make_fill_direction_invalid,
        _make_fill_instrument_invalid,
        _make_fill_quantity_bool,
        _make_fill_fee_negative,
        _make_fill_slippage_non_finite,
        _make_fill_time_noncanonical,
        _make_fill_time_naive,
        _make_fill_time_non_utc,
        _move_fill_outside_period,
        _duplicate_fill,
    ],
    ids=lambda mutate: cast("Callable[[dict[str, object]], None]", mutate).__name__,
)
def test_decoder_rejects_schema_identity_and_value_drift(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    payload = _payload()
    mutate(payload)

    with pytest.raises(AppProcessError) as exc_info:
        report_evidence.decode_backtest_report_evidence(payload)

    assert exc_info.value.details["reason"] == "invalid_backtest_report_evidence"


def test_decoder_returns_the_same_frozen_projection_and_hash() -> None:
    projected = report_evidence.BacktestReportEvidence.from_report(_report())

    decoded = report_evidence.decode_backtest_report_evidence(
        projected.canonical_payload()
    )

    assert decoded == projected
    assert decoded.content_hash == projected.content_hash


def test_projection_rejects_invalid_real_report_instead_of_normalizing_it() -> None:
    invalid = replace(
        _report(),
        nav_series=(
            ("2026-01-02", 101_000.0),
            ("2026-01-01", 100_000.0),
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        report_evidence.BacktestReportEvidence.from_report(invalid)

    assert exc_info.value.details["reason"] == "invalid_backtest_report_evidence"


class _DateTime(datetime):
    """Prove durable timestamps and fills require exact datetimes."""


@pytest.mark.parametrize(
    "event_time",
    [
        datetime(2026, 1, 2, 9, 31),
        datetime(2026, 1, 2, 17, 31, tzinfo=timezone(timedelta(hours=8))),
        _DateTime(2026, 1, 2, 9, 31, tzinfo=UTC),
    ],
)
def test_projection_rejects_non_exact_or_non_utc_fill_time(
    event_time: datetime,
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        report_evidence.BacktestReportEvidence.from_report(
            _report(event_time=event_time)
        )

    assert exc_info.value.details["reason"] == "invalid_backtest_report_evidence"


ATTEMPT_CREATED_AT = datetime(2026, 1, 3, 4, 5, 6, 789012, tzinfo=UTC)


def _artifact_identity(
    *,
    attempt: str = "attempt-1",
    run: str = "run-1",
    attempt_created_at: datetime = ATTEMPT_CREATED_AT,
) -> object:
    from ditto_application.processes.experiments._report_evidence import (
        BacktestReportArtifactIdentity,
    )

    return BacktestReportArtifactIdentity(
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=AttemptId(attempt),
        attempt_created_at=attempt_created_at,
        run_id=BacktestRunId(run),
        test_window=DateWindow(date(2026, 1, 1), date(2026, 1, 2)),
        reproduction_fingerprint=ContentHash("a" * 64),
    )


def test_report_artifact_identity_uses_exact_attempt_scoped_path_and_kind() -> None:
    from ditto_application.processes.experiments._report_evidence import (
        BACKTEST_REPORT_ARTIFACT_KIND,
        BacktestReportArtifactIdentity,
    )

    identity = cast("BacktestReportArtifactIdentity", _artifact_identity())

    assert BACKTEST_REPORT_ARTIFACT_KIND == "backtest_report_evidence"
    assert identity.artifact_kind == BACKTEST_REPORT_ARTIFACT_KIND
    assert identity.relative_path == (
        "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
        "attempts/attempt-1/backtest-report-evidence.json"
    )
    assert identity.artifact_id.startswith("backtest-report-evidence-")


def test_attempt_creation_time_is_part_of_artifact_identity_not_path() -> None:
    from ditto_application.processes.experiments._report_evidence import (
        BacktestReportArtifactIdentity,
    )

    first = cast("BacktestReportArtifactIdentity", _artifact_identity())
    later = cast(
        "BacktestReportArtifactIdentity",
        _artifact_identity(
            attempt_created_at=ATTEMPT_CREATED_AT + timedelta(microseconds=1)
        ),
    )

    assert later.artifact_id != first.artifact_id
    assert later.relative_path == first.relative_path


@pytest.mark.parametrize(
    "attempt_created_at",
    [
        datetime(2026, 1, 3, 4, 5, 6, 789012),
        datetime(
            2026,
            1,
            3,
            12,
            5,
            6,
            789012,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        _DateTime(2026, 1, 3, 4, 5, 6, 789012, tzinfo=UTC),
    ],
)
def test_report_artifact_identity_requires_exact_aware_utc_attempt_time(
    attempt_created_at: datetime,
) -> None:
    with pytest.raises(AppProcessError):
        _artifact_identity(attempt_created_at=attempt_created_at)


def test_retry_attempt_has_a_different_artifact_id_and_path() -> None:
    from ditto_application.processes.experiments._report_evidence import (
        BacktestReportArtifactIdentity,
    )

    first = cast("BacktestReportArtifactIdentity", _artifact_identity())
    retry = cast(
        "BacktestReportArtifactIdentity",
        _artifact_identity(attempt="attempt-2", run="run-2"),
    )

    assert retry.artifact_id != first.artifact_id
    assert retry.relative_path != first.relative_path
