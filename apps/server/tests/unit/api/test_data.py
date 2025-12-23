"""数据API测试."""

from unittest.mock import Mock, patch

import pytest
from ditto_server.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """测试客户端."""
    return TestClient(app)


@pytest.fixture
def mock_data_reader() -> Mock:
    """模拟数据读取器."""
    mock = Mock()

    # 模拟ETF列表数据
    mock_etf_list = [
        {
            "symbol": "510300",
            "name": "沪深300ETF",
            "market": "上海",
            "category": "指数型",
        },
        {
            "symbol": "159915",
            "name": "创业板ETF",
            "market": "深圳",
            "category": "指数型",
        },
    ]
    mock_df = Mock()
    mock_df.to_dicts.return_value = mock_etf_list
    mock_df.__len__ = Mock(return_value=len(mock_etf_list))
    mock.get_etf_list.return_value = mock_df

    # 模拟日线数据
    mock_daily = [
        {
            "date": "2024-01-01",
            "open": 3.5,
            "high": 3.6,
            "low": 3.4,
            "close": 3.55,
            "volume": 1000000,
        },
        {
            "date": "2024-01-02",
            "open": 3.55,
            "high": 3.65,
            "low": 3.45,
            "close": 3.6,
            "volume": 1100000,
        },
    ]
    mock.get_daily_data.return_value = Mock(
        is_empty=Mock(return_value=False),
        to_dicts=Mock(return_value=mock_daily),
    )

    # 模拟复权因子数据
    mock.get_adjustment_factors.return_value = Mock(
        is_empty=Mock(return_value=False),
        to_dicts=Mock(
            return_value=[
                {
                    "symbol": "510300",
                    "ex_date": "2024-01-01",
                    "adj_factor": 1.0,
                }
            ]
        ),
    )

    # 模拟交易日历数据
    mock.get_trading_calendar.return_value = Mock(
        is_empty=Mock(return_value=False),
        to_dicts=Mock(
            return_value=[
                {"date": "2024-01-01", "is_trading_day": True},
                {"date": "2024-01-02", "is_trading_day": True},
            ]
        ),
    )

    return mock


class TestETFListAPI:
    """ETF列表API测试."""

    @patch("ditto_server.api.data.get_data_readers")
    def test_get_etf_list_success(
        self, mock_readers: Mock, client: TestClient, mock_data_reader: Mock
    ) -> None:
        """测试成功获取ETF列表."""
        mock_readers.return_value = (mock_data_reader, None)

        response = client.get("/api/v1/data/etf/list")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert len(data["data"]) == 2
        assert data["data"][0]["symbol"] == "510300"

    @patch("ditto_server.api.data.get_data_readers")
    def test_get_etf_list_error(self, mock_reader: Mock, client: TestClient) -> None:
        """测试获取ETF列表失败."""
        mock_reader.side_effect = Exception("Database connection failed")

        response = client.get("/api/v1/data/etf/list")

        assert response.status_code == 500
        data = response.json()
        assert "Failed to fetch ETF list" in data["detail"]


class TestDailyDataAPI:
    """日线数据API测试."""

    @patch("ditto_server.api.data.get_data_readers")
    def test_get_daily_data_success(
        self, mock_readers: Mock, client: TestClient, mock_data_reader: Mock
    ) -> None:
        """测试成功获取日线数据."""
        mock_readers.return_value = (mock_data_reader, None)

        response = client.get(
            "/api/v1/data/etf/510300/daily?start_date=2024-01-01&end_date=2024-01-31"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert data["symbol"] == "510300"
        assert data["start_date"] == "2024-01-01"
        assert data["end_date"] == "2024-01-31"
        assert data["adjusted"] is True

    @patch("ditto_server.api.data.get_data_readers")
    def test_get_daily_data_empty(self, mock_reader: Mock, client: TestClient) -> None:
        """测试获取空数据."""
        mock_reader.return_value[0].get_daily_data.return_value = Mock(
            is_empty=Mock(return_value=True)
        )

        response = client.get(
            "/api/v1/data/etf/999999/daily?start_date=2024-01-01&end_date=2024-01-31"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 0
        assert "No data found" in data["message"]

    def test_get_daily_data_invalid_date(self, client: TestClient) -> None:
        """测试无效日期格式."""
        response = client.get(
            "/api/v1/data/etf/510300/daily?start_date=2024-13-01&end_date=2024-01-31"
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid date format" in data["detail"]


class TestAdjustmentFactorsAPI:
    """复权因子API测试."""

    @patch("ditto_server.api.data.get_data_readers")
    def test_get_adjustment_factors_success(
        self, mock_readers: Mock, client: TestClient, mock_data_reader: Mock
    ) -> None:
        """测试成功获取复权因子."""
        mock_readers.return_value = (mock_data_reader, None)

        response = client.get("/api/v1/data/etf/510300/adjustments")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["symbol"] == "510300"
        assert len(data["data"]) == 1


class TestTradingCalendarAPI:
    """交易日历API测试."""

    @patch("ditto_server.api.data.get_data_readers")
    def test_get_trading_calendar_success(
        self, mock_readers: Mock, client: TestClient, mock_data_reader: Mock
    ) -> None:
        """测试成功获取交易日历."""
        mock_readers.return_value = (mock_data_reader, None)

        response = client.get(
            "/api/v1/data/trading/calendar?start_date=2024-01-01&end_date=2024-01-31"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert data["start_date"] == "2024-01-01"
        assert data["end_date"] == "2024-01-31"


# class TestDataQualityReportAPI:
#     """数据质量报告API测试."""
#
#     @patch("ditto_server.api.data.DataQualityReporter")
#     @patch("ditto_server.api.data.get_data_readers")
#     def test_get_quality_report_success(self, mock_reader, mock_reporter, client):
#         """测试成功获取数据质量报告."""
#         mock_reporter_instance = Mock()
#         mock_reporter_instance.generate_market_report.return_value = {
#             "total_symbols": 100,
#             "data_quality_score": 0.95,
#             "issues": [],
#         }
#         mock_reporter.return_value = mock_reporter_instance
#
#         response = client.get("/api/v1/data/quality/report")
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["success"] is True
#         assert "data" in data
#         assert "generated_at" in data
#         assert data["data"]["total_symbols"] == 100
