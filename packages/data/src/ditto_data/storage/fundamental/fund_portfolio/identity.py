"""Public-fund holder identities; never allocate tradable instrument IDs."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha256

import orjson
import polars as pl
from ditto_platform.foundation import SQLiteClient

from ditto_data.models.metadata import FUND_HOLDER_CODE_PATTERN, FundReportEvidence


class FundIdentityStore:
    """Keep fund_basic evidence independently of the securities master."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def register(self, frame: pl.DataFrame) -> None:
        """Register observed identities, including inactive and OTC funds."""
        rows = frame.to_dicts()
        for row in rows:
            code = row.get("source_ticker")
            if (
                not isinstance(code, str)
                # fund_basic includes legacy 0000371.OF and H-share F000355.OF.
                or not re.fullmatch(FUND_HOLDER_CODE_PATTERN, code)
                or row.get("market") not in {"O", "E"}
                or row.get("status") not in {"L", "D", "I"}
                or not row.get("name")
            ):
                raise ValueError(f"invalid fund_basic identity: {code!r}")
        observed_at = datetime.now(UTC).isoformat()
        with self._client.conn:
            self._client.executemany(
                (
                    "INSERT INTO fund_holder (source_ticker, name, market, status, "
                    "source_payload, observed_at) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(source_ticker) DO UPDATE SET "
                    "name=excluded.name, market=excluded.market, "
                    "status=excluded.status, "
                    "source_payload=excluded.source_payload, "
                    "observed_at=excluded.observed_at"
                ),
                [
                    (
                        row["source_ticker"],
                        row["name"],
                        row["market"],
                        row["status"],
                        orjson.dumps(row, option=orjson.OPT_SORT_KEYS).decode(),
                        observed_at,
                    )
                    for row in rows
                ],
            )

    def list_codes(self) -> list[str]:
        """Return the observed holder universe, without filtering status."""
        return [
            str(row["source_ticker"])
            for row in self._client.fetchall(
                "SELECT source_ticker FROM fund_holder ORDER BY source_ticker"
            )
        ]

    def require(self, codes: list[str]) -> None:
        """Reject an entire write if any fund identity is absent."""
        missing = set(codes) - set(self.list_codes())
        if missing:
            raise ValueError(f"unregistered fund holders: {sorted(missing)}")

    def register_report(self, evidence: FundReportEvidence, document: bytes) -> None:
        """Retain a verified original without replacing an existing assertion."""
        self.require([evidence.source_ticker])
        if sha256(document).hexdigest() != evidence.document_sha256:
            raise ValueError("fund report document checksum mismatch")
        reports = self.reports(evidence.source_ticker)
        if evidence.revision_of is not None and not any(
            item.document_sha256 == evidence.revision_of
            and item.report_date == evidence.report_date
            and item.report_type == evidence.report_type
            and item.document_form == evidence.document_form
            and item.announcement_date <= evidence.announcement_date
            for item in reports
        ):
            raise ValueError("fund report revision has no matching original")
        for item in reports:
            if item.document_sha256 == evidence.document_sha256 and item != evidence:
                raise ValueError("fund report evidence is immutable")
        with self._client.conn:
            self._client.execute(
                (
                    "INSERT OR IGNORE INTO fund_report_evidence "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    evidence.source_ticker,
                    evidence.document_sha256,
                    evidence.report_date.isoformat(),
                    evidence.announcement_date.isoformat(),
                    evidence.holdings_sha256,
                    evidence.model_dump_json(),
                    document,
                    datetime.now(UTC).isoformat(),
                ),
            )
            stored = self._client.fetchval(
                (
                    "SELECT evidence_json FROM fund_report_evidence "
                    "WHERE source_ticker = ? AND document_sha256 = ?"
                ),
                (evidence.source_ticker, evidence.document_sha256),
            )
            if stored != evidence.model_dump_json():
                raise ValueError("fund report evidence is immutable")

    def reports(self, source_ticker: str) -> list[FundReportEvidence]:
        """Return explicit bodies, summaries and revisions."""
        return [
            FundReportEvidence.model_validate_json(row["evidence_json"])
            for row in self._client.fetchall(
                (
                    "SELECT evidence_json FROM fund_report_evidence "
                    "WHERE source_ticker = ? "
                    "ORDER BY announcement_date, document_sha256"
                ),
                (source_ticker,),
            )
        ]
