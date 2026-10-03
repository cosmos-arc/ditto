"""Q3 live-discovery normalization and consumer-evidence helpers."""

from __future__ import annotations

import hashlib
import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast

import polars as pl
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.processes.selection.facade import (
    IndustryRotationObservationDraft,
    LimitStateDraft,
    SelectionFactorValueDraft,
    SelectionInstrumentDraft,
)
from ditto_application.processes.selection.facade import (
    derive_limit_state as shared_derive_limit_state,
)
from ditto_data.catalog.metadata import DatasetSchedule
from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_kernel.identity import InstrumentId

__all__ = [
    "_ETF_CODE",
    "_ETF_INSTRUMENT_ID",
    "_STOCK_CODE",
    "_STOCK_INSTRUMENT_ID",
    "_TARGET_DATE",
    "_TECHNICAL_FROM",
    "_TECHNICAL_PROFILE",
    "ConsumerProbe",
    "_TechnicalEvidenceContext",
    "_context",
    "_envelope_summary",
    "_payload",
    "_rotation_observations",
    "_selection_frame",
    "_selection_instruments",
    "_sha256_file",
    "_snapshot",
    "_technical_consumer_evidence",
    "_universe_snapshot_id",
    "build_expected_dates",
    "derive_limit_state",
    "normalized_rank_values",
    "probe_consumer_payload",
]

_TARGET_DATE = date(2024, 3, 29)
_TECHNICAL_FROM = date(2022, 10, 1)
_TECHNICAL_PROFILE = "technical_daily"
_STOCK_CODE = "600519.SH"
_ETF_CODE = "518880.SH"
_STOCK_INSTRUMENT_ID = InstrumentId(1_003_251)
_ETF_INSTRUMENT_ID = InstrumentId(2_001_724)
_MIN_UNIVERSE_SIZE = 8
_MIN_LISTING_DAYS = 120


@dataclass(frozen=True, slots=True)
class _SQLiteConsumerContract:
    table: str
    object_label: str
    where_clause: str = ""
    parameters: tuple[str, ...] = ()


_SQLITE_CONSUMERS = {
    "calendar": _SQLiteConsumerContract("trading_calendar", "trading_calendar"),
    "stock_basic": _SQLiteConsumerContract(
        "instrument",
        "instrument[asset_class=stock]",
        " WHERE asset_class = ?",
        ("stock",),
    ),
    "etf_basic": _SQLiteConsumerContract(
        "instrument",
        "instrument[asset_class=etf]",
        " WHERE asset_class = ?",
        ("etf",),
    ),
    "index_basic": _SQLiteConsumerContract(
        "instrument",
        "instrument[asset_class=index]",
        " WHERE asset_class = ?",
        ("index",),
    ),
    "index_weight": _SQLiteConsumerContract("index_weight", "index_weight"),
    "corporate_actions": _SQLiteConsumerContract(
        "corporate_actions", "corporate_actions"
    ),
    "balance_sheet": _SQLiteConsumerContract("balance_sheet", "balance_sheet"),
    "income_statement": _SQLiteConsumerContract("income_statement", "income_statement"),
    "cash_flow": _SQLiteConsumerContract("cash_flow", "cash_flow"),
    "dividend": _SQLiteConsumerContract("dividend", "dividend"),
    "valuation_metrics": _SQLiteConsumerContract(
        "valuation_metrics", "valuation_metrics"
    ),
    "macro_indicators": _SQLiteConsumerContract(
        "macro_indicator_data", "macro_indicator_data"
    ),
}
_PARQUET_CONSUMERS = {
    "stock_daily": "market/stock/bars",
    "etf_daily": "market/etf/bars",
    "index_daily": "market/index/bars",
    "global_index_daily": "market/index/global_bars",
    "stock_status": "market/stock/status",
    "adj_factor": "market/stock/adj",
    "fund_adj": "market/etf/adj",
    "commodity_daily": "market/commodity/bars",
}

type ConsumerProbe = dict[str, int | str]


@dataclass(frozen=True, slots=True)
class _TechnicalEvidenceContext:
    evidence_root: Path
    recovery_evidence: Path
    generated_at: datetime
    data_root: Path


def build_expected_dates(
    *,
    schedule: DatasetSchedule,
    target_from: date,
    target_to: date,
    trading_days_provider: Callable[[str, str], list[str]],
) -> tuple[date, ...]:
    """Build the explicit partition schedule expected over one target interval."""
    if target_to < target_from:
        raise ValueError("expected-date target interval is reversed")
    if schedule == "trading_days":
        values = tuple(
            date.fromisoformat(value)
            for value in trading_days_provider(
                target_from.isoformat(), target_to.isoformat()
            )
        )
    else:
        days = (target_to - target_from).days
        values = tuple(
            target_from + timedelta(days=offset) for offset in range(days + 1)
        )
    expected = tuple(
        sorted({value for value in values if target_from <= value <= target_to})
    )
    if not expected:
        raise ValueError("expected partition schedule is empty")
    return expected


