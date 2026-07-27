"""Canonical backtest-report evidence hashing for R3 comparisons."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import NoReturn, Protocol, cast

from ditto_analysis.experiments import (
    ArtifactRecord,
    AttemptId,
    BacktestRunId,
    CandidateId,
    ContentHash,
    DateWindow,
    ExperimentId,
    FoldId,
    LeaseFence,
    canonical_payload,
)
from ditto_analysis.experiments.persistence import validate_artifact_relative_path
from ditto_backtest.statistics import BacktestReport as _BacktestReport
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import FillEvent as _FillEvent

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._evidence_values import (
    comparison_error,
)

BACKTEST_REPORT_ARTIFACT_KIND = "backtest_report_evidence"
BACKTEST_REPORT_EVIDENCE_SCHEMA_ID = "ditto.r3.backtest-report-evidence"
BACKTEST_REPORT_EVIDENCE_SCHEMA_VERSION = 1
_ARTIFACT_ID_PREFIX = "backtest-report-evidence"
_REPORT_KEYS = frozenset(
    {
        "artifact_schema",
        "fill_log",
        "final_nav",
        "initial_cash",
        "nav_series",
        "period",
        "run_id",
    }
)
_SCHEMA_KEYS = frozenset({"id", "version"})
_FILL_KEYS = frozenset(
    {
        "correlation_id",
        "cumulative_quantity",
        "direction",
        "event_time",
        "fee",
        "fill_id",
        "fill_price",
        "filled_quantity",
        "instrument_id",
        "leaves_quantity",
        "order_id",
        "slippage",
    }
)
_PAIR_SIZE = 2


def _invalid(**details: object) -> NoReturn:
    comparison_error("invalid_backtest_report_evidence", **details)


def _exact_mapping(
    value: object,
    keys: frozenset[str],
    *,
    field_name: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _invalid(field=field_name)
    raw = cast("Mapping[object, object]", value)
    if any(type(key) is not str for key in raw) or frozenset(raw) != keys:
        _invalid(field=field_name)
    return cast("Mapping[str, object]", raw)


def _exact_list(value: object, *, field_name: str) -> list[object]:
    if type(value) is not list:
        _invalid(field=field_name)
    return cast("list[object]", value)


def _canonical_text(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _invalid(field=field_name)
    return value


def _is_exact_aware_utc_datetime(value: object) -> bool:
    if type(value) is not datetime or value.tzinfo is None:
        return False
    try:
        return value.utcoffset() == timedelta(0)
    except (OverflowError, TypeError, ValueError):
        return False


def _canonical_date(value: object, *, field_name: str) -> date:
    if type(value) is not str:
        _invalid(field=field_name)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _invalid(field=field_name)
    if parsed.isoformat() != value:
        _invalid(field=field_name)
    return parsed


def _canonical_datetime(value: object, *, field_name: str) -> datetime:
    if type(value) is not str:
        _invalid(field=field_name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _invalid(field=field_name)
    if parsed.isoformat() != value or not _is_exact_aware_utc_datetime(parsed):
        _invalid(field=field_name)
    return parsed


def _finite_float(
    value: object,
    *,
    field_name: str,
    minimum: float | None = None,
    strictly_positive: bool = False,
) -> float:
    if type(value) is not float or not math.isfinite(value):
        _invalid(field=field_name)
    if (minimum is not None and value < minimum) or (
        strictly_positive and value <= 0.0
    ):
        _invalid(field=field_name)
    return value


def _quantity(
    value: object,
    *,
    field_name: str,
    allow_zero: bool,
) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        _invalid(field=field_name)
    return value


def _period_dates(period: tuple[str, str]) -> tuple[date, date]:
    if type(period) is not tuple or len(period) != _PAIR_SIZE:
        _invalid(field="period")
    start = _canonical_date(period[0], field_name="period.start")
    end = _canonical_date(period[1], field_name="period.end")
    if start > end:
        _invalid(field="period")
    return start, end


def _decode_period(value: object) -> tuple[str, str]:
    raw = _exact_list(value, field_name="period")
    if len(raw) != _PAIR_SIZE:
        _invalid(field="period")
    start = _canonical_date(raw[0], field_name="period.start")
    end = _canonical_date(raw[1], field_name="period.end")
    if start > end:
        _invalid(field="period")
    return start.isoformat(), end.isoformat()


def _decode_nav_series(value: object) -> tuple[tuple[str, float], ...]:
    rows: list[tuple[str, float]] = []
    for raw_row in _exact_list(value, field_name="nav_series"):
        row = _exact_list(raw_row, field_name="nav_series.item")
        if len(row) != _PAIR_SIZE:
            _invalid(field="nav_series.item")
        parsed_date = _canonical_date(row[0], field_name="nav_series.date")
        nav = _finite_float(
            row[1],
            field_name="nav_series.nav",
            strictly_positive=True,
        )
        rows.append((parsed_date.isoformat(), nav))
    return tuple(rows)


def _decode_instrument_id(value: object) -> InstrumentId:
    if type(value) is not str:
        _invalid(field="fill_log.instrument_id")
    try:
        parsed = int(value)
    except ValueError:
        _invalid(field="fill_log.instrument_id")
    if parsed <= 0 or str(parsed) != value:
        _invalid(field="fill_log.instrument_id")
    return InstrumentId(parsed)


def _decode_direction(value: object) -> OrderSide:
    if type(value) is not str:
        _invalid(field="fill_log.direction")
    try:
        return OrderSide(value)
    except ValueError:
        _invalid(field="fill_log.direction")


def _optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _canonical_text(value, field_name=field_name)


@dataclass(frozen=True, slots=True)
class BacktestFillEvidence:
    """The exact fill facts consumed by R3 comparison evidence."""

    correlation_id: str | None
    cumulative_quantity: int
    direction: OrderSide
    event_time: datetime
    fee: float
    fill_id: str
    fill_price: float
    filled_quantity: int
    instrument_id: InstrumentId
    leaves_quantity: int
    order_id: str
    slippage: float

    def __post_init__(self) -> None:
        """Reject values that cannot be exact completed-fill evidence."""
        _optional_text(self.correlation_id, field_name="fill_log.correlation_id")
        cumulative = _quantity(
            self.cumulative_quantity,
            field_name="fill_log.cumulative_quantity",
            allow_zero=False,
        )
        if type(self.direction) is not OrderSide:
            _invalid(field="fill_log.direction")
        if not _is_exact_aware_utc_datetime(self.event_time):
            _invalid(field="fill_log.event_time")
        _finite_float(self.fee, field_name="fill_log.fee", minimum=0.0)
        _canonical_text(self.fill_id, field_name="fill_log.fill_id")
        _finite_float(
            self.fill_price,
            field_name="fill_log.fill_price",
            strictly_positive=True,
        )
        filled = _quantity(
            self.filled_quantity,
            field_name="fill_log.filled_quantity",
            allow_zero=False,
        )
        if type(self.instrument_id) is not int or self.instrument_id <= 0:
            _invalid(field="fill_log.instrument_id")
        _quantity(
            self.leaves_quantity,
            field_name="fill_log.leaves_quantity",
            allow_zero=True,
        )
        _canonical_text(self.order_id, field_name="fill_log.order_id")
        _finite_float(self.slippage, field_name="fill_log.slippage")
        if cumulative < filled:
            _invalid(field="fill_log.cumulative_quantity")

    @classmethod
    def from_fill(cls, fill: _FillEvent) -> BacktestFillEvidence:
        """Project one exact backtest fill without inventing report fields."""
        if type(fill) is not _FillEvent:
            comparison_error("invalid_backtest_report")
        return cls(
            correlation_id=fill.correlation_id,
            cumulative_quantity=fill.cumulative_quantity,
            direction=fill.direction,
            event_time=fill.event_time,
            fee=fill.fee,
            fill_id=fill.fill_id,
            fill_price=fill.fill_price,
            filled_quantity=fill.filled_quantity,
            instrument_id=fill.instrument_id,
            leaves_quantity=fill.leaves_quantity,
            order_id=fill.order_id,
            slippage=fill.slippage,
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return the exact 12-field fill preimage used by the legacy hash API."""
        return {
            "correlation_id": self.correlation_id,
            "cumulative_quantity": self.cumulative_quantity,
            "direction": self.direction.value,
            "event_time": self.event_time.isoformat(),
            "fee": self.fee,
            "fill_id": self.fill_id,
            "fill_price": self.fill_price,
            "filled_quantity": self.filled_quantity,
            "instrument_id": str(self.instrument_id),
            "leaves_quantity": self.leaves_quantity,
            "order_id": self.order_id,
            "slippage": self.slippage,
        }


