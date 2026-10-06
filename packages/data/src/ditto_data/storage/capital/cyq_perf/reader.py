"""CyqPerf parquet reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class CyqPerfReader(ParquetDatasetReader):
    """Read capital/cyq_perf facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/cyq_perf")
