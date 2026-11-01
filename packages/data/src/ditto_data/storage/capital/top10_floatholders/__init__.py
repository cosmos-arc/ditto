"""Top10 floatholders parquet storage."""

from ditto_data.storage.capital.top10_floatholders.reader import (
    Top10FloatholdersReader,
)
from ditto_data.storage.capital.top10_floatholders.writer import (
    Top10FloatholdersWriter,
)

__all__ = ["Top10FloatholdersReader", "Top10FloatholdersWriter"]
