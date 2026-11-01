"""Top10 holders parquet storage."""

from ditto_data.storage.capital.top10_holders.reader import Top10HoldersReader
from ditto_data.storage.capital.top10_holders.writer import Top10HoldersWriter

__all__ = ["Top10HoldersReader", "Top10HoldersWriter"]
