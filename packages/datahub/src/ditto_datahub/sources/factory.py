"""DataSource factory for creating data source instances."""

from __future__ import annotations

from ditto_datahub.sources.base import DataSource
from ditto_datahub.sources.tushare.source import TushareSource


def get_source(name: str) -> DataSource:
    """
    Factory function to get DataSource instance.

    Args:
        name: Source name ("tushare" or "akshare").

    Returns:
        DataSource instance.

    Raises:
        ValueError: If source name is unknown or not implemented.

    """
    normalized_name = name.lower().strip()

    if normalized_name == "tushare":
        return TushareSource()

    if normalized_name == "akshare":
        raise ValueError(
            f"Source '{name}' is not yet implemented. Planned for Sprint-02."
        )

    raise ValueError(f"Unknown source: '{name}'. Supported sources: tushare")
