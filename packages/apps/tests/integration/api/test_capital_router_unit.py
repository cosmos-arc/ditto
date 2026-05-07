"""Tests for Capital API router.

使用 FastAPI TestClient 测试路由，mock CapitalQueryFacade 和 MetadataQueryFacade.
"""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.capital import router
from ditto_apps.middleware import api_error_handler
from fastapi import FastAPI
from fastapi.testclient import TestClient

RESOLVED_INSTRUMENT_ID = 1_000_001


@pytest.fixture
def mock_capital_facade() -> MagicMock:
    """创建 mock CapitalQueryFacade."""
    return MagicMock(spec=CapitalQueryFacade)


@pytest.fixture
def mock_metadata_facade() -> MagicMock:
    """创建 mock MetadataQueryFacade."""
    mock = MagicMock(spec=MetadataQueryFacade)
    mock.resolve_instrument_identifier.return_value = RESOLVED_INSTRUMENT_ID
    return mock


@pytest.fixture
def app(
    mock_capital_facade: MagicMock,
    mock_metadata_facade: MagicMock,
) -> FastAPI:
    """创建测试 FastAPI 应用."""
    app = FastAPI()

    # 注册 APIError 异常处理器（与 main.py 一致）
    app.add_exception_handler(APIError, api_error_handler)

    # 使用依赖注入覆盖
    from dishka import Provider, Scope, make_async_container, provide
    from dishka.integrations.fastapi import setup_dishka

    class TestProvider(Provider):
        """测试 Provider."""

        scope = Scope.REQUEST

        @provide
        def get_capital_facade(self) -> CapitalQueryFacade:
            """返回 mock CapitalQueryFacade."""
            return mock_capital_facade

        @provide
        def get_metadata_facade(self) -> MetadataQueryFacade:
            """返回 mock MetadataQueryFacade."""
            return mock_metadata_facade

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
        mock_capital_facade: MagicMock,
    ) -> None:
        """测试有效参数查询融资融券数据."""
        # Arrange
        mock_capital_facade.get_margin_trading.return_value = pl.DataFrame(
            {
                "instrument_id": [RESOLVED_INSTRUMENT_ID],
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
                "instrument_id": RESOLVED_INSTRUMENT_ID,
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["instrument_id"] == RESOLVED_INSTRUMENT_ID
        assert data["data"][0]["trade_date"] == "2024-01-15"
        assert data["data"][0]["margin_buy_balance"] == 1000000.0

        # 验证 facade 被正确调用
        mock_capital_facade.get_margin_trading.assert_called_once_with(
            RESOLVED_INSTRUMENT_ID, date(2024, 1, 15)
        )

    def test_get_margin_with_ticker(
        self,
        client: TestClient,
        mock_capital_facade: MagicMock,
    ) -> None:
        """测试使用 ticker 参数查询融资融券数据."""
        # Arrange
        mock_capital_facade.get_margin_trading.return_value = pl.DataFrame(
            {
                "instrument_id": [RESOLVED_INSTRUMENT_ID],
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
                "ticker": "000001",
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1

    def test_get_margin_empty_result(
        self,
        client: TestClient,
        mock_capital_facade: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_capital_facade.get_margin_trading.return_value = pl.DataFrame()

        # Act
        response = client.get(
            "/api/v1/capital/margin",
            params={
                "instrument_id": RESOLVED_INSTRUMENT_ID,
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_get_margin_missing_all_identifiers(
        self,
        client: TestClient,
    ) -> None:
        """测试缺少所有标识符参数（instrument_id/ticker/standard_ticker 都未提供）."""
        # Act
        response = client.get(
            "/api/v1/capital/margin",
            params={
                "as_of_date": "2024-01-15",
            },
        )

        # Assert - resolve_identifier_for_api 抛出 BadRequestError (400)
        assert response.status_code == 400

    def test_get_margin_missing_as_of_date(
        self,
        client: TestClient,
    ) -> None:
        """测试缺少 as_of_date 参数."""
        # Act
        response = client.get(
            "/api/v1/capital/margin",
            params={
                "instrument_id": RESOLVED_INSTRUMENT_ID,
            },
        )

        # Assert - FastAPI 验证失败
        assert response.status_code == 422

    def test_get_margin_invalid_date_format(
        self,
        client: TestClient,
    ) -> None:
        """测试无效的日期格式."""
        # Act
        response = client.get(
            "/api/v1/capital/margin",
            params={
                "instrument_id": RESOLVED_INSTRUMENT_ID,
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
        mock_capital_facade: MagicMock,
    ) -> None:
        """测试有效参数查询估值指标数据."""
        # Arrange
        mock_capital_facade.get_valuation_metrics.return_value = pl.DataFrame(
            {
                "instrument_id": [RESOLVED_INSTRUMENT_ID],
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
                "instrument_id": RESOLVED_INSTRUMENT_ID,
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["instrument_id"] == RESOLVED_INSTRUMENT_ID
        assert data["data"][0]["pe_ratio"] == 15.5
        assert data["data"][0]["pb_ratio"] == 2.3

        # 验证 facade 被正确调用
        mock_capital_facade.get_valuation_metrics.assert_called_once_with(
            RESOLVED_INSTRUMENT_ID, date(2024, 1, 15)
        )

    def test_get_valuation_with_null_values(
        self,
        client: TestClient,
        mock_capital_facade: MagicMock,
    ) -> None:
        """测试包含 NULL 值的结果."""
        # Arrange
        mock_capital_facade.get_valuation_metrics.return_value = pl.DataFrame(
            {
                "instrument_id": [RESOLVED_INSTRUMENT_ID],
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
                "instrument_id": RESOLVED_INSTRUMENT_ID,
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
        mock_capital_facade: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_capital_facade.get_valuation_metrics.return_value = pl.DataFrame()

        # Act
        response = client.get(
            "/api/v1/capital/valuation",
            params={
                "instrument_id": RESOLVED_INSTRUMENT_ID,
                "as_of_date": "2024-01-15",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_get_valuation_missing_all_identifiers(
        self,
        client: TestClient,
    ) -> None:
        """测试缺少所有标识符参数."""
        # Act
        response = client.get(
            "/api/v1/capital/valuation",
            params={
                "as_of_date": "2024-01-15",
            },
        )

        # Assert - resolve_identifier_for_api 抛出 BadRequestError (400)
        assert response.status_code == 400

    def test_get_valuation_missing_as_of_date(
        self,
        client: TestClient,
    ) -> None:
        """测试缺少 as_of_date 参数."""
        # Act
        response = client.get(
            "/api/v1/capital/valuation",
            params={
                "instrument_id": RESOLVED_INSTRUMENT_ID,
            },
        )

        # Assert - FastAPI 验证失败
        assert response.status_code == 422
