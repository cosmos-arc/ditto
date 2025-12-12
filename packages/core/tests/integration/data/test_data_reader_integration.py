"""Integration tests for the DataReader implementation."""

from datetime import date

import pytest
from ditto_core.data.services.data_reader import DataReader


class TestDataReaderIntegration:
    """Integration tests for DataReader."""

    @pytest.fixture
    def test_reader(self):
        """Create a DataReader instance with temporary databases."""
        return DataReader.for_testing()

    def test_full_etf_workflow(self, test_reader):
        """Test complete ETF data workflow."""
        # 1. Store ETF info
        etf_data = [
            {
                "symbol": "159915",
                "name": "创业板ETF",
                "list_date": date(2011, 9, 20),
                "fund_family": "易方达基金",
            },
            {
                "symbol": "510300",
                "name": "沪深300ETF",
                "list_date": date(2012, 5, 4),
                "fund_family": "华泰柏瑞基金",
            },
        ]

        test_reader.store_etf_info(etf_data)

        # 2. Store daily data
        daily_data = [
            {
                "symbol": "159915",
                "date": "2024-01-02",
                "open": 2.5,
                "high": 2.6,
                "low": 2.4,
                "close": 2.55,
                "volume": 1000000,
                "amount": 2550000.0,
            },
            {
                "symbol": "159915",
                "date": "2024-01-03",
                "open": 2.55,
                "high": 2.65,
                "low": 2.5,
                "close": 2.6,
                "volume": 1200000,
                "amount": 3120000.0,
            },
            {
                "symbol": "510300",
                "date": "2024-01-02",
                "open": 4.0,
                "high": 4.1,
                "low": 3.95,
                "close": 4.05,
                "volume": 2000000,
                "amount": 8100000.0,
            },
        ]

        test_reader.store_daily_data(daily_data)

        # 3. Store trading calendar
        calendar_data = [
            {"date": "2024-01-01", "is_trading_day": False, "market": "SZSE"},
            {"date": "2024-01-02", "is_trading_day": True, "market": "SZSE"},
            {"date": "2024-01-03", "is_trading_day": True, "market": "SZSE"},
            {"date": "2024-01-04", "is_trading_day": True, "market": "SZSE"},
        ]

        test_reader.store_trading_calendar(calendar_data)

        # 4. Store adjustment factors
        adj_data = [
            {
                "symbol": "159915",
                "ex_date": "2024-01-02",
                "adj_factor": 1.0,
                "adj_type": "none",
            },
            {
                "symbol": "159915",
                "ex_date": "2024-06-01",
                "adj_factor": 1.05,
                "adj_type": "dividend",
            },
        ]

        test_reader.store_adjustment_factors(adj_data)

        # 5. Verify all data can be retrieved correctly
        etf_list = test_reader.get_etf_list()
        assert len(etf_list) == 2
        assert set(etf_list["symbol"].to_list()) == {"159915", "510300"}

        # 6. Test date range query
        daily_159915 = test_reader.get_daily_data("159915", "2024-01-01", "2024-01-05")
        assert len(daily_159915) == 2
        assert daily_159915["symbol"][0] == "159915"

        daily_510300 = test_reader.get_daily_data("510300", "2024-01-01", "2024-01-05")
        assert len(daily_510300) == 1
        assert daily_510300["symbol"][0] == "510300"

        # 7. Test trading calendar query
        trading_days = test_reader.get_trading_calendar("2024-01-01", "2024-01-05")
        assert len(trading_days) == 4  # Including Jan 1

        trading_days_only = trading_days.filter(trading_days["is_trading_day"] == True)
        assert len(trading_days_only) == 3  # Jan 2, 3, 4 are trading days

        # 8. Test adjustment factors query
        adj_factors = test_reader.get_adjustment_factors("159915")
        assert len(adj_factors) == 2
        assert adj_factors["symbol"][0] == "159915"

    def test_data_isolation_between_instances(self):
        """Test that different DataReader instances have isolated data."""
        # Create two separate instances
        reader1 = DataReader.for_testing()
        reader2 = DataReader.for_testing()

        # Store data in reader1
        reader1.store_etf_info([{"symbol": "TEST1", "name": "Test ETF 1"}])

        # Store data in reader2
        reader2.store_etf_info([{"symbol": "TEST2", "name": "Test ETF 2"}])

        # Verify isolation
        etf_list1 = reader1.get_etf_list()
        etf_list2 = reader2.get_etf_list()

        assert len(etf_list1) == 1
        assert etf_list1["symbol"][0] == "TEST1"

        assert len(etf_list2) == 1
        assert etf_list2["symbol"][0] == "TEST2"

    def test_null_values_handling(self, test_reader):
        """Test handling of null/None values in data."""
        # Store ETF info with some null values
        etf_data = [
            {"symbol": "NULL1", "name": "Test with null date"},
            {"symbol": "NULL2", "name": "Test with date", "list_date": "2024-01-01"},
        ]

        test_reader.store_etf_info(etf_data)

        # Retrieve and verify
        result = test_reader.get_etf_list()
        assert len(result) == 2
        assert result.filter(result["symbol"] == "NULL1")["list_date"][0] is None
        assert result.filter(result["symbol"] == "NULL2")["list_date"][0] is not None

    def test_empty_queries_return_correct_structure(self, test_reader):
        """Test that empty queries return DataFrames with correct structure."""
        # ETF list should have correct columns even when empty
        etf_list = test_reader.get_etf_list()
        assert list(etf_list.columns) == [
            "symbol",
            "name",
            "list_date",
            "knowledge_date",
        ]

        # Daily data should have correct columns
        daily = test_reader.get_daily_data("NOTEXIST", "2024-01-01", "2024-01-05")
        expected_cols = [
            "symbol",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "knowledge_date",
        ]
        assert all(col in daily.columns for col in expected_cols)

        # Trading calendar should have correct columns
        calendar = test_reader.get_trading_calendar("2024-01-01", "2024-01-05")
        expected_cols = ["date", "is_trading_day", "market", "knowledge_date"]
        assert all(col in calendar.columns for col in expected_cols)

    def test_large_dataset_performance(self, test_reader):
        """Test performance with larger datasets."""
        import time

        # Generate test data
        n_records = 10000
        symbols = ["ETF001", "ETF002", "ETF003", "ETF004", "ETF005"]
        dates = [f"2024-{i:02d}-{j:02d}" for i in range(1, 13) for j in range(1, 29)]

        daily_data = []
        for symbol in symbols:
            for date_str in dates[:100]:  # 100 days per symbol
                daily_data.append(
                    {
                        "symbol": symbol,
                        "date": date_str,
                        "open": 2.0,
                        "high": 2.1,
                        "low": 1.9,
                        "close": 2.05,
                        "volume": 1000000,
                    }
                )

        # Measure storage time
        start_time = time.time()
        test_reader.store_daily_data(daily_data)
        store_time = time.time() - start_time
        print(f"\nStored {len(daily_data)} records in {store_time:.3f} seconds")

        # Measure query time
        start_time = time.time()
        result = test_reader.get_daily_data("ETF001", "2024-01-01", "2024-12-31")
        query_time = time.time() - start_time
        print(f"Queried {len(result)} records in {query_time:.3f} seconds")

        # Verify results
        assert len(result) == 100
        assert all(result["symbol"] == "ETF001")

        # Performance assertions (these are loose bounds)
        assert store_time < 5.0, f"Storage took too long: {store_time}s"
        assert query_time < 1.0, f"Query took too long: {query_time}s"
