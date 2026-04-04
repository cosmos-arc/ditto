"""Tests for Metadata API router.

使用 FastAPI TestClient 测试路由，mock MetadataService.
"""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.services.metadata_service import MetadataService
from ditto_interfaces.api.routes.metadata import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_metadata_service() -> MagicMock:
    """创建 mock MetadataService."""
    return MagicMock(spec=MetadataService)


@pytest.fixture
def app(mock_metadata_service: MagicMock) -> FastAPI:
    """创建测试 FastAPI 应用."""
    app = FastAPI()

    # 使用依赖注入覆盖
    from dishka import Provider, Scope, make_async_container, provide
    from dishka.integrations.fastapi import setup_dishka

    class TestProvider(Provider):
        """测试 Provider."""

        scope = Scope.APP

        @provide
        def get_metadata_service(self) -> MetadataService:
            """返回 mock MetadataService."""
            return mock_metadata_service

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)

    app.include_router(router, prefix="/api/v1")

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """创建测试客户端."""
    return TestClient(app)


@pytest.mark.integration
class TestGetInstrumentById:
    """测试 GET /instruments/{instrument_id}."""

    def test_get_instrument_found(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试获取存在的标的."""
        # Arrange
        mock_metadata_service.get_instrument.return_value = {
            "instrument_id": 1,
            "ticker": "600000",
            "name": "浦发银行",
            "asset_class": "stock",
            "exchange": "SSE",
            "list_date": "1999-11-10",
            "is_active": 1,
        }

        # Act
        response = client.get("/api/v1/metadata/instruments/1")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["instrument_id"] == 1
        assert data["ticker"] == "600000"
        assert data["name"] == "浦发银行"
        assert data["asset_class"] == "stock"
        assert data["exchange"] == "SSE"
        assert data["list_date"] == "1999-11-10"
        assert data["is_active"] is True

    def test_get_instrument_not_found(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试获取不存在的标的."""
        # Arrange
        mock_metadata_service.get_instrument.return_value = None

        # Act
        response = client.get("/api/v1/metadata/instruments/99999")

        # Assert
        assert response.status_code == 404

    def test_get_instrument_with_invalid_id(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试无效的 instrument_id 格式."""
        # Act
        response = client.get("/api/v1/metadata/instruments/invalid")

        # Assert - FastAPI 自动验证路径参数
        assert response.status_code == 422


@pytest.mark.integration
class TestListInstruments:
    """测试 GET /instruments."""

    def test_list_instruments_default_params(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试默认参数查询."""
        # Arrange
        mock_metadata_service.find_securities.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "ticker": ["600000", "000001"],
                "name": ["浦发银行", "平安银行"],
                "asset_class": ["stock", "stock"],
                "exchange": ["SSE", "SZSE"],
                "list_date": ["1999-11-10", "1991-04-03"],
                "is_active": [1, 1],
            }
        )

        # Act
        response = client.get("/api/v1/metadata/instruments")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 2
        assert data["data"][0]["ticker"] == "600000"
        assert data["data"][1]["ticker"] == "000001"

    def test_list_instruments_with_asset_class_filter(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试按资产类别过滤."""
        # Arrange
        mock_metadata_service.find_securities.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "ticker": ["600000"],
                "name": ["浦发银行"],
                "asset_class": ["stock"],
                "exchange": ["SSE"],
                "list_date": ["1999-11-10"],
                "is_active": [1],
            }
        )

        # Act
        response = client.get("/api/v1/metadata/instruments?asset_class=stock")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["asset_class"] == "stock"

        # 验证 service 被正确调用
        mock_metadata_service.find_securities.assert_called_once()
        call_kwargs = mock_metadata_service.find_securities.call_args.kwargs
        assert call_kwargs["asset_class"] == "stock"

    def test_list_instruments_with_exchange_filter(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试按交易所过滤."""
        # Arrange
        mock_metadata_service.find_securities.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "ticker": ["600000"],
                "name": ["浦发银行"],
                "asset_class": ["stock"],
                "exchange": ["SSE"],
                "list_date": ["1999-11-10"],
                "is_active": [1],
            }
        )

        # Act
        response = client.get("/api/v1/metadata/instruments?exchange=SSE")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1

        # 验证 service 被正确调用
        call_kwargs = mock_metadata_service.find_securities.call_args.kwargs
        assert call_kwargs["exchange"] == "SSE"

    def test_list_instruments_with_is_active_filter(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试按活跃状态过滤."""
        # Arrange
        mock_metadata_service.find_securities.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "ticker": ["600000"],
                "name": ["浦发银行"],
                "asset_class": ["stock"],
                "exchange": ["SSE"],
                "list_date": ["1999-11-10"],
                "is_active": [1],
            }
        )

        # Act
        response = client.get("/api/v1/metadata/instruments?is_active=true")

        # Assert
        assert response.status_code == 200

        # 验证 service 被正确调用
        call_kwargs = mock_metadata_service.find_securities.call_args.kwargs
        assert call_kwargs["is_active"] is True

    def test_list_instruments_with_limit(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试限制返回数量."""
        # Arrange
        mock_metadata_service.find_securities.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "ticker": ["600000"],
                "name": ["浦发银行"],
                "asset_class": ["stock"],
                "exchange": ["SSE"],
                "list_date": ["1999-11-10"],
                "is_active": [1],
            }
        )

        # Act
        response = client.get("/api/v1/metadata/instruments?limit=10")

        # Assert
        assert response.status_code == 200

    def test_list_instruments_empty_result(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_metadata_service.find_securities.return_value = pl.DataFrame()

        # Act
        response = client.get("/api/v1/metadata/instruments")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_list_instruments_with_invalid_asset_class(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试无效的资产类别."""
        # Act
        response = client.get("/api/v1/metadata/instruments?asset_class=invalid")

        # Assert - FastAPI 验证枚举值
        assert response.status_code == 422

    def test_list_instruments_with_invalid_limit(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试无效的 limit 值."""
        # Act
        response = client.get("/api/v1/metadata/instruments?limit=0")

        # Assert - FastAPI 验证 limit 范围
        assert response.status_code == 422

    def test_list_instruments_with_limit_too_large(
        self,
        client: TestClient,
        mock_metadata_service: MagicMock,
    ) -> None:
        """测试 limit 超过最大值."""
        # Act
        response = client.get("/api/v1/metadata/instruments?limit=1001")

        # Assert - FastAPI 验证 limit 范围
        assert response.status_code == 422
