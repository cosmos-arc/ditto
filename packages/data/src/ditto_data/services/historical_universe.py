"""Historical universe projection over qualified immutable provider frames."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

import polars as pl

HISTORY_FIELDS = (
    "instrument_id",
    "effective_from",
    "effective_to",
    "publication_at",
    "available_at",
)
MASTER_FIELDS = (*HISTORY_FIELDS, "list_date", "delist_date")
STATUS_FIELDS = (*HISTORY_FIELDS, "is_suspended")
MEMBERSHIP_FIELDS = (*HISTORY_FIELDS, "index_id")


def project_daily_status_intervals(
    frame: pl.DataFrame,
    *,
    observed_at: datetime,
    resolve_instrument: Callable[[list[str], str], dict[str, int]],
) -> pl.DataFrame:
    """
    Project a raw daily status snapshot into same-day PIT intervals.

    Daily provider snapshots state one fact per trade date; the honest PIT
    projection is an interval that covers exactly that trade date, with the
    snapshot's own observation time as its knowledge time. Rows whose source
    ticker cannot be resolved to a durable identity stay out of the roster
    rather than entering it under a guessed key.
    """
    required = {"source_ticker", "trade_date", "is_suspended"}
    if not required.issubset(set(frame.columns)):
        raise ValueError("HISTORY_FIELDS_MISSING")
    trade_dates = sorted(
        {
            (
                value.date().isoformat()
                if isinstance(value, datetime)
                else value.isoformat()
                if isinstance(value, date)
                else str(value)
            )
            for value in frame["trade_date"].unique().to_list()
        }
    )
    tickers = sorted(set(frame["source_ticker"].to_list()))
    resolved: dict[tuple[str, str], int] = {}
    for trade_date in trade_dates:
        resolved.update(
            ((ticker, trade_date), instrument_id)
            for ticker, instrument_id in resolve_instrument(tickers, trade_date).items()
        )
    lookup = pl.DataFrame(
        {
            "source_ticker": [key[0] for key in resolved],
            "trade_date": [key[1] for key in resolved],
            "_instrument_id": list(resolved.values()),
        },
        schema={
            "source_ticker": pl.String,
            "trade_date": pl.String,
            "_instrument_id": pl.Int64,
        },
    )
    normalized = frame.with_columns(
        pl.col("trade_date").cast(pl.Utf8).alias("_trade_date_key")
    ).join(
        lookup,
        left_on=["source_ticker", "_trade_date_key"],
        right_on=["source_ticker", "trade_date"],
        how="left",
    )
    projected = normalized.with_columns(
        pl.col("_instrument_id").alias("instrument_id"),
        pl.col("is_suspended").cast(pl.Boolean).alias("is_suspended"),
        pl.col("trade_date").cast(pl.Date).alias("effective_from"),
        (pl.col("trade_date").cast(pl.Date) + pl.duration(days=1)).alias(
            "effective_to"
        ),
        pl.lit(observed_at).cast(pl.Datetime(time_zone="UTC")).alias("publication_at"),
        pl.lit(observed_at).cast(pl.Datetime(time_zone="UTC")).alias("available_at"),
    ).drop_nulls("instrument_id")
    return projected.drop("_trade_date_key", "trade_date_right", strict=False)


def project_basic_master_intervals(
    frame: pl.DataFrame,
    *,
    observed_at: datetime,
    resolve_instrument: Callable[[str, date], int | None],
) -> pl.DataFrame:
    """
    Project a raw basic-list snapshot into listing-lifetime PIT intervals.

    A basic snapshot is the provider's current roster: each row states one
    instrument's listing lifetime as best known now. The projection keeps
    that honesty — the interval spans list_date to delist_date and the whole
    snapshot becomes visible only at its observation time, so a later
    snapshot never leaks into an earlier cutoff's replay.
    """
    required = {"source_ticker", "list_date"}
    if not required.issubset(set(frame.columns)):
        raise ValueError("HISTORY_FIELDS_MISSING")
    asof = observed_at.date().isoformat()
    resolved = resolve_instrument(sorted(set(frame["source_ticker"].to_list())), asof)
    projected = frame.with_columns(
        pl.col("source_ticker")
        .replace_strict(resolved, default=None, return_dtype=pl.Int64)
        .alias("instrument_id"),
        pl.lit(observed_at).cast(pl.Datetime(time_zone="UTC")).alias("publication_at"),
        pl.lit(observed_at).cast(pl.Datetime(time_zone="UTC")).alias("available_at"),
    ).drop_nulls(subset=["instrument_id", "list_date"])
    delist = projected["delist_date"] if "delist_date" in projected.columns else None
    if delist is None:
        projected = projected.with_columns(
            pl.lit(None, dtype=pl.Date).alias("delist_date")
        )
    projected = projected.with_columns(
        pl.col("list_date").cast(pl.Date).alias("list_date"),
        pl.col("delist_date").cast(pl.Date).alias("delist_date"),
    )
    # The roster row stays open-ended: delisting is carried by the delist_date
    # column so the exclusion stays an honest roster fact, not row expiry.
    return projected.with_columns(
        pl.col("list_date").alias("effective_from"),
        pl.lit(None, dtype=pl.Date).alias("effective_to"),
    )


def visible_history(
    frame: pl.DataFrame,
    *,
    fields: tuple[str, ...],
    as_of: date,
    knowledge_cutoff: datetime,
    publication_cutoff: datetime,
    require_continuity: bool = False,
) -> pl.DataFrame:
    """Resolve revisions before validity; never revive an expired older revision."""
    if knowledge_cutoff.tzinfo is None or publication_cutoff.tzinfo is None:
        raise ValueError("HISTORY_CUTOFF_MISSING")
    _validate_history(frame, fields)
    visible = frame.filter(
        (
            pl.col("available_at").dt.convert_time_zone("UTC")
            <= knowledge_cutoff.astimezone(UTC)
        )
        & (
            pl.col("publication_at").dt.convert_time_zone("UTC")
            <= publication_cutoff.astimezone(UTC)
        )
        & (pl.col("effective_from") <= as_of)
    )
    known_ids = set(visible["instrument_id"].to_list())
    key = ["instrument_id", "effective_from"]
    if visible.select(
        pl.struct(*key, "available_at", "publication_at").is_duplicated().any()
    ).item():
        raise ValueError("HISTORY_REVISION_CONFLICT")
    visible = (
        visible.sort([*key, "available_at", "publication_at"])
        .unique(subset=key, keep="last")
        .filter(pl.col("effective_to").is_null() | (pl.col("effective_to") > as_of))
    )
    if visible["instrument_id"].is_duplicated().any():
        raise ValueError("HISTORY_INTERVAL_CONFLICT")
    if require_continuity and known_ids != set(visible["instrument_id"].to_list()):
        raise ValueError("MASTER_HISTORY_COVERAGE_MISSING")
    return visible.sort("instrument_id")


def project_historical_universe(
    master: pl.DataFrame,
    status: pl.DataFrame,
    *,
    as_of: date,
    knowledge_cutoff: datetime,
    publication_cutoff: datetime,
    membership: pl.DataFrame | None = None,
    index_id: str | None = None,
) -> pl.DataFrame:
    """Retain the observation roster and attach fail-closed investment reasons."""
    identity = visible_history(
        master,
        fields=(
            *MASTER_FIELDS,
            *(
                ("tracking_index",)
                if index_id is not None and membership is None
                else ()
            ),
        ),
        as_of=as_of,
        knowledge_cutoff=knowledge_cutoff,
        publication_cutoff=publication_cutoff,
        require_continuity=True,
    )
    if identity.select("list_date", "delist_date").dtypes != [pl.Date, pl.Date]:
        raise ValueError("HISTORY_DATE_PRECISION_INVALID")
    if identity.filter(pl.col("delist_date") <= pl.col("list_date")).height:
        raise ValueError("LISTING_INTERVAL_INVALID")
    if identity["list_date"].null_count():
        raise ValueError("LISTING_HISTORY_MISSING")
    trading = visible_history(
        status,
        fields=STATUS_FIELDS,
        as_of=as_of,
        knowledge_cutoff=knowledge_cutoff,
        publication_cutoff=publication_cutoff,
    )
    if trading.schema["is_suspended"] != pl.Boolean:
        raise ValueError("TRADING_STATUS_INVALID")
    identity_fields = ["instrument_id", "list_date", "delist_date"]
    if "tracking_index" in identity.columns:
        identity_fields.append("tracking_index")
    result = identity.select(identity_fields).join(
        trading.select("instrument_id", "is_suspended"),
        on="instrument_id",
        how="left",
    )
    reasons = [
        pl.when(pl.col("list_date") > as_of).then(pl.lit("NOT_YET_LISTED")),
        pl.when(pl.col("delist_date") <= as_of).then(pl.lit("DELISTED")),
        pl.when(pl.col("is_suspended").is_null()).then(
            pl.lit("TRADING_STATUS_MISSING")
        ),
        pl.when(pl.col("is_suspended")).then(pl.lit("SUSPENDED")),
    ]
    if index_id is not None and membership is None:
        reasons.append(
            pl.when(pl.col("tracking_index").is_null()).then(
                pl.lit("TRACKING_RELATION_MISSING")
            )
        )
        reasons.append(
            pl.when(pl.col("tracking_index") != index_id).then(
                pl.lit("OTHER_TRACKING_INDEX")
            )
        )
    if index_id is not None and membership is not None:
        if "index_id" not in membership.columns:
            raise ValueError("MEMBERSHIP_HISTORY_MISSING")
        members = visible_history(
            membership.filter(pl.col("index_id") == index_id),
            fields=MEMBERSHIP_FIELDS,
            as_of=as_of,
            knowledge_cutoff=knowledge_cutoff,
            publication_cutoff=publication_cutoff,
        )["instrument_id"]
        reasons.append(
            pl.when(~pl.col("instrument_id").is_in(members.implode())).then(
                pl.lit("NOT_INDEX_MEMBER")
            )
        )
    elif index_id is None and membership is not None:
        raise ValueError("MEMBERSHIP_SCOPE_MISSING")
    return (
        result.with_columns(
            pl.concat_list(reasons).list.drop_nulls().alias("exclusion_reasons")
        )
        .with_columns((pl.col("exclusion_reasons").list.len() == 0).alias("investable"))
        .sort("instrument_id")
    )


def _validate_history(frame: pl.DataFrame, fields: tuple[str, ...]) -> None:
    if not set(fields).issubset(frame.columns):
        raise ValueError("HISTORY_FIELDS_MISSING")
    if frame.schema["instrument_id"] != pl.Int64:
        raise ValueError("HISTORY_INSTRUMENT_INVALID")
    for column in ("effective_from", "effective_to"):
        if frame.schema[column] != pl.Date:
            raise ValueError("HISTORY_DATE_PRECISION_INVALID")
    for column in ("available_at", "publication_at"):
        dtype = frame.schema[column]
        if not isinstance(dtype, pl.Datetime) or dtype.time_zone is None:
            raise ValueError("HISTORY_TIME_EVIDENCE_MISSING")
    required = ("instrument_id", "effective_from", "publication_at", "available_at")
    if frame.select(pl.any_horizontal(pl.col(required).is_null()).any()).item():
        raise ValueError("HISTORY_TIME_EVIDENCE_MISSING")
    if frame.filter(pl.col("effective_to") <= pl.col("effective_from")).height:
        raise ValueError("HISTORY_INTERVAL_INVALID")
