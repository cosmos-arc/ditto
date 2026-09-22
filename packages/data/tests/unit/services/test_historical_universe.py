"""Historical observation pools retain failures and exclude future evidence."""

from datetime import UTC, date, datetime

import polars as pl
import pytest
from ditto_data.services.historical_universe import project_historical_universe


@pytest.mark.pit
def test_delisting_boundary_retains_observation_and_future_revision_does_not_leak():
    known = datetime(2026, 1, 1, tzinfo=UTC)
    future = datetime(2026, 2, 1, tzinfo=UTC)
    master = pl.DataFrame(
        {
            "instrument_id": [1, 2, 1],
            "effective_from": [date(2020, 1, 1)] * 3,
            "effective_to": [None] * 3,
            "publication_at": [known, known, future],
            "available_at": [known, known, future],
            "list_date": [date(2020, 1, 1)] * 3,
            "delist_date": [date(2026, 1, 15), None, None],
        },
        schema_overrides={"effective_to": pl.Date, "delist_date": pl.Date},
    )
    status = pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "effective_from": [date(2026, 1, 1)] * 2,
            "effective_to": [date(2026, 2, 1)] * 2,
            "publication_at": [known] * 2,
            "available_at": [known] * 2,
            "is_suspended": [False, False],
        }
    )
    result = project_historical_universe(
        master,
        status,
        as_of=date(2026, 1, 15),
        knowledge_cutoff=known,
        publication_cutoff=known,
    )
    assert result.select("instrument_id", "investable", "exclusion_reasons").rows() == [
        (1, False, ["DELISTED"]),
        (2, True, []),
    ]
    before = project_historical_universe(
        master,
        status,
        as_of=date(2026, 1, 14),
        knowledge_cutoff=known,
        publication_cutoff=known,
    )
    assert before["investable"].to_list() == [True, True]
    revised = project_historical_universe(
        master,
        status,
        as_of=date(2026, 1, 15),
        knowledge_cutoff=future,
        publication_cutoff=future,
    )
    assert revised["investable"].to_list() == [True, True]


@pytest.mark.pit
def test_index_intervals_and_future_members_do_not_rewrite_observation_roster():

    master, status = history_frames((1, 2))
    early = datetime(2026, 1, 10, tzinfo=UTC)
    later = datetime(2026, 1, 16, tzinfo=UTC)
    membership = status.drop("is_suspended").with_columns(
        pl.lit("csi300").alias("index_id")
    )
    membership = membership.with_columns(
        pl.when(pl.col("instrument_id") == 1)
        .then(pl.lit(date(2026, 1, 15)))
        .otherwise(None)
        .cast(pl.Date)
        .alias("effective_to"),
        pl.when(pl.col("instrument_id") == 2)
        .then(pl.lit(later))
        .otherwise(pl.lit(VISIBLE))
        .alias("available_at"),
    )

    def resolve(day, cutoff):
        return project_historical_universe(
            master,
            status,
            membership=membership,
            index_id="csi300",
            as_of=day,
            knowledge_cutoff=cutoff,
            publication_cutoff=cutoff,
        )

    assert resolve(date(2026, 1, 14), early)["investable"].to_list() == [True, False]
    boundary = resolve(date(2026, 1, 15), early)
    assert boundary["instrument_id"].to_list() == [1, 2]
    assert boundary["exclusion_reasons"].to_list() == [
        ["NOT_INDEX_MEMBER"],
        ["NOT_INDEX_MEMBER"],
    ]
    assert resolve(date(2026, 1, 16), later)["investable"].to_list() == [False, True]


@pytest.mark.pit
def test_unknown_status_is_excluded_and_unproven_history_is_rejected():

    master, status = history_frames((1, 2))
    result = project_historical_universe(
        master,
        status.head(1),
        as_of=date(2026, 1, 15),
        knowledge_cutoff=VISIBLE,
        publication_cutoff=VISIBLE,
    )
    assert result["exclusion_reasons"].to_list() == [[], ["TRADING_STATUS_MISSING"]]
    with pytest.raises(ValueError, match="HISTORY_FIELDS_MISSING"):
        project_historical_universe(
            master.drop("available_at"),
            status,
            as_of=date(2026, 1, 15),
            knowledge_cutoff=VISIBLE,
            publication_cutoff=VISIBLE,
        )


VISIBLE = datetime(2026, 1, 1, tzinfo=UTC)


def history_frames(ids):
    common = {
        "instrument_id": list(ids),
        "effective_from": [date(2020, 1, 1)] * len(ids),
        "effective_to": [None] * len(ids),
        "publication_at": [VISIBLE] * len(ids),
        "available_at": [VISIBLE] * len(ids),
    }
    return (
        pl.DataFrame(
            {
                **common,
                "list_date": [date(2020, 1, 1)] * len(ids),
                "delist_date": [None] * len(ids),
            },
            schema_overrides={"effective_to": pl.Date, "delist_date": pl.Date},
        ),
        pl.DataFrame(
            {**common, "is_suspended": [False] * len(ids)},
            schema_overrides={"effective_to": pl.Date},
        ),
    )


@pytest.mark.pit
def test_master_gap_cannot_silently_remove_a_failed_security():
    master, status = history_frames((1, 2))
    master = master.with_columns(
        pl.when(pl.col("instrument_id") == 1)
        .then(pl.lit(date(2026, 1, 10)))
        .otherwise(None)
        .cast(pl.Date)
        .alias("effective_to")
    )
    with pytest.raises(ValueError, match="MASTER_HISTORY_COVERAGE_MISSING"):
        project_historical_universe(
            master,
            status,
            as_of=date(2026, 1, 15),
            knowledge_cutoff=VISIBLE,
            publication_cutoff=VISIBLE,
        )


@pytest.mark.pit
def test_etf_tracking_change_obeys_effective_and_knowledge_boundaries():
    master, status = history_frames((1,))
    old = master.with_columns(
        pl.lit("csi300").alias("tracking_index"),
        pl.lit(date(2026, 1, 15)).alias("effective_to"),
    )
    new = master.with_columns(
        pl.lit("csi500").alias("tracking_index"),
        pl.lit(date(2026, 1, 15)).alias("effective_from"),
    )
    master = pl.concat([old, new])

    def resolve(day):
        return project_historical_universe(
            master,
            status,
            index_id="csi300",
            as_of=day,
            knowledge_cutoff=VISIBLE,
            publication_cutoff=VISIBLE,
        )

    assert resolve(date(2026, 1, 14))["investable"].to_list() == [True]
    assert resolve(date(2026, 1, 15))["exclusion_reasons"].to_list() == [
        ["OTHER_TRACKING_INDEX"]
    ]
