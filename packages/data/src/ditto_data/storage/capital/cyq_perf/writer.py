"""CyqPerf parquet writer."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter


class CyqPerfWriter(ParquetDatasetWriter):
    """Write capital/cyq_perf facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "capital/cyq_perf")
