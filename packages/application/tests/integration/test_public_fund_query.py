"""Real fund holder identity, Parquet persistence and application query seam."""

from datetime import date
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

import orjson
import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.fundamental import FundamentalQueryFacade
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.di.fundamental import FundamentalProvider
from ditto_data.models.metadata import FundReportEvidence
from ditto_data.services.fundamental_store import fund_holdings_checksum
from ditto_platform.foundation import (
    FileLockManager,
    OnDuplicate,
    SQLiteClient,
    SQLitePool,
)


@pytest.mark.pit
def test_otc_fund_disclosures_preserve_nulls_and_late_observations(
    tmp_path: Path,
) -> None:
    schema = Path(str(files("ditto_data.scripts") / "schema.sql"))
    pool = SQLitePool(str(tmp_path / "metadata.sqlite"), schema_path=schema)
    pool.init_schema()
    try:
        client = SQLiteClient(pool)
        settings = DataStoreSettings(data_root=tmp_path)
        provider = FundamentalProvider()
        store = provider.fundamental_store(
            provider.fundamental_readers(client, settings),
            provider.fundamental_writers(
                client, settings, FileLockManager(tmp_path / "locks")
            ),
            client,
        )
        store.register_fund_holders(
            pl.DataFrame(
                {
                    "source_ticker": ["000001.OF"],
                    "name": ["华夏成长"],
                    "market": ["O"],
                    "status": ["L"],
                }
            )
        )
        frame = pl.DataFrame(
            {
                "source_ticker": ["000001.OF"] * 2,
                "report_date": [date(2026, 6, 30)] * 2,
                "knowledge_date": [date(2026, 7, 21), date(2026, 8, 31)],
                "holding_symbol": ["600519.SH"] * 2,
                "market_value": [10.0, 999999.0],
                "holding_shares": [None, 5.0],
                "instrument_id": pl.Series([None, None], dtype=pl.Int64),
                "source": ["tushare"] * 2,
            }
        )
        store.save_fund_portfolio(frame, 2026, OnDuplicate.VERIFY_IDENTICAL)
        store.save_fund_portfolio(frame, 2026, OnDuplicate.VERIFY_IDENTICAL)
        query = FundamentalQueryFacade(store)
        visible = query.get_fund_portfolio(
            "000001.OF",
            "2026-01-01",
            "2026-12-31",
            "2026-07-21",
            allow_experimental_data=True,
        )
        assert visible["market_value"].to_list() == [10.0]
        assert visible["holding_shares"].to_list() == [None]
        assert visible["report_type"].to_list() == ["unknown"]
        assert visible["holding_scope"].to_list() == ["disclosed_subset"]
        assert (
            query.get_fund_portfolio(
                "000001.OF",
                "2026-01-01",
                "2026-12-31",
                "2026-08-31",
                allow_experimental_data=True,
            ).height
            == 2
        )
        assert client.fetchval("SELECT COUNT(*) FROM instrument") == 0
        with pytest.raises(AppQueryError, match="completeness is unverified"):
            query.get_fund_portfolio(
                "000001.OF", "2026-01-01", "2026-12-31", require_complete=True
            )
        with pytest.raises(ValueError, match="unregistered fund holders"):
            store.save_fund_portfolio(
                frame.with_columns(pl.lit("999999.OF").alias("source_ticker")), 2026
            )
        for index, report_type in enumerate(("quarterly", "semiannual")):
            document = f"recorded {report_type} report fixture".encode()
            observation = frame.slice(index, 1)
            evidence = FundReportEvidence.model_validate(
                {
                    "source_ticker": "000001.OF",
                    "report_date": "2026-06-30",
                    "announcement_date": observation["knowledge_date"][0],
                    "report_type": report_type,
                    "document_form": "body",
                    "document_sha256": sha256(document).hexdigest(),
                    "source_url": "https://example.test/fund-report.pdf",
                    "title": f"2026 {report_type} report",
                    "holdings_sha256": fund_holdings_checksum(observation),
                    "evidence_note": "Recorded fixture; exact holding rows checked",
                }
            )
            store.register_fund_report(evidence, document)
            store.register_fund_report(evidence, document)
            with pytest.raises(ValueError, match="document checksum mismatch"):
                store.register_fund_report(evidence, b"changed document")
        annotated = query.get_fund_portfolio(
            "000001.OF",
            "2026-01-01",
            "2026-12-31",
            "2026-08-31",
            allow_experimental_data=True,
        )
        assert annotated["report_type"].to_list() == ["quarterly", "semiannual"]
        assert annotated["revision_of"].to_list() == [None, None]
        assert all(
            orjson.loads(value)[0]["document_form"] == "body"
            for value in annotated["report_evidence"]
        )
        assert annotated["holding_shares"].to_list() == [None, 5.0]
    finally:
        pool.close()
