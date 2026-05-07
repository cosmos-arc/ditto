"""Quality factor definitions — profitability and earnings quality."""

from __future__ import annotations

from ditto_features.factors.spec import FactorSpec

__all__ = ["QUALITIES"]

QUALITIES: dict[str, FactorSpec] = {
    "roa": FactorSpec(
        id="roa",
        expression="fundamentals.net_income / fundamentals.total_assets",
        dependencies=("fundamentals.net_income", "fundamentals.total_assets"),
        description="Return on Assets",
    ),
    "accruals": FactorSpec(
        id="accruals",
        expression=(
            "(fundamentals.net_income - fundamentals.ocf) / fundamentals.total_assets"
        ),
        dependencies=(
            "fundamentals.net_income",
            "fundamentals.ocf",
            "fundamentals.total_assets",
        ),
        description="Accruals ratio: (NI - OCF) / total assets (lower = better)",
    ),
    "delta_roe": FactorSpec(
        id="delta_roe",
        expression="ts_delta(roe, 4)",
        dependencies=("roe",),
        description="ROE marginal change over 4 quarters",
    ),
    "roe_stability": FactorSpec(
        id="roe_stability",
        expression="-ts_std(roe, 8)",
        dependencies=("roe",),
        description="ROE stability: neg. rolling std over 8 quarters",
    ),
    "cash_ratio": FactorSpec(
        id="cash_ratio",
        expression="fundamentals.ocf / fundamentals.net_income",
        dependencies=("fundamentals.ocf", "fundamentals.net_income"),
        description="Cash earnings ratio: operating cash flow / net income",
    ),
    "gross_margin": FactorSpec(
        id="gross_margin",
        expression="(fundamentals.revenue - fundamentals.cogs) / fundamentals.revenue",
        dependencies=("fundamentals.revenue", "fundamentals.cogs"),
        description="Gross profit margin",
    ),
    "operating_leverage": FactorSpec(
        id="operating_leverage",
        expression=(
            "ts_delta(fundamentals.op_income, 4) / ts_delta(fundamentals.revenue, 4)"
        ),
        dependencies=("fundamentals.op_income", "fundamentals.revenue"),
        description="Operating leverage: op_income vs revenue quarterly change",
    ),
    "earnings_smoothness": FactorSpec(
        id="earnings_smoothness",
        expression="-ts_corr(roe, delta_roe, 8)",
        dependencies=("roe", "delta_roe"),
        description="Earnings smoothness: neg. corr of ROE level vs change",
    ),
}
