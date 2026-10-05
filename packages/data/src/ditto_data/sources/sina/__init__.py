"""新浪外盘期货数据源（免费公开无 key，#436）."""

from ditto_data.sources.sina.client import SinaClient
from ditto_data.sources.sina.source import SinaSource

__all__ = ["SinaClient", "SinaSource"]
