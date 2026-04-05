"""Tests for Dataset Configuration Registry."""

from datetime import time

import pytest
from ditto_app.config import (
    INGESTION_SPECS,
    DatasetSpec,
    T1ConfigSpec,
    TaskTier,
    create_t0_config,
    create_t1_config,
    get_all_datasets,
    get_dataset_config,
    get_datasets_by_tier,
    get_parallel_datasets,
)
from ditto_data.models import Dataset


@pytest.mark.unit
class TestDatasetEnum:
    """Test Dataset enumeration."""

    @pytest.mark.parametrize(
        "dataset",
        [
            # T0 meta datasets
            Dataset.CALENDAR,
            Dataset.STOCK_BASIC,
            Dataset.ETF_BASIC,
            # T1 incremental datasets
            Dataset.ETF_DAILY,
            Dataset.STOCK_DAILY,
            Dataset.STOCK_STATUS,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.BALANCE_SHEET,
            Dataset.INCOME_STATEMENT,
            Dataset.CASH_FLOW,
            Dataset.DIVIDEND,
            Dataset.VALUATION_METRICS,
            Dataset.MARGIN_TRADING,
            Dataset.PLEDGE_RATIO,
            Dataset.MACRO_INDICATORS,
        ],
    )
    def test_dataset_enum_contains(self, dataset: Dataset) -> None:
        """Test that datasets are defined in the enum."""
        assert dataset in Dataset

    def test_dataset_values(self) -> None:
        """Test dataset enum values match expected strings."""
        assert Dataset.CALENDAR.value == "calendar"
        assert Dataset.STOCK_BASIC.value == "stock_basic"
        assert Dataset.ETF_BASIC.value == "etf_basic"
        assert Dataset.ETF_DAILY.value == "etf_daily"
        assert Dataset.STOCK_DAILY.value == "stock_daily"
        assert Dataset.STOCK_STATUS.value == "stock_status"
        assert Dataset.ADJ_FACTOR.value == "adj_factor"
        assert Dataset.FUND_ADJ.value == "fund_adj"
        assert Dataset.BALANCE_SHEET.value == "balance_sheet"
        assert Dataset.INCOME_STATEMENT.value == "income_statement"
        assert Dataset.CASH_FLOW.value == "cash_flow"
        assert Dataset.DIVIDEND.value == "dividend"
        assert Dataset.VALUATION_METRICS.value == "valuation_metrics"
        assert Dataset.MARGIN_TRADING.value == "margin_trading"
        assert Dataset.PLEDGE_RATIO.value == "pledge_ratio"
        assert Dataset.MACRO_INDICATORS.value == "macro_indicators"


@pytest.mark.unit
class TestTaskTierEnum:
    """Test TaskTier enumeration."""

    def test_task_tier_values(self) -> None:
        """Test task tier enum values."""
        assert TaskTier.T0_META.value == "t0_meta"
        assert TaskTier.T1_INCREMENTAL.value == "t1_incremental"
        assert TaskTier.T2_REPAIR.value == "t2_repair"
        assert TaskTier.T3_QUALITY.value == "t3_quality"


