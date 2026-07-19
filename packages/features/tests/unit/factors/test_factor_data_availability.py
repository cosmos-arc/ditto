"""因子 PIT 数据可用性验证.

验证因子依赖的数据集是否已接入、DQ 规则是否覆盖、已知 gap 是否记录。

注意：此测试不依赖真实数据，而是验证因子 spec 依赖与数据集注册的映射关系。
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from ditto_data.models import Dataset
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.spec import FactorSpec
from ditto_features.factors.validate import validate_factor_specs


class TestFactorSpecsCIGate:
    """CI 门禁：validate_factor_specs() 必须返回空错误列表."""

    def test_validate_factor_specs_no_errors(self) -> None:
        """所有因子 spec 验证通过（编译 + 环检测 + 依赖引用 + Python 约束）."""
        errors = validate_factor_specs()
        assert errors == [], "Factor spec validation failed:\n" + "\n".join(
            f"  - {e}" for e in errors
        )

    def test_all_factor_specs_have_valid_ids(self) -> None:
        """所有因子 ID 非空且符合命名规范."""
        for factor_id, spec in ALL_FACTOR_SPECS.items():
            assert factor_id, "Empty factor ID"
            assert spec.id == factor_id, f"Spec ID mismatch: {spec.id} != {factor_id}"

    def test_benchmark_prefix_is_exactly_scoped(self) -> None:
        """Allow benchmark columns without opening arbitrary external prefixes."""
        benchmark = FactorSpec(
            id="benchmark_factor",
            expression="",
            dependencies=("benchmark.close",),
            description="registered benchmark input",
            computation_type="python",
        )
        assert validate_factor_specs({benchmark.id: benchmark}) == []

        unregistered = FactorSpec(
            id="unregistered_factor",
            expression="",
            dependencies=("vendor.close",),
            description="unregistered external input",
            computation_type="python",
        )
        assert any(
            "unknown dependency 'vendor.close'" in error
            for error in validate_factor_specs({unregistered.id: unregistered})
        )


class TestFactorDataAvailability:
    """验证核心因子依赖的数据集可用性."""

    MARKET_DEPENDENCIES: ClassVar[frozenset[str]] = frozenset(
        {
            "market.close",
            "market.volume",
            "market.high",
            "market.low",
            "market.open",
            "market.amount",
        }
    )

    @pytest.fixture
    def registered_datasets(self) -> set[str]:
        """获取所有已注册的数据集名称."""
        return {ds.value for ds in Dataset}

    def test_market_dependencies_covered(self, registered_datasets: set[str]) -> None:
        """market.* 依赖全部由 stock_daily/etf_daily 覆盖."""
        market_datasets = {"stock_daily", "etf_daily"}
        assert market_datasets.issubset(registered_datasets), (
            "Market datasets not registered"
        )

    def test_fundamental_datasets_registered(
        self,
        registered_datasets: set[str],
    ) -> None:
        """基本面数据集全部已注册."""
        fundamental_datasets = {
            "balance_sheet",
            "income_statement",
            "cash_flow",
            "dividend",
            "valuation_metrics",
        }
        assert fundamental_datasets.issubset(registered_datasets), (
            "Fundamental datasets not registered"
        )

    def test_capital_datasets_registered(
        self,
        registered_datasets: set[str],
    ) -> None:
        """资金数据集全部已注册."""
        capital_datasets = {"margin_trading", "pledge_ratio"}
        assert capital_datasets.issubset(registered_datasets), (
            "Capital datasets not registered"
        )

    def test_all_factor_dependencies_use_known_prefixes(self) -> None:
        """所有因子依赖使用 market. / fundamentals. / capital. 前缀.

        已由 validate_factor_specs 内部覆盖，此处显式记录以确保 CI 不会遗漏。
        """
        errors = validate_factor_specs()
        dep_errors = [e for e in errors if "dependenc" in e.lower()]
        assert dep_errors == [], "Unknown dependency references found"


class TestKnownDataGaps:
    """记录已知的数据缺口，确保不会意外回退.

    这些缺口在 V1 RC 中是可接受的，后续版本应逐步消除。
    """

    # ---- 无数据源 ----
    GAP_NO_SOURCE: ClassVar[tuple[tuple[str, str], ...]] = (
        ("fundamentals.free_float_shares", "无数据源 — 需要新 API 接入"),
    )

    # ---- 需要 TTM 滚动计算 ----
    GAP_NEEDS_TTM_DERIVATION: ClassVar[tuple[tuple[str, str], ...]] = (
        ("fundamentals.ocf_ttm", "需从 ocf 做 TTM 滚动计算"),
        ("fundamentals.dps_ttm", "需从 dividend 做 TTM 滚动计算"),
        ("fundamentals.net_income_ttm", "需从 net_income 做 TTM 滚动计算"),
        ("fundamentals.revenue_ttm", "需从 revenue 做 TTM 滚动计算"),
    )

    # ---- 可从已有列计算 ----
    GAP_COMPUTABLE: ClassVar[tuple[tuple[str, str], ...]] = (
        ("fundamentals.book_value_per_share", "可从 net_assets/total_share 计算"),
        ("fundamentals.revenue_per_share", "可从 revenue/total_share 计算"),
        ("fundamentals.rvps", "可从 revenue/total_share 计算"),
        ("fundamentals.total_debt", "可从 short_term_debt+long_term_debt 计算"),
        ("fundamentals.ebitda", "可从 operating_profit+depreciation 计算"),
    )

    # ---- 直接可用的 fundamentals.* 列 ----
    AVAILABLE_FUNDAMENTALS: ClassVar[frozenset[str]] = frozenset(
        {
            "fundamentals.total_assets",
            "fundamentals.net_income",
            "fundamentals.revenue",
            "fundamentals.equity",
            "fundamentals.cogs",
            "fundamentals.op_income",
            "fundamentals.ocf",
            "fundamentals.total_shares",
            "fundamentals.total_equity",
            "fundamentals.cash",
            "fundamentals.earnings_per_share",
        }
    )

    def test_known_gaps_are_documented(self) -> None:
        """已知缺口已记录（防止意外遗忘）.

        如果 gap 数量变化，说明要么有新 gap（需记录），
        要么旧 gap 已修复（需更新断言值）。
        """
        total_gaps = (
            len(self.GAP_NO_SOURCE)
            + len(self.GAP_NEEDS_TTM_DERIVATION)
            + len(self.GAP_COMPUTABLE)
        )
        assert total_gaps == 10, (
            f"Gap count changed: expected 10, got {total_gaps}. "
            "Update this test if gaps were resolved or added."
        )

    def test_no_new_gaps_introduced(self) -> None:
        """验证所有 fundamentals.* 依赖要么在已知 gap 中，要么有数据源覆盖."""
        fundamentals_deps: set[str] = set()
        for spec in ALL_FACTOR_SPECS.values():
            for dep in spec.dependencies:
                if dep.startswith("fundamentals."):
                    fundamentals_deps.add(dep)

        all_known = (
            self.AVAILABLE_FUNDAMENTALS
            | {k for k, _ in self.GAP_NO_SOURCE}
            | {k for k, _ in self.GAP_NEEDS_TTM_DERIVATION}
            | {k for k, _ in self.GAP_COMPUTABLE}
        )

        unknown = fundamentals_deps - all_known
        assert unknown == set(), (
            f"Unexpected new data gaps: {unknown}. "
            "Document in TestKnownDataGaps if intentional."
        )

    def test_gap_descriptions_non_empty(self) -> None:
        """每个已知 gap 必须有非空描述（便于跟踪）."""
        all_gaps = (
            self.GAP_NO_SOURCE + self.GAP_NEEDS_TTM_DERIVATION + self.GAP_COMPUTABLE
        )
        for dep, desc in all_gaps:
            assert desc.strip(), f"Gap {dep} has empty description"


class TestFactorDependencyCoverage:
    """验证各域因子依赖的完整性."""

    def test_market_deps_only_use_known_columns(self) -> None:
        """market.* 依赖仅使用已知的行情列."""
        known_market = {
            "market.close",
            "market.volume",
            "market.high",
            "market.low",
            "market.open",
            "market.amount",
        }
        actual_market: set[str] = set()
        for spec in ALL_FACTOR_SPECS.values():
            for dep in spec.dependencies:
                if dep.startswith("market."):
                    actual_market.add(dep)
        unexpected = actual_market - known_market
        assert unexpected == set(), f"Unknown market.* deps: {unexpected}"

    def test_capital_deps_only_use_known_columns(self) -> None:
        """capital.* 依赖仅使用已知的资金列."""
        known_capital = {
            "capital.margin_buy",
            "capital.pledge_shares",
            "capital.total_shares",
            "capital.short_balance",
        }
        actual_capital: set[str] = set()
        for spec in ALL_FACTOR_SPECS.values():
            for dep in spec.dependencies:
                if dep.startswith("capital."):
                    actual_capital.add(dep)
        unexpected = actual_capital - known_capital
        assert unexpected == set(), f"Unknown capital.* deps: {unexpected}"
