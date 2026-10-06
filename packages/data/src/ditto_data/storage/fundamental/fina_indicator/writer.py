"""FinaIndicator parquet writer."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class FinaIndicatorWriter(ParquetDatasetWriter):
    """Write fundamental/fina_indicator facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "fundamental/fina_indicator")
