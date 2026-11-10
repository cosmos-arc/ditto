"""Frozen membership identities keep their exit facts immutable across retries."""

from unittest.mock import MagicMock

from ditto_application.builders.historical_members import (
    freeze_membership_intervals,
    freeze_roster,
)


def _metadata(delist_date: str | None) -> MagicMock:
    metadata = MagicMock()
    metadata.universe.get_constituent_history.return_value = [
        {"instrument_id": 1005603, "effective_from": "2017-07-03", "effective_to": None}
    ]
    metadata.instrument.get_instrument.return_value = {
        "ticker": "000033",
        "asset_class": "stock",
        "exchange": "SZSE",
        "list_date": "1994-01-03",
        "delist_date": delist_date,
    }
    metadata.instrument.get_source_ticker.return_value = "000033.SZ"
    return metadata


def test_original_roster_freezes_the_exit_fact_present_at_request_time():
    roster = list(
        freeze_roster(
            _metadata("2017-07-07"),
            freeze_membership_intervals(
                _metadata("2017-07-07"), "u", start="2017-07-03", end="2017-07-10"
            ),
            start="2017-07-03",
            source="tushare",
        )
    )
    assert roster[0]["delist_date"] == "2017-07-07"


def test_saved_roster_keeps_missing_exit_fact_even_after_master_updates():
    """An along-original retry must not adopt a later-recorded delisting."""
    frozen_without_fact = list(
        freeze_roster(
            _metadata(None),
            freeze_membership_intervals(
                _metadata(None), "u", start="2017-07-03", end="2017-07-10"
            ),
            start="2017-07-03",
            source="tushare",
        )
    )
    assert frozen_without_fact[0]["delist_date"] is None

    metadata_now_with_fact = _metadata("2017-07-07")
    metadata_now_with_fact.universe.get_constituent_history.return_value = [
        {"instrument_id": 1005603, "effective_from": "2017-07-03", "effective_to": None}
    ]
    retried = list(
        freeze_roster(
            metadata_now_with_fact,
            freeze_membership_intervals(
                metadata_now_with_fact,
                "u",
                start="2017-07-03",
                end="2017-07-10",
                original={
                    "membership_intervals": [
                        {
                            "instrument_id": 1005603,
                            "effective_from": "2017-07-03",
                            "effective_to": None,
                        }
                    ],
                    "roster": frozen_without_fact,
                },
            ),
            start="2017-07-03",
            source="tushare",
            original={"roster": frozen_without_fact},
        )
    )
    assert retried[0]["delist_date"] is None
    metadata_now_with_fact.instrument.get_instrument.assert_not_called()
