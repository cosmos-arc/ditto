"""
Research strategy template catalog for template-first strategy authoring.

The catalog is the single server-side statement of the three research
templates this product commits to (stock multi-factor selection, ETF
rotation, ETF trend). Entry defaults mirror the seeded runnable specs so a
draft created from a template entry deserializes and runs through the same
legacy template factories the backtest executes.
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_strategy.alpha.specs import ParamConstraint
from ditto_strategy.alpha.templates import (
    get_etf_rotation_param_constraints,
    get_etf_trend_swing_param_constraints,
)
from ditto_strategy.alpha.templates import (
    get_param_constraints as get_stock_selection_param_constraints,
)

__all__ = [
    "StrategyTemplateCatalogEntry",
    "StrategyTemplateCatalogQuery",
]


def _constraint_payload(value: ParamConstraint) -> dict[str, object]:
    return {
        "name": value.name,
        "dtype": value.dtype,
        "min_value": value.min_value,
        "max_value": value.max_value,
        "step": value.step,
        "allowed_values": list(value.allowed_values),
    }


@dataclass(frozen=True, slots=True)
class StrategyTemplateCatalogEntry:
    """One choosable research template with runnable defaults."""

    template_id: str
    display_name: str
    asset_class: str
    description: str
    universe: str
    benchmark: str
    default_frequency: str
    required_datasets: tuple[str, ...]
    param_constraints: tuple[dict[str, object], ...]


_STOCK_SELECTION = StrategyTemplateCatalogEntry(
    template_id="stock_selection",
    display_name="股票多因子选股",
    asset_class="stock",
    description=("按因子权重合成分数选股并定期调仓; 适合验证候选池与多因子选择思路。"),
    universe="csi_a_share",
    benchmark="000300.SH",
    default_frequency="M",
    required_datasets=(
        "stock_daily",
        "adj_factor",
        "balance_sheet",
        "income_statement",
    ),
    param_constraints=tuple(
        _constraint_payload(item) for item in get_stock_selection_param_constraints()
    ),
)

_ETF_ROTATION = StrategyTemplateCatalogEntry(
    template_id="etf_rotation",
    display_name="ETF 轮动",
    asset_class="etf",
    description="按动量合成分数在 ETF 池内轮动持有前几名; 适合验证 ETF 相对强弱思路。",
    universe="csi_etf_broad",
    benchmark="000300.SH",
    default_frequency="M",
    required_datasets=("etf_daily",),
    param_constraints=tuple(
        _constraint_payload(item) for item in get_etf_rotation_param_constraints()
    ),
)

_ETF_TREND_SWING = StrategyTemplateCatalogEntry(
    template_id="etf_trend_swing",
    display_name="ETF 趋势",
    asset_class="etf",
    description="按趋势信号进出 ETF 并以移动止损保护利润; 适合验证 ETF 趋势跟随思路。",
    universe="csi_etf_broad",
    benchmark="000300.SH",
    default_frequency="W",
    required_datasets=("etf_daily",),
    param_constraints=tuple(
        _constraint_payload(item) for item in get_etf_trend_swing_param_constraints()
    ),
)

_TEMPLATE_ENTRIES: tuple[StrategyTemplateCatalogEntry, ...] = (
    _STOCK_SELECTION,
    _ETF_ROTATION,
    _ETF_TREND_SWING,
)

_TEMPLATE_BY_ID: dict[str, StrategyTemplateCatalogEntry] = {
    entry.template_id: entry for entry in _TEMPLATE_ENTRIES
}


class StrategyTemplateCatalogQuery:
    """List the research templates strategy authoring may start from."""

    def list_entries(self) -> tuple[StrategyTemplateCatalogEntry, ...]:
        """Return every committed research template, ordered for display."""
        return _TEMPLATE_ENTRIES

    def entry(self, template_id: str) -> StrategyTemplateCatalogEntry | None:
        """Return one exact template entry or None when not committed."""
        return _TEMPLATE_BY_ID.get(template_id)