@pytest.mark.unit
class TestDatasetSpec:
    """Test DatasetSpec model."""

    def test_dataset_config_validation(self) -> None:
        """Test DatasetSpec model validation with all required fields."""
        config = DatasetSpec(
            dataset=Dataset.ETF_DAILY,
            tier=TaskTier.T1_INCREMENTAL,
            description="ETF daily bars",
            update_frequency="每日",
            typical_available_time=time(18, 0),
            priority=20,
            depends_on=[Dataset.ETF_BASIC],
            retry_limit=3,
            timeout_seconds=300,
            quality_checks_enabled=True,
            critical_fields=[
                "trade_date",
                "ts_code",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
            task_name="ingest_etf_bars",
            requires_trade_date=True,
        )

        assert config.dataset == Dataset.ETF_DAILY
        assert config.tier == TaskTier.T1_INCREMENTAL
        assert config.update_frequency == "每日"
        assert config.typical_available_time == time(18, 0)
        assert config.priority == 20
        assert config.depends_on == [Dataset.ETF_BASIC]
        assert config.retry_limit == 3
        assert config.timeout_seconds == 300
        assert config.quality_checks_enabled is True
        assert config.critical_fields == [
            "trade_date",
            "ts_code",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

    def test_dataset_config_with_dependencies(self) -> None:
        """Test DatasetSpec with depends_on field."""
        config = DatasetSpec(
            dataset=Dataset.STOCK_DAILY,
            tier=TaskTier.T1_INCREMENTAL,
            description="Stock daily bars",
            update_frequency="每日",
            typical_available_time=time(17, 0),
            priority=20,
            depends_on=[Dataset.STOCK_BASIC],
            retry_limit=3,
            timeout_seconds=600,
            quality_checks_enabled=True,
            critical_fields=[
                "trade_date",
                "ts_code",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
            task_name="ingest_stock_daily",
            requires_trade_date=True,
        )

        assert config.depends_on == [Dataset.STOCK_BASIC]

    def test_dataset_config_adj_factor_dependencies(self) -> None:
        """Test ADJ_FACTOR depends on STOCK_DAILY."""
        config = DatasetSpec(
            dataset=Dataset.ADJ_FACTOR,
            tier=TaskTier.T1_INCREMENTAL,
            description="复权因子",
            update_frequency="每日",
            typical_available_time=time(19, 0),
            priority=30,
            depends_on=[Dataset.STOCK_DAILY],
            retry_limit=3,
            timeout_seconds=300,
            quality_checks_enabled=True,
            critical_fields=["trade_date", "ts_code", "adj_factor"],
            task_name="ingest_adj_factor",
            requires_trade_date=True,
        )

        assert config.depends_on == [Dataset.STOCK_DAILY]


@pytest.mark.unit
class TestDatasetRegistry:
    """Test INGESTION_SPECS."""

    def test_registry_is_defined(self) -> None:
        """Test INGESTION_SPECS is defined."""
        assert isinstance(INGESTION_SPECS, dict)
        assert len(INGESTION_SPECS) > 0

    def test_registry_contains_all_datasets(self) -> None:
        """Test registry contains all Dataset enum values."""
        for dataset in Dataset:
            assert dataset in INGESTION_SPECS, f"{dataset} not in registry"

    def test_registry_configs_are_valid(self) -> None:
        """Test all registry configs are valid DatasetSpec instances."""
        for dataset, config in INGESTION_SPECS.items():
            assert isinstance(config, DatasetSpec)
            assert config.dataset == dataset

    def test_t0_meta_datasets_config(self) -> None:
        """Test T0 meta datasets configuration."""
        # Calendar should be T0
        calendar = INGESTION_SPECS[Dataset.CALENDAR]
        assert calendar.tier == TaskTier.T0_META
        assert calendar.requires_trade_date is False
        assert calendar.priority == 10  # Highest priority

        # Stock basic should be T0
        stock_basic = INGESTION_SPECS[Dataset.STOCK_BASIC]
        assert stock_basic.tier == TaskTier.T0_META
        assert stock_basic.requires_trade_date is False
        assert stock_basic.task_name == "ingest_stock_basic"

        # ETF basic should be T0
        etf_basic = INGESTION_SPECS[Dataset.ETF_BASIC]
        assert etf_basic.tier == TaskTier.T0_META
        assert etf_basic.requires_trade_date is False

    def test_t1_daily_datasets_config(self) -> None:
        """Test T1 daily datasets configuration."""
        # ETF daily should be T1
        etf_daily = INGESTION_SPECS[Dataset.ETF_DAILY]
        assert etf_daily.tier == TaskTier.T1_INCREMENTAL
        assert etf_daily.requires_trade_date is True
        assert etf_daily.task_name == "ingest_etf_bars"
        assert etf_daily.update_frequency == "每日"
        assert isinstance(etf_daily.typical_available_time, time)

        # Stock daily should be T1
        stock_daily = INGESTION_SPECS[Dataset.STOCK_DAILY]
        assert stock_daily.tier == TaskTier.T1_INCREMENTAL
        assert stock_daily.requires_trade_date is True
        assert stock_daily.task_name == "ingest_stock_daily"

        # Stock status should be T1
        stock_status = INGESTION_SPECS[Dataset.STOCK_STATUS]
        assert stock_status.tier == TaskTier.T1_INCREMENTAL
        assert stock_status.requires_trade_date is True
        assert stock_status.task_name == "ingest_stock_status"

        # Adj factor should be T1
        adj_factor = INGESTION_SPECS[Dataset.ADJ_FACTOR]
        assert adj_factor.tier == TaskTier.T1_INCREMENTAL
        assert adj_factor.requires_trade_date is True
        assert adj_factor.task_name == "ingest_adj_factor"

        # Fund adj should be T1
        fund_adj = INGESTION_SPECS[Dataset.FUND_ADJ]
        assert fund_adj.tier == TaskTier.T1_INCREMENTAL
        assert fund_adj.requires_trade_date is True
        assert fund_adj.task_name == "ingest_fund_adj"

        # Fundamental datasets should be T1
        balance_sheet = INGESTION_SPECS[Dataset.BALANCE_SHEET]
        assert balance_sheet.tier == TaskTier.T1_INCREMENTAL
        assert balance_sheet.task_name == "ingest_balance_sheet"

        income_statement = INGESTION_SPECS[Dataset.INCOME_STATEMENT]
        assert income_statement.tier == TaskTier.T1_INCREMENTAL
        assert income_statement.task_name == "ingest_income_statement"

        cash_flow = INGESTION_SPECS[Dataset.CASH_FLOW]
        assert cash_flow.tier == TaskTier.T1_INCREMENTAL
        assert cash_flow.task_name == "ingest_cash_flow"

        dividend = INGESTION_SPECS[Dataset.DIVIDEND]
        assert dividend.tier == TaskTier.T1_INCREMENTAL
        assert dividend.task_name == "ingest_dividend"

        # Capital datasets should be T1
        valuation_metrics = INGESTION_SPECS[Dataset.VALUATION_METRICS]
        assert valuation_metrics.tier == TaskTier.T1_INCREMENTAL
        assert valuation_metrics.task_name == "ingest_valuation_metrics"

        margin_trading = INGESTION_SPECS[Dataset.MARGIN_TRADING]
        assert margin_trading.tier == TaskTier.T1_INCREMENTAL
        assert margin_trading.task_name == "ingest_margin_trading"

        pledge_ratio = INGESTION_SPECS[Dataset.PLEDGE_RATIO]
        assert pledge_ratio.tier == TaskTier.T1_INCREMENTAL
        assert pledge_ratio.task_name == "ingest_pledge_ratio"

        macro_indicators = INGESTION_SPECS[Dataset.MACRO_INDICATORS]
        assert macro_indicators.tier == TaskTier.T1_INCREMENTAL
        assert macro_indicators.task_name == "ingest_macro_indicators"

    def test_required_fields_exist(self) -> None:
        """Test all datasets have required spec fields."""
        for _dataset, config in INGESTION_SPECS.items():
            # Check all required fields are present
            assert hasattr(config, "dataset")
            assert hasattr(config, "tier")
            assert hasattr(config, "description")
            assert hasattr(config, "update_frequency")
            assert hasattr(config, "typical_available_time")
            assert hasattr(config, "priority")
            assert hasattr(config, "depends_on")
            assert hasattr(config, "retry_limit")
            assert hasattr(config, "timeout_seconds")
            assert hasattr(config, "quality_checks_enabled")
            assert hasattr(config, "critical_fields")

            # Validate field types
            assert isinstance(config.dataset, Dataset)
            assert isinstance(config.tier, TaskTier)
            assert isinstance(config.description, str)
            assert isinstance(config.update_frequency, str)
            assert isinstance(config.typical_available_time, time)
            assert isinstance(config.priority, int)
            assert isinstance(config.depends_on, list)
            assert isinstance(config.retry_limit, int)
            assert isinstance(config.timeout_seconds, int)
            assert isinstance(config.quality_checks_enabled, bool)
            assert isinstance(config.critical_fields, list)


@pytest.mark.unit
class TestHelperFunctions:
    """Test helper functions."""

    def test_get_datasets_by_tier_t0(self) -> None:
        """Test get_datasets_by_tier for T0."""
        t0_datasets = get_datasets_by_tier(TaskTier.T0_META)

        assert Dataset.CALENDAR in t0_datasets
        assert Dataset.STOCK_BASIC in t0_datasets
        assert Dataset.ETF_BASIC in t0_datasets
        assert Dataset.ETF_DAILY not in t0_datasets
        assert Dataset.STOCK_DAILY not in t0_datasets

    def test_get_datasets_by_tier_t1(self) -> None:
        """Test get_datasets_by_tier for T1."""
        t1_datasets = get_datasets_by_tier(TaskTier.T1_INCREMENTAL)

        assert Dataset.ETF_DAILY in t1_datasets
        assert Dataset.STOCK_DAILY in t1_datasets
        assert Dataset.STOCK_STATUS in t1_datasets
        assert Dataset.ADJ_FACTOR in t1_datasets
        assert Dataset.FUND_ADJ in t1_datasets
        assert Dataset.BALANCE_SHEET in t1_datasets
        assert Dataset.INCOME_STATEMENT in t1_datasets
        assert Dataset.CASH_FLOW in t1_datasets
        assert Dataset.DIVIDEND in t1_datasets
        assert Dataset.VALUATION_METRICS in t1_datasets
        assert Dataset.MARGIN_TRADING in t1_datasets
        assert Dataset.PLEDGE_RATIO in t1_datasets
        assert Dataset.MACRO_INDICATORS in t1_datasets
        assert Dataset.CALENDAR not in t1_datasets
        assert Dataset.STOCK_BASIC not in t1_datasets

    def test_get_datasets_by_tier_t2(self) -> None:
        """Test get_datasets_by_tier for T2."""
        t2_datasets = get_datasets_by_tier(TaskTier.T2_REPAIR)

        # T2 is for repair/backfill, can be empty
        # (repair flow uses all datasets dynamically)
        # This test ensures the function works correctly even if no T2-specific datasets
        assert isinstance(t2_datasets, list)

    def test_get_dataset_config(self) -> None:
        """Test get_dataset_config function."""
        config = get_dataset_config(Dataset.ETF_DAILY)

        assert isinstance(config, DatasetSpec)
        assert config.dataset == Dataset.ETF_DAILY
        assert config.tier == TaskTier.T1_INCREMENTAL

    def test_get_dataset_config_all_datasets(self) -> None:
        """Test get_dataset_config works for all datasets."""
        for dataset in Dataset:
            config = get_dataset_config(dataset)
            assert isinstance(config, DatasetSpec)
            assert config.dataset == dataset


@pytest.mark.unit
class TestDatasetDependencies:
    """Test dataset dependency relationships."""

    def test_calendar_no_dependencies(self) -> None:
        """Test calendar has no dependencies (foundation dataset)."""
        config = get_dataset_config(Dataset.CALENDAR)
        assert len(config.depends_on) == 0

    def test_t1_etf_daily_depends_on_etf_basic(self) -> None:
        """Test ETF_DAILY depends on ETF_BASIC."""
        config = get_dataset_config(Dataset.ETF_DAILY)
        assert Dataset.ETF_BASIC in config.depends_on

    def test_t1_stock_daily_depends_on_stock_basic(self) -> None:
        """Test STOCK_DAILY depends on STOCK_BASIC."""
        config = get_dataset_config(Dataset.STOCK_DAILY)
        assert Dataset.STOCK_BASIC in config.depends_on

    def test_t1_adj_factor_depends_on_stock_daily(self) -> None:
        """Test ADJ_FACTOR depends on STOCK_DAILY."""
        config = get_dataset_config(Dataset.ADJ_FACTOR)
        assert Dataset.STOCK_DAILY in config.depends_on

    def test_t1_stock_status_depends_on_stock_daily(self) -> None:
        """Test STOCK_STATUS depends on STOCK_DAILY."""
        config = get_dataset_config(Dataset.STOCK_STATUS)
        assert Dataset.STOCK_DAILY in config.depends_on

    def test_t1_valuation_metrics_depends_on_stock_daily(self) -> None:
        """Test VALUATION_METRICS depends on STOCK_DAILY."""
        config = get_dataset_config(Dataset.VALUATION_METRICS)
        assert Dataset.STOCK_DAILY in config.depends_on

    def test_no_circular_dependencies(self) -> None:
        """Test there are no circular dependencies in the registry."""
        # Build dependency graph
        dep_graph = {}
        for dataset, config in INGESTION_SPECS.items():
            dep_graph[dataset] = set(config.depends_on)

        # Check for cycles using DFS
        def has_cycle(
            node: Dataset,
            visited: set[Dataset],
            rec_stack: set[Dataset],
        ) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in dep_graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for dataset in Dataset:
            if has_cycle(dataset, set(), set()):
                pytest.fail(f"Circular dependency detected involving {dataset}")


@pytest.mark.unit
class TestExtendedHelperFunctions:
    """Test extended helper functions for parallel execution."""

    def test_get_all_datasets(self) -> None:
        """Test get_all_datasets returns all datasets."""
        all_datasets = get_all_datasets()

        assert len(all_datasets) > 0
        assert Dataset.CALENDAR in all_datasets
        assert Dataset.ETF_DAILY in all_datasets

    def test_get_parallel_datasets_t1(self) -> None:
        """
        Test get_parallel_datasets for T1 tier.

        T1 datasets have a dependency chain:
        - Level 0: Datasets with no intra-T1 dependencies
        - Level 1: Datasets depending on STOCK_DAILY/ETF_DAILY
        """
        levels = get_parallel_datasets(TaskTier.T1_INCREMENTAL)

        # T1 should have 2 levels due to T1->T1 dependencies
        assert len(levels) == 2

        # Level 0 should include bars datasets
        assert Dataset.ETF_DAILY in levels[0]
        assert Dataset.STOCK_DAILY in levels[0]

        # Level 1 should include datasets depending on bars datasets
        level1_set = set(levels[1])
        assert {
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.STOCK_STATUS,
            Dataset.VALUATION_METRICS,
            Dataset.MARGIN_TRADING,
        }.issubset(level1_set)

    def test_get_parallel_datasets_t0(self) -> None:
        """Test get_parallel_datasets for T0 tier."""
        levels = get_parallel_datasets(TaskTier.T0_META)

        # T0 should have 1 level with all datasets (no dependencies)
        assert len(levels) == 1
        assert len(levels[0]) >= 3  # calendar, stock_basic, etf_basic

    def test_get_parallel_datasets_empty_tier(self) -> None:
        """Test get_parallel_datasets for tier with no datasets."""
        levels = get_parallel_datasets(TaskTier.T2_REPAIR)

        # T2 has no datasets, should return empty list
        assert levels == []

    def test_parallel_execution_validation(self) -> None:
        """Test that parallel execution groups are valid."""
        levels = get_parallel_datasets(TaskTier.T1_INCREMENTAL)

        # Verify no dataset appears twice
        seen = set()
        for level in levels:
            for dataset in level:
                assert dataset not in seen, f"{dataset} appears in multiple levels"
                seen.add(dataset)

        # Verify all datasets are accounted for
        t1_datasets = set(get_datasets_by_tier(TaskTier.T1_INCREMENTAL))
        assert seen == t1_datasets


@pytest.mark.unit
class TestFactoryFunctions:
    """Test factory functions for dataset configuration."""

    def test_create_t0_config_creates_valid_config(self) -> None:
        """Test create_t0_config creates a valid T0 dataset configuration."""
        config = create_t0_config(
            dataset=Dataset.CALENDAR,
            description="交易日历",
            typical_available_time=time(8, 0),
            critical_fields=["cal_date", "is_trade"],
            task_name="ingest_calendar",
        )

        assert isinstance(config, DatasetSpec)
        assert config.dataset == Dataset.CALENDAR
        assert config.tier == TaskTier.T0_META
        assert config.description == "交易日历"
        assert config.priority == 10
        assert config.depends_on == []
        assert config.retry_limit == 3
        assert config.quality_checks_enabled is True
        assert config.requires_trade_date is False
        assert config.update_frequency == "每日"

    def test_create_t0_config_with_custom_timeout(self) -> None:
        """Test create_t0_config with custom timeout_seconds."""
        config = create_t0_config(
            dataset=Dataset.CALENDAR,
            description="交易日历",
            typical_available_time=time(8, 0),
            critical_fields=["cal_date", "is_trade"],
            task_name="ingest_calendar",
            timeout_seconds=120,
        )

        assert config.timeout_seconds == 120

    def test_create_t1_config_creates_valid_config(self) -> None:
        """Test create_t1_config creates a valid T1 dataset configuration."""
        config = create_t1_config(
            dataset=Dataset.ETF_DAILY,
            description="ETF日行情数据",
            typical_available_time=time(18, 0),
            depends_on=[Dataset.ETF_BASIC],
            critical_fields=["trade_date", "ts_code", "close"],
            task_name="ingest_etf_bars",
        )

        assert isinstance(config, DatasetSpec)
        assert config.dataset == Dataset.ETF_DAILY
        assert config.tier == TaskTier.T1_INCREMENTAL
        assert config.description == "ETF日行情数据"
        assert config.priority == 20  # default
        assert config.depends_on == [Dataset.ETF_BASIC]
        assert config.retry_limit == 3
        assert config.quality_checks_enabled is True
        assert config.requires_trade_date is True
        assert config.update_frequency == "每日"

    def test_create_t1_config_with_custom_priority(self) -> None:
        """Test create_t1_config with custom priority."""
        config = create_t1_config(
            dataset=Dataset.ADJ_FACTOR,
            description="复权因子",
            typical_available_time=time(19, 0),
            depends_on=[Dataset.STOCK_DAILY],
            critical_fields=["trade_date", "ts_code", "adj_factor"],
            task_name="ingest_adj_factor",
            priority=30,
        )

        assert config.priority == 30

    def test_create_t1_config_with_custom_timeout(self) -> None:
        """Test create_t1_config with custom timeout_seconds."""
        config = create_t1_config(
            dataset=Dataset.STOCK_DAILY,
            description="股票日行情数据",
            typical_available_time=time(17, 0),
            depends_on=[Dataset.STOCK_BASIC],
            critical_fields=["trade_date", "ts_code", "close"],
            task_name="ingest_stock_daily",
            timeout_seconds=600,
        )

        assert config.timeout_seconds == 600


@pytest.mark.unit
class TestT1ConfigSpec:
    """Test T1ConfigSpec configuration parameter class."""

    def test_t1_config_params_creates_valid_params(self) -> None:
        """Test T1ConfigSpec creates valid configuration parameters."""
        params = T1ConfigSpec(
            dataset=Dataset.ETF_DAILY,
            description="ETF日行情数据",
            typical_available_time=time(18, 0),
            depends_on=[Dataset.ETF_BASIC],
            critical_fields=["trade_date", "ts_code", "close"],
            task_name="ingest_etf_bars",
        )

        assert params.dataset == Dataset.ETF_DAILY
        assert params.description == "ETF日行情数据"
        assert params.typical_available_time == time(18, 0)
        assert params.depends_on == [Dataset.ETF_BASIC]
        assert params.critical_fields == ["trade_date", "ts_code", "close"]
        assert params.task_name == "ingest_etf_bars"
        assert params.priority == 20  # default
        assert params.timeout_seconds == 300  # default

    def test_t1_config_params_with_custom_priority(self) -> None:
        """Test T1ConfigSpec with custom priority."""
        params = T1ConfigSpec(
            dataset=Dataset.ADJ_FACTOR,
            description="复权因子",
            typical_available_time=time(19, 0),
            depends_on=[Dataset.STOCK_DAILY],
            critical_fields=["trade_date", "ts_code", "adj_factor"],
            task_name="ingest_adj_factor",
            priority=30,
        )

        assert params.priority == 30

    def test_t1_config_params_with_custom_timeout(self) -> None:
        """Test T1ConfigSpec with custom timeout_seconds."""
        params = T1ConfigSpec(
            dataset=Dataset.STOCK_DAILY,
            description="股票日行情数据",
            typical_available_time=time(17, 0),
            depends_on=[Dataset.STOCK_BASIC],
            critical_fields=["trade_date", "ts_code", "close"],
            task_name="ingest_stock_daily",
            timeout_seconds=600,
        )

        assert params.timeout_seconds == 600

    def test_t1_config_params_validation(self) -> None:
        """Test T1ConfigSpec validates required fields."""
        with pytest.raises(ValueError):
            T1ConfigSpec(
                # Missing required field: dataset
                description="ETF日行情数据",
                typical_available_time=time(18, 0),
                depends_on=[Dataset.ETF_BASIC],
                critical_fields=["trade_date", "ts_code", "close"],
                task_name="ingest_etf_bars",
            )

    def test_create_t1_config_with_params(self) -> None:
        """Test create_t1_config accepts T1ConfigSpec."""
        params = T1ConfigSpec(
            dataset=Dataset.ETF_DAILY,
            description="ETF日行情数据",
            typical_available_time=time(18, 0),
            depends_on=[Dataset.ETF_BASIC],
            critical_fields=["trade_date", "ts_code", "close"],
            task_name="ingest_etf_bars",
        )

        config = create_t1_config(params)

        assert isinstance(config, DatasetSpec)
        assert config.dataset == Dataset.ETF_DAILY
        assert config.tier == TaskTier.T1_INCREMENTAL
        assert config.description == "ETF日行情数据"
        assert config.priority == 20
        assert config.timeout_seconds == 300

    def test_create_t1_config_with_params_custom_values(self) -> None:
        """Test create_t1_config with T1ConfigSpec custom values."""
        params = T1ConfigSpec(
            dataset=Dataset.ADJ_FACTOR,
            description="复权因子",
            typical_available_time=time(19, 0),
            depends_on=[Dataset.STOCK_DAILY],
            critical_fields=["trade_date", "ts_code", "adj_factor"],
            task_name="ingest_adj_factor",
            priority=30,
            timeout_seconds=600,
        )

        config = create_t1_config(params)

        assert config.priority == 30
        assert config.timeout_seconds == 600
