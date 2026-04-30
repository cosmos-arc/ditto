"""Tests for Macro API router.

使用 FastAPI TestClient 测试路由，mock MacroService.
"""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.services.macro_service import MacroService
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_macro_service() -> MagicMock:
    """创建 mock MacroService."""
    return MagicMock(spec=MacroService)


@pytest.fixture
def app(mock_macro_service: MagicMock) -> FastAPI:
    """创建测试 FastAPI 应用."""
    from dishka import Provider, Scope, make_async_container, provide
    from dishka.integrations.fastapi import setup_dishka

    app = FastAPI()

    # 导入 router 在 fixture 内部以避免循环导入
    from ditto_apps.api.routes.macro import router

    class TestProvider(Provider):
        """测试 Provider."""

        scope = Scope.APP

        @provide
        def get_macro_service(self) -> MacroService:
            """返回 mock MacroService."""
            return mock_macro_service

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)

    app.include_router(router, prefix="/api/v1")

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """创建测试客户端."""
    return TestClient(app)


@pytest.mark.integration
class TestGetIndicators:
    """测试 POST /indicators."""

    def test_post_indicators_with_valid_params(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试有效参数查询宏观指标."""
        # Arrange
        mock_macro_service.find_indicators.return_value = pl.DataFrame(
            {
                "indicator_id": [1, 1],
                "code": ["GDP", "GDP"],
                "name": ["国内生产总值", "国内生产总值"],
                "category": ["economic", "economic"],
                "frequency": ["quarterly", "quarterly"],
                "date": ["2024-03-31", "2024-06-30"],
                "value": [296299.0, 320000.0],
                "unit": ["亿元", "亿元"],
            }
        )

        # Act
        response = client.post(
            "/api/v1/macro/indicators",
            json={
                "indicators": ["GDP"],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 2
        assert data["data"][0]["code"] == "GDP"
        assert data["data"][0]["date"] == "2024-03-31"

    def test_post_indicators_with_category_filter(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试按类别过滤."""
        # Arrange
        mock_macro_service.find_indicators.return_value = pl.DataFrame(
            {
                "indicator_id": [1],
                "code": ["GDP"],
                "name": ["国内生产总值"],
                "category": ["economic"],
                "frequency": ["quarterly"],
                "date": ["2024-03-31"],
                "value": [296299.0],
                "unit": ["亿元"],
            }
        )

        # Act
        response = client.post(
            "/api/v1/macro/indicators",
            json={
                "category": "economic",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["category"] == "economic"

        # 验证 service 被正确调用
        mock_macro_service.find_indicators.assert_called_once()

    def test_post_indicators_with_frequency_filter(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试按频率过滤."""
        # Arrange
        mock_macro_service.find_indicators.return_value = pl.DataFrame(
            {
                "indicator_id": [1],
                "code": ["GDP"],
                "name": ["国内生产总值"],
                "category": ["economic"],
                "frequency": ["quarterly"],
                "date": ["2024-03-31"],
                "value": [296299.0],
                "unit": ["亿元"],
            }
        )

        # Act
        response = client.post(
            "/api/v1/macro/indicators",
            json={
                "frequency": "quarterly",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["frequency"] == "quarterly"

    def test_post_indicators_empty_result(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_macro_service.find_indicators.return_value = pl.DataFrame()

        # Act
        response = client.post(
            "/api/v1/macro/indicators",
            json={
                "indicators": ["INVALID_CODE"],
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_post_indicators_with_invalid_date_range(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试无效日期范围 (start_date > end_date)."""
        # Act
        response = client.post(
            "/api/v1/macro/indicators",
            json={
                "start_date": "2024-12-31",
                "end_date": "2024-01-01",
            },
        )

        # Assert - Pydantic 验证失败
        assert response.status_code == 422

    def test_post_indicators_with_invalid_category(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试无效的类别."""
        # Act
        response = client.post(
            "/api/v1/macro/indicators",
            json={
                "category": "invalid",
            },
        )

        # Assert - Pydantic 验证失败
        assert response.status_code == 422

    def test_post_indicators_with_invalid_frequency(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试无效的频率."""
        # Act
        response = client.post(
            "/api/v1/macro/indicators",
            json={
                "frequency": "invalid",
            },
        )

        # Assert - Pydantic 验证失败
        assert response.status_code == 422

    def test_post_indicators_without_params(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试不提供参数（返回所有指标）."""
        # Arrange
        mock_macro_service.find_indicators.return_value = pl.DataFrame()

        # Act
        response = client.post(
            "/api/v1/macro/indicators",
            json={},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_post_indicators_with_indicator_ids(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试使用指标 ID 列表查询."""
        # Arrange
        mock_macro_service.find_indicators.return_value = pl.DataFrame(
            {
                "indicator_id": [1, 2],
                "code": ["GDP", "CPI"],
                "name": ["国内生产总值", "消费者物价指数"],
                "category": ["economic", "economic"],
                "frequency": ["quarterly", "monthly"],
                "date": ["2024-03-31", "2024-06-30"],
                "value": [296299.0, 102.5],
                "unit": ["亿元", None],
            }
        )

        # Act
        response = client.post(
            "/api/v1/macro/indicators",
            json={
                "indicators": [1, 2],
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2


@pytest.mark.integration
class TestGetIndicatorsMetadata:
    """测试 GET /indicators/metadata."""

    def test_get_metadata_with_valid_params(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试获取指标元数据列表."""
        # Arrange
        mock_macro_service.list_indicators.return_value = pl.DataFrame(
            {
                "indicator_id": [1, 2],
                "code": ["GDP", "CPI"],
                "name": ["国内生产总值", "消费者物价指数"],
                "category": ["economic", "economic"],
                "frequency": ["quarterly", "monthly"],
                "date": ["2024-03-31", "2024-06-30"],
                "value": [296299.0, 102.5],
                "unit": ["亿元", None],
            }
        )

        # Act
        response = client.get(
            "/api/v1/macro/indicators/metadata",
            params={
                "start": "2024-01-01",
                "end": "2024-12-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 2
        assert data["data"][0]["code"] == "GDP"

    def test_get_metadata_with_category_filter(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试按类别获取元数据."""
        # Arrange
        mock_macro_service.list_indicators.return_value = pl.DataFrame(
            {
                "indicator_id": [1],
                "code": ["GDP"],
                "name": ["国内生产总值"],
                "category": ["economic"],
                "frequency": ["quarterly"],
                "date": ["2024-03-31"],
                "value": [296299.0],
                "unit": ["亿元"],
            }
        )

        # Act
        response = client.get(
            "/api/v1/macro/indicators/metadata",
            params={
                "start": "2024-01-01",
                "end": "2024-12-31",
                "category": "economic",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["category"] == "economic"

        # 验证 service 被正确调用
        mock_macro_service.list_indicators.assert_called_once()
        call_kwargs = mock_macro_service.list_indicators.call_args.kwargs
        assert call_kwargs["start"] == "2024-01-01"
        assert call_kwargs["end"] == "2024-12-31"
        assert call_kwargs["category"] == "economic"

    def test_get_metadata_empty_result(
        self,
        client: TestClient,
        mock_macro_service: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_macro_service.list_indicators.return_value = pl.DataFrame()

        # Act
        response = client.get(
            "/api/v1/macro/indicators/metadata",
            params={
                "start": "2024-01-01",
                "end": "2024-12-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0
