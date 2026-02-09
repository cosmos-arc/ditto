"""Tests for IndustryWriter."""

from __future__ import annotations

from typing import Any

import pytest
from ditto_datahub.stores.metadata.industry.industry_writer import (
    IndustryWriter,
)
from ditto_datahub.stores.metadata.industry.models import IndustryBasic


@pytest.fixture
def mock_client() -> Any:
    """Create mock SQLite client."""
    from unittest.mock import Mock

    client = Mock()
    client.execute = Mock()
    client.commit = Mock()
    client.rollback = Mock()
    return client


@pytest.fixture
def mock_cache() -> Any:
    """Create mock cache manager."""
    from unittest.mock import Mock

    cache = Mock()
    cache.invalidate = Mock(return_value=True)
    cache.invalidate_pattern = Mock(return_value=2)
    return cache


@pytest.fixture
def writer(mock_client: Any, mock_cache: Any) -> IndustryWriter:
    """Create IndustryWriter instance."""
    return IndustryWriter(mock_client, mock_cache)


class TestIndustryWriter:
    """Test suite for IndustryWriter."""

    def test_register_inserts_record(
        self,
        writer: IndustryWriter,
        mock_client: Any,
    ) -> None:
        """Test register inserts industry record."""
        industry = IndustryBasic(
            industry_id="sw_l1_new",
            industry_name="新行业",
            industry_level="L1",
        )

        writer.register(industry)

        mock_client.execute.assert_called_once()
        call_args = mock_client.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "INSERT OR REPLACE INTO industry_basic" in sql
        assert params[0] == "sw_l1_new"
        assert params[1] == "新行业"

    def test_register_commits_transaction(
        self,
        writer: IndustryWriter,
        mock_client: Any,
    ) -> None:
        """Test register commits after insert."""
        industry = IndustryBasic(
            industry_id="sw_l1_new",
            industry_name="新行业",
            industry_level="L1",
        )

        writer.register(industry)

        mock_client.commit.assert_called_once()

    def test_register_invalidates_cache(
        self,
        writer: IndustryWriter,
        mock_cache: Any,
    ) -> None:
        """Test register invalidates industry cache."""
        industry = IndustryBasic(
            industry_id="sw_l1_new",
            industry_name="新行业",
            industry_level="L1",
        )

        writer.register(industry)

        mock_cache.invalidate_pattern.assert_called_once_with("industry:*")

    def test_register_with_parent_id(
        self,
        writer: IndustryWriter,
        mock_client: Any,
    ) -> None:
        """Test register with parent_id."""
        industry = IndustryBasic(
            industry_id="sw_l2_new",
            industry_name="二级行业",
            industry_level="L2",
            parent_id="sw_l1_01",
        )

        writer.register(industry)

        call_args = mock_client.execute.call_args
        params = call_args[0][1]
        assert params[3] == "sw_l1_01"  # parent_id

    def test_register_with_inactive(
        self,
        writer: IndustryWriter,
        mock_client: Any,
    ) -> None:
        """Test register with inactive industry."""
        industry = IndustryBasic(
            industry_id="sw_l1_inactive",
            industry_name="停用行业",
            industry_level="L1",
            is_active=False,
        )

        writer.register(industry)

        call_args = mock_client.execute.call_args
        params = call_args[0][1]
        assert params[4] == 0  # is_active

    def test_register_with_active_true(
        self,
        writer: IndustryWriter,
        mock_client: Any,
    ) -> None:
        """Test register with active industry (default)."""
        industry = IndustryBasic(
            industry_id="sw_l1_active",
            industry_name="活跃行业",
            industry_level="L1",
            is_active=True,
        )

        writer.register(industry)

        call_args = mock_client.execute.call_args
        params = call_args[0][1]
        assert params[4] == 1  # is_active

    def test_register_handles_database_error(
        self,
        writer: IndustryWriter,
        mock_client: Any,
    ) -> None:
        """Test register propagates database errors."""
        mock_client.execute.side_effect = Exception("Database error")

        industry = IndustryBasic(
            industry_id="sw_l1_error",
            industry_name="错误行业",
            industry_level="L1",
        )

        with pytest.raises(Exception, match="Database error"):
            writer.register(industry)

        # Should not commit on error
        mock_client.commit.assert_not_called()
