"""Operator registry metadata for derived expressions."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches

__all__ = [
    "P0_OPERATOR_SPECS",
    "P0_OPERATOR_VERSIONS",
    "OperatorSpec",
    "suggest_operator_names",
]


@dataclass(frozen=True)
class OperatorSpec:
    """Stable operator metadata used by validation and codegen."""

    name: str
    version: str
    min_args: int
    max_args: int
    int_literal_positions: tuple[int, ...] = ()

    def accepts_arity(self, argument_count: int) -> bool:
        """Return whether the given arity is valid for this operator."""
        return self.min_args <= argument_count <= self.max_args


def _operator(
    name: str,
    *,
    min_args: int,
    max_args: int,
    int_literal_positions: tuple[int, ...] = (),
) -> OperatorSpec:
    return OperatorSpec(
        name=name,
        version="1.0.0",
        min_args=min_args,
        max_args=max_args,
        int_literal_positions=int_literal_positions,
    )


P0_OPERATOR_SPECS: dict[str, OperatorSpec] = {
    "ts_mean": _operator("ts_mean", min_args=2, max_args=2, int_literal_positions=(1,)),
    "ts_sum": _operator("ts_sum", min_args=2, max_args=2, int_literal_positions=(1,)),
    "ts_std": _operator("ts_std", min_args=2, max_args=2, int_literal_positions=(1,)),
    "ts_var": _operator("ts_var", min_args=2, max_args=2, int_literal_positions=(1,)),
    "ts_max": _operator("ts_max", min_args=2, max_args=2, int_literal_positions=(1,)),
    "ts_min": _operator("ts_min", min_args=2, max_args=2, int_literal_positions=(1,)),
    "ts_count": _operator(
        "ts_count",
        min_args=2,
        max_args=2,
        int_literal_positions=(1,),
    ),
    "ts_median": _operator(
        "ts_median",
        min_args=2,
        max_args=2,
        int_literal_positions=(1,),
    ),
    "ts_delay": _operator(
        "ts_delay",
        min_args=2,
        max_args=2,
        int_literal_positions=(1,),
    ),
    "ts_delta": _operator(
        "ts_delta",
        min_args=2,
        max_args=2,
        int_literal_positions=(1,),
    ),
    "ts_pct_change": _operator(
        "ts_pct_change",
        min_args=2,
        max_args=2,
        int_literal_positions=(1,),
    ),
    "ts_rank": _operator(
        "ts_rank",
        min_args=2,
        max_args=2,
        int_literal_positions=(1,),
    ),
    "ts_argmax": _operator(
        "ts_argmax",
        min_args=2,
        max_args=2,
        int_literal_positions=(1,),
    ),
    "ts_argmin": _operator(
        "ts_argmin",
        min_args=2,
        max_args=2,
        int_literal_positions=(1,),
    ),
    "ts_corr": _operator(
        "ts_corr",
        min_args=3,
        max_args=3,
        int_literal_positions=(2,),
    ),
    "ts_cov": _operator(
        "ts_cov",
        min_args=3,
        max_args=3,
        int_literal_positions=(2,),
    ),
    "ts_ema": _operator("ts_ema", min_args=2, max_args=2, int_literal_positions=(1,)),
    "ts_decay_linear": _operator(
        "ts_decay_linear",
        min_args=2,
        max_args=2,
        int_literal_positions=(1,),
    ),
    "cs_rank": _operator("cs_rank", min_args=1, max_args=1),
    "cs_scale": _operator("cs_scale", min_args=1, max_args=1),
    "cs_zscore": _operator("cs_zscore", min_args=1, max_args=1),
    "cs_demean": _operator("cs_demean", min_args=1, max_args=1),
    "cs_winsorize": _operator(
        "cs_winsorize",
        min_args=1,
        max_args=4,
        int_literal_positions=(1, 2, 3),
    ),
    "group_rank": _operator("group_rank", min_args=2, max_args=2),
    "group_zscore": _operator("group_zscore", min_args=2, max_args=2),
    "abs": _operator("abs", min_args=1, max_args=1),
    "log": _operator("log", min_args=1, max_args=1),
    "log10": _operator("log10", min_args=1, max_args=1),
    "log2": _operator("log2", min_args=1, max_args=1),
    "floor": _operator("floor", min_args=1, max_args=1),
    "ceil": _operator("ceil", min_args=1, max_args=1),
    "exp": _operator("exp", min_args=1, max_args=1),
    "sqrt": _operator("sqrt", min_args=1, max_args=1),
    "sign": _operator("sign", min_args=1, max_args=1),
    "power": _operator("power", min_args=2, max_args=2),
    "max2": _operator("max2", min_args=2, max_args=2),
    "min2": _operator("min2", min_args=2, max_args=2),
    "round": _operator("round", min_args=2, max_args=2, int_literal_positions=(1,)),
    "clip": _operator("clip", min_args=3, max_args=3),
    "if_else": _operator("if_else", min_args=3, max_args=3),
    "coalesce": _operator("coalesce", min_args=2, max_args=10),
}

P0_OPERATOR_VERSIONS: dict[str, str] = {
    name: spec.version for name, spec in P0_OPERATOR_SPECS.items()
}


def suggest_operator_names(name: str, limit: int = 3) -> tuple[str, ...]:
    """Return close operator-name matches for diagnostics."""
    return tuple(get_close_matches(name, P0_OPERATOR_SPECS.keys(), n=limit, cutoff=0.4))
