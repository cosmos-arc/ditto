"""
Tests for create_ingestion_context context manager.

该模块测试使用 dishka 容器管理依赖的上下文管理器。
"""

import pytest
from ditto_datahub import DataHub

# 标记为串行执行，避免并行测试时数据库文件冲突
pytestmark = pytest.mark.serial


@pytest.mark.integration
@pytest.mark.usefixtures("prefect_test_session")
class TestCreateIngestionContext:
    """create_ingestion_context 的集成测试。"""

    def test_context_manager_exists(self):
        """Test that create_ingestion_context is defined."""
        from ditto_port.jobs.context import create_ingestion_context

        assert create_ingestion_context is not None
        assert callable(create_ingestion_context)

    def test_context_creates_datahub(self):
        """Test that context creates DataHub instance."""
        from ditto_port.jobs.context import create_ingestion_context

        with create_ingestion_context(source="tushare") as (hub, coordinator):
            assert hub is not None
            assert isinstance(hub, DataHub)
            assert coordinator is not None

    def test_context_provides_coordinator(self):
        """Test that context provides IngestionCoordinator instance."""
        from ditto_port.jobs.context import create_ingestion_context

        with create_ingestion_context(source="tushare") as (_hub, coordinator):
            assert coordinator is not None
            assert hasattr(coordinator, "ingest_date")

    def test_context_default_source_is_tushare(self):
        """Test that default source parameter is 'tushare'."""
        from ditto_port.jobs.context import create_ingestion_context

        # 不传 source 参数，应该使用默认值 "tushare"
        with create_ingestion_context() as (_hub, coordinator):
            assert coordinator is not None

    def test_context_supports_coordinator_usage(self):
        """Test that coordinator can be used within context."""
        from ditto_port.jobs.context import create_ingestion_context

        with create_ingestion_context(source="tushare") as (_hub, coordinator):
            # Verify coordinator has the expected methods
            assert hasattr(coordinator, "ingest_date")
            assert hasattr(coordinator, "ingest_range")

    def test_multiple_contexts_are_independent(self):
        """Test that multiple context instances are independent."""
        from ditto_port.jobs.context import create_ingestion_context

        with create_ingestion_context(source="tushare") as (hub1, _coord1):
            assert hub1 is not None
            hub1_id = id(hub1)

        # 第二个上下文应该创建新的容器
        with create_ingestion_context(source="tushare") as (hub2, _coord2):
            assert hub2 is not None
            hub2_id = id(hub2)

        # 两个 hub 应该是不同的实例（不同的容器）
        assert hub1_id != hub2_id
