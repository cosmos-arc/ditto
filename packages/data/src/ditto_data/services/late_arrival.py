"""Re-export shim — module moved to ditto_data.ingestion."""

from ditto_data.ingestion.late_arrival import check_late_arrival

__all__ = [
    "check_late_arrival",
]
