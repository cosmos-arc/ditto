"""Runtime input provider backed by local truth-layer parquet and derived artifacts."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import polars as pl
from ditto_datahub.services.derived import DerivedArtifactReader
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from ditto_datahub.services.market_service import MarketService

from ditto_port.services.derived.materialization import InputContext

__all__ = ["RuntimeDerivedInputProvider"]

_MARKET_DATASET_COLUMNS: dict[str, frozenset[str]] = {
    "market.stock_daily": frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
        }
    ),
    "market.adj_factor": frozenset({"adj_factor"}),
    "market.stock_status": frozenset(
        {"is_suspended", "suspend_timing", "is_st", "st_type", "list_status"}
    ),
}

_ETF_DATASET_COLUMNS: dict[str, frozenset[str]] = {
    "etf.daily": frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
            "pct_change",
        }
    ),
}

# Maps market dataset refs to MarketService method names.
_MARKET_SERVICE_METHODS: dict[str, str] = {
    "market.stock_daily": "get_stock_bars",
    "market.adj_factor": "get_adj_factors",
    "market.stock_status": "get_stock_status",
}


class RuntimeDerivedInputProvider:
    """Read runtime inputs from local market truth and upstream derived artifacts."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        market_service: MarketService,
        artifact_root: Path,
        data_root: Path,
    ) -> None:
        self._artifact_reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=artifact_root,
        )
        self._market_service = market_service

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load one runtime input frame for the requested dependency set."""
        spec = context.spec
        plan = context.plan
        join_keys = [*spec.entity_keys, *spec.effective_time_keys]

        market_deps, etf_deps, derived_deps = _classify_dependencies(
            context.dependencies,
        )
        adj = _resolve_adj_type(spec)

        start = str(plan.compute_start)
        end = str(plan.compute_end)

        frames = list(
            self._load_market_frames(market_deps, start, end, join_keys),
        )
        frames.extend(self._load_etf_frames(etf_deps, start, end, join_keys, adj))
        frames.extend(self._load_derived_frames(derived_deps, start, end, join_keys))

        if not frames:
            raise NotImplementedError(
                f"Phase 3 input backend not wired for derived_id={spec.id}"
            )
        return _join_frames(frames, join_keys=join_keys)

    def _load_market_frames(
        self,
        deps: dict[str, set[str]],
        start: str,
        end: str,
        join_keys: list[str],
    ) -> list[pl.DataFrame]:
        """Load stock market data frames for classified market dependencies."""
        frames: list[pl.DataFrame] = []
        for dataset_ref, value_columns in deps.items():
            raw = self._fetch_market_data(dataset_ref, start, end)
            if raw is None:
                continue
            frames.append(
                _prepare_market_frame(
                    raw,
                    join_keys=join_keys,
                    value_columns=value_columns,
                    availability_column="trade_date",
                )
            )
        return frames

    def _fetch_market_data(
        self,
        dataset_ref: str,
        start: str,
        end: str,
    ) -> pl.DataFrame | None:
        """Fetch market data for a given dataset reference."""
        if dataset_ref == "market.stock_daily":
            return self._market_service.get_stock_bars(start=start, end=end)
        if dataset_ref == "market.adj_factor":
            return self._market_service.get_adj_factors(start=start, end=end)
        if dataset_ref == "market.stock_status":
            return self._market_service.get_stock_status(start=start, end=end)
        return None

    def _load_etf_frames(
        self,
        deps: dict[str, set[str]],
        start: str,
        end: str,
        join_keys: list[str],
        adj: str,
    ) -> list[pl.DataFrame]:
        """Load ETF data frames for classified ETF dependencies."""
        frames: list[pl.DataFrame] = []
        if "etf.daily" in deps:
            raw = self._market_service.get_etf_bars(
                start=start,
                end=end,
                adj=adj,
            )
            frames.append(
                _prepare_market_frame(
                    raw,
                    join_keys=join_keys,
                    value_columns=deps["etf.daily"],
                    availability_column="trade_date",
                )
            )
        return frames

    def _load_derived_frames(
        self,
        deps: list[str],
        start: str,
        end: str,
        join_keys: list[str],
    ) -> list[pl.DataFrame]:
        """Load upstream derived artifact frames."""
        frames: list[pl.DataFrame] = []
        for derived_id in deps:
            version = self._artifact_reader.resolve_offline_version(derived_id)
            upstream = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=version,
                start=start,
                end=end,
            )
            frames.append(
                _prepare_derived_frame(
                    upstream,
                    join_keys=join_keys,
                    column_name=derived_id,
                )
            )
        return frames


def _classify_dependencies(
    dependencies: tuple[str, ...],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    list[str],
]:
    """Separate dependencies into market, ETF, and derived namespaces."""
    market_dependencies: dict[str, set[str]] = defaultdict(set)
    etf_dependencies: dict[str, set[str]] = defaultdict(set)
    derived_dependencies: list[str] = []

    for dependency in dependencies:
        if dependency.startswith("etf."):
            dataset_ref, column = _resolve_etf_dependency(dependency)
            etf_dependencies[dataset_ref].add(column)
        elif dependency.startswith("market."):
            dataset_ref, column = _resolve_market_dependency(dependency)
            market_dependencies[dataset_ref].add(column)
        elif "." in dependency:
            derived_dependencies.append(dependency)
        else:
            raise NotImplementedError(
                f"Unsupported dependency={dependency} (market.*, etf.*, @derived only)"
            )

    return (
        dict(market_dependencies),
        dict(etf_dependencies),
        derived_dependencies,
    )


def _resolve_adj_type(spec: object) -> str:
    """Extract adj_type from spec's execution_policy, defaulting to 'none'."""
    ep = getattr(spec, "execution_policy", None)
    return ep.adj_type if ep else "none"


def _resolve_market_dependency(dependency: str) -> tuple[str, str]:
    """Resolve a 'market.*' dependency to (dataset_ref, column_name)."""
    column_name = dependency.removeprefix("market.")
    for dataset_ref, columns in _MARKET_DATASET_COLUMNS.items():
        if column_name in columns:
            return (dataset_ref, column_name)
    raise NotImplementedError(f"Unsupported market dependency={dependency}")


def _resolve_etf_dependency(dependency: str) -> tuple[str, str]:
    """Resolve an 'etf.*' dependency to (dataset_ref, column_name)."""
    column_name = dependency.removeprefix("etf.")
    for dataset_ref, columns in _ETF_DATASET_COLUMNS.items():
        if column_name in columns:
            return (dataset_ref, column_name)
    raise NotImplementedError(f"Unsupported ETF dependency={dependency}")


def _prepare_market_frame(
    frame: pl.DataFrame,
    *,
    join_keys: list[str],
    value_columns: set[str],
    availability_column: str,
) -> pl.DataFrame:
    selected_columns = [*join_keys, *sorted(value_columns)]
    existing_columns = [
        column for column in selected_columns if column in frame.columns
    ]
    prepared = frame.select(existing_columns)
    return prepared.with_columns(
        pl.col(availability_column).alias("availability_time__0")
    )


def _prepare_derived_frame(
    frame: pl.DataFrame,
    *,
    join_keys: list[str],
    column_name: str,
) -> pl.DataFrame:
    selected_columns = [*join_keys]
    if "value" in frame.columns:
        selected_columns.append("value")
    if "availability_time" in frame.columns:
        selected_columns.append("availability_time")
    prepared = frame.select(selected_columns)
    renamed: dict[str, str] = {}
    if "value" in prepared.columns:
        renamed["value"] = column_name
    if "availability_time" in prepared.columns:
        renamed["availability_time"] = "availability_time__0"
    return prepared.rename(renamed)


def _join_frames(
    frames: list[pl.DataFrame],
    *,
    join_keys: list[str],
) -> pl.DataFrame:
    base = frames[0]
    availability_columns = ["availability_time__0"]
    for index, frame in enumerate(frames[1:], start=1):
        renamed = {
            column: f"{column}__{index}"
            for column in frame.columns
            if column.startswith("availability_time__")
        }
        next_frame = frame.rename(renamed)
        availability_columns.extend(renamed.values())
        base = base.join(next_frame, on=join_keys, how="left")
    return base.with_columns(
        pl.max_horizontal(
            *(pl.col(column) for column in availability_columns),
        ).alias("availability_time"),
    ).drop(availability_columns)
