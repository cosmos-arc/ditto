"""Tests for Fundamental API router.

使用 FastAPI TestClient 测试路由，mock FundamentalService 和 MetadataService.
"""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_interfaces.api.routes.fundamental import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_fundamental_service() -> MagicMock:
    """创建 mock FundamentalService."""
    return MagicMock(spec=FundamentalService)


@pytest.fixture
def mock_metadata_service() -> MagicMock:
    """创建 mock MetadataService."""
    mock = MagicMock(spec=MetadataService)
    mock.resolve_instrument_identifier.return_value = 1_000_001
    return mock


@pytest.fixture
def app(
    mock_fundamental_service: MagicMock,
    mock_metadata_service: MagicMock,
) -> FastAPI:
    """创建测试 FastAPI 应用."""
    app = FastAPI()

    # 使用依赖注入覆盖
    from dishka import Provider, Scope, make_async_container, provide
    from dishka.integrations.fastapi import setup_dishka

    class TestProvider(Provider):
        """测试 Provider."""

        scope = Scope.APP

        @provide
        def get_fundamental_service(self) -> FundamentalService:
            """返回 mock FundamentalService."""
            return mock_fundamental_service

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
class TestGetFinancials:
    """测试 GET /financials/{type}."""

    def test_get_balance_sheet_with_valid_params(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试有效参数查询资产负债表."""
        # Arrange
        mock_fundamental_service.get_balance_sheet.return_value = pl.DataFrame(
            {
                "instrument_id": [1_000_001],
                "report_date": ["2024-03-31"],
                "data": [{"total_assets": 1000000.0}],
            }
        )

        # Act
        response = client.get(
            "/api/v1/fundamental/financials/balance_sheet",
            params={
                "instrument_id": 1000001,
                "as_of_date": "2024-03-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["instrument_id"] == 1000001

    def test_get_income_statement(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试查询利润表."""
        # Arrange
        mock_fundamental_service.get_income_statement.return_value = pl.DataFrame(
            {
                "instrument_id": [1_000_001],
                "report_date": ["2024-03-31"],
                "data": [{"revenue": 500000.0}],
            }
        )

        # Act
        response = client.get(
            "/api/v1/fundamental/financials/income_statement",
            params={
                "instrument_id": 1000001,
                "as_of_date": "2024-03-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        mock_fundamental_service.get_income_statement.assert_called_once()

    def test_get_cash_flow(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试查询现金流量表."""
        # Arrange
        mock_fundamental_service.get_cash_flow.return_value = pl.DataFrame(
            {
                "instrument_id": [1_000_001],
                "report_date": ["2024-03-31"],
                "data": [{"operating_cash_flow": 300000.0}],
            }
        )

        # Act
        response = client.get(
            "/api/v1/fundamental/financials/cash_flow",
            params={
                "instrument_id": 1000001,
                "as_of_date": "2024-03-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        mock_fundamental_service.get_cash_flow.assert_called_once()

    def test_get_financials_empty_result(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_fundamental_service.get_balance_sheet.return_value = None

        # Act
        response = client.get(
            "/api/v1/fundamental/financials/balance_sheet",
            params={
                "instrument_id": 99999,
                "as_of_date": "2024-03-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_get_financials_invalid_type(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试无效的财务报表类型."""
        # Act
        response = client.get(
            "/api/v1/fundamental/financials/invalid_type",
            params={
                "instrument_id": 1000001,
                "as_of_date": "2024-03-31",
            },
        )

        # Assert - 路径参数验证失败
        assert response.status_code == 422


@pytest.mark.integration
class TestGetDividend:
    """测试 GET /dividend."""

    def test_get_dividend_with_valid_params(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试有效参数查询分红."""
        # Arrange
        mock_fundamental_service.get_dividend.return_value = pl.DataFrame(
            {
                "instrument_id": [1_000_001],
                "announce_date": ["2024-03-31"],
                "dividend_type": ["cash"],
                "amount": [0.5],
            }
        )

        # Act
        response = client.get(
            "/api/v1/fundamental/dividend",
            params={
                "instrument_id": 1000001,
                "as_of_date": "2024-03-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["instrument_id"] == 1000001
        assert data["data"][0]["amount"] == 0.5

    def test_get_dividend_empty_result(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试空分红结果."""
        # Arrange
        mock_fundamental_service.get_dividend.return_value = None

        # Act
        response = client.get(
            "/api/v1/fundamental/dividend",
            params={
                "instrument_id": 99999,
                "as_of_date": "2024-03-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_get_dividend_missing_params(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试缺少必须参数."""
        # Act
        response = client.get("/api/v1/fundamental/dividend")

        # Assert - 参数验证失败
        assert response.status_code == 422


@pytest.mark.integration
class TestListCorporateActions:
    """测试 GET /corporate-actions."""

    def test_list_corporate_actions_with_valid_params(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试有效参数查询公司行动."""
        # Arrange
        mock_fundamental_service.list_corporate_actions.return_value = pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_001],
                "action_date": ["2024-01-15", "2024-03-31"],
                "action_type": ["dividend", "split"],
                "description": ["现金分红", "1:2 股票拆分"],
            }
        )

        # Act
        response = client.get(
            "/api/v1/fundamental/corporate-actions",
            params={
                "instrument_id": 1000001,
                "start_date": "2024-01-01",
                "end_date": "2024-03-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 2
        assert data["data"][0]["action_type"] == "dividend"
        assert data["data"][1]["action_type"] == "split"

    def test_list_corporate_actions_empty_result(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试空结果."""
        # Arrange
        mock_fundamental_service.list_corporate_actions.return_value = pl.DataFrame()

        # Act
        response = client.get(
            "/api/v1/fundamental/corporate-actions",
            params={
                "instrument_id": 99999,
                "start_date": "2024-01-01",
                "end_date": "2024-03-31",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0

    def test_list_corporate_actions_invalid_date_range(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试无效日期范围 (start_date > end_date)."""
        # Act
        response = client.get(
            "/api/v1/fundamental/corporate-actions",
            params={
                "instrument_id": 1000001,
                "start_date": "2024-03-31",
                "end_date": "2024-01-01",
            },
        )

        # Assert - 路由内的日期验证
        assert response.status_code == 400

    def test_list_corporate_actions_missing_params(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试缺少必须参数."""
        # Act
        response = client.get("/api/v1/fundamental/corporate-actions")

        # Assert - 参数验证失败
        assert response.status_code == 422

    def test_list_corporate_actions_same_dates(
        self,
        client: TestClient,
        mock_fundamental_service: MagicMock,
    ) -> None:
        """测试相同日期范围 (start_date == end_date)."""
        # Arrange
        mock_fundamental_service.list_corporate_actions.return_value = pl.DataFrame()

        # Act
        response = client.get(
            "/api/v1/fundamental/corporate-actions",
            params={
                "instrument_id": 1000001,
                "start_date": "2024-03-31",
                "end_date": "2024-03-31",
            },
        )

        # Assert
        assert response.status_code == 200
