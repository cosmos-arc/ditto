"""Public fund identities remain outside the tradable instrument universe."""

import polars as pl
import pytest
from ditto_data.storage.fundamental.fund_portfolio.identity import FundIdentityStore
from ditto_platform.foundation import SQLiteClient, SQLitePool


def test_public_fund_identity_is_independent_and_fail_closed(
    sqlite_pool_with_schema: SQLitePool,
) -> None:
    client = SQLiteClient(sqlite_pool_with_schema)
    identities = FundIdentityStore(client)
    holders = pl.DataFrame(
        {
            "source_ticker": ["000001.OF", "510300.SH"],
            "name": ["华夏成长", "沪深300"],
            "market": ["O", "E"],
            "status": ["L", "D"],
            "found_date": ["20011218", "20120504"],
        }
    )
    identities.register(holders)
    identities.register(holders)
    assert identities.list_codes() == ["000001.OF", "510300.SH"]
    assert client.fetchval("SELECT COUNT(*) FROM instrument") == 0
    identities.require(["000001.OF"])
    with pytest.raises(ValueError, match="unregistered fund holders"):
        identities.require(["000001.OF", "999999.OF"])


def test_legacy_codes_and_report_revision_identity(
    sqlite_pool_with_schema: SQLitePool,
) -> None:
    """Bodies, summaries and revisions retain explicit, immutable identities."""
    from hashlib import sha256

    from ditto_data.models.metadata import FundReportEvidence

    identities = FundIdentityStore(SQLiteClient(sqlite_pool_with_schema))
    identities.register(
        pl.DataFrame(
            {
                "source_ticker": ["0000371.OF", "F000355.OF"],
                "name": ["legacy", "share class"],
                "market": ["O", "O"],
                "status": ["D", "I"],
            }
        )
    )
    identities.require(["0000371.OF", "F000355.OF"])
    base = {
        "source_ticker": "0000371.OF",
        "report_date": "2025-12-31",
        "announcement_date": "2026-03-30",
        "report_type": "annual",
        "document_form": "body",
        "document_sha256": sha256(b"annual").hexdigest(),
        "source_url": "https://example.test/report",
        "title": "Annual body",
        "holdings_sha256": "1" * 64,
        "evidence_note": "Reviewed fixture",
    }
    original = FundReportEvidence.model_validate(base)
    identities.register_report(original, b"annual")
    summary = FundReportEvidence.model_validate(
        {
            **base,
            "document_form": "summary",
            "document_sha256": sha256(b"summary").hexdigest(),
        }
    )
    identities.register_report(summary, b"summary")
    revised = FundReportEvidence.model_validate(
        {
            **base,
            "announcement_date": "2026-04-01",
            "document_sha256": sha256(b"revised").hexdigest(),
            "revision_of": original.document_sha256,
        }
    )
    identities.register_report(revised, b"revised")
    identities.register_report(revised, b"revised")
    assert len(identities.reports("0000371.OF")) == 3
    with pytest.raises(ValueError, match="no matching original"):
        identities.register_report(
            FundReportEvidence.model_validate(
                {
                    **revised.model_dump(),
                    "revision_of": summary.document_sha256,
                }
            ),
            b"revised",
        )
    with pytest.raises(ValueError, match="immutable"):
        identities.register_report(
            FundReportEvidence.model_validate(
                {
                    **original.model_dump(),
                    "title": "changed assertion",
                }
            ),
            b"annual",
        )


def test_legacy_trading_links_survive_independent_holder_writes(
    sqlite_pool_with_schema: SQLitePool,
    tmp_path,
) -> None:
    from datetime import date

    from ditto_data.config.data_store import DataStoreSettings
    from ditto_data.di.fundamental import FundamentalProvider
    from ditto_platform.foundation import FileLockManager, OnDuplicate

    client = SQLiteClient(sqlite_pool_with_schema)
    settings = DataStoreSettings(data_root=tmp_path)
    provider = FundamentalProvider()
    writers = provider.fundamental_writers(
        client, settings, FileLockManager(tmp_path / "locks")
    )
    store = provider.fundamental_store(
        provider.fundamental_readers(client, settings), writers, client
    )
    store.register_fund_holders(
        pl.DataFrame(
            {
                "source_ticker": ["510300.SH", "000001.OF"],
                "name": ["ETF", "OTC"],
                "market": ["E", "O"],
                "status": ["L", "L"],
            }
        )
    )
    legacy = pl.DataFrame(
        {
            "source_ticker": ["510300.SH"],
            "report_date": [date(2026, 6, 30)],
            "knowledge_date": [date(2026, 7, 21)],
            "holding_symbol": ["600519.SH"],
            "market_value": [10.0],
            "holding_shares": [1.0],
            "instrument_id": [2000001],
            "source": ["tushare"],
        }
    )
    assert writers.fund_portfolio is not None
    # Seed the previous writer shape directly; the new service never creates IDs.
    writers.fund_portfolio.write(legacy, 2026, OnDuplicate.ERROR)
    incoming = legacy.with_columns(pl.lit(None, dtype=pl.Int64).alias("instrument_id"))
    prepared = store.preserve_fund_trading_links(incoming)
    assert prepared.equals(legacy)
    assert store.save_fund_portfolio(incoming, 2026, OnDuplicate.VERIFY_IDENTICAL) == 0
    new_holder = legacy.with_columns(pl.lit("000001.OF").alias("source_ticker"))
    assert (
        store.save_fund_portfolio(new_holder, 2026, OnDuplicate.VERIFY_IDENTICAL) == 1
    )
    assert store.preserve_fund_trading_links(new_holder)["instrument_id"].to_list() == [
        None
    ]
    with pytest.raises(ValueError, match="retry contains changed values"):
        store.save_fund_portfolio(
            incoming.with_columns(pl.lit(20.0).alias("market_value")),
            2026,
            OnDuplicate.VERIFY_IDENTICAL,
        )
