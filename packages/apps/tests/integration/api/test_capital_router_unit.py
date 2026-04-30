"""Tests for Capital API router.

使用 FastAPI TestClient 测试路由，mock CapitalService.
"""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_apps.api.routes.capital import router
from ditto_data.services.capital_service import CapitalService
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_capital_service() -> MagicMock:
    """创建 mock CapitalService."""
    return MagicMock(spec=CapitalService)


@pytest.fixture
def app(mock_capital_service: MagicMock) -> FastAPI:
    """创建测试 FastAPI 应用."""
    app = FastAPI()

    # 使用依赖注入覆盖
    from dishka import Provider, Scope, make_async_container, provide
    from dishka.integrations.fastapi import setup_dishka

    class TestProvider(Provider):
        """测试 Provider."""

        scope = Scope.APP

        @provide
        def get_capital_service(self) -> CapitalService:
            """返回 mock CapitalService."""
            return mock_capital_service

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)

    app.include_router(router, prefix="/api/v1")

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """创建测试客户端."""
    return TestClient(app)


@pytest.mark.integration
class TestGetMargin:
    """测试 GET /margin."""

    def test_get_margin_with_valid_params(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试有效参数查询融资融券数据."""
        # Arrange
        mock_capital_service.get_margin_trading.return_value = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "trade_date": ["2024-01-15"],
                "margin_buy_balance": [1000000.0],
                "short_sell_balance": [500000.0],
                "margin_buy_volume": [100000],
                "short_sell_volume": [50000],
            }
        )

        # Act
        response = client.get(
            "/api/v1/capital/margin",
            params={
                "instrument_id": "000001.SZ",
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["instrument_id"] == "000001.SZ"
        assert data["data"][0]["trade_date"] == "2024-01-15"
        assert data["data"][0]["margin_buy_balance"] == 1000000.0

        # 验证 service 被正确调用
        mock_capital_service.get_margin_trading.assert_called_once_with(
            "000001.SZ", date(2024, 1, 15)
        )

    def test_get_margin_empty_result(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_capital_service.get_margin_trading.return_value = pl.DataFrame()

        # Act
        response = client.get(
            "/api/v1/capital/margin",
            params={
                "instrument_id": "999999.SZ",
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_get_margin_missing_instrument_id(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试缺少 instrument_id 参数."""
        # Act
        response = client.get(
            "/api/v1/capital/margin",
            params={
                "as_of_date": "2024-01-15",
            },
        )

        # Assert - FastAPI 验证失败
        assert response.status_code == 422

    def test_get_margin_missing_as_of_date(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试缺少 as_of_date 参数."""
        # Act
        response = client.get(
            "/api/v1/capital/margin",
            params={
                "instrument_id": "000001.SZ",
            },
        )

        # Assert - FastAPI 验证失败
        assert response.status_code == 422

    def test_get_margin_invalid_date_format(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试无效的日期格式."""
        # Act
        response = client.get(
            "/api/v1/capital/margin",
            params={
                "instrument_id": "000001.SZ",
                "as_of_date": "2024/01/15",  # 错误格式
            },
        )

        # Assert - FastAPI 验证失败
        assert response.status_code == 422


@pytest.mark.integration
class TestGetValuation:
    """测试 GET /valuation."""

    def test_get_valuation_with_valid_params(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试有效参数查询估值指标数据."""
        # Arrange
        mock_capital_service.get_valuation_metrics.return_value = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "trade_date": ["2024-01-15"],
                "pe_ratio": [15.5],
                "pb_ratio": [2.3],
                "ps_ratio": [3.2],
                "dividend_yield": [0.025],
                "market_cap": [50000000000.0],
            }
        )

        # Act
        response = client.get(
            "/api/v1/capital/valuation",
            params={
                "instrument_id": "000001.SZ",
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["instrument_id"] == "000001.SZ"
        assert data["data"][0]["pe_ratio"] == 15.5
        assert data["data"][0]["pb_ratio"] == 2.3

        # 验证 service 被正确调用
        mock_capital_service.get_valuation_metrics.assert_called_once_with(
            "000001.SZ", date(2024, 1, 15)
        )

    def test_get_valuation_with_null_values(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试包含 NULL 值的结果."""
        # Arrange
        mock_capital_service.get_valuation_metrics.return_value = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "trade_date": ["2024-01-15"],
                "pe_ratio": [None],
                "pb_ratio": [2.3],
                "ps_ratio": [None],
                "dividend_yield": [None],
                "market_cap": [50000000000.0],
            }
        )

        # Act
        response = client.get(
            "/api/v1/capital/valuation",
            params={
                "instrument_id": "000001.SZ",
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"][0]["pe_ratio"] is None
        assert data["data"][0]["ps_ratio"] is None
        assert data["data"][0]["dividend_yield"] is None

    def test_get_valuation_empty_result(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_capital_service.get_valuation_metrics.return_value = pl.DataFrame()

        # Act
        response = client.get(
            "/api/v1/capital/valuation",
            params={
                "instrument_id": "999999.SZ",
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0


@pytest.mark.integration
class TestGetFutures:
    """测试 GET /futures."""

    def test_get_futures_with_valid_params(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试有效参数查询期货数据."""
        # Arrange
        mock_capital_service.get_futures.return_value = pl.DataFrame(
            {
                "instrument_id": ["IF2401"],
                "trade_date": ["2024-01-15"],
                "open_interest": [100000],
                "settlement_price": [3850.0],
                "volume": [50000],
                "turnover": [192500000.0],
            }
        )

        # Act
        response = client.get(
            "/api/v1/capital/futures",
            params={
                "instrument_id": "IF2401",
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["instrument_id"] == "IF2401"
        assert data["data"][0]["open_interest"] == 100000
        assert data["data"][0]["settlement_price"] == 3850.0

        # 验证 service 被正确调用
        mock_capital_service.get_futures.assert_called_once_with(
            "IF2401", date(2024, 1, 15)
        )

    def test_get_futures_with_null_values(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试包含 NULL 值的结果."""
        # Arrange
        mock_capital_service.get_futures.return_value = pl.DataFrame(
            {
                "instrument_id": ["IF2401"],
                "trade_date": ["2024-01-15"],
                "open_interest": [100000],
                "settlement_price": [None],
                "volume": [50000],
                "turnover": [None],
            }
        )

        # Act
        response = client.get(
            "/api/v1/capital/futures",
            params={
                "instrument_id": "IF2401",
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"][0]["settlement_price"] is None
        assert data["data"][0]["turnover"] is None

    def test_get_futures_empty_result(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_capital_service.get_futures.return_value = pl.DataFrame()

        # Act
        response = client.get(
            "/api/v1/capital/futures",
            params={
                "instrument_id": "INVALID",
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_get_futures_missing_params(
        self,
        client: TestClient,
        mock_capital_service: MagicMock,
    ) -> None:
        """测试缺少必要参数."""
        # Act
        response = client.get("/api/v1/capital/futures")

        # Assert - FastAPI 验证失败
        assert response.status_code == 422
