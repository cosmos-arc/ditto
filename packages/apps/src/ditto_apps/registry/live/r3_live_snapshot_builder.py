"""Build immutable R3 research snapshots from one isolated live R2 data root."""

from __future__ import annotations

import hashlib
import sqlite3
from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from math import isfinite
from pathlib import Path
from typing import Literal, cast

import orjson
import polars as pl
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.research.records import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from ditto_application.builders.research_factor_registry import (
    ResearchFactorRegistry,
)
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments.planning_probes import (
    R3_RESEARCH_CERTIFICATION_PROFILE,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    ResearchFrameKind,
    VerifiedResearchFrame,
    research_frame_schema_hash,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)
from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.live.r3_live_market_projection import (
    align_live_membership,
    build_live_bars,
)

__all__ = [
    "LiveDatasetSnapshotBinding",
    "LiveResearchSnapshotBuild",
    "build_composed_live_research_snapshot",
    "build_live_research_snapshot",
]

type LiveLane = Literal["stock", "etf"]

_START = date(2015, 2, 1)
_END = date(2026, 7, 31)
_BUILDER_VERSION = "r3-live-research-snapshot-v4"
_STOCK_INDEX = "000300.SH"
_BENCHMARK_INSTRUMENT_ID = 3_000_149
_ETF_IDS = (2_002_506, 2_002_571, 2_002_631)
_CONTROL_PLANE_CREATED_AT = "2026-07-30T00:00:00Z"
_FACTOR_ARTIFACT_SCHEMA = "ditto.r3-live-factor-registration.v1"
_PRIMARY_DATASET = {"stock": "stock_daily", "etf": "etf_daily"}
_LINEAGE_DATASETS = {
    "stock": (
        "adj_factor",
        "balance_sheet",
        "calendar",
        "income_statement",
        "index_weight",
        "stock_basic",
        "stock_daily",
        "valuation_metrics",
    ),
    "etf": ("calendar", "etf_basic", "etf_daily", "index_daily"),
}
_REQUIRED_DEPENDENCIES = {
    "stock": ("adj_factor", "balance_sheet", "income_statement", "valuation_metrics"),
    "etf": (),
}


@dataclass(frozen=True, slots=True)
class LiveDatasetSnapshotBinding:
    """Exact active R2 certification and snapshots used by one R3 dependency."""

    dataset_id: str
    certification_report_id: str
    certified_at: str
    certified_from: str
    certified_through: str
    snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LiveResearchSnapshotBuild:
    """Exact identities emitted by one successful live snapshot build."""

    lane: LiveLane
    snapshot_id: str
    manifest_hash: str
    dataset_id: str
    snapshot_start: str
    snapshot_end: str
    source_snapshot_ids: tuple[str, ...]
    dataset_bindings: tuple[LiveDatasetSnapshotBinding, ...]
    primary_authority_snapshot_id: str
    input_evidence: tuple[dict[str, str], ...]
    row_count: int


