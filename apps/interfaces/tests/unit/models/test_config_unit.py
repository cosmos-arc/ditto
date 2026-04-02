"""Tests for Port config models."""

import pytest


@pytest.mark.unit
class TestDatasetEnum:
    """测试 Port Dataset 枚举."""

    def test_index_basic_exists(self) -> None:
        """验证 INDEX_BASIC 枚举存在且值正确."""
        from ditto_datahub.models import Dataset

        assert hasattr(Dataset, "INDEX_BASIC")
        assert Dataset.INDEX_BASIC.value == "index_basic"

    def test_index_daily_exists(self) -> None:
        """验证 INDEX_DAILY 枚举存在且值正确."""
        from ditto_datahub.models import Dataset

        assert hasattr(Dataset, "INDEX_DAILY")
        assert Dataset.INDEX_DAILY.value == "index_daily"


@pytest.mark.unit
class TestDatasetRegistry:
    """测试 INGESTION_SPECS."""

    def test_registry_has_index_basic(self) -> None:
        """验证 INGESTION_SPECS 包含 index_basic."""
        from ditto_app.config import INGESTION_SPECS, TaskTier
        from ditto_datahub.models import Dataset

        assert Dataset.INDEX_BASIC in INGESTION_SPECS
        config = INGESTION_SPECS[Dataset.INDEX_BASIC]
        assert config.tier == TaskTier.T0_META
        assert config.task_name == "ingest_index_basic"

    def test_registry_has_index_daily(self) -> None:
        """验证 INGESTION_SPECS 包含 index_daily."""
        from ditto_app.config import INGESTION_SPECS, TaskTier
        from ditto_datahub.models import Dataset

        assert Dataset.INDEX_DAILY in INGESTION_SPECS
        config = INGESTION_SPECS[Dataset.INDEX_DAILY]
        assert config.tier == TaskTier.T1_INCREMENTAL
        assert config.task_name == "ingest_index_daily"
