"""Runtime input provider backed by local truth-layer parquet and derived artifacts."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import polars as pl
from ditto_datahub.services.derived import DerivedArtifactReader
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from ditto_datahub.stores.market.stock.adj import StockAdjFactorReader
from ditto_datahub.stores.market.stock.bars import StockBarsReader
from ditto_datahub.stores.market.stock.status import StockStatusReader

from ditto_port.services.derived.materialization import InputContext

__all__ = ["RuntimeDerivedInputProvider"]

_MARKET_DATASET_COLUMNS = {
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


class RuntimeDerivedInputProvider:
    """Read runtime inputs from local market truth and upstream derived artifacts."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        artifact_root: Path,
        data_root: Path,
    ) -> None:
        self._artifact_reader = DerivedArtifactReader(
            catalog_service=catalog_service,
            artifact_root=artifact_root,
        )
        self._stock_bars_reader = StockBarsReader(Path(data_root))
        self._stock_adj_reader = StockAdjFactorReader(Path(data_root))
        self._stock_status_reader = StockStatusReader(Path(data_root))

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load one runtime input frame for the requested dependency set."""
        spec = context.spec
        plan = context.plan
        dependencies = context.dependencies
        join_keys = [*spec.entity_keys, *spec.effective_time_keys]
        market_dependencies: dict[str, set[str]] = defaultdict(set)
        derived_dependencies: list[str] = []
        for dependency in dependencies:
            if dependency.startswith("market."):
                dataset_ref, column = _resolve_market_dependency(dependency)
                market_dependencies[dataset_ref].add(column)
                continue
            if "." not in dependency:
                raise NotImplementedError(
                    "RuntimeDerivedInputProvider only supports market.* "
                    + "or @derived dependencies: "
                    + f"dependency={dependency}"
                )
            derived_dependencies.append(dependency)

        frames: list[pl.DataFrame] = []
        if "market.stock_daily" in market_dependencies:
            frames.append(
                _prepare_market_frame(
                    self._stock_bars_reader.read(
                        start_date=plan.compute_start,
                        end_date=plan.compute_end,
                    ),
                    join_keys=join_keys,
                    value_columns=market_dependencies["market.stock_daily"],
                    availability_column="trade_date",
                )
            )
        if "market.adj_factor" in market_dependencies:
            frames.append(
                _prepare_market_frame(
                    self._stock_adj_reader.read(
                        start_date=plan.compute_start,
                        end_date=plan.compute_end,
                    ),
                    join_keys=join_keys,
                    value_columns=market_dependencies["market.adj_factor"],
                    availability_column="trade_date",
                )
            )
        if "market.stock_status" in market_dependencies:
            frames.append(
                _prepare_market_frame(
                    self._stock_status_reader.read(
                        start_date=plan.compute_start,
                        end_date=plan.compute_end,
                    ),
                    join_keys=join_keys,
                    value_columns=market_dependencies["market.stock_status"],
                    availability_column="trade_date",
                )
            )
        for derived_id in derived_dependencies:
            version = self._artifact_reader.resolve_offline_version(derived_id)
            upstream = self._artifact_reader.read_frame(
                derived_id=derived_id,
                version=version,
                start=plan.compute_start,
                end=plan.compute_end,
            )
            frames.append(
                _prepare_derived_frame(
                    upstream,
                    join_keys=join_keys,
                    column_name=derived_id,
                )
            )
        if not frames:
            raise NotImplementedError(
                f"Phase 3 input backend not wired for derived_id={spec.id}"
            )
        return _join_frames(frames, join_keys=join_keys)


def _resolve_market_dependency(dependency: str) -> tuple[str, str]:
    column_name = dependency.removeprefix("market.")
    for dataset_ref, columns in _MARKET_DATASET_COLUMNS.items():
        if column_name in columns:
            return (dataset_ref, column_name)
    raise NotImplementedError(
        "RuntimeDerivedInputProvider does not support market dependency "
        + f"dependency={dependency}"
    )


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
