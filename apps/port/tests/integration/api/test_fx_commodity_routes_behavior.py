"""Tests for FX and Commodity API routes behavior.

验证 FX/Commodity 路由的查询行为正确性，包括：
- asset_class 参数正确传递
- instrument_id 映射正确性
- 空数据处理
"""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.services.market_service import MarketService
from ditto_port.api.routes.commodity import router as commodity_router
from ditto_port.api.routes.fx import router as fx_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_market_service() -> MagicMock:
    """创建 mock MarketService."""
    return MagicMock(spec=MarketService)


@pytest.fixture
def fx_app(mock_market_service: MagicMock) -> FastAPI:
    """创建测试 FastAPI 应用（FX 路由）."""
    app = FastAPI()

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

    app.include_router(fx_router, prefix="/api/v1")

    return app


@pytest.fixture
def commodity_app(mock_market_service: MagicMock) -> FastAPI:
    """创建测试 FastAPI 应用（Commodity 路由）."""
    app = FastAPI()

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

    app.include_router(commodity_router, prefix="/api/v1")

    return app


@pytest.fixture
def fx_client(fx_app: FastAPI) -> TestClient:
    """创建 FX 测试客户端."""
    return TestClient(fx_app)


@pytest.fixture
def commodity_client(commodity_app: FastAPI) -> TestClient:
    """创建 Commodity 测试客户端."""
    return TestClient(commodity_app)


FX_QUERY = {
    "pairs": ["USDCNH.FXCM"],
    "start_date": "2024-01-15",
    "end_date": "2024-01-17",
}
COMMODITY_QUERY = {
    "symbols": ["COMMOD_WTI"],
    "start_date": "2024-01-15",
    "end_date": "2024-01-17",
}


@pytest.mark.integration
class TestFXRoutesBehavior:
    """FX 路由行为测试."""

    def test_empty_data_returns_empty_list(
        self,
        fx_client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """验证空数据返回空列表."""
        # Arrange
        mock_market_service.list_bars.return_value = pl.DataFrame()

        # Act
        response = fx_client.post("/api/v1/fx/bars", json=FX_QUERY)

        # Assert
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_asset_class_parameter_passed_correctly(
        self,
        fx_client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """验证 asset_class='fx' 参数正确传递给 MarketService."""
        # Arrange
        mock_market_service.list_bars.return_value = pl.DataFrame()

        # Act
        fx_client.post("/api/v1/fx/bars", json=FX_QUERY)

        # Assert
        mock_market_service.list_bars.assert_called_once()
        call_kwargs = mock_market_service.list_bars.call_args.kwargs
        assert call_kwargs.get("asset_class") == "fx", "应显式传入 asset_class='fx'"

    def test_instrument_id_mapping_for_usdcnh(
        self,
        fx_client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """验证 USDCNH.FXCM 映射到正确的 instrument_id."""
        # Arrange
        mock_market_service.list_bars.return_value = pl.DataFrame()

        # Act
        fx_client.post("/api/v1/fx/bars", json=FX_QUERY)

        # Assert
        call_kwargs = mock_market_service.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        assert 4_000_001 in instrument_ids, "USDCNH.FXCM 应映射到 4_000_001"

    def test_all_pairs_when_not_specified(
        self,
        fx_client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """验证不指定 pairs 时返回所有货币对."""
        # Arrange
        mock_market_service.list_bars.return_value = pl.DataFrame()

        # Act
        fx_client.post(
            "/api/v1/fx/bars",
            json={"start_date": "2024-01-15", "end_date": "2024-01-17"},
        )

        # Assert
        call_kwargs = mock_market_service.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        # 应包含所有 6 个货币对
        assert len(instrument_ids) == 6, "应请求所有 6 个货币对"


@pytest.mark.integration
class TestCommodityRoutesBehavior:
    """Commodity 路由行为测试."""

    def test_empty_data_returns_empty_list(
        self,
        commodity_client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """验证空数据返回空列表."""
        # Arrange
        mock_market_service.list_bars.return_value = pl.DataFrame()

        # Act
        response = commodity_client.post("/api/v1/commodity/bars", json=COMMODITY_QUERY)

        # Assert
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_asset_class_parameter_passed_correctly(
        self,
        commodity_client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """验证 asset_class='commodity' 参数正确传递给 MarketService."""
        # Arrange
        mock_market_service.list_bars.return_value = pl.DataFrame()

        # Act
        commodity_client.post("/api/v1/commodity/bars", json=COMMODITY_QUERY)

        # Assert
        mock_market_service.list_bars.assert_called_once()
        call_kwargs = mock_market_service.list_bars.call_args.kwargs
        assert call_kwargs.get("asset_class") == "commodity", (
            "应显式传入 asset_class='commodity'"
        )

    def test_instrument_id_mapping_for_wti(
        self,
        commodity_client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """验证 COMMOD_WTI 映射到正确的 instrument_id."""
        # Arrange
        mock_market_service.list_bars.return_value = pl.DataFrame()

        # Act
        commodity_client.post("/api/v1/commodity/bars", json=COMMODITY_QUERY)

        # Assert
        call_kwargs = mock_market_service.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        assert 5_000_001 in instrument_ids, "COMMOD_WTI 应映射到 5_000_001"

    def test_all_symbols_when_not_specified(
        self,
        commodity_client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """验证不指定 symbols 时返回所有商品."""
        # Arrange
        mock_market_service.list_bars.return_value = pl.DataFrame()

        # Act
        commodity_client.post(
            "/api/v1/commodity/bars",
            json={"start_date": "2024-01-15", "end_date": "2024-01-17"},
        )

        # Assert
        call_kwargs = mock_market_service.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        # 4 个商品 + 2 个 VIX = 6 个
        assert len(instrument_ids) == 6, (
            f"应请求所有 6 个商品/VIX 指标, 实际 {len(instrument_ids)}"
        )

    def test_vix_symbol_mapping(
        self,
        commodity_client: TestClient,
        mock_market_service: MagicMock,
    ) -> None:
        """验证 VIX 符号映射正确."""
        # Arrange
        mock_market_service.list_bars.return_value = pl.DataFrame()

        # Act
        commodity_client.post(
            "/api/v1/commodity/bars",
            json={
                "symbols": ["VIX_30D"],
                "start_date": "2024-01-15",
                "end_date": "2024-01-17",
            },
        )

        # Assert
        call_kwargs = mock_market_service.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        # VIX_30D 应映射到 5_100_001
        assert 5_100_001 in instrument_ids, "VIX_30D 应映射到 5_100_001"
