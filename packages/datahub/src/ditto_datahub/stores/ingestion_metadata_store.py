"""Ingestion metadata store for tracking data ingestion history."""

from ditto_foundation import logger

from ditto_datahub.sources.metadata import IngestionMetadata
from ditto_datahub.stores.sqlite_client import SQLiteClient


class IngestionMetadataStore:
    """
    Store for ingestion metadata.

    Tracks data ingestion history for incremental updates,
    including last trade date, checksum, and row counts.
    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize store.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client
        logger.debug(
            "IngestionMetadataStore initialized",
            event="ingestion_metadata_store_init",
        )

    def get_metadata(self, dataset: str, source: str) -> IngestionMetadata | None:
        """
        Get ingestion metadata for a dataset.

        Args:
            dataset: Dataset name (e.g., "etf_daily").
            source: Data source identifier (e.g., "tushare").

        Returns:
            IngestionMetadata if found, None otherwise.

        """
        sql = """
            SELECT dataset, source, last_trade_date,
                   last_checksum, last_rows, last_updated_at
            FROM ingestion_metadata
            WHERE dataset = ? AND source = ?
        """

        row = self._client.fetchone(sql, [dataset, source])

        if not row:
            return None

        return IngestionMetadata(
            dataset=row["dataset"],
            source=row["source"],
            last_trade_date=row["last_trade_date"],  # Already a string
            last_checksum=row["last_checksum"],
            last_rows=row["last_rows"],
            last_updated_at=row["last_updated_at"],
        )

    def save_metadata(self, metadata: IngestionMetadata) -> None:
        """
        Save or update ingestion metadata.

        Args:
            metadata: IngestionMetadata to save.

        """
        sql = """
            INSERT INTO ingestion_metadata
            (dataset, source, last_trade_date, last_checksum,
             last_rows, last_updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (dataset, source) DO UPDATE SET
                last_trade_date = excluded.last_trade_date,
                last_checksum = excluded.last_checksum,
                last_rows = excluded.last_rows,
                last_updated_at = excluded.last_updated_at
        """

        self._client.execute(
            sql,
            [
                metadata.dataset,
                metadata.source,
                metadata.last_trade_date,  # Already a string (ISO format)
                metadata.last_checksum,
                metadata.last_rows,
                metadata.last_updated_at,
            ],
        )
        self._client.commit()

        logger.debug(
            "Ingestion metadata saved",
            event="ingestion_metadata_saved",
            dataset=metadata.dataset,
            source=metadata.source,
            last_trade_date=metadata.last_trade_date,
        )

    def list_pending_datasets(
        self, trade_date: str, source: str = "tushare"
    ) -> list[tuple[str, str]]:
        """
        List datasets that need ingestion for a given trade date.

        A dataset needs ingestion if:
        - No metadata exists (last_trade_date IS NULL)
        - last_trade_date < trade_date

        Args:
            trade_date: Trade date to check (YYYY-MM-DD format).
            source: Data source identifier (default: "tushare").

        Returns:
            List of (dataset, source) tuples that need ingestion.

        """
        sql = """
            SELECT dataset, source
            FROM ingestion_metadata
            WHERE source = ?
              AND (last_trade_date IS NULL OR last_trade_date < ?)
        """

        rows = self._client.fetchall(sql, [source, trade_date])
        return [(row["dataset"], row["source"]) for row in rows]

    def list_all_datasets(self, source: str = "tushare") -> list[tuple[str, str]]:
        """
        List all datasets with metadata.

        Args:
            source: Data source identifier (default: "tushare").

        Returns:
            List of (dataset, source) tuples.

        """
        sql = """
            SELECT dataset, source
            FROM ingestion_metadata
            WHERE source = ?
            ORDER BY dataset
        """

        rows = self._client.fetchall(sql, [source])
        return [(row["dataset"], row["source"]) for row in rows]
