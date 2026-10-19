"""Application catalog maturity helper tests."""

import pytest
from ditto_application.catalog_maturity import (
    assert_strategy_runtime_data_allowed,
    catalog_dataset_asset_class,
    strategy_runtime_dataset_ids,
)
from ditto_application.exceptions import AppBuilderError
from ditto_application.strategy_spec_legacy_deserialization import (
    default_required_datasets_for_template,
)
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.alpha.specs import StrategySpec


class TestCatalogDatasetAssetClass:
    """Application-facing dataset asset-class resolution."""

    def test_known_instrument_dataset_returns_asset_class(self) -> None:
        assert catalog_dataset_asset_class("stock_daily") == "stock"

    def test_metadata_dataset_returns_none(self) -> None:
        assert catalog_dataset_asset_class("stock_basic") is None

    def test_unknown_dataset_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown dataset_id"):
            catalog_dataset_asset_class("unknown_dataset")


def _stock_spec(
    *,
    required_datasets: tuple[str, ...] = (),
    benchmark: str | None = "000300.SH",
) -> StrategySpec:
    return StrategySpec(
        strategy_id="stock-alpha",
        name="Stock Alpha",
        template="stock_selection",
        universe="csi_a_share",
        asset_class="stock",
        benchmark=benchmark,
        required_datasets=required_datasets,
    )


class TestStrategyRuntimeDatasetIds:
    """strategy runtime maturity gate dataset scope."""

    def test_includes_asset_pair_and_benchmark(self) -> None:
        spec = _stock_spec()

        assert strategy_runtime_dataset_ids(spec) == (
            "stock_daily",
            "stock_basic",
            "index_daily",
            "index_basic",
        )

    def test_includes_declared_required_datasets_without_duplicates(self) -> None:
        spec = _stock_spec(
            required_datasets=("stock_daily", "adj_factor", "balance_sheet"),
        )

        assert strategy_runtime_dataset_ids(spec) == (
            "stock_daily",
            "stock_basic",
            "adj_factor",
            "balance_sheet",
            "index_daily",
            "index_basic",
        )


class TestAssertStrategyRuntimeDataAllowed:
    """strategy runtime fail-closed maturity gate."""

    def test_seed_stock_selection_rotation_passes_without_opt_in(self) -> None:
        """#196 策略腿晋级后,种子股票模板声明数据集全部走正式路径。"""
        spec = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]

        assert_strategy_runtime_data_allowed(spec)

    def test_blocks_experimental_statement_lane_after_promotion(self) -> None:
        """两表晋级后,仍为 experimental 的 cash_flow 消费规格继续被拦截。"""
        spec = _stock_spec(
            required_datasets=(
                "stock_daily",
                "adj_factor",
                "cash_flow",
            ),
        )

        with pytest.raises(AppBuilderError, match="cash_flow=experimental"):
            assert_strategy_runtime_data_allowed(spec)

    def test_stock_lane_allowed_by_static_assignment(self) -> None:
        """核心市场 lane 静态为 initial-focus,正式运行无需显式放行。"""
        spec = _stock_spec(
            required_datasets=default_required_datasets_for_template(
                "stock_sector_rotation",
            ),
        )

        assert_strategy_runtime_data_allowed(spec)

    def test_cash_flow_lane_requires_explicit_research_opt_in(self) -> None:
        """无正式消费者的 cash_flow 保持 experimental,必须显式研究放行。"""
        spec = _stock_spec(
            required_datasets=("cash_flow",),
        )

        with pytest.raises(AppBuilderError, match="cash_flow=experimental"):
            assert_strategy_runtime_data_allowed(spec)

        assert_strategy_runtime_data_allowed(
            spec,
            allow_experimental_data=True,
        )

    def test_research_opt_in_allows_experimental_required_datasets(self) -> None:
        spec = _stock_spec(
            required_datasets=("stock_daily", "cash_flow"),
        )

        assert_strategy_runtime_data_allowed(spec, allow_experimental_data=True)

    def test_unknown_required_dataset_blocks_formal_runtime(self) -> None:
        spec = _stock_spec(required_datasets=("stock_daily", "not_a_catalog_dataset"))

        with pytest.raises(AppBuilderError, match="not_a_catalog_dataset=unknown"):
            assert_strategy_runtime_data_allowed(spec)

    def test_unknown_required_dataset_blocks_even_with_research_opt_in(self) -> None:
        """研究 opt-in 只放行 experimental,不放行目录未声明的未知数据集。"""
        spec = _stock_spec(required_datasets=("stock_daily", "not_a_catalog_dataset"))

        with pytest.raises(AppBuilderError, match="not_a_catalog_dataset=unknown"):
            assert_strategy_runtime_data_allowed(spec, allow_experimental_data=True)
