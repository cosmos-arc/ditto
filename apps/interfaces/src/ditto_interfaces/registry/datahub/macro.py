"""DataHub 层 - Macro Domain Provider。"""

from dishka import Provider, Scope, provide
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.stores.macro.indicator.indicator_reader import (
    IndicatorReader as MacroIndicatorReader,
)
from ditto_datahub.stores.macro.indicator.indicator_writer import (
    IndicatorWriter as MacroIndicatorWriter,
)
from ditto_datahub.stores.macro.indicator.metadata_reader import (
    IndicatorMetadataReader as MacroIndicatorMetadataReader,
)
from ditto_datahub.stores.macro.indicator.metadata_writer import (
    IndicatorMetadataWriter as MacroIndicatorMetadataWriter,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient

__all__ = ["MacroProvider"]


class MacroProvider(Provider):
    """Macro Domain Provider - 宏观经济指标."""

    scope = Scope.APP

    # ========================================================================
    # Macro Indicator Stores
    # ========================================================================

    @provide
    def macro_indicator_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorReader:
        """Macro indicator reader."""
        return MacroIndicatorReader(client=sqlite_client)

    @provide
    def macro_indicator_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorWriter:
        """Macro indicator writer."""
        return MacroIndicatorWriter(client=sqlite_client)

    @provide
    def macro_indicator_metadata_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorMetadataReader:
        """Macro indicator metadata reader."""
        return MacroIndicatorMetadataReader(client=sqlite_client)

    @provide
    def macro_indicator_metadata_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorMetadataWriter:
        """Macro indicator metadata writer."""
        return MacroIndicatorMetadataWriter(client=sqlite_client)

    # ========================================================================
    # Macro Service
    # ========================================================================

    @provide
    def macro_service(
        self,
        indicator_reader: MacroIndicatorReader,
        indicator_writer: MacroIndicatorWriter,
        metadata_reader: MacroIndicatorMetadataReader,
        metadata_writer: MacroIndicatorMetadataWriter,
    ) -> MacroService:
        """Macro domain unified service."""
        return MacroService(
            indicator_reader=indicator_reader,
            indicator_writer=indicator_writer,
            metadata_reader=metadata_reader,
            metadata_writer=metadata_writer,
        )