def _canonical(value: object) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def _parquet(frame: pl.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.write_parquet(buffer, compression="zstd", statistics=True)
    return buffer.getvalue()


def _content_addressed_input_id(logical_id: str, content_hash: str) -> str:
    """Keep the logical role readable while making immutable storage append-only."""
    return f"{logical_id}@sha256:{content_hash}"


def _evidence(
    input_id: str,
    artifact_kind: str,
    frame: pl.DataFrame,
) -> tuple[ContentAddressedResearchInput, bytes]:
    payload = _parquet(frame)
    content_hash = hashlib.sha256(payload).hexdigest()
    evidence = ContentAddressedResearchInput(
        input_id=_content_addressed_input_id(input_id, content_hash),
        artifact_kind=artifact_kind,
        content_hash=content_hash,
        schema_hash=research_frame_schema_hash(frame),
    )
    try:
        ResearchFrameKind(artifact_kind)
    except ValueError:
        pass
    else:
        source_ids = tuple(sorted(frame["source_snapshot_id"].unique().to_list()))
        VerifiedResearchFrame(evidence, source_ids, payload)
    return evidence, payload


def _dependency_evidence(
    dataset_id: str,
    source_snapshot_ids: tuple[str, ...],
) -> tuple[ContentAddressedResearchInput, bytes]:
    payload = _canonical(
        {
            "dataset_id": dataset_id,
            "schema": "ditto.r3-live-dependency.v1",
            "source_snapshot_ids": list(source_snapshot_ids),
        }
    )
    content_hash = hashlib.sha256(payload).hexdigest()
    return (
        ContentAddressedResearchInput(
            input_id=_content_addressed_input_id(dataset_id, content_hash),
            artifact_kind=f"dependency_{dataset_id}",
            content_hash=content_hash,
            schema_hash=hashlib.sha256(b"ditto.r3-live-dependency.v1").hexdigest(),
        ),
        payload,
    )


def _factor_evidence() -> tuple[tuple[ContentAddressedResearchInput, bytes], ...]:
    """Freeze every versioned code registration available to live runtimes."""
    registry = ResearchFactorRegistry()
    schema_hash = hashlib.sha256(_FACTOR_ARTIFACT_SCHEMA.encode()).hexdigest()
    artifacts: list[tuple[ContentAddressedResearchInput, bytes]] = []
    for registration in registry.registrations.values():
        payload = _canonical(
            {
                "schema": _FACTOR_ARTIFACT_SCHEMA,
                "registry_manifest_hash": registry.manifest_hash,
                "registration": registration.manifest_payload(),
            }
        )
        artifacts.append(
            (
                ContentAddressedResearchInput(
                    input_id=f"{registration.factor_id}@{registration.version}",
                    artifact_kind="factor",
                    content_hash=hashlib.sha256(payload).hexdigest(),
                    schema_hash=schema_hash,
                ),
                payload,
            )
        )
    return tuple(artifacts)


def _database(data_root: Path) -> sqlite3.Connection:
    path = data_root / "metadata" / "metadata.sqlite"
    if not path.is_file():
        raise ValueError(f"live metadata database is missing: {path}")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _certified_dataset_binding(
    *,
    certification_reader: CertificationReader,
    snapshot_reader: ProviderSnapshotReader,
    dataset_id: str,
) -> tuple[tuple[ProviderSnapshot, ...], LiveDatasetSnapshotBinding]:
    report = certification_reader.get_active_report(
        dataset_id,
        R3_RESEARCH_CERTIFICATION_PROFILE,
    )
    if report is None:
        raise ValueError(f"active live certification is missing: {dataset_id}")
    coverage = report.coverage
    if coverage.complete_from is None or coverage.complete_from > _START:
        raise ValueError(f"live certification starts too late: {dataset_id}")
    if coverage.target_to < _END:
        raise ValueError(f"live certification ends too early: {dataset_id}")
    snapshots: list[ProviderSnapshot] = []
    for snapshot_id in report.evidence.snapshot_ids:
        snapshot = snapshot_reader.get_snapshot(snapshot_id)
        if snapshot is None:
            raise ValueError(
                f"certified provider snapshot is missing: {dataset_id}/{snapshot_id}"
            )
        if snapshot.dataset_id != dataset_id:
            raise ValueError(
                "certified provider snapshot dataset mismatch: "
                + f"{dataset_id}/{snapshot_id}"
            )
        if not snapshot.payload_retained or snapshot.payload_uri is None:
            raise ValueError(
                "certified provider payload is not retained: "
                + f"{dataset_id}/{snapshot_id}"
            )
        snapshots.append(snapshot)
    ordered = tuple(
        sorted(
            snapshots,
            key=lambda item: (
                item.request_start,
                item.request_end,
                item.snapshot_id.encode(),
            ),
        )
    )
    if not ordered:
        raise ValueError(f"active certification has no snapshots: {dataset_id}")
    return ordered, LiveDatasetSnapshotBinding(
        dataset_id=dataset_id,
        certification_report_id=report.report_id,
        certified_at=report.generated_at.astimezone(UTC).isoformat(),
        certified_from=coverage.complete_from.isoformat(),
        certified_through=coverage.target_to.isoformat(),
        snapshot_ids=tuple(item.snapshot_id for item in ordered),
    )


def _certified_source_snapshots(
    *,
    certification_reader: CertificationReader,
    snapshot_reader: ProviderSnapshotReader,
    lane: LiveLane,
) -> tuple[
    tuple[str, ...],
    str,
    dict[str, tuple[str, ...]],
    tuple[LiveDatasetSnapshotBinding, ...],
]:
    """Resolve only snapshots frozen into each dependency's active R2 report."""
    by_dataset: dict[str, tuple[str, ...]] = {}
    snapshots_by_dataset: dict[str, tuple[ProviderSnapshot, ...]] = {}
    bindings: list[LiveDatasetSnapshotBinding] = []
    for dataset_id in _LINEAGE_DATASETS[lane]:
        ordered, binding = _certified_dataset_binding(
            certification_reader=certification_reader,
            snapshot_reader=snapshot_reader,
            dataset_id=dataset_id,
        )
        snapshot_ids = tuple(item.snapshot_id for item in ordered)
        by_dataset[dataset_id] = snapshot_ids
        snapshots_by_dataset[dataset_id] = ordered
        bindings.append(binding)
    primary = _PRIMARY_DATASET[lane]
    authority_candidates = tuple(
        snapshot
        for snapshot in snapshots_by_dataset[primary]
        if date.fromisoformat(snapshot.request_start)
        <= _END
        <= date.fromisoformat(snapshot.request_end)
    )
    if not authority_candidates:
        raise ValueError(f"primary live provider evidence is stale: {primary}")
    authority = max(
        authority_candidates,
        key=lambda item: (
            item.request_end,
            item.request_start,
            item.snapshot_id.encode(),
        ),
    )
    sources = tuple(sorted({item for values in by_dataset.values() for item in values}))
    return sources, authority.snapshot_id, by_dataset, tuple(bindings)


def _calendar(
    connection: sqlite3.Connection,
    *,
    authority_snapshot_id: str,
) -> tuple[pl.DataFrame, tuple[date, ...]]:
    rows = connection.execute(
        """
        SELECT trade_date, is_open
        FROM trading_calendar
        WHERE trade_date BETWEEN ? AND ?
        ORDER BY trade_date
        """,
        (_START.isoformat(), _END.isoformat()),
    ).fetchall()
    expected_days = (_END - _START).days + 1
    if len(rows) != expected_days:
        raise ValueError("live calendar does not contain every natural day")
    dates = tuple(date.fromisoformat(str(row["trade_date"])) for row in rows)
    sessions = tuple(
        observed
        for observed, row in zip(dates, rows, strict=True)
        if bool(row["is_open"])
    )
    if not sessions:
        raise ValueError("live calendar contains no open sessions")
    return (
        pl.DataFrame(
            {
                "trade_date": dates,
                "is_open": tuple(bool(row["is_open"]) for row in rows),
                "source_snapshot_id": (authority_snapshot_id,) * len(rows),
            },
            schema={
                "trade_date": pl.Date,
                "is_open": pl.Boolean,
                "source_snapshot_id": pl.String,
            },
        ),
        sessions,
    )


def _stock_membership(
    connection: sqlite3.Connection,
    sessions: tuple[date, ...],
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    rows = connection.execute(
        """
        SELECT instrument_id, effective_from
        FROM index_weight
        WHERE index_id = ? AND effective_from <= ?
        ORDER BY effective_from, instrument_id
        """,
        (_STOCK_INDEX, _END.isoformat()),
    ).fetchall()
    by_effective: dict[date, list[int]] = {}
    for row in rows:
        effective = date.fromisoformat(str(row["effective_from"]))
        by_effective.setdefault(effective, []).append(int(row["instrument_id"]))
    effective_dates = tuple(sorted(by_effective))
    if not effective_dates:
        raise ValueError("CSI300 PIT membership evidence is missing")
    output_dates: list[date] = []
    instrument_ids: list[int] = []
    known_at: list[date] = []
    for session in sessions:
        position = bisect_left(effective_dates, session) - 1
        if position < 0:
            continue
        effective = effective_dates[position]
        members = by_effective[effective]
        output_dates.extend((session,) * len(members))
        instrument_ids.extend(members)
        known_at.extend((effective,) * len(members))
    if not output_dates:
        raise ValueError("CSI300 PIT membership projection is empty")
    return pl.DataFrame(
        {
            "trade_date": output_dates,
            "instrument_id": instrument_ids,
            "is_member": (True,) * len(output_dates),
            "known_at": known_at,
            "source_snapshot_id": (authority_snapshot_id,) * len(output_dates),
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "is_member": pl.Boolean,
            "known_at": pl.Date,
            "source_snapshot_id": pl.String,
        },
    ).sort(["trade_date", "instrument_id"])


def _etf_membership(
    sessions: tuple[date, ...],
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "trade_date": tuple(day for day in sessions for _ in _ETF_IDS),
            "instrument_id": _ETF_IDS * len(sessions),
            "is_member": (True,) * (len(sessions) * len(_ETF_IDS)),
            "known_at": tuple(
                day - timedelta(days=1) for day in sessions for _ in _ETF_IDS
            ),
            "source_snapshot_id": (authority_snapshot_id,)
            * (len(sessions) * len(_ETF_IDS)),
        },
        schema={
            "trade_date": pl.Date,
            "instrument_id": pl.Int64,
            "is_member": pl.Boolean,
            "known_at": pl.Date,
            "source_snapshot_id": pl.String,
        },
    )


def _fundamental(
    connection: sqlite3.Connection,
    lane: LiveLane,
    instrument_ids: tuple[int, ...],
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    if lane == "etf":
        return pl.DataFrame(
            {
                "instrument_id": instrument_ids,
                "known_at": (_START - timedelta(days=1),) * len(instrument_ids),
                "roe": (0.0,) * len(instrument_ids),
                "net_margin": (0.0,) * len(instrument_ids),
                "eps": (0.0,) * len(instrument_ids),
                "market_cap": (0.0,) * len(instrument_ids),
                "source_snapshot_id": (authority_snapshot_id,) * len(instrument_ids),
            },
            schema={
                "instrument_id": pl.Int64,
                "known_at": pl.Date,
                "roe": pl.Float64,
                "net_margin": pl.Float64,
                "eps": pl.Float64,
                "market_cap": pl.Float64,
                "source_snapshot_id": pl.String,
            },
        )
    query = (
        "SELECT i.instrument_id, i.knowledge_date AS income_known_at, "
        "b.knowledge_date AS balance_known_at, i.net_profit, i.revenue, "
        "i.eps, b.net_assets FROM income_statement AS i "
        "LEFT JOIN balance_sheet AS b ON b.instrument_id = i.instrument_id "
        "AND b.report_date = i.report_date WHERE i.instrument_id = ? "
        "AND i.knowledge_date <= ? "
        "ORDER BY i.instrument_id, i.knowledge_date, i.report_date"
    )
    rows = tuple(
        row
        for instrument_id in instrument_ids
        for row in connection.execute(
            query,
            (instrument_id, _END.isoformat()),
        ).fetchall()
    )
    output: list[dict[str, object]] = []
    for row in rows:
        instrument_id = int(row["instrument_id"])
        income_known = date.fromisoformat(str(row["income_known_at"]))
        balance_known = (
            income_known
            if row["balance_known_at"] is None
            else date.fromisoformat(str(row["balance_known_at"]))
        )
        net_profit = None if row["net_profit"] is None else float(row["net_profit"])
        revenue = None if row["revenue"] is None else float(row["revenue"])
        net_assets = None if row["net_assets"] is None else float(row["net_assets"])
        eps = None if row["eps"] is None else float(row["eps"])
        if (
            net_profit is None
            or revenue in {None, 0.0}
            or net_assets in {None, 0.0}
            or eps is None
        ):
            continue
        roe = net_profit / cast("float", net_assets)
        net_margin = net_profit / cast("float", revenue)
        if not all(isfinite(value) for value in (roe, net_margin, eps)):
            continue
        output.append(
            {
                "instrument_id": instrument_id,
                "known_at": max(income_known, balance_known),
                "roe": roe,
                "net_margin": net_margin,
                "eps": eps,
                "source_snapshot_id": authority_snapshot_id,
            }
        )
    financial = (
        pl.DataFrame(
            output,
            schema={
                "instrument_id": pl.Int64,
                "known_at": pl.Date,
                "roe": pl.Float64,
                "net_margin": pl.Float64,
                "eps": pl.Float64,
                "source_snapshot_id": pl.String,
            },
        )
        .unique(subset=("instrument_id", "known_at"), keep="last")
        .sort(["instrument_id", "known_at"])
    )
    if financial.is_empty():
        return financial.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("market_cap")
        )

    placeholders = ",".join("?" for _ in instrument_ids)
    valuation_query = (
        f"SELECT instrument_id, trade_date, knowledge_date, market_cap FROM "  # noqa: S608 -- placeholders only
        f"valuation_metrics WHERE instrument_id IN ({placeholders}) "
        "AND knowledge_date <= ? AND market_cap IS NOT NULL ORDER BY "
        "instrument_id, knowledge_date, trade_date"
    )
    valuation = pl.read_database(
        query=valuation_query,
        connection=connection,
        execute_options={"parameters": (*instrument_ids, _END.isoformat())},
    )
    if valuation.is_empty():
        return financial.head(0).with_columns(
            pl.lit(None, dtype=pl.Float64).alias("market_cap")
        )
    valuation = (
        valuation.with_columns(
            pl.col("trade_date").cast(pl.String).str.to_date(),
            pl.col("knowledge_date").cast(pl.String).str.to_date().alias("known_at"),
            pl.col("market_cap").cast(pl.Float64),
        )
        .filter(pl.col("market_cap").is_finite() & (pl.col("market_cap") > 0.0))
        .sort(["instrument_id", "known_at", "trade_date"])
        .unique(subset=("instrument_id", "known_at"), keep="last")
        .select("instrument_id", "known_at", "market_cap")
        .sort(["instrument_id", "known_at"])
    )
    return (
        valuation.join_asof(
            financial.drop("source_snapshot_id"),
            on="known_at",
            by="instrument_id",
            strategy="backward",
            check_sortedness=False,
        )
        .drop_nulls(("roe", "net_margin", "eps", "market_cap"))
        .with_columns(pl.lit(authority_snapshot_id).alias("source_snapshot_id"))
        .select(
            "instrument_id",
            "known_at",
            "roe",
            "net_margin",
            "eps",
            "market_cap",
            "source_snapshot_id",
        )
        .sort(["instrument_id", "known_at"])
    )


def _membership_with_complete_fundamentals(
    membership: pl.DataFrame,
    fundamental: pl.DataFrame,
) -> pl.DataFrame:
    """Start stock eligibility only after one complete PIT row is knowable."""
    first_known = fundamental.group_by("instrument_id").agg(
        pl.col("known_at").min().alias("first_fundamental_known_at")
    )
    return (
        membership.join(first_known, on="instrument_id", how="left")
        .filter(
            pl.col("first_fundamental_known_at").is_not_null()
            & (pl.col("first_fundamental_known_at") < pl.col("trade_date"))
        )
        .drop("first_fundamental_known_at")
        .sort(["trade_date", "instrument_id"])
    )


def _membership_with_instrument_lifecycle(
    connection: sqlite3.Connection,
    membership: pl.DataFrame,
) -> pl.DataFrame:
    """Remove index rows outside exact listed and delisted date boundaries."""
    instrument_ids = tuple(
        sorted(int(item) for item in membership["instrument_id"].unique())
    )
    if not instrument_ids:
        raise ValueError("live membership has no instrument identities")
    requested_ids = set(instrument_ids)
    rows = tuple(
        row
        for row in connection.execute(
            "SELECT instrument_id, list_date, delist_date FROM instrument"
        ).fetchall()
        if int(row["instrument_id"]) in requested_ids
    )
    observed_ids = {int(row["instrument_id"]) for row in rows}
    missing = sorted(set(instrument_ids) - observed_ids)
    if missing:
        rendered = ", ".join(str(item) for item in missing)
        raise ValueError(f"live membership instrument metadata is missing: {rendered}")
    lifecycle = pl.DataFrame(
        {
            "instrument_id": tuple(int(row["instrument_id"]) for row in rows),
            "_list_date": tuple(
                None
                if row["list_date"] is None
                else date.fromisoformat(str(row["list_date"]))
                for row in rows
            ),
            "_delist_date": tuple(
                None
                if row["delist_date"] is None
                else date.fromisoformat(str(row["delist_date"]))
                for row in rows
            ),
        },
        schema={
            "instrument_id": pl.Int64,
            "_list_date": pl.Date,
            "_delist_date": pl.Date,
        },
    )
    aligned = (
        membership.join(lifecycle, on="instrument_id", how="inner")
        .filter(
            (
                pl.col("_list_date").is_null()
                | (pl.col("trade_date") >= pl.col("_list_date"))
            )
            & (
                pl.col("_delist_date").is_null()
                | (pl.col("trade_date") <= pl.col("_delist_date"))
            )
        )
        .drop("_list_date", "_delist_date")
        .sort(["trade_date", "instrument_id"])
    )
    if aligned.is_empty():
        raise ValueError("live membership is empty after lifecycle alignment")
    return aligned


def _classification(
    lane: LiveLane,
    instrument_ids: tuple[int, ...],
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": instrument_ids,
            "known_at": (_START - timedelta(days=1),) * len(instrument_ids),
            "sector_id": (("csi300",) if lane == "stock" else ("broad_etf",))
            * len(instrument_ids),
            "source_snapshot_id": (authority_snapshot_id,) * len(instrument_ids),
        },
        schema={
            "instrument_id": pl.Int64,
            "known_at": pl.Date,
            "sector_id": pl.String,
            "source_snapshot_id": pl.String,
        },
    )


