"""Re-export partition strategy from platform (backward compat)."""

from ditto_platform.foundation.storage.partition_strategy import (
    PartitionStrategy,
    YearlyPartition,
)

__all__ = ["PartitionStrategy", "YearlyPartition"]
