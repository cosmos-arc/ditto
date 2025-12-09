"""Factory for creating data source instances."""

from typing import Any, Dict, Type

from .akshare import AkShareDataSource
from .base import DataSource
from .tushare import TushareDataSource
from ..constants import DataSourceType


class DataSourceFactory:
    """Factory for creating data source instances."""

    # Registry of available data sources
    _sources: Dict[str, Type[DataSource]] = {
        DataSourceType.TUSHARE: TushareDataSource,
        DataSourceType.AKSHARE: AkShareDataSource,
    }

    @classmethod
    def create(cls, source_type: str, config: Dict[str, Any] | None = None) -> DataSource:
        """
        Create a data source instance.

        Args:
            source_type: Type of data source (from DataSourceType constants)
            config: Configuration dictionary for the data source

        Returns:
            An instance of the requested data source

        Raises:
            ValueError: If source_type is not supported
            ImportError: If required dependencies are not installed
        """
        if source_type not in cls._sources:
            available = ", ".join(cls._sources.keys())
            raise ValueError(
                f"Unsupported data source type: {source_type}. "
                f"Available types: {available}"
            )

        data_source_class = cls._sources[source_type]
        return data_source_class(config)

    @classmethod
    def register_source(cls, source_type: str, source_class: Type[DataSource]) -> None:
        """
        Register a new data source type.

        Args:
            source_type: The type identifier for the data source
            source_class: The data source class to register
        """
        cls._sources[source_type] = source_class

    @classmethod
    def get_available_sources(cls) -> list[str]:
        """Get list of available data source types."""
        return list(cls._sources.keys())

    @classmethod
    def create_tushare(cls, token: str, **kwargs: Any) -> TushareDataSource:
        """
        Convenience method to create Tushare data source.

        Args:
            token: Tushare API token
            **kwargs: Additional configuration options

        Returns:
            TushareDataSource instance
        """
        config = {"token": token, **kwargs}
        return cls.create(DataSourceType.TUSHARE, config)

    @classmethod
    def create_akshare(cls, **kwargs: Any) -> AkShareDataSource:
        """
        Convenience method to create AkShare data source.

        Args:
            **kwargs: Configuration options

        Returns:
            AkShareDataSource instance
        """
        return cls.create(DataSourceType.AKSHARE, kwargs)