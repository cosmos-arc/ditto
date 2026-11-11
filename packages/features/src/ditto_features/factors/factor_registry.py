"""FactorSpec-only registry with no governed-catalog import cycle."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_features.factors.alpha import ALPHAS
from ditto_features.factors.alternative import ALTERNATIVES
from ditto_features.factors.fundamental import FUNDAMENTALS
from ditto_features.factors.growth import GROWTHS
from ditto_features.factors.liquidity import LIQUIDITIES
from ditto_features.factors.momentum import MOMENTUMS
from ditto_features.factors.primitives import PRIMITIVES
from ditto_features.factors.quality import QUALITIES
from ditto_features.factors.size import SIZES
from ditto_features.factors.spec import FactorSpec
from ditto_features.factors.technical import TECHNICALS
from ditto_features.factors.value import VALUES
from ditto_features.factors.volatility import VOLATILITIES

__all__ = [  # noqa: RUF022 -- 分组常量按合并顺序展示
    "ALL_FACTOR_SPECS",
    "FACTOR_GROUP_LABELS",
    "FACTOR_GROUPS",
]

# 分组归属的单一权威：展示层按组呈现因子目录，不再各自从合并表猜测。
# 每个因子恰好归属一个组（按定义子表）；同名 id 跨子表冲突时以合并表
# 的最终归属为准，不重复呈现。
FACTOR_GROUPS: tuple[tuple[str, Mapping[str, FactorSpec]], ...] = (
    ("primitive", PRIMITIVES),
    ("technical", TECHNICALS),
    ("fundamental", FUNDAMENTALS),
    ("alpha", ALPHAS),
    ("size", SIZES),
    ("value", VALUES),
    ("momentum", MOMENTUMS),
    ("quality", QUALITIES),
    ("volatility", VOLATILITIES),
    ("liquidity", LIQUIDITIES),
    ("growth", GROWTHS),
    ("alternative", ALTERNATIVES),
)

FACTOR_GROUP_LABELS: Mapping[str, str] = {
    "primitive": "基础行情",
    "momentum": "动量与反转",
    "technical": "技术指标",
    "fundamental": "基本面",
    "alpha": "Alpha",
    "size": "规模",
    "value": "价值",
    "quality": "质量",
    "volatility": "波动",
    "liquidity": "流动性",
    "growth": "成长",
    "alternative": "另类",
}

ALL_FACTOR_SPECS: dict[str, FactorSpec] = {
    **PRIMITIVES,
    **TECHNICALS,
    **FUNDAMENTALS,
    **ALPHAS,
    **SIZES,
    **VALUES,
    **MOMENTUMS,
    **QUALITIES,
    **VOLATILITIES,
    **LIQUIDITIES,
    **GROWTHS,
    **ALTERNATIVES,
}