def _instrument_code(ticker: str, exchange: str) -> str:
    suffix = "SH" if exchange == "SSE" else "SZ"
    return f"{ticker}.{suffix}"


def _instrument_rules(
    connection: sqlite3.Connection,
    instrument_ids: tuple[int, ...],
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    requested = tuple(sorted(set(instrument_ids) | {_BENCHMARK_INSTRUMENT_ID}))
    rows = tuple(
        row
        for instrument_id in requested
        for row in connection.execute(
            "SELECT * FROM instrument WHERE instrument_id = ?",
            (instrument_id,),
        ).fetchall()
    )
    if {int(row["instrument_id"]) for row in rows} != set(requested):
        raise ValueError("live instrument rules are incomplete")
    payload: list[dict[str, object]] = []
    for row in sorted(rows, key=lambda item: int(item["instrument_id"])):
        asset_class = str(row["asset_class"])
        list_date = (
            _START - timedelta(days=1)
            if row["list_date"] is None
            else date.fromisoformat(str(row["list_date"]))
        )
        known_at = list_date
        payload.append(
            {
                "instrument_code": _instrument_code(
                    str(row["ticker"]), str(row["exchange"])
                ),
                "instrument_id": int(row["instrument_id"]),
                "asset_class": asset_class,
                "exchange": "XSHG" if row["exchange"] == "SSE" else "XSHE",
                "currency": "CNY",
                "tick_size": 0.001 if asset_class in {"etf", "index"} else 0.01,
                "lot_size": 1 if asset_class == "index" else 100,
                "multiplier": 1.0,
                "board_segment": str(row["board"] or asset_class),
                "lifecycle_state": "normal",
                "ipo_date": list_date,
                "delisting_date": (
                    None
                    if row["delist_date"] is None
                    else date.fromisoformat(str(row["delist_date"]))
                ),
                "as_of_date": known_at,
                "known_at": known_at,
                "settlement_cycle": 1,
                "fund_settlement_cycle": 0,
                "price_limit_pct": None if asset_class == "index" else 0.1,
                "order_types_supported": ["market", "limit"],
                "call_auction_sessions": ["open", "close"],
                "commission_rate": 0.0003 if asset_class == "etf" else 0.001,
                "min_commission": 5.0,
                "stamp_duty_rate": 0.0 if asset_class != "stock" else 0.0005,
                "transfer_fee_rate": 0.00001,
                "source_snapshot_id": authority_snapshot_id,
            }
        )
    frame = pl.DataFrame(
        payload,
        schema={
            "instrument_code": pl.String,
            "instrument_id": pl.Int64,
            "asset_class": pl.String,
            "exchange": pl.String,
            "currency": pl.String,
            "tick_size": pl.Float64,
            "lot_size": pl.Int64,
            "multiplier": pl.Float64,
            "board_segment": pl.String,
            "lifecycle_state": pl.String,
            "ipo_date": pl.Date,
            "delisting_date": pl.Date,
            "as_of_date": pl.Date,
            "known_at": pl.Date,
            "settlement_cycle": pl.Int64,
            "fund_settlement_cycle": pl.Int64,
            "price_limit_pct": pl.Float64,
            "order_types_supported": pl.List(pl.String),
            "call_auction_sessions": pl.List(pl.String),
            "commission_rate": pl.Float64,
            "min_commission": pl.Float64,
            "stamp_duty_rate": pl.Float64,
            "transfer_fee_rate": pl.Float64,
            "source_snapshot_id": pl.String,
        },
    )
    # Parse the final bytes through the production trust boundary before publish.
    evidence, artifact_bytes = _evidence(
        "instrument-rules-validation",
        "instrument_rules",
        frame,
    )
    VerifiedInstrumentRulesArtifact(evidence, artifact_bytes)
    return frame


def _publish_inputs(
    service: ResearchArtifactService,
    inputs: Iterable[tuple[ContentAddressedResearchInput, bytes]],
) -> tuple[ContentAddressedResearchInput, ...]:
    published: list[ContentAddressedResearchInput] = []
    for evidence, payload in inputs:
        observed = service.publish_frozen_research_input(evidence.input_id, payload)
        if observed != evidence.content_hash:
            raise ValueError("frozen input publication hash drift")
        published.append(evidence)
    return tuple(sorted(published, key=lambda item: item.input_id.encode()))


def _ensure_live_catalog_parents(
    catalog_service: ResearchCatalogService,
    *,
    lane: LiveLane,
    calendar_input: ContentAddressedResearchInput,
    calendar_row_count: int,
    created_at: str,
) -> str:
    """Persist the exact parents required by a live dataset snapshot."""
    spine_id = f"r3-live-{lane}-spine"
    dataset_id = f"r3-live-{lane}-golden"
    spine_spec = ResearchSpineSpecRecord(
        spine_id=spine_id,
        universe_id=f"r3-live-{lane}-membership",
        calendar="cn_stock",
        grain="1d",
        entity_key="instrument_id",
        description=f"R3 live {lane} point-in-time research spine",
        created_at=_CONTROL_PLANE_CREATED_AT,
    )
    existing_spine_spec = catalog_service.get_spine_spec(spine_id)
    if existing_spine_spec is None:
        catalog_service.save_spine_spec(spine_spec)
    elif existing_spine_spec != spine_spec:
        raise ValueError(f"live research spine spec replay drift: {spine_id}")

    dataset_spec = ResearchDatasetSpecRecord(
        dataset_id=dataset_id,
        spine_id=spine_id,
        derived_ids=(
            f"r3-live-{lane}-classification",
            f"r3-live-{lane}-fundamental",
            f"r3-live-{lane}-instrument-rules",
            _PRIMARY_DATASET[lane],
        ),
        join_policy="left_preserving_pit",
        known_at_policy="sample_time",
        late_arrival_policy="require_rebuild",
        description=f"R3 live {lane} golden-lane dataset",
        created_at=_CONTROL_PLANE_CREATED_AT,
    )
    existing_dataset_spec = catalog_service.get_dataset_spec(dataset_id)
    if existing_dataset_spec is None:
        catalog_service.save_dataset_spec(dataset_spec)
    elif existing_dataset_spec != dataset_spec:
        raise ValueError(f"live research dataset spec replay drift: {dataset_id}")

    spine_identity = hashlib.sha256(
        _canonical(
            {
                "calendar_content_hash": calendar_input.content_hash,
                "calendar_input_id": calendar_input.input_id,
                "created_at": created_at,
                "lane": lane,
            }
        )
    ).hexdigest()
    spine_snapshot_id = f"r3-live-{lane}-calendar-{spine_identity}"
    artifact_identity = hashlib.sha256(calendar_input.input_id.encode()).hexdigest()
    spine_snapshot = ResearchSpineSnapshotRecord(
        spine_snapshot_id=spine_snapshot_id,
        spine_id=spine_id,
        snapshot_start=_START.isoformat(),
        snapshot_end=_END.isoformat(),
        row_count=calendar_row_count,
        data_path=f"frozen-research-inputs/v1/{artifact_identity}",
        manifest_hash=calendar_input.content_hash,
        created_at=created_at,
    )
    existing_spine_snapshot = catalog_service.get_spine_snapshot(spine_snapshot_id)
    if existing_spine_snapshot is None:
        catalog_service.save_spine_snapshot(spine_snapshot)
    elif existing_spine_snapshot != spine_snapshot:
        raise ValueError(
            f"live research spine snapshot replay drift: {spine_snapshot_id}"
        )
    return spine_snapshot_id


def build_live_research_snapshot(
    *,
    lane: LiveLane,
    data_root: Path,
    artifact_service: ResearchArtifactService,
    catalog_service: ResearchCatalogService,
    certification_reader: CertificationReader,
    snapshot_reader: ProviderSnapshotReader,
    created_at: datetime | None = None,
) -> LiveResearchSnapshotBuild:
    """Freeze one content-addressed live research snapshot and catalog record."""
    root = data_root.expanduser().resolve(strict=True)
    connection = _database(root)
    try:
        sources, authority_source, by_dataset, bindings = _certified_source_snapshots(
            certification_reader=certification_reader,
            snapshot_reader=snapshot_reader,
            lane=lane,
        )
        calendar, sessions = _calendar(
            connection,
            authority_snapshot_id=authority_source,
        )
        membership = (
            _stock_membership(
                connection,
                sessions,
                authority_snapshot_id=authority_source,
            )
            if lane == "stock"
            else _etf_membership(
                sessions,
                authority_snapshot_id=authority_source,
            )
        )
        membership = align_live_membership(root, lane, membership)
        membership = _membership_with_instrument_lifecycle(connection, membership)
        instrument_ids = tuple(sorted(membership["instrument_id"].unique().to_list()))
        fundamental = _fundamental(
            connection,
            lane,
            instrument_ids,
            authority_snapshot_id=authority_source,
        )
        if lane == "stock":
            membership = _membership_with_complete_fundamentals(
                membership,
                fundamental,
            )
            if membership.is_empty():
                raise ValueError("live stock membership has no complete fundamentals")
            instrument_ids = tuple(
                sorted(membership["instrument_id"].unique().to_list())
            )
            fundamental = fundamental.filter(
                pl.col("instrument_id").is_in(instrument_ids)
            )
        bars = build_live_bars(
            root,
            lane,
            membership,
            sessions,
            authority_snapshot_id=authority_source,
        )
        classification = _classification(
            lane,
            instrument_ids,
            authority_snapshot_id=authority_source,
        )
        rules = _instrument_rules(
            connection,
            instrument_ids,
            authority_snapshot_id=authority_source,
        )
    finally:
        connection.close()
    now = (
        created_at.astimezone(UTC)
        if created_at is not None
        else max(datetime.fromisoformat(item.certified_at) for item in bindings)
    )
    created_at_text = now.isoformat().replace("+00:00", "Z")
    primary = _PRIMARY_DATASET[lane]
    inputs: list[tuple[ContentAddressedResearchInput, bytes]] = [
        _evidence(primary, "bars", bars),
        _evidence(f"r3-live-{lane}-calendar", "calendar", calendar),
        _evidence(f"r3-live-{lane}-membership", "membership", membership),
        _evidence(f"r3-live-{lane}-instrument-rules", "instrument_rules", rules),
        _evidence(f"r3-live-{lane}-fundamental", "fundamental", fundamental),
        _evidence(f"r3-live-{lane}-classification", "classification", classification),
    ]
    required_dependencies = _REQUIRED_DEPENDENCIES[lane]
    inputs.extend(
        _dependency_evidence(dataset_id, by_dataset[dataset_id])
        for dataset_id in required_dependencies
    )
    inputs.extend(_factor_evidence())
    published = _publish_inputs(artifact_service, inputs)
    dataset_id = f"r3-live-{lane}-golden"
    calendar_input = next(
        item for item in published if item.artifact_kind == ResearchFrameKind.CALENDAR
    )
    spine_snapshot_id = _ensure_live_catalog_parents(
        catalog_service,
        lane=lane,
        calendar_input=calendar_input,
        calendar_row_count=calendar.height,
        created_at=created_at_text,
    )
    manifest_preimage = {
        "schema_version": 1,
        "snapshot_id": "pending",
        "dataset_id": dataset_id,
        "source_snapshot_ids": list(sources),
        "known_at_policy": "sample_time",
        "builder_version": _BUILDER_VERSION,
        "inputs": [dict(item.as_payload()) for item in published],
    }
    identity_hash = hashlib.sha256(
        _canonical(
            {
                "created_at": created_at_text,
                "manifest": manifest_preimage,
            }
        )
    ).hexdigest()
    snapshot_id = f"r3-live-{lane}-{identity_hash}"
    manifest_preimage["snapshot_id"] = snapshot_id
    manifest = _canonical(manifest_preimage)
    manifest_hash = hashlib.sha256(manifest).hexdigest()
    if (
        artifact_service.publish_frozen_research_input(snapshot_id, manifest)
        != manifest_hash
    ):
        raise ValueError("frozen snapshot manifest publication hash drift")
    record = ResearchDatasetSnapshotRecord(
        snapshot_id=snapshot_id,
        dataset_id=dataset_id,
        dataset_spec_version=1,
        spine_snapshot_id=spine_snapshot_id,
        snapshot_start=_START.isoformat(),
        snapshot_end=_END.isoformat(),
        row_count=bars.height,
        data_path=f"frozen-research-inputs/v1/{snapshot_id}",
        manifest_hash=manifest_hash,
        known_at_policy="sample_time",
        effective_cutoff=_END.isoformat(),
        resolved_versions={item.input_id: 1 for item in published},
        resolved_inputs=tuple(
            cast("dict[str, str | int]", dict(item.as_payload())) for item in published
        ),
        source_snapshot_ids=sources,
        builder_version=_BUILDER_VERSION,
        created_at=created_at_text,
    )
    existing = catalog_service.get_dataset_snapshot(snapshot_id)
    if existing is None:
        catalog_service.save_dataset_snapshot(record)
    elif existing != record:
        raise ValueError("live research snapshot catalog replay drift")
    return LiveResearchSnapshotBuild(
        lane=lane,
        snapshot_id=snapshot_id,
        manifest_hash=manifest_hash,
        dataset_id=dataset_id,
        snapshot_start=_START.isoformat(),
        snapshot_end=_END.isoformat(),
        source_snapshot_ids=sources,
        dataset_bindings=bindings,
        primary_authority_snapshot_id=authority_source,
        input_evidence=tuple(
            cast("dict[str, str]", dict(item.as_payload())) for item in published
        ),
        row_count=bars.height,
    )


def build_composed_live_research_snapshot(
    *,
    lane: LiveLane,
    data_root: Path,
) -> LiveResearchSnapshotBuild:
    """Resolve production ports and build one isolated live snapshot."""
    container = make_app_container()
    try:
        return build_live_research_snapshot(
            lane=lane,
            data_root=data_root,
            artifact_service=container.get(ResearchArtifactService),
            catalog_service=container.get(ResearchCatalogService),
            certification_reader=container.get(CertificationReader),
            snapshot_reader=container.get(ProviderSnapshotReader),
        )
    finally:
        container.close()
