"""Constants for data sources and database types."""


class DataSourceType:
    """Data source type constants."""

    TUSHARE = "tushare"
    AKSHARE = "akshare"


class DatabaseType:
    """Database type constants."""

    ANALYTICAL = "duckdb"
    TRANSACTIONAL = "sqlite"
