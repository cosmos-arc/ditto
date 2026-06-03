"""Dependency registry for derived materialization inputs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ditto_kernel.market import GRAIN_TO_TIME_KEYS, GrainId

__all__ = [
    "DependencyContract",
    "DependencyGroups",
    "DependencyRef",
    "ResolvedDependency",
    "classify_dependencies",
    "contract_for_ref",
    "dependency_contracts",
    "dependency_refs",
    "missing_contract_columns",
    "resolve_dependency",
    "resolve_etf_dependency",
    "resolve_market_dependency",
]


@dataclass(frozen=True)
class DependencyRef:
    """Stable dependency edge persisted in the derived catalog."""

    kind: str
    ref: str


@dataclass(frozen=True)
class DependencyContract:
    """Schema and time contract required to load one dependency edge."""

    ref: DependencyRef
    catalog_dataset_id: str
    catalog_namespace: str
    required_columns: tuple[str, ...]
    entity_keys: tuple[str, ...]
    time_keys: tuple[str, ...]
    availability_time_key: str
    grain: GrainId
    schema_version: str

    @property
    def required_frame_columns(self) -> tuple[str, ...]:
        """Return all input columns needed before dependency joins."""
        return _dedupe_columns(
            (
                *self.entity_keys,
                *self.time_keys,
                self.availability_time_key,
                *self.required_columns,
            )
        )


@dataclass(frozen=True)
class ResolvedDependency:
    """Registry result for one expression-analysis dependency."""

    source: str
    kind: str
    ref: str
    column: str | None

    def to_ref(self) -> DependencyRef:
        """Return the durable catalog edge for this dependency."""
        return DependencyRef(kind=self.kind, ref=self.ref)


@dataclass(frozen=True)
class DependencyGroups:
    """Runtime dependency groups keyed by upstream dataset namespace."""

    market: dict[str, frozenset[str]]
    etf: dict[str, frozenset[str]]
    derived: tuple[str, ...]


@dataclass(frozen=True)
class _DatasetContractTemplate:
    ref: str
    catalog_dataset_id: str
    catalog_namespace: str
    columns: tuple[str, ...]
    schema_version: str
    entity_keys: tuple[str, ...] = ("instrument_id",)
    grain: GrainId = "1d"
    time_keys: tuple[str, ...] = GRAIN_TO_TIME_KEYS["1d"]
    availability_time_key: str = "trade_date"

    def to_contract(self, required_columns: tuple[str, ...]) -> DependencyContract:
        return DependencyContract(
            ref=DependencyRef(kind="dataset", ref=self.ref),
            catalog_dataset_id=self.catalog_dataset_id,
            catalog_namespace=self.catalog_namespace,
            required_columns=required_columns,
            entity_keys=self.entity_keys,
            time_keys=self.time_keys,
            availability_time_key=self.availability_time_key,
            grain=self.grain,
            schema_version=self.schema_version,
        )


_MARKET_DATASET_COLUMNS: dict[str, tuple[str, ...]] = {
    "market.stock_daily": (
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
    ),
    "market.adj_factor": ("adj_factor",),
    "market.stock_status": (
        "is_suspended",
        "suspend_timing",
        "is_st",
        "st_type",
        "list_status",
    ),
}

_ETF_DATASET_COLUMNS: dict[str, tuple[str, ...]] = {
    "etf.daily": (
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "pct_change",
    ),
}

_DATASET_CONTRACTS: dict[str, _DatasetContractTemplate] = {
    "market.stock_daily": _DatasetContractTemplate(
        ref="market.stock_daily",
        catalog_dataset_id="stock_daily",
        catalog_namespace="market",
        columns=_MARKET_DATASET_COLUMNS["market.stock_daily"],
        schema_version="market.stock_daily.v1",
    ),
    "market.adj_factor": _DatasetContractTemplate(
        ref="market.adj_factor",
        catalog_dataset_id="adj_factor",
        catalog_namespace="market",
        columns=_MARKET_DATASET_COLUMNS["market.adj_factor"],
        schema_version="market.adj_factor.v1",
    ),
    "market.stock_status": _DatasetContractTemplate(
        ref="market.stock_status",
        catalog_dataset_id="stock_status",
        catalog_namespace="market",
        columns=_MARKET_DATASET_COLUMNS["market.stock_status"],
        schema_version="market.stock_status.v1",
    ),
    "etf.daily": _DatasetContractTemplate(
        ref="etf.daily",
        catalog_dataset_id="etf_daily",
        catalog_namespace="etf",
        columns=_ETF_DATASET_COLUMNS["etf.daily"],
        schema_version="etf.daily.v1",
    ),
}


def resolve_dependency(dependency: str) -> ResolvedDependency | None:
    """Resolve one analysis dependency to its durable and runtime metadata."""
    if dependency.startswith("market."):
        ref, column = resolve_market_dependency(dependency)
        return ResolvedDependency(
            source=dependency,
            kind="dataset",
            ref=ref,
            column=column,
        )
    if dependency.startswith("etf."):
        ref, column = resolve_etf_dependency(dependency)
        return ResolvedDependency(
            source=dependency,
            kind="dataset",
            ref=ref,
            column=column,
        )
    if "." in dependency:
        return ResolvedDependency(
            source=dependency,
            kind="derived",
            ref=dependency,
            column=None,
        )
    return None


def resolve_market_dependency(dependency: str) -> tuple[str, str]:
    """Resolve a ``market.*`` dependency to ``(dataset_ref, column)``."""
    column_name = dependency.removeprefix("market.")
    for dataset_ref, columns in _MARKET_DATASET_COLUMNS.items():
        if column_name in columns:
            return (dataset_ref, column_name)
    raise NotImplementedError(f"Unsupported market dependency={dependency}")


def resolve_etf_dependency(dependency: str) -> tuple[str, str]:
    """Resolve an ``etf.*`` dependency to ``(dataset_ref, column)``."""
    column_name = dependency.removeprefix("etf.")
    for dataset_ref, columns in _ETF_DATASET_COLUMNS.items():
        if column_name in columns:
            return (dataset_ref, column_name)
    raise NotImplementedError(f"Unsupported ETF dependency={dependency}")


def dependency_refs(
    dependencies: tuple[str, ...],
) -> tuple[DependencyRef, ...]:
    """Return deduped persistent dependency refs in first-seen order."""
    refs: list[DependencyRef] = []
    seen: set[DependencyRef] = set()
    for dependency in dependencies:
        resolved = resolve_dependency(dependency)
        if resolved is None:
            continue
        ref = resolved.to_ref()
        if ref in seen:
            continue
        refs.append(ref)
        seen.add(ref)
    return tuple(refs)


def contract_for_ref(ref: DependencyRef) -> DependencyContract | None:
    """Return the full registered contract for a dataset dependency ref."""
    if ref.kind != "dataset":
        return None
    template = _DATASET_CONTRACTS.get(ref.ref)
    if template is None:
        return None
    return template.to_contract(template.columns)


def dependency_contracts(
    dependencies: tuple[str, ...],
) -> tuple[DependencyContract, ...]:
    """Return dataset contracts limited to the requested dependency columns."""
    requested_columns_by_ref: dict[DependencyRef, list[str]] = {}
    for dependency in dependencies:
        resolved = resolve_dependency(dependency)
        if resolved is None or resolved.kind != "dataset" or resolved.column is None:
            continue
        ref = resolved.to_ref()
        columns = requested_columns_by_ref.setdefault(ref, [])
        if resolved.column not in columns:
            columns.append(resolved.column)

    contracts: list[DependencyContract] = []
    for ref, columns in requested_columns_by_ref.items():
        template = _DATASET_CONTRACTS.get(ref.ref)
        if template is not None:
            contracts.append(template.to_contract(tuple(columns)))
    return tuple(contracts)


def missing_contract_columns(
    contract: DependencyContract,
    available_columns: tuple[str, ...],
) -> tuple[str, ...]:
    """Return required contract columns absent from an available schema."""
    available = set(available_columns)
    return tuple(
        column for column in contract.required_frame_columns if column not in available
    )


def classify_dependencies(
    dependencies: tuple[str, ...],
) -> DependencyGroups:
    """Group dependencies for runtime input loading."""
    market_dependencies: dict[str, set[str]] = defaultdict(set)
    etf_dependencies: dict[str, set[str]] = defaultdict(set)
    derived_dependencies: list[str] = []

    for dependency in dependencies:
        resolved = resolve_dependency(dependency)
        if resolved is None:
            raise NotImplementedError(
                f"Unsupported dependency={dependency} (market.*, etf.*, @derived only)"
            )
        if resolved.kind == "derived":
            derived_dependencies.append(resolved.ref)
            continue
        if resolved.ref.startswith("market."):
            if resolved.column is None:
                raise NotImplementedError(f"Unsupported dependency={dependency}")
            market_dependencies[resolved.ref].add(resolved.column)
            continue
        if resolved.ref.startswith("etf."):
            if resolved.column is None:
                raise NotImplementedError(f"Unsupported dependency={dependency}")
            etf_dependencies[resolved.ref].add(resolved.column)
            continue
        raise NotImplementedError(f"Unsupported dependency={dependency}")

    return DependencyGroups(
        market={
            dataset_ref: frozenset(columns)
            for dataset_ref, columns in market_dependencies.items()
        },
        etf={
            dataset_ref: frozenset(columns)
            for dataset_ref, columns in etf_dependencies.items()
        },
        derived=tuple(derived_dependencies),
    )


def _dedupe_columns(columns: tuple[str, ...]) -> tuple[str, ...]:
    """Dedupe columns while preserving semantic order."""
    deduped: list[str] = []
    seen: set[str] = set()
    for column in columns:
        if column in seen:
            continue
        deduped.append(column)
        seen.add(column)
    return tuple(deduped)
