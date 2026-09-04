"""Global index daily bar storage."""

from ditto_data.storage.market.index.global_bars.reader import GlobalIndexBarsReader
from ditto_data.storage.market.index.global_bars.writer import GlobalIndexBarsWriter

__all__ = ["GlobalIndexBarsReader", "GlobalIndexBarsWriter"]
