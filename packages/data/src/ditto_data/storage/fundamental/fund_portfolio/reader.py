"""FundPortfolio parquet reader."""

from ditto_platform.foundation import ParquetStore

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


class FundPortfolioReader(ParquetDatasetReader):
    """Read fundamental/fund_portfolio facts."""

    def __init__(self, store: ParquetStore) -> None:
        super().__init__(store, "fundamental/fund_portfolio")
