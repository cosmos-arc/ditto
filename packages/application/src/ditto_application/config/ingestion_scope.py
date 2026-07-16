"""Resolve a strategy's required datasets to a deterministic ingestion scope."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ditto_data.models import Dataset

from ditto_application.config.queries import INGESTION_SPECS
from ditto_application.config.specs import TaskTier
from ditto_application.exceptions import AppConfigurationError

__all__ = ["IngestionScope", "resolve_ingestion_scope"]


@dataclass(frozen=True)
class IngestionScope:
    """Dependency-closed daily datasets in executable tier order."""

    t0_datasets: tuple[Dataset, ...]
    t1_levels: tuple[tuple[Dataset, ...], ...]

    @property
    def datasets(self) -> tuple[Dataset, ...]:
        """Return every selected dataset in execution order."""
        return (
            *self.t0_datasets,
            *(dataset for level in self.t1_levels for dataset in level),
        )


def resolve_ingestion_scope(required_datasets: Sequence[str]) -> IngestionScope:
    """Resolve the transitive catalog dependency closure or fail closed."""
    if not required_datasets:
        raise AppConfigurationError(
            "ingestion scope requires at least one required dataset"
        )

    requested = tuple(_registered_dataset(value) for value in required_datasets)
    selected: set[Dataset] = set()
    visiting: set[Dataset] = set()

    def include(dataset: Dataset) -> None:
        if dataset in selected:
            return
        if dataset in visiting:
            raise AppConfigurationError(
                f"cyclic ingestion dependency detected at dataset={dataset.value}"
            )
        config = INGESTION_SPECS.get(dataset)
        if config is None:
            raise AppConfigurationError(
                f"dataset is not registered for ingestion: {dataset.value}"
            )
        visiting.add(dataset)
        for dependency in config.depends_on:
            include(dependency)
        visiting.remove(dataset)
        selected.add(dataset)

    for dataset in requested:
        include(dataset)

    ordered = tuple(dataset for dataset in INGESTION_SPECS if dataset in selected)
    t0_datasets = tuple(
        dataset
        for dataset in ordered
        if INGESTION_SPECS[dataset].tier is TaskTier.T0_META
    )
    t1_datasets = tuple(
        dataset
        for dataset in ordered
        if INGESTION_SPECS[dataset].tier is TaskTier.T1_INCREMENTAL
    )
    supported = {*t0_datasets, *t1_datasets}
    unsupported = [dataset.value for dataset in ordered if dataset not in supported]
    if unsupported:
        raise AppConfigurationError(
            "required datasets use unsupported daily ingestion tiers: "
            + ", ".join(unsupported)
        )
    return IngestionScope(
        t0_datasets=t0_datasets,
        t1_levels=_dependency_levels(t1_datasets, completed=set(t0_datasets)),
    )


def _registered_dataset(value: str) -> Dataset:
    try:
        dataset = Dataset(value)
    except ValueError as exc:
        raise AppConfigurationError(f"unknown required dataset: {value}") from exc
    if dataset not in INGESTION_SPECS:
        raise AppConfigurationError(f"dataset is not registered for ingestion: {value}")
    return dataset


def _dependency_levels(
    datasets: tuple[Dataset, ...],
    *,
    completed: set[Dataset],
) -> tuple[tuple[Dataset, ...], ...]:
    levels: list[tuple[Dataset, ...]] = []
    remaining: list[Dataset] = list(datasets)
    while remaining:
        level_members: list[Dataset] = []
        for dataset in remaining:
            dependencies: list[Dataset] = INGESTION_SPECS[dataset].depends_on
            if all(dependency in completed for dependency in dependencies):
                level_members.append(dataset)
        level = tuple(level_members)
        if not level:
            blocked = ", ".join(dataset.value for dataset in remaining)
            raise AppConfigurationError(
                f"unresolvable ingestion dependency closure: {blocked}"
            )
        levels.append(level)
        completed.update(level)
        remaining = [dataset for dataset in remaining if dataset not in level]
    return tuple(levels)
