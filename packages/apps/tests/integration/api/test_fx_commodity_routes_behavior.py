"""Tests for FX and Commodity API routes behavior.

验证 FX/Commodity 路由的查询行为正确性，包括：
- code 参数正确传递
- instrument_id 映射正确性
- 空数据处理
"""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.queries.commodity import CommodityQueryFacade
from ditto_application.queries.fx import FXQueryFacade
from ditto_apps.api.routes.commodity import router as commodity_router
from ditto_apps.api.routes.fx import router as fx_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_fx_facade() -> MagicMock:
    """创建 mock FXQueryFacade."""
    mock = MagicMock(spec=FXQueryFacade)
    # FXQueryFacade 继承 InstrumentCodeQueryFacade，需要 mock 关键方法
    mock.get_valid_codes.return_value = {
        "USDCNH.FXCM",
        "EURUSD.FXCM",
        "GBPUSD.FXCM",
        "USDJPY.FXCM",
        "AUDUSD.FXCM",
        "USDCAD.FXCM",
    }
    mock.get_all_instrument_ids.return_value = [
        4_000_001,
        4_000_002,
        4_000_003,
        4_000_004,
        4_000_005,
        4_000_006,
    ]
    mock.code_to_instrument_id.side_effect = {
        "USDCNH.FXCM": 4_000_001,
        "EURUSD.FXCM": 4_000_002,
        "GBPUSD.FXCM": 4_000_003,
        "USDJPY.FXCM": 4_000_004,
        "AUDUSD.FXCM": 4_000_005,
        "USDCAD.FXCM": 4_000_006,
    }.get
    mock.instrument_id_to_code.return_value = "USDCNH.FXCM"
    mock.list_bars.return_value = pl.DataFrame()
    return mock


@pytest.fixture
def mock_commodity_facade() -> MagicMock:
    """创建 mock CommodityQueryFacade."""
    mock = MagicMock(spec=CommodityQueryFacade)
    # CommodityQueryFacade 合并了 commodity + VIX 映射
    mock.get_valid_codes.return_value = {
        "COMMOD_WTI",
        "COMMOD_BRENT",
        "COMMOD_GOLD",
        "COMMOD_SILVER",
        "VIX_30D",
        "VIX_9D",
    }
    mock.get_all_instrument_ids.return_value = [
        5_000_001,
        5_000_002,
        5_000_003,
        5_000_004,
        5_100_001,
        5_100_002,
    ]
    mock.code_to_instrument_id.side_effect = {
        "COMMOD_WTI": 5_000_001,
        "COMMOD_BRENT": 5_000_002,
        "COMMOD_GOLD": 5_000_003,
        "COMMOD_SILVER": 5_000_004,
        "VIX_30D": 5_100_001,
        "VIX_9D": 5_100_002,
    }.get
    mock.instrument_id_to_code.return_value = "COMMOD_WTI"
    mock.list_bars.return_value = pl.DataFrame()
    return mock


@pytest.fixture
def fx_app(mock_fx_facade: MagicMock) -> FastAPI:
    """创建测试 FastAPI 应用（FX 路由）."""
    app = FastAPI()

    from dishka import Provider, Scope, make_async_container, provide
    from dishka.integrations.fastapi import setup_dishka

    class TestProvider(Provider):
        """测试 Provider."""

        scope = Scope.REQUEST

        @provide
        def get_fx_facade(self) -> FXQueryFacade:
            """返回 mock FXQueryFacade."""
            return mock_fx_facade

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)

    app.include_router(fx_router, prefix="/api/v1")

    return app


@pytest.fixture
def commodity_app(mock_commodity_facade: MagicMock) -> FastAPI:
    """创建测试 FastAPI 应用（Commodity 路由）."""
    app = FastAPI()

    from dishka import Provider, Scope, make_async_container, provide
    from dishka.integrations.fastapi import setup_dishka

    class TestProvider(Provider):
        """测试 Provider."""

        scope = Scope.REQUEST

        @provide
        def get_commodity_facade(self) -> CommodityQueryFacade:
            """返回 mock CommodityQueryFacade."""
            return mock_commodity_facade

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
    "currency_pairs": ["USDCNH.FXCM"],
    "start_date": "2024-01-15",
    "end_date": "2024-01-17",
}
COMMODITY_QUERY = {
    "commodity_codes": ["COMMOD_WTI"],
    "start_date": "2024-01-15",
    "end_date": "2024-01-17",
}


