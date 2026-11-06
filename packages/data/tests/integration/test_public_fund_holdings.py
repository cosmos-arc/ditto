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
