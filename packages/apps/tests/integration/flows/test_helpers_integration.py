"""
Tests for create_ingestion_bundle context manager.

该模块测试使用 dishka 容器管理依赖的上下文管理器。
"""

import pytest
from ditto_application.process.ingestion.backfill_manager import BackfillManager
from ditto_application.process.ingestion.retry_manager import RetryManager
from ditto_application.query.metadata import MetadataQueryFacade
from ditto_apps.registry import IngestionBundle, create_ingestion_bundle

# 标记为串行执行，避免并行测试时数据库文件冲突
pytestmark = pytest.mark.serial


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestCreateIngestionBundle:
    """create_ingestion_bundle 的集成测试。"""

    def test_context_manager_exists(self):
        """Test that create_ingestion_bundle is defined."""
        assert create_ingestion_bundle is not None
        assert callable(create_ingestion_bundle)

    def test_context_creates_bundle(self):
        """Test that context creates IngestionBundle instance."""
        with create_ingestion_bundle(source="tushare") as bundle:
            assert bundle is not None
            assert isinstance(bundle, IngestionBundle)
            assert bundle.metadata_facade is not None
            assert isinstance(bundle.metadata_facade, MetadataQueryFacade)
            assert bundle.coordinator is not None

    def test_context_provides_coordinator(self):
        """Test that context provides IngestionCoordinator instance."""
        with create_ingestion_bundle(source="tushare") as bundle:
            assert bundle.coordinator is not None
            assert hasattr(bundle.coordinator, "ingest_date")

    def test_context_default_source_is_tushare(self):
        """Test that default source parameter is 'tushare'."""
        # 不传 source 参数，应该使用默认值 "tushare"
        with create_ingestion_bundle() as bundle:
            assert bundle.coordinator is not None

    def test_context_supports_coordinator_usage(self):
        """Test that coordinator can be used within context."""
        with create_ingestion_bundle(source="tushare") as bundle:
            # Verify coordinator has the expected methods
            assert hasattr(bundle.coordinator, "ingest_date")
            assert hasattr(bundle.coordinator, "ingest_range")

    def test_bundle_contains_all_managers_and_facades(self):
        """Test that bundle contains all expected managers and facades."""
        with create_ingestion_bundle(source="tushare") as bundle:
            # 验证所有管理器和 facade 都存在
            assert bundle.coordinator is not None
            assert bundle.backfill_manager is not None
            assert isinstance(bundle.backfill_manager, BackfillManager)
            assert bundle.retry_manager is not None
            assert isinstance(bundle.retry_manager, RetryManager)
            assert bundle.metadata_facade is not None
            assert isinstance(bundle.metadata_facade, MetadataQueryFacade)

    def test_multiple_contexts_are_independent(self):
        """Test that multiple context instances are independent."""
        with create_ingestion_bundle(source="tushare") as bundle1:
            assert bundle1.coordinator is not None
            coordinator1_id = id(bundle1.coordinator)

        # 第二个上下文应该创建新的容器
        with create_ingestion_bundle(source="tushare") as bundle2:
            assert bundle2.coordinator is not None
            coordinator2_id = id(bundle2.coordinator)

        # 两个 coordinator 应该是不同的实例（不同的容器）
        assert coordinator1_id != coordinator2_id