@pytest.mark.integration
class TestFXRoutesBehavior:
    """FX 路由行为测试."""

    def test_empty_data_returns_empty_list(
        self,
        fx_client: TestClient,
        mock_fx_facade: MagicMock,
    ) -> None:
        """验证空数据返回空列表."""
        # Arrange
        mock_fx_facade.list_bars.return_value = pl.DataFrame()

        # Act
        response = fx_client.post("/api/v1/fx/bars", json=FX_QUERY)

        # Assert
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_instrument_id_mapping_for_usdcnh(
        self,
        fx_client: TestClient,
        mock_fx_facade: MagicMock,
    ) -> None:
        """验证 USDCNH.FXCM 映射到正确的 instrument_id 并传入 list_bars."""
        # Arrange
        mock_fx_facade.list_bars.return_value = pl.DataFrame()

        # Act
        fx_client.post("/api/v1/fx/bars", json=FX_QUERY)

        # Assert
        mock_fx_facade.list_bars.assert_called_once()
        call_kwargs = mock_fx_facade.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        assert 4_000_001 in instrument_ids, "USDCNH.FXCM 应映射到 4_000_001"

    def test_code_to_instrument_id_called_for_pair(
        self,
        fx_client: TestClient,
        mock_fx_facade: MagicMock,
    ) -> None:
        """验证 facade 的 code_to_instrument_id 被正确调用."""
        # Arrange
        mock_fx_facade.list_bars.return_value = pl.DataFrame()

        # Act
        fx_client.post("/api/v1/fx/bars", json=FX_QUERY)

        # Assert
        mock_fx_facade.code_to_instrument_id.assert_called_once_with("USDCNH.FXCM")

    def test_all_pairs_when_not_specified(
        self,
        fx_client: TestClient,
        mock_fx_facade: MagicMock,
    ) -> None:
        """验证不指定 currency_pairs 时调用 get_all_instrument_ids."""
        # Arrange
        mock_fx_facade.list_bars.return_value = pl.DataFrame()

        # Act
        fx_client.post(
            "/api/v1/fx/bars",
            json={"start_date": "2024-01-15", "end_date": "2024-01-17"},
        )

        # Assert
        mock_fx_facade.get_all_instrument_ids.assert_called_once()
        mock_fx_facade.list_bars.assert_called_once()
        call_kwargs = mock_fx_facade.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        # 应包含所有 6 个货币对
        assert len(instrument_ids) == 6, "应请求所有 6 个货币对"


@pytest.mark.integration
class TestCommodityRoutesBehavior:
    """Commodity 路由行为测试."""

    def test_empty_data_returns_empty_list(
        self,
        commodity_client: TestClient,
        mock_commodity_facade: MagicMock,
    ) -> None:
        """验证空数据返回空列表."""
        # Arrange
        mock_commodity_facade.list_bars.return_value = pl.DataFrame()

        # Act
        response = commodity_client.post("/api/v1/commodity/bars", json=COMMODITY_QUERY)

        # Assert
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_instrument_id_mapping_for_wti(
        self,
        commodity_client: TestClient,
        mock_commodity_facade: MagicMock,
    ) -> None:
        """验证 COMMOD_WTI 映射到正确的 instrument_id 并传入 list_bars."""
        # Arrange
        mock_commodity_facade.list_bars.return_value = pl.DataFrame()

        # Act
        commodity_client.post("/api/v1/commodity/bars", json=COMMODITY_QUERY)

        # Assert
        mock_commodity_facade.list_bars.assert_called_once()
        call_kwargs = mock_commodity_facade.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        assert 5_000_001 in instrument_ids, "COMMOD_WTI 应映射到 5_000_001"

    def test_code_to_instrument_id_called_for_code(
        self,
        commodity_client: TestClient,
        mock_commodity_facade: MagicMock,
    ) -> None:
        """验证 facade 的 code_to_instrument_id 被正确调用."""
        # Arrange
        mock_commodity_facade.list_bars.return_value = pl.DataFrame()

        # Act
        commodity_client.post("/api/v1/commodity/bars", json=COMMODITY_QUERY)

        # Assert
        mock_commodity_facade.code_to_instrument_id.assert_called_once_with(
            "COMMOD_WTI"
        )

    def test_all_symbols_when_not_specified(
        self,
        commodity_client: TestClient,
        mock_commodity_facade: MagicMock,
    ) -> None:
        """验证不指定 commodity_codes 时调用 get_all_instrument_ids."""
        # Arrange
        mock_commodity_facade.list_bars.return_value = pl.DataFrame()

        # Act
        commodity_client.post(
            "/api/v1/commodity/bars",
            json={"start_date": "2024-01-15", "end_date": "2024-01-17"},
        )

        # Assert
        mock_commodity_facade.get_all_instrument_ids.assert_called_once()
        mock_commodity_facade.list_bars.assert_called_once()
        call_kwargs = mock_commodity_facade.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        # 4 个商品 + 2 个 VIX = 6 个
        assert len(instrument_ids) == 6, (
            f"应请求所有 6 个商品/VIX 指标, 实际 {len(instrument_ids)}"
        )

    def test_vix_symbol_mapping(
        self,
        commodity_client: TestClient,
        mock_commodity_facade: MagicMock,
    ) -> None:
        """验证 VIX 符号映射正确."""
        # Arrange
        mock_commodity_facade.list_bars.return_value = pl.DataFrame()

        # Act
        commodity_client.post(
            "/api/v1/commodity/bars",
            json={
                "commodity_codes": ["VIX_30D"],
                "start_date": "2024-01-15",
                "end_date": "2024-01-17",
            },
        )

        # Assert
        mock_commodity_facade.list_bars.assert_called_once()
        call_kwargs = mock_commodity_facade.list_bars.call_args.kwargs
        instrument_ids = call_kwargs.get("instrument_ids", [])
        # VIX_30D 应映射到 5_100_001
        assert 5_100_001 in instrument_ids, "VIX_30D 应映射到 5_100_001"
