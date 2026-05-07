"""Partition strategy for Parquet file organization."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PartitionStrategy(Protocol):
    """
    Partition strategy protocol.

    Defines how data is organized into different partition files.
    Uses Protocol (structural subtyping); implementers need not explicitly inherit.

    Examples:
        >>> strategy = YearlyPartition()
        >>> key = strategy.get_partition_key("2024-01-01")
        >>> assert key == "2024"
        >>> filename = strategy.get_filename(key)
        >>> assert filename == "2024.parquet"

    """

    def get_partition_key(self, date_str: str) -> str:
        """
        Extract partition key from date string.

        Args:
            date_str: Date string (YYYY-MM-DD).

        Returns:
            Partition key.

        """
        ...

    def get_filename(self, partition_key: str) -> str:
        """
        Generate partition file name.

        Args:
            partition_key: Partition key.

        Returns:
            File name.

        """
        ...

    def get_partitions_from_filters(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> list[str]:
        """
        Get partition keys to read based on date range filters.

        Args:
            start_date: Start date (YYYY-MM-DD) (optional).
            end_date: End date (YYYY-MM-DD) (optional).

        Returns:
            List of partition keys.

        """
        ...


class YearlyPartition:
    """
    Yearly partition strategy.

    Organizes data into yearly Parquet files:
    - 2020.parquet
    - 2021.parquet
    - 2022.parquet
    ...

    Examples:
        >>> strategy = YearlyPartition()
        >>> strategy.get_partition_key("2024-01-15")
        '2024'
        >>> strategy.get_filename("2024")
        '2024.parquet'
        >>> strategy.get_partitions_from_filters("2023-01-01", "2024-12-31")
        ['2023', '2024']

    """

    def get_partition_key(self, date_str: str) -> str:
        """
        Extract year from date string.

        Args:
            date_str: Date string (YYYY-MM-DD).

        Returns:
            Year string.

        """
        return date_str[:4]

    def get_filename(self, partition_key: str) -> str:
        """
        Generate partition file name.

        Args:
            partition_key: Year string.

        Returns:
            File name (YYYY.parquet).

        """
        return f"{partition_key}.parquet"

    def get_partitions_from_filters(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> list[str]:
        """
        Get year list based on date range filters.

        Args:
            start_date: Start date (YYYY-MM-DD) (optional).
            end_date: End date (YYYY-MM-DD) (optional).

        Returns:
            List of year strings. Empty list means scan all files.

        """
        # No filters, return empty (scan all files)
        if not start_date and not end_date:
            return []

        start_year = int(start_date[:4]) if start_date else None
        end_year = int(end_date[:4]) if end_date else None

        # Both start_year and end_year provided: return range
        if start_year and end_year:
            return [str(y) for y in range(start_year, end_year + 1)]

        # Only start_year or end_year: return empty list, scan all files
        # Rely on Polars predicate pushdown for date filtering
        return []