def probe_consumer_payload(data_root: Path, dataset_id: str) -> ConsumerProbe:
    """Read one canonical storage object through its production physical contract."""
    root = data_root.expanduser().resolve(strict=False)
    sqlite_contract = _SQLITE_CONSUMERS.get(dataset_id)
    if sqlite_contract is not None:
        sqlite_path = root / "metadata" / "metadata.sqlite"
        if not sqlite_path.is_file():
            raise ValueError(f"consumer SQLite database is missing: {sqlite_path}")
        with sqlite3.connect(sqlite_path) as connection:
            row_count = int(
                connection.execute(
                    f'SELECT COUNT(*) FROM "{sqlite_contract.table}"'  # noqa: S608
                    + sqlite_contract.where_clause,
                    sqlite_contract.parameters,
                ).fetchone()[0]
            )
        probe: ConsumerProbe = {
            "kind": "sqlite",
            "object": sqlite_contract.object_label,
            "row_count": row_count,
        }
    else:
        relative = _PARQUET_CONSUMERS.get(dataset_id)
        if relative is None:
            raise ValueError(f"no production consumer probe is declared: {dataset_id}")
        payload_root = root / relative
        files = tuple(sorted(payload_root.glob("*.parquet")))
        if not files:
            raise ValueError(f"consumer Parquet payload is missing: {dataset_id}")
        row_count = int(
            pl.scan_parquet(list(files)).select(pl.len().alias("rows")).collect().item()
        )
        probe = {
            "file_count": len(files),
            "kind": "parquet",
            "object": relative,
            "row_count": row_count,
        }
    if cast(int, probe["row_count"]) <= 0:
        raise ValueError(f"consumer payload is empty: {dataset_id}")
    return probe


def normalized_rank_values(
    frame: pl.DataFrame,
    *,
    value_column: str,
    output_column: str,
) -> pl.DataFrame:
    """Map deterministic average ranks to the closed interval [-1, 1]."""
    if value_column not in frame.columns or frame.is_empty():
        raise ValueError(f"Q3 rank input is missing: {value_column}")
    if frame[value_column].null_count():
        raise ValueError(f"Q3 rank input contains nulls: {value_column}")
    if len(frame) == 1:
        return frame.with_columns(pl.lit(0.0).alias(output_column))
    return frame.with_columns(
        (
            2.0
            * (pl.col(value_column).rank(method="average") - 1.0)
            / (len(frame) - 1.0)
            - 1.0
        ).alias(output_column)
    )


