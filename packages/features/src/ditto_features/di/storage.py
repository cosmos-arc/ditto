"""Features storage DI Provider — 衍生数据 SQLite 存储装配."""

from dishka import Provider, Scope, provide
from ditto_data.storage.sqlite_client import SQLiteClient

from ditto_features.services.derived_catalog_service import DerivedCatalogService
from ditto_features.storage.sqlite.derived import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)

__all__ = ["FeaturesStorageProvider"]


class FeaturesStorageProvider(Provider):
    """衍生数据 Provider — SQLite catalog 读写与域服务."""

    scope = Scope.APP

    @provide
    def derived_catalog_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteDerivedCatalogReader:
        """统一派生 catalog 读取器."""
        return SQLiteDerivedCatalogReader(sqlite_client)

    @provide
    def derived_catalog_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteDerivedCatalogWriter:
        """统一派生 catalog 写入器."""
        return SQLiteDerivedCatalogWriter(sqlite_client)

    @provide
    def derived_catalog_service(
        self,
        derived_catalog_reader: SQLiteDerivedCatalogReader,
        derived_catalog_writer: SQLiteDerivedCatalogWriter,
    ) -> DerivedCatalogService:
        """统一派生 catalog 记录服务."""
        return DerivedCatalogService(
            catalog_reader=derived_catalog_reader,
            catalog_writer=derived_catalog_writer,
        )
