"""HsgtTop10 parquet reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.capital.version_eligibility import CapitalVersionReader


class HsgtTop10Reader(CapitalVersionReader):
    """Read capital/hsgt_top10 facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/hsgt_top10")