def derive_limit_state(
    *,
    source_ticker: str,
    pct_change: float,
    close: float,
    high: float,
    low: float,
    is_st: bool,
) -> LimitStateDraft:
    """Board/ST-aware close limit (shared authority in ditto_data.helpers)."""
    return shared_derive_limit_state(
        source_ticker=source_ticker,
        pct_change=pct_change,
        close=close,
        high=high,
        low=low,
        is_st=is_st,
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_addressed(root: Path, stem: str, payload: object) -> tuple[Path, str]:
    content = canonical_bytes(payload)
    digest = hashlib.sha256(content).hexdigest()
    path = root / f"{stem}.sha256-{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content:
        raise ValueError(f"Q3 content-addressed evidence conflict: {path}")
    path.write_bytes(content)
    return path, digest


def _snapshot(
    reader: ProviderSnapshotReader,
    *,
    dataset_id: str,
    request_start: date,
    request_end: date,
    required_partition_key: str | None = None,
) -> ProviderSnapshot:
    matches = tuple(
        item
        for item in reader.list_snapshots(dataset_id=dataset_id)
        if item.request_start == request_start.isoformat()
        and item.request_end == request_end.isoformat()
        and (
            required_partition_key is None
            or required_partition_key in item.canonical_asset.partition_keys
        )
        and item.payload_retained
        and item.payload_uri is not None
    )
    if len(matches) != 1:
        interval = f"{dataset_id}/{request_start}/{request_end}"
        message = (
            "Q3 requires one exact retained snapshot: "
            + interval
            + f", found={len(matches)}"
        )
        raise ValueError(message)
    return matches[0]


def _payload(
    snapshot: ProviderSnapshot,
    reader: ProviderPayloadReader,
) -> pl.DataFrame:
    if snapshot.payload_uri is None:
        raise ValueError(f"Q3 retained payload missing: {snapshot.snapshot_id}")
    return reader.read_payload(
        ProviderPayloadArtifact(
            dataset_id=snapshot.dataset_id,
            source=snapshot.source,
            checksum=snapshot.checksum,
            row_count=snapshot.row_count,
            uri=snapshot.payload_uri,
        )
    )


def _bounded_universe(frame: pl.DataFrame, *, limit: int) -> pl.DataFrame:
    """Keep a deterministic liquid core plus real hard-filter edge cases."""
    if frame.is_empty() or limit < _MIN_UNIVERSE_SIZE:
        raise ValueError("Q3 bounded universe is invalid")
    rows = frame.sort("source_ticker").to_dicts()
    priority = sorted(
        (
            row
            for row in rows
            if bool(row["is_st"])
            or bool(row["is_suspended"])
            or row["limit_state"] != "normal"
            or int(row["listing_days"]) < _MIN_LISTING_DAYS
        ),
        key=lambda row: str(row["source_ticker"]),
    )[: max(8, limit // 4)]
    liquid = sorted(
        rows,
        key=lambda row: (-float(row["amount"]), str(row["source_ticker"])),
    )
    illiquid = sorted(
        rows,
        key=lambda row: (float(row["amount"]), str(row["source_ticker"])),
    )[: max(8, limit // 8)]
    selected: list[str] = []
    for row in (*priority, *illiquid, *liquid):
        code = str(row["source_ticker"])
        if code not in selected:
            selected.append(code)
        if len(selected) == min(limit, len(rows)):
            break
    return frame.filter(pl.col("source_ticker").is_in(selected)).sort("source_ticker")


def _selection_frame(
    *,
    asset_kind: str,
    daily: pl.DataFrame,
    basic: pl.DataFrame,
    metadata: pl.DataFrame,
    industry_mapping: pl.DataFrame | None,
    stock_status: pl.DataFrame | None,
    limit: int,
) -> pl.DataFrame:
    basic_facts = basic.select("source_ticker", "name", "list_date")
    identifiers = metadata.select("instrument_id", "source_ticker")
    frame = daily.join(basic_facts, on="source_ticker", how="inner").join(
        identifiers,
        on="source_ticker",
        how="inner",
    )
    if asset_kind == "stock":
        if industry_mapping is None or stock_status is None:
            raise ValueError("Q3 stock selection requires industry and status facts")
        industries = industry_mapping.select(
            pl.col("instrument_id").alias("source_ticker"),
            "industry_id",
        )
        statuses = stock_status.select("source_ticker", "is_st", "is_suspended")
        frame = frame.join(industries, on="source_ticker", how="left").join(
            statuses,
            on="source_ticker",
            how="inner",
        )
    else:
        frame = frame.with_columns(
            pl.lit(None, dtype=pl.String).alias("industry_id"),
            pl.lit(False).alias("is_st"),
            # A retained bar on the target date is positive trading evidence.
            pl.lit(False).alias("is_suspended"),
        )
    frame = frame.with_columns(
        (_TARGET_DATE - pl.col("list_date")).dt.total_days().alias("listing_days")
    )
    limit_states = [
        derive_limit_state(
            source_ticker=str(row["source_ticker"]),
            pct_change=float(row["pct_change"]),
            close=float(row["close"]),
            high=float(row["high"]),
            low=float(row["low"]),
            is_st=bool(row["is_st"]),
        )
        for row in frame.select(
            "source_ticker", "pct_change", "close", "high", "low", "is_st"
        ).to_dicts()
    ]
    frame = frame.with_columns(pl.Series("limit_state", limit_states))
    frame = _bounded_universe(frame, limit=limit)
    frame = normalized_rank_values(
        frame,
        value_column="pct_change",
        output_column="momentum_score",
    )
    return normalized_rank_values(
        frame,
        value_column="amount",
        output_column="liquidity_score",
    )


def _selection_instruments(frame: pl.DataFrame) -> tuple[SelectionInstrumentDraft, ...]:
    return tuple(
        SelectionInstrumentDraft(
            instrument_id=InstrumentId(int(row["instrument_id"])),
            instrument_name=str(row["name"]),
            industry_id=(
                None if row["industry_id"] is None else str(row["industry_id"])
            ),
            factor_values=(
                SelectionFactorValueDraft(
                    "liquidity_rank", float(row["liquidity_score"])
                ),
                SelectionFactorValueDraft(
                    "momentum_1d_rank", float(row["momentum_score"])
                ),
            ),
            average_turnover=float(row["amount"]),
            is_st=bool(row["is_st"]),
            is_suspended=bool(row["is_suspended"]),
            listing_days=int(row["listing_days"]),
            limit_state=cast("LimitStateDraft", row["limit_state"]),
            tracking_error=None,
        )
        for row in frame.sort("instrument_id").to_dicts()
    )


def _rotation_observations(
    *,
    classification: pl.DataFrame,
    mapping: pl.DataFrame,
    stock_daily: pl.DataFrame,
    regime_score: float,
) -> tuple[IndustryRotationObservationDraft, ...]:
    membership = mapping.select(
        pl.col("instrument_id").alias("source_ticker"),
        "industry_id",
    )
    observed = stock_daily.join(membership, on="source_ticker", how="inner")
    grouped = {
        str(row["industry_id"]): row
        for row in observed.group_by("industry_id")
        .agg(
            pl.len().alias("member_count"),
            (pl.col("pct_change") > 0.0).sum().alias("advancing_count"),
            (pl.col("pct_change") < 0.0).sum().alias("declining_count"),
            pl.col("pct_change").mean().alias("mean_pct_change"),
        )
        .to_dicts()
    }
    output: list[IndustryRotationObservationDraft] = []
    for item in classification.sort("industry_id").to_dicts():
        industry_id = str(item["industry_id"])
        values = grouped.get(industry_id)
        if values is None:
            continue
        output.append(
            IndustryRotationObservationDraft(
                industry_id=industry_id,
                industry_name=str(item["industry_name"]),
                relative_strength_5d=None,
                relative_strength_20d=None,
                relative_strength_60d=None,
                advancing_count=int(values["advancing_count"]),
                declining_count=int(values["declining_count"]),
                member_count=int(values["member_count"]),
                trend_score=math.tanh(float(values["mean_pct_change"]) / 5.0),
                fundamental_score=None,
                regime_alignment_score=regime_score,
            )
        )
    if not output:
        raise ValueError("Q3 industry rotation has no real mapped observations")
    return tuple(output)


def _universe_snapshot_id(
    *,
    asset_kind: str,
    source_snapshot_ids: tuple[str, ...],
    instruments: tuple[SelectionInstrumentDraft, ...],
) -> str:
    digest = canonical_sha256(
        {
            "asset_kind": asset_kind,
            "instrument_ids": tuple(int(item.instrument_id) for item in instruments),
            "source_snapshot_ids": source_snapshot_ids,
        }
    )
    return f"universe:sha256:{digest}"


def _technical_consumer_evidence(
    *,
    dataset_id: str,
    instrument_code: str,
    snapshot: ProviderSnapshot,
    payload: pl.DataFrame,
    context: _TechnicalEvidenceContext,
) -> tuple[dict[str, object], str]:
    """Write the exact technical-range consumer read smoke evidence."""
    if dataset_id not in {"stock_daily", "etf_daily"}:
        raise ValueError("Q3 technical evidence requires a daily market product")
    if snapshot.dataset_id != dataset_id:
        raise ValueError("Q3 technical evidence snapshot dataset drift")
    consumer_payload = {
        "schema": "ditto.q3-technical-consumer.v1",
        "dataset_id": dataset_id,
        "snapshot_id": snapshot.snapshot_id,
        "instrument_code": instrument_code,
        "row_count": len(payload),
        "first_trade_date": min(payload["trade_date"]).isoformat(),
        "last_trade_date": max(payload["trade_date"]).isoformat(),
        "processed_probe": probe_consumer_payload(context.data_root, dataset_id),
    }
    _consumer_path, consumer_hash = _write_addressed(
        context.evidence_root / "consumer" / dataset_id,
        "technical-range-read-smoke",
        consumer_payload,
    )
    return consumer_payload, consumer_hash


def _context(
    *,
    decision_at: datetime,
    source_snapshot_ids: tuple[str, ...],
    allowed_universe: tuple[str, ...],
) -> TemporalToolContext:
    snapshot_set_id = aggregate_source_snapshot_ids(source_snapshot_ids)
    if snapshot_set_id is None:
        raise ValueError("Q3 tool context requires source snapshots")
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=decision_at,
            knowledge_cutoff=decision_at,
            publication_cutoff=decision_at,
            source_snapshot_id=snapshot_set_id,
            execution_eligible_at="not_applicable",
            allowed_universe=allowed_universe,
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _envelope_summary(
    left: EvidenceEnvelope,
    right: EvidenceEnvelope,
) -> dict[str, object]:
    if not left.verify_integrity() or not right.verify_integrity():
        raise ValueError("Q3 Agent evidence integrity failed")
    if left.integrity_hash != right.integrity_hash:
        raise ValueError("Q3 Agent evidence replay is non-deterministic")
    return {
        "tool_name": left.tool_name,
        "evidence_id": left.evidence_id,
        "integrity_hash": left.integrity_hash,
        "artifact_refs": left.artifact_refs,
        "lineage": left.lineage,
        "deterministic": True,
    }
