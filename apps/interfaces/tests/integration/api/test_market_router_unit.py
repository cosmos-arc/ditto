"""Tests for Market API router.

使用 FastAPI TestClient 测试路由，mock MarketService.
"""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.services.market_service import MarketService
from ditto_interfaces.api.routes.market import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_market_service() -> MagicMock:
    """创建 mock MarketService."""
    return MagicMock(spec=MarketService)


@pytest.fixture
def app(mock_market_service: MagicMock) -> FastAPI:
    """创建测试 FastAPI 应用."""
    app = FastAPI()

    # 使用依赖注入覆盖
    from dishka import Provider, Scope, make_async_container, provide
    from dishka.integrations.fastapi import setup_dishka

    class TestProvider(Provider):
        """测试 Provider."""

        scope = Scope.APP

        @provide
        def get_market_service(self) -> MarketService:
            """返回 mock MarketService."""
            return mock_market_service

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)

    app.include_router(router, prefix="/api/v1")

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """创建测试客户端."""
    return TestClient(app)


@pytest.mark.integration
class TestPostBars:
    """测试 POST /bars."""

    def test_post_bars_with_valid_params(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试有效参数查询 K 线."""
        # Arrange
        mock_market_service.find_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": ["2024-01-15", "2024-01-16"],
                "open": [10.0, 10.5],
                "high": [11.0, 11.5],
                "low": [9.5, 10.0],
                "close": [10.5, 11.0],
                "volume": [1000000, 1100000],
                "amount": [10500000.0, 11550000.0],
            }
        )

        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1],
                "start_date": "2024-01-15",
                "end_date": "2024-01-16",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 2
        assert data["data"][0]["instrument_id"] == 1
        assert data["data"][0]["trade_date"] == "2024-01-15"

    def test_post_bars_with_qfq_adjustment(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试前复权查询."""
        # Arrange
        mock_market_service.find_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-15"],
                "open": [9.5],  # 前复权后的价格
                "high": [10.5],
                "low": [9.0],
                "close": [10.0],
                "volume": [1000000],
                "amount": [10000000.0],
            }
        )

        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1],
                "adjustment": "qfq",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1

        # 验证 service 被正确调用
        mock_market_service.find_bars.assert_called_once()
        call_args = mock_market_service.find_bars.call_args
        query = call_args[0][0]
        assert query.adj.value == "qfq"

    def test_post_bars_with_limit(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试限制返回数量."""
        # Arrange
        mock_market_service.find_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "trade_date": ["2024-01-15", "2024-01-15", "2024-01-15"],
                "open": [10.0, 20.0, 30.0],
                "high": [11.0, 21.0, 31.0],
                "low": [9.5, 19.5, 29.5],
                "close": [10.5, 20.5, 30.5],
                "volume": [1000000, 2000000, 3000000],
                "amount": [10500000.0, 41000000.0, 91500000.0],
            }
        )

        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1, 2, 3],
                "limit": 2,
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        # limit 应用于响应数据
        assert len(data["data"]) == 2

    def test_post_bars_empty_result(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_market_service.find_bars.return_value = pl.DataFrame()

        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [99999],
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_post_bars_with_invalid_date_range(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试无效日期范围 (start_date > end_date)."""
        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1],
                "start_date": "2024-01-31",
                "end_date": "2024-01-01",
            },
        )

        # Assert - Pydantic 验证失败
        assert response.status_code == 422

    def test_post_bars_with_invalid_adjustment(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试无效的复权类型."""
        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1],
                "adjustment": "invalid",
            },
        )

        # Assert - Pydantic 验证失败
        assert response.status_code == 422

    def test_post_bars_with_invalid_limit(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试无效的 limit 值."""
        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1],
                "limit": 0,
            },
        )

        # Assert - Pydantic 验证失败
        assert response.status_code == 422

    def test_post_bars_with_limit_too_large(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试 limit 超过最大值."""
        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1],
                "limit": 10001,
            },
        )

        # Assert - Pydantic 验证失败
        assert response.status_code == 422

    def test_post_bars_without_instrument_ids(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试不提供 instrument_ids (允许为空)."""
        # Arrange
        mock_market_service.find_bars.return_value = pl.DataFrame()

        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_post_bars_with_turnover_rate(
        self,
        client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """测试返回换手率."""
        # Arrange
        mock_market_service.find_bars.return_value = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-15"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.5],
                "close": [10.5],
                "volume": [1000000],
                "amount": [10500000.0],
                "turnover_rate": [0.025],
            }
        )

        # Act
        response = client.post(
            "/api/v1/market/bars",
            json={
                "instrument_ids": [1],
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"][0]["turnover_rate"] == 0.025