@dataclass(frozen=True, slots=True)
class BacktestReportEvidence:
    """Schema-v1 projection of only the report facts R3 comparisons consume."""

    run_id: str
    period: tuple[str, str]
    initial_cash: float
    final_nav: float
    nav_series: tuple[tuple[str, float], ...]
    fill_log: tuple[BacktestFillEvidence, ...]

    def __post_init__(self) -> None:
        """Validate complete typed values and same-period ordering constraints."""
        _canonical_text(self.run_id, field_name="run_id")
        period_start, period_end = _period_dates(self.period)
        _finite_float(self.initial_cash, field_name="initial_cash", minimum=0.0)
        _finite_float(
            self.final_nav,
            field_name="final_nav",
            strictly_positive=True,
        )
        if type(self.nav_series) is not tuple or not self.nav_series:
            _invalid(field="nav_series")
        previous: date | None = None
        for row in self.nav_series:
            if type(row) is not tuple or len(row) != _PAIR_SIZE:
                _invalid(field="nav_series.item")
            current = _canonical_date(row[0], field_name="nav_series.date")
            _finite_float(
                row[1],
                field_name="nav_series.nav",
                strictly_positive=True,
            )
            if (
                current < period_start
                or current > period_end
                or (previous is not None and current <= previous)
            ):
                _invalid(field="nav_series")
            previous = current
        if self.nav_series[-1][1] != self.final_nav:
            _invalid(field="final_nav")
        if type(self.fill_log) is not tuple or any(
            type(fill) is not BacktestFillEvidence for fill in self.fill_log
        ):
            _invalid(field="fill_log")
        fill_ids: set[str] = set()
        for fill in self.fill_log:
            if (
                fill.fill_id in fill_ids
                or fill.event_time.date() < period_start
                or fill.event_time.date() > period_end
            ):
                _invalid(field="fill_log")
            fill_ids.add(fill.fill_id)

    @classmethod
    def from_report(cls, report: _BacktestReport) -> BacktestReportEvidence:
        """Project an exact real report without reconstructing omitted fields."""
        if type(report) is not _BacktestReport or any(
            type(fill) is not _FillEvent for fill in report.fill_log
        ):
            comparison_error("invalid_backtest_report")
        return cls(
            run_id=report.run_id,
            period=report.period,
            initial_cash=report.initial_cash,
            final_nav=report.final_nav,
            nav_series=report.nav_series,
            fill_log=tuple(
                BacktestFillEvidence.from_fill(fill) for fill in report.fill_log
            ),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return the backward-compatible canonical Schema-v1 preimage."""
        return {
            "artifact_schema": {
                "id": BACKTEST_REPORT_EVIDENCE_SCHEMA_ID,
                "version": BACKTEST_REPORT_EVIDENCE_SCHEMA_VERSION,
            },
            "fill_log": [fill.canonical_payload() for fill in self.fill_log],
            "final_nav": self.final_nav,
            "initial_cash": self.initial_cash,
            "nav_series": [list(item) for item in self.nav_series],
            "period": list(self.period),
            "run_id": self.run_id,
        }

    @property
    def content_hash(self) -> ContentHash:
        """Hash the exact canonical artifact payload."""
        return canonical_payload(self.canonical_payload()).content_hash


def _decode_fill(value: object) -> BacktestFillEvidence:
    raw = _exact_mapping(value, _FILL_KEYS, field_name="fill_log.item")
    return BacktestFillEvidence(
        correlation_id=_optional_text(
            raw["correlation_id"],
            field_name="fill_log.correlation_id",
        ),
        cumulative_quantity=_quantity(
            raw["cumulative_quantity"],
            field_name="fill_log.cumulative_quantity",
            allow_zero=False,
        ),
        direction=_decode_direction(raw["direction"]),
        event_time=_canonical_datetime(
            raw["event_time"],
            field_name="fill_log.event_time",
        ),
        fee=_finite_float(raw["fee"], field_name="fill_log.fee", minimum=0.0),
        fill_id=_canonical_text(raw["fill_id"], field_name="fill_log.fill_id"),
        fill_price=_finite_float(
            raw["fill_price"],
            field_name="fill_log.fill_price",
            strictly_positive=True,
        ),
        filled_quantity=_quantity(
            raw["filled_quantity"],
            field_name="fill_log.filled_quantity",
            allow_zero=False,
        ),
        instrument_id=_decode_instrument_id(raw["instrument_id"]),
        leaves_quantity=_quantity(
            raw["leaves_quantity"],
            field_name="fill_log.leaves_quantity",
            allow_zero=True,
        ),
        order_id=_canonical_text(raw["order_id"], field_name="fill_log.order_id"),
        slippage=_finite_float(
            raw["slippage"],
            field_name="fill_log.slippage",
        ),
    )


def decode_backtest_report_evidence(
    payload: Mapping[str, object],
) -> BacktestReportEvidence:
    """Strictly decode one exact Schema-v1 report projection."""
    raw = _exact_mapping(payload, _REPORT_KEYS, field_name="report")
    schema = _exact_mapping(
        raw["artifact_schema"],
        _SCHEMA_KEYS,
        field_name="artifact_schema",
    )
    if (
        type(schema["id"]) is not str
        or schema["id"] != BACKTEST_REPORT_EVIDENCE_SCHEMA_ID
        or type(schema["version"]) is not int
        or schema["version"] != BACKTEST_REPORT_EVIDENCE_SCHEMA_VERSION
    ):
        _invalid(field="artifact_schema")
    return BacktestReportEvidence(
        run_id=_canonical_text(raw["run_id"], field_name="run_id"),
        period=_decode_period(raw["period"]),
        initial_cash=_finite_float(
            raw["initial_cash"],
            field_name="initial_cash",
            minimum=0.0,
        ),
        final_nav=_finite_float(
            raw["final_nav"],
            field_name="final_nav",
            strictly_positive=True,
        ),
        nav_series=_decode_nav_series(raw["nav_series"]),
        fill_log=tuple(
            _decode_fill(fill)
            for fill in _exact_list(raw["fill_log"], field_name="fill_log")
        ),
    )


def _legacy_report_payload(report: _BacktestReport) -> dict[str, object]:
    if type(report) is not _BacktestReport or any(
        type(fill) is not _FillEvent for fill in report.fill_log
    ):
        comparison_error("invalid_backtest_report")
    return {
        "artifact_schema": {
            "id": BACKTEST_REPORT_EVIDENCE_SCHEMA_ID,
            "version": BACKTEST_REPORT_EVIDENCE_SCHEMA_VERSION,
        },
        "fill_log": [
            {
                "correlation_id": fill.correlation_id,
                "cumulative_quantity": fill.cumulative_quantity,
                "direction": fill.direction.value,
                "event_time": fill.event_time.isoformat(),
                "fee": fill.fee,
                "fill_id": fill.fill_id,
                "fill_price": fill.fill_price,
                "filled_quantity": fill.filled_quantity,
                "instrument_id": str(fill.instrument_id),
                "leaves_quantity": fill.leaves_quantity,
                "order_id": fill.order_id,
                "slippage": fill.slippage,
            }
            for fill in report.fill_log
        ],
        "final_nav": report.final_nav,
        "initial_cash": report.initial_cash,
        "nav_series": [list(item) for item in report.nav_series],
        "period": list(report.period),
        "run_id": report.run_id,
    }


def backtest_report_content_hash(report: _BacktestReport) -> ContentHash:
    """Hash every report field used to recompute R3 comparison evidence."""
    return canonical_payload(_legacy_report_payload(report)).content_hash


def _identity_error(reason: str) -> NoReturn:
    raise AppProcessError(
        "backtest report artifact identity is invalid",
        details={"code": "SPEC_INVALID", "reason": reason},
    )


@dataclass(frozen=True, slots=True)
class BacktestReportArtifactIdentity:
    """Exact attempt lineage used to address one immutable report projection."""

    experiment_id: ExperimentId
    candidate_id: CandidateId
    fold_id: FoldId
    attempt_id: AttemptId
    attempt_created_at: datetime
    run_id: BacktestRunId
    test_window: DateWindow
    reproduction_fingerprint: ContentHash

    def __post_init__(self) -> None:
        """Reject erased or non-nominal lineage before deriving paths."""
        typed = (
            (self.experiment_id, ExperimentId),
            (self.candidate_id, CandidateId),
            (self.fold_id, FoldId),
            (self.attempt_id, AttemptId),
            (self.run_id, BacktestRunId),
            (self.test_window, DateWindow),
            (self.reproduction_fingerprint, ContentHash),
        )
        if any(
            type(value) is not expected for value, expected in typed
        ) or not _is_exact_aware_utc_datetime(self.attempt_created_at):
            _identity_error("invalid_backtest_report_artifact_identity")
        validate_artifact_relative_path(self.relative_path)

    @property
    def artifact_kind(self) -> str:
        """Return the stable index kind for Schema-v1 report evidence."""
        return BACKTEST_REPORT_ARTIFACT_KIND

    @property
    def artifact_id(self) -> str:
        """Return a deterministic ID over complete attempt/report identity."""
        identity_hash = canonical_payload(
            {
                "artifact_kind": BACKTEST_REPORT_ARTIFACT_KIND,
                "attempt_created_at": self.attempt_created_at.isoformat(),
                "attempt_id": str(self.attempt_id),
                "candidate_id": str(self.candidate_id),
                "experiment_id": str(self.experiment_id),
                "fold_id": str(self.fold_id),
                "reproduction_fingerprint": str(self.reproduction_fingerprint),
                "run_id": str(self.run_id),
                "test_window": {
                    "end": self.test_window.end.isoformat(),
                    "start": self.test_window.start.isoformat(),
                },
            }
        ).content_hash
        return f"{_ARTIFACT_ID_PREFIX}-{identity_hash}"

    @property
    def relative_path(self) -> str:
        """Return the exact attempt-scoped immutable JSON path."""
        return (
            f"experiments/{self.experiment_id}/candidates/{self.candidate_id}/"
            f"folds/{self.fold_id}/attempts/{self.attempt_id}/"
            "backtest-report-evidence.json"
        )


@dataclass(frozen=True, slots=True)
class LoadedBacktestReportArtifact:
    """One report projection paired with its verified immutable index fact."""

    record: ArtifactRecord
    evidence: BacktestReportEvidence

    def __post_init__(self) -> None:
        """Retain only exact frozen index and evidence values."""
        if (
            type(self.record) is not ArtifactRecord
            or type(self.evidence) is not BacktestReportEvidence
        ):
            _identity_error("invalid_loaded_backtest_report_artifact")


class BacktestReportArtifactPublisher(Protocol):
    """Attempt worker port for immutable report-evidence publication."""

    def publish(
        self,
        identity: BacktestReportArtifactIdentity,
        evidence: BacktestReportEvidence,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> ArtifactRecord:
        """Publish one exact report projection under the worker fence."""
        ...


class BacktestReportArtifactIndexReader(Protocol):
    """Narrow immutable-index metadata port consumed by the builder adapter."""

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        """Return one immutable indexed fact by deterministic identity."""
        ...

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None:
        """Return one immutable indexed fact by attempt-scoped path."""
        ...


class BacktestReportArtifactReader(Protocol):
    """Evidence-stage port for verified report-evidence reads."""

    def read(
        self,
        identity: BacktestReportArtifactIdentity,
    ) -> LoadedBacktestReportArtifact | None:
        """Return missing objectively, while failing closed on existing drift."""
        ...
