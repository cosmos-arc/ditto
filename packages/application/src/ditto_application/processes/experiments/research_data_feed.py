"""Provider-free frozen exact/PIT data feed for R3 research execution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import polars as pl
from ditto_backtest.data_feed import Slice
from ditto_backtest.provenance import aggregate_source_snapshot_id
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import MarketSnapshot

from ditto_application.processes.experiments._research_data_feed_values import (
    date_expr as _date_expr,
)
from ditto_application.processes.experiments._research_data_feed_values import (
    exact_iso_date as _exact_iso_date,
)
from ditto_application.processes.experiments._research_data_feed_values import (
    iso_date_expr as _iso_date_expr,
)
from ditto_application.processes.experiments._research_data_feed_values import (
    market_snapshot as _market_snapshot,
)
from ditto_application.processes.experiments._research_data_feed_values import (
    valid_column_dtype as _valid_column_dtype,
)
from ditto_application.processes.experiments._research_data_feed_verification import (
    ResearchDataFeedVerificationMixin,
)
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
    ExactBenchmarkBinding,
    ResearchSnapshotBinding,
    research_data_feed_manifest_hash,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    DATE_COLUMNS as _DATE_COLUMNS,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    KEY_COLUMNS as _KEY_COLUMNS,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    NUMERIC_COLUMNS as _NUMERIC_COLUMNS,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    REQUIRED_COLUMNS as _REQUIRED_COLUMNS,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    FrozenResearchDataFrames,
    ResearchDataEvidenceManifest,
    ResearchFrameEvidenceManifest,
    ResearchFrameKind,
    VerifiedResearchFrame,
    research_artifact_content_hash,
    research_frame_schema_hash,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    research_data_error as _error,
)

__all__ = [
    "FrozenResearchDataFrames",
    "ResearchDataEvidenceManifest",
    "ResearchDataFeed",
    "ResearchFrameEvidenceManifest",
    "ResearchFrameKind",
    "VerifiedResearchFrame",
    "research_artifact_content_hash",
    "research_data_feed_manifest_hash",
    "research_frame_schema_hash",
]


def _exact_knowledge_lag_days(value: object) -> int:
    if type(value) is not int or value < 0:
        raise _error(
            "knowledge_lag_days must be an exact non-negative integer",
            "invalid_knowledge_lag_days",
        )
    return value


_FRAME_KINDS_BY_VALUE = {kind.value: kind for kind in ResearchFrameKind}
_SUPPORTED_KNOWN_AT_POLICIES = frozenset({"sample_time"})


class ResearchDataFeed(ResearchDataFeedVerificationMixin):
    """DataFeed backed exclusively by injected frozen research frames."""

    def __init__(
        self,
        *,
        snapshot: ResearchSnapshotBinding,
        frames: FrozenResearchDataFrames,
        start_date: str,
        end_date: str,
        knowledge_lag_days: int,
        benchmark: ExactBenchmarkBinding | None = None,
        expected_manifest_hash: str | None = None,
    ) -> None:
        if type(snapshot) is not ResearchSnapshotBinding:
            raise _error(
                "research feed requires an exact snapshot binding",
                "invalid_research_snapshot_binding",
            )
        if type(frames) is not FrozenResearchDataFrames:
            raise _error(
                "research feed requires exact frozen frame bindings",
                "invalid_research_frame_set",
            )
        self._snapshot = snapshot
        self._frames = frames
        self._start_date = _exact_iso_date(start_date, "start_date")
        self._end_date = _exact_iso_date(end_date, "end_date")
        self._knowledge_lag_days = _exact_knowledge_lag_days(knowledge_lag_days)
        if self._start_date > self._end_date:
            raise _error(
                "research execution start_date must not follow end_date",
                "invalid_execution_window",
                start_date=self._start_date,
                end_date=self._end_date,
            )
        if snapshot.known_at_policy not in _SUPPORTED_KNOWN_AT_POLICIES:
            raise _error(
                "research feed known_at_policy is unsupported",
                "unsupported_known_at_policy",
                known_at_policy=snapshot.known_at_policy,
            )
        if benchmark is not None and type(benchmark) is not ExactBenchmarkBinding:
            raise _error(
                "research benchmark requires an exact frozen binding",
                "invalid_benchmark_binding",
            )
        self._benchmark = benchmark
        self._benchmark_id = (
            None if benchmark is None else InstrumentId(benchmark.instrument_id)
        )
        self._expected_manifest_hash = expected_manifest_hash
        for kind, frame in frames.items():
            if type(frame) is not VerifiedResearchFrame:
                raise _error(
                    f"{kind.value} frame evidence is missing",
                    "missing_required_research_frame",
                    frame_kind=kind.value,
                )
        self._frames = replace(
            frames,
            bars=replace(frames.bars),
            calendar=replace(frames.calendar),
            membership=replace(frames.membership),
            fundamental=(
                None if frames.fundamental is None else replace(frames.fundamental)
            ),
            classification=(
                None
                if frames.classification is None
                else replace(frames.classification)
            ),
        )
        self._validate_frame_bindings()
        declared_manifest_hash = research_data_feed_manifest_hash(snapshot)
        if (
            expected_manifest_hash is not None
            and expected_manifest_hash != declared_manifest_hash
        ):
            raise _error(
                "expected feed manifest drifted from the exact snapshot",
                "data_feed_manifest_hash_drift",
                expected_manifest_hash=expected_manifest_hash,
                actual_manifest_hash=declared_manifest_hash,
            )
        self._validate_benchmark_binding()
        self._validate_pit_membership()
        self._validate_execution_sessions()
        self._validate_benchmark_coverage()
        self._evidence_manifest = self._build_evidence_manifest()
        if (
            self._expected_manifest_hash is not None
            and self._evidence_manifest.canonical_hash != self._expected_manifest_hash
        ):
            raise _error(
                "constructed feed manifest drifted from execution semantics",
                "data_feed_manifest_hash_drift",
            )

    def _build_evidence_manifest(self) -> ResearchDataEvidenceManifest:
        frames = tuple(
            ResearchFrameEvidenceManifest(
                frame_kind=kind,
                input_id=verified.input_evidence.input_id,
                content_hash=verified.input_evidence.content_hash,
                schema_hash=verified.input_evidence.schema_hash,
                source_snapshot_ids=verified.source_snapshot_ids,
            )
            for kind, verified in self._frames.items()
        )
        return ResearchDataEvidenceManifest(
            snapshot_id=self._snapshot.exact_snapshot.snapshot_id,
            snapshot_manifest_hash=self._snapshot.exact_snapshot.manifest_hash,
            source_snapshot_ids=self._snapshot.source_snapshot_ids,
            frames=frames,
            canonical_hash=research_data_feed_manifest_hash(self._snapshot),
        )

    @property
    def evidence_manifest(self) -> ResearchDataEvidenceManifest:
        """Return immutable hashes/sources for execution-bundle cross-checking."""
        return self._evidence_manifest

    def _validate_frame_bindings(self) -> None:
        """Bind every feed frame to an exact snapshot input and source set."""
        snapshot_inputs: dict[
            ResearchFrameKind,
            ContentAddressedResearchInput,
        ] = {}
        for evidence in self._snapshot.inputs:
            kind = _FRAME_KINDS_BY_VALUE.get(evidence.artifact_kind)
            if kind is None:
                continue
            if kind in snapshot_inputs:
                raise _error(
                    f"snapshot declares {kind.value} more than once",
                    "duplicate_feed_artifact_kind",
                    frame_kind=kind.value,
                )
            snapshot_inputs[kind] = evidence

        snapshot_sources = set(self._snapshot.source_snapshot_ids)
        frame_items = self._frames.items()
        supplied_kinds = {kind for kind, _ in frame_items}
        missing_declared = sorted(
            (kind for kind in snapshot_inputs if kind not in supplied_kinds),
            key=lambda kind: kind.value,
        )
        if missing_declared:
            kind = missing_declared[0]
            raise _error(
                f"snapshot-declared {kind.value} frame was not supplied",
                "missing_declared_research_frame",
                frame_kind=kind.value,
            )

        for kind, frame in frame_items:
            if type(frame) is not VerifiedResearchFrame:
                raise _error(
                    f"{kind.value} frame evidence is missing",
                    "missing_required_research_frame",
                    frame_kind=kind.value,
                )
            evidence = frame.input_evidence
            if evidence.artifact_kind != kind.value:
                raise _error(
                    f"{kind.value} frame is bound as {evidence.artifact_kind}",
                    "research_frame_kind_mismatch",
                    frame_kind=kind.value,
                    artifact_kind=evidence.artifact_kind,
                )
            if snapshot_inputs.get(kind) != evidence:
                raise _error(
                    f"{kind.value} frame is absent from exact snapshot inputs",
                    "frame_not_bound_to_exact_snapshot",
                    frame_kind=kind.value,
                    input_id=evidence.input_id,
                )
            unbound_sources = sorted(
                set(frame.source_snapshot_ids) - snapshot_sources,
            )
            if unbound_sources:
                raise _error(
                    f"{kind.value} frame uses unbound source snapshots",
                    "unbound_frame_source_snapshot",
                    frame_kind=kind.value,
                    source_snapshot_ids=unbound_sources,
                )
            self._validate_frame_schema(kind, frame)

    def _validate_benchmark_binding(self) -> None:
        if self._benchmark is None:
            return
        if (
            self._benchmark.mapping_input not in self._snapshot.inputs
            or self._benchmark.bars_input not in self._snapshot.inputs
            or self._benchmark.bars_input != self._frames.bars.input_evidence
        ):
            raise _error(
                "benchmark evidence drifted from the constructed frozen feed",
                "benchmark_input_evidence_drift",
            )

    @staticmethod
    def _validate_frame_schema(
        kind: ResearchFrameKind,
        verified: VerifiedResearchFrame,
    ) -> None:
        """Validate the exact runtime columns without coercing weak evidence."""
        frame = verified.frame
        missing = sorted(_REQUIRED_COLUMNS[kind] - set(frame.columns))
        if missing:
            raise _error(
                f"{kind.value} frame is missing required columns",
                "missing_frozen_frame_columns",
                frame_kind=kind.value,
                missing_columns=missing,
            )
        if frame.is_empty():
            raise _error(
                f"{kind.value} frame has no frozen rows",
                "empty_frozen_frame",
                frame_kind=kind.value,
            )
        schema = frame.schema
        required_columns = sorted(_REQUIRED_COLUMNS[kind])
        for column in required_columns:
            dtype = schema[column]
            if not _valid_column_dtype(column, dtype):
                raise _error(
                    f"{kind.value}.{column} has incompatible dtype {dtype}",
                    "invalid_frozen_frame_schema",
                    frame_kind=kind.value,
                    column=column,
                    dtype=str(dtype),
                )
        null_columns = [
            column for column in required_columns if frame[column].null_count() > 0
        ]
        if null_columns:
            raise _error(
                f"{kind.value} required columns contain null values",
                "null_frozen_frame_column",
                frame_kind=kind.value,
                columns=null_columns,
            )
        non_finite = [
            column
            for column in sorted(_REQUIRED_COLUMNS[kind] & _NUMERIC_COLUMNS)
            if not frame[column].is_finite().all()
        ]
        if non_finite:
            raise _error(
                f"{kind.value} numeric columns contain non-finite values",
                "non_finite_frozen_numeric",
                frame_kind=kind.value,
                columns=non_finite,
            )
        ResearchDataFeed._validate_frame_keys(kind, frame)
        raw_row_sources = frame["source_snapshot_id"].unique().to_list()
        if any(
            type(item) is not str or not item or item != item.strip()
            for item in raw_row_sources
        ):
            raise _error(
                f"{kind.value} contains invalid row provenance",
                "invalid_row_source_snapshot",
                frame_kind=kind.value,
            )
        row_sources = tuple(sorted(raw_row_sources))
        if row_sources != verified.source_snapshot_ids:
            raise _error(
                f"{kind.value} row provenance differs from verified evidence",
                "row_source_snapshot_mismatch",
                frame_kind=kind.value,
                row_source_snapshot_ids=list(row_sources),
                evidence_source_snapshot_ids=list(verified.source_snapshot_ids),
            )

    @staticmethod
    def _validate_frame_keys(
        kind: ResearchFrameKind,
        frame: pl.DataFrame,
    ) -> None:
        """Require valid, unique semantic keys after daily date normalization."""
        expressions = [
            (
                _date_expr(frame, column).alias(column)
                if column in _DATE_COLUMNS
                else pl.col(column)
            )
            for column in _KEY_COLUMNS[kind]
        ]
        try:
            keys = frame.select(expressions)
        except pl.exceptions.PolarsError:
            raise _error(
                f"{kind.value} contains an invalid frozen date value",
                "invalid_frozen_date_value",
                frame_kind=kind.value,
            ) from None
        if keys.null_count().row(0) != (0,) * len(keys.columns):
            raise _error(
                f"{kind.value} contains a null semantic key",
                "invalid_frozen_frame_key",
                frame_kind=kind.value,
            )
        duplicated = keys.is_duplicated()
        if duplicated.any():
            first = keys.filter(duplicated).row(0, named=True)
            raise _error(
                f"{kind.value} contains a duplicate semantic key",
                "duplicate_frozen_frame_key",
                frame_kind=kind.value,
                **first,
            )

    def _validate_pit_membership(self) -> None:
        """Reject membership unavailable at the lagged knowledge cutoff."""
        membership = self._frames.membership.frame
        normalized = membership.with_columns(
            _date_expr(membership, "trade_date").alias("_trade_date"),
            _date_expr(membership, "known_at").alias("_known_at"),
        )
        unavailable = normalized.filter(
            pl.col("_known_at")
            > (pl.col("_trade_date") - pl.duration(days=self._knowledge_lag_days)),
        )
        if not unavailable.is_empty():
            first = unavailable.select(
                pl.col("_trade_date").alias("trade_date"),
                "instrument_id",
                pl.col("_known_at").alias("known_at"),
            ).row(
                0,
                named=True,
            )
            trade_date_value = first["trade_date"]
            if type(trade_date_value) is not date:
                raise _error(
                    "membership trade_date normalization failed",
                    "invalid_frozen_date_value",
                    frame_kind=ResearchFrameKind.MEMBERSHIP.value,
                )
            raise _error(
                "membership evidence was unavailable at its knowledge cutoff",
                "membership_knowledge_lag_violation",
                knowledge_date=(
                    trade_date_value - timedelta(days=self._knowledge_lag_days)
                ).isoformat(),
                knowledge_lag_days=self._knowledge_lag_days,
                **first,
            )

        active_pairs = membership.filter(pl.col("is_member")).select(
            _iso_date_expr(membership, "trade_date").alias("trade_date"),
            "instrument_id",
        )
        bars = self._frames.bars.frame
        bar_pairs = bars.select(
            _iso_date_expr(bars, "trade_date").alias("trade_date"),
            "instrument_id",
        )
        missing = active_pairs.join(
            bar_pairs,
            on=["trade_date", "instrument_id"],
            how="anti",
        )
        if not missing.is_empty():
            first = missing.row(0, named=True)
            raise _error(
                "active PIT member has no exact frozen bar",
                "missing_exact_member_bar",
                **first,
            )

    def trading_days(self) -> list[str]:
        """Return the exact open sessions bounded to this fold."""
        calendar = self._frames.calendar.frame
        normalized = calendar.select(
            _iso_date_expr(calendar, "trade_date").alias("trade_date"),
            "is_open",
        )
        return sorted(
            normalized.filter(
                pl.col("is_open")
                & (pl.col("trade_date") >= self._start_date)
                & (pl.col("trade_date") <= self._end_date),
            )["trade_date"].to_list(),
        )

    def _validate_execution_sessions(self) -> None:
        """Require explicit open sessions and one daily membership projection."""
        sessions = self.trading_days()
        if not sessions:
            raise _error(
                "research window has no exact frozen open session",
                "no_frozen_execution_sessions",
                start_date=self._start_date,
                end_date=self._end_date,
            )
        membership = self._frames.membership.frame
        membership_dates = set(
            membership.select(
                _iso_date_expr(membership, "trade_date").alias("trade_date"),
            )["trade_date"].to_list(),
        )
        missing_dates = sorted(set(sessions) - membership_dates)
        if missing_dates:
            raise _error(
                "execution session lacks exact daily membership evidence",
                "missing_exact_membership_session",
                trade_dates=missing_dates,
            )

    def _validate_benchmark_coverage(self) -> None:
        """Require one exact frozen benchmark bar for every execution session."""
        if self._benchmark_id is None:
            return
        bars = self._frames.bars.frame
        benchmark_dates = set(
            bars.filter(
                pl.col("instrument_id") == int(self._benchmark_id),
            )
            .select(
                _iso_date_expr(bars, "trade_date").alias("trade_date"),
            )["trade_date"]
            .to_list(),
        )
        missing_dates = sorted(set(self.trading_days()) - benchmark_dates)
        if missing_dates:
            raise _error(
                "configured benchmark lacks an exact frozen bar",
                "missing_exact_benchmark_bar",
                benchmark_id=int(self._benchmark_id),
                trade_dates=missing_dates,
            )

    def get_slice(self, date: str) -> Slice:
        """Return one exact session slice filtered by that day's PIT membership."""
        if date not in self.trading_days():
            raise _error(
                "slice date is not an exact frozen execution session",
                "unknown_frozen_calendar_session",
                trade_date=date,
            )
        membership = self._frames.membership.frame.filter(
            (_iso_date_expr(self._frames.membership.frame, "trade_date") == date)
            & pl.col("is_member"),
        ).select("instrument_id")
        frozen_bars = self._frames.bars.frame
        day_bars = frozen_bars.filter(
            _iso_date_expr(frozen_bars, "trade_date") == date,
        )
        member_bars = day_bars.join(membership, on="instrument_id", how="semi")
        bars: dict[InstrumentId, MarketSnapshot] = {}
        source_snapshot_ids: dict[InstrumentId, str] = {}
        for row in member_bars.to_dicts():
            instrument_id = InstrumentId(int(row["instrument_id"]))
            if self._benchmark_id is not None and instrument_id == self._benchmark_id:
                continue
            bars[instrument_id] = _market_snapshot(date, instrument_id, row)
            source_id = aggregate_source_snapshot_id(
                [str(row["source_snapshot_id"])],
            )
            if source_id is not None:
                source_snapshot_ids[instrument_id] = source_id

        benchmark_close: float | None = None
        if self._benchmark_id is not None:
            benchmark = day_bars.filter(
                pl.col("instrument_id") == int(self._benchmark_id),
            )
            if not benchmark.is_empty():
                benchmark_close = float(benchmark["close"][0])

        step_time = datetime.fromisoformat(date).replace(
            hour=15,
            minute=0,
            second=0,
            tzinfo=UTC,
        )
        return Slice(
            trade_date=date,
            step_time=step_time,
            bars=bars,
            benchmark_close=benchmark_close,
            source_snapshot_ids=source_snapshot_ids,
        )

    def get_history(
        self,
        instrument_ids: list[InstrumentId],
        as_of_date: str,
        lookback_days: int,
    ) -> pl.DataFrame:
        """Return exact pre-as-of bars for instruments in the current PIT universe."""
        as_of_date = _exact_iso_date(as_of_date, "as_of_date")
        if type(lookback_days) is not int or lookback_days < 0:
            raise _error(
                "lookback_days must be a non-negative exact integer",
                "invalid_history_lookback",
                lookback_days=lookback_days,
            )
        bars = self._frames.bars.frame
        if lookback_days == 0 or not instrument_ids:
            return bars.clear()
        requested_ids = sorted({int(item) for item in instrument_ids})
        membership = self._frames.membership.frame
        dated_membership = membership.with_columns(
            _iso_date_expr(membership, "trade_date").alias("trade_date"),
        )
        known_membership = dated_membership.filter(pl.col("trade_date") <= as_of_date)
        if known_membership.is_empty():
            raise _error(
                "history request predates frozen PIT membership",
                "history_membership_date_unavailable",
                as_of_date=as_of_date,
            )
        membership_date = str(known_membership["trade_date"].max())
        current_ids = set(
            known_membership.filter(
                (pl.col("trade_date") == membership_date) & pl.col("is_member"),
            )["instrument_id"].to_list()
        )
        outside_membership = [
            instrument_id
            for instrument_id in requested_ids
            if instrument_id not in current_ids
        ]
        if outside_membership:
            raise _error(
                "history request includes instrument outside current PIT membership",
                "history_request_outside_pit_membership",
                instrument_ids=outside_membership,
                as_of_date=as_of_date,
                membership_date=membership_date,
            )
        calendar = self._frames.calendar.frame
        open_sessions = calendar.filter(pl.col("is_open")).select(
            _iso_date_expr(calendar, "trade_date").alias("trade_date"),
        )
        result = (
            bars.with_columns(
                _iso_date_expr(bars, "trade_date").alias("trade_date"),
            )
            .join(open_sessions, on="trade_date", how="semi")
            .filter(
                pl.col("instrument_id").is_in(requested_ids)
                & (pl.col("trade_date") < as_of_date),
            )
            .sort(["instrument_id", "trade_date"])
            .group_by("instrument_id", maintain_order=True)
            .tail(lookback_days)
            .sort(["instrument_id", "trade_date"])
        )
        counts = {
            int(row["instrument_id"]): int(row["len"])
            for row in result.group_by("instrument_id").len().to_dicts()
        }
        insufficient = [
            instrument_id
            for instrument_id in requested_ids
            if counts.get(instrument_id, 0) < lookback_days
        ]
        if insufficient:
            raise _error(
                "exact frozen history is shorter than lookback",
                "insufficient_frozen_history",
                instrument_ids=insufficient,
                as_of_date=as_of_date,
                lookback_days=lookback_days,
            )
        return result

    def get_fundamental_snapshot(
        self,
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        """Return latest frozen fundamental rows known by ``as_of_date``."""
        return self._get_pit_snapshot(
            kind=ResearchFrameKind.FUNDAMENTAL,
            verified=self._frames.fundamental,
            instrument_ids=instrument_ids,
            as_of_date=as_of_date,
        )

    def get_classification_snapshot(
        self,
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        """Return latest frozen classification rows known by ``as_of_date``."""
        return self._get_pit_snapshot(
            kind=ResearchFrameKind.CLASSIFICATION,
            verified=self._frames.classification,
            instrument_ids=instrument_ids,
            as_of_date=as_of_date,
        )

    @staticmethod
    def _get_pit_snapshot(
        *,
        kind: ResearchFrameKind,
        verified: VerifiedResearchFrame | None,
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        """Project one latest-known row per requested instrument, without fallback."""
        if verified is None:
            raise _error(
                f"{kind.value} evidence was not frozen for this execution",
                "missing_frozen_pit_frame",
                frame_kind=kind.value,
            )
        raw_as_of: object = as_of_date
        if type(raw_as_of) is not date:
            raise _error(
                "PIT snapshot as_of_date must be an exact date",
                "invalid_pit_as_of_date",
                frame_kind=kind.value,
            )
        requested_ids = sorted({int(item) for item in instrument_ids})
        output_columns = [
            column
            for column in verified.frame.columns
            if column not in {"known_at", "source_snapshot_id"}
        ]
        if not requested_ids:
            return verified.frame.select(output_columns).clear()
        result = (
            verified.frame.filter(
                pl.col("instrument_id").is_in(requested_ids)
                & (_date_expr(verified.frame, "known_at") <= pl.lit(as_of_date)),
            )
            .sort(["instrument_id", "known_at"])
            .group_by("instrument_id", maintain_order=True)
            .tail(1)
            .select(output_columns)
            .sort("instrument_id")
        )
        available = {int(item) for item in result["instrument_id"].to_list()}
        missing = sorted(set(requested_ids) - available)
        if missing:
            raise _error(
                f"{kind.value} has no frozen known-at row for requested instruments",
                "missing_frozen_pit_row",
                frame_kind=kind.value,
                instrument_ids=missing,
                as_of_date=as_of_date.isoformat(),
            )
        return result
