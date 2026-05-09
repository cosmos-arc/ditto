"""Path layout helpers for ParquetStore — partition resolution and file discovery."""

from __future__ import annotations

from pathlib import Path

from ditto_platform.foundation.storage.partition_strategy import PartitionStrategy


def get_path(
    data_root: Path,
    dataset: str,
    partition_key: str,
    partition: PartitionStrategy,
) -> Path:
    """Resolve a single partition file path."""
    return data_root / dataset / partition.get_filename(partition_key)


def get_partition_key(date_str: str, partition: PartitionStrategy) -> str:
    """Extract partition key from a date string."""
    return partition.get_partition_key(date_str)


def collect_paths(
    data_root: Path,
    dataset: str,
    partition: PartitionStrategy,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[Path]:
    """Collect partition file paths, optionally filtered by date range."""
    partition_keys = partition.get_partitions_from_filters(start_date, end_date)

    if not partition_keys:
        dataset_dir = data_root / dataset
        if not dataset_dir.exists():
            return []
        return sorted(dataset_dir.glob("*.parquet"))

    paths: list[Path] = []
    for key in partition_keys:
        path = get_path(data_root, dataset, key, partition)
        if path.exists():
            paths.append(path)
    return sorted(paths)
