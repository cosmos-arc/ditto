"""DataHub 层 - Features & Factors Domain Provider。"""

from dishka import Provider, Scope, provide
from ditto_datahub.config.data_store import DataStoreSettings
from ditto_datahub.services.factor_service import FactorService
from ditto_datahub.services.feature_service import FeatureService
from ditto_datahub.stores.factors.factor_metadata_reader import (
    FactorMetadataReader,
)
from ditto_datahub.stores.factors.factor_metadata_writer import (
    FactorMetadataWriter,
)
from ditto_datahub.stores.factors.factor_reader import FactorReader
from ditto_datahub.stores.factors.factor_writer import FactorWriter

# Features stores (使用别名避免行太长)
from ditto_datahub.stores.features.technical import (
    IndicatorMetadataReader as TechnicalIndicatorMetadataReader,
)
from ditto_datahub.stores.features.technical import (
    IndicatorMetadataWriter as TechnicalIndicatorMetadataWriter,
)
from ditto_datahub.stores.features.technical import (
    IndicatorReader as TechnicalIndicatorReader,
)
from ditto_datahub.stores.features.technical import (
    IndicatorWriter as TechnicalIndicatorWriter,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient

__all__ = ["FeaturesProvider"]


class FeaturesProvider(Provider):
    """Features & Factors Domain Provider - 技术指标、因子."""

    scope = Scope.APP

    # ========================================================================
    # Technical Indicator Stores
    # ========================================================================

    @provide
    def technical_indicator_reader(
        self,
        settings: DataStoreSettings,
    ) -> TechnicalIndicatorReader:
        """TechnicalIndicator reader."""
        return TechnicalIndicatorReader(
            settings.features_technical_indicators_narrow_path
        )

    @provide
    def technical_indicator_writer(
        self,
        settings: DataStoreSettings,
    ) -> TechnicalIndicatorWriter:
        """TechnicalIndicator writer."""
        return TechnicalIndicatorWriter(
            settings.features_technical_indicators_narrow_path
        )

    @provide
    def technical_indicator_metadata_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> TechnicalIndicatorMetadataReader:
        """TechnicalIndicator metadata reader."""
        return TechnicalIndicatorMetadataReader(client=sqlite_client)

    @provide
    def technical_indicator_metadata_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> TechnicalIndicatorMetadataWriter:
        """TechnicalIndicator metadata writer."""
        return TechnicalIndicatorMetadataWriter(client=sqlite_client)

    # ========================================================================
    # Factor Stores
    # ========================================================================

    @provide
    def factor_reader(
        self,
        settings: DataStoreSettings,
    ) -> FactorReader:
        """Factor reader."""
        return FactorReader(settings.factors_narrow_path)

    @provide
    def factor_writer(
        self,
        settings: DataStoreSettings,
    ) -> FactorWriter:
        """Factor writer."""
        return FactorWriter(settings.factors_narrow_path)

    @provide
    def factor_metadata_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> FactorMetadataReader:
        """Factor metadata reader."""
        return FactorMetadataReader(client=sqlite_client)

    @provide
    def factor_metadata_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> FactorMetadataWriter:
        """Factor metadata writer."""
        return FactorMetadataWriter(client=sqlite_client)

    # ========================================================================
    # Feature Service
    # ========================================================================

    @provide
    def feature_service(
        self,
        indicator_reader: TechnicalIndicatorReader,
        indicator_writer: TechnicalIndicatorWriter,
        metadata_reader: TechnicalIndicatorMetadataReader,
        metadata_writer: TechnicalIndicatorMetadataWriter,
    ) -> FeatureService:
        """Features domain unified service."""
        return FeatureService(
            indicator_reader=indicator_reader,
            indicator_writer=indicator_writer,
            metadata_reader=metadata_reader,
            metadata_writer=metadata_writer,
        )

    # ========================================================================
    # Factor Service
    # ========================================================================

    @provide
    def factor_service(
        self,
        factor_reader: FactorReader,
        factor_writer: FactorWriter,
        metadata_reader: FactorMetadataReader,
        metadata_writer: FactorMetadataWriter,
    ) -> FactorService:
        """Factors domain unified service."""
        return FactorService(
            factor_reader=factor_reader,
            factor_writer=factor_writer,
            metadata_reader=metadata_reader,
            metadata_writer=metadata_writer,
        )
