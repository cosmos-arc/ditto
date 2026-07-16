"""Idempotent bootstrap for built-in seed strategies."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol

import orjson
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.contracts import StrategyCatalogReader

__all__ = [
    "SeedBootstrapResult",
    "SeedBootstrapStatus",
    "SeedCreatePort",
    "SeedPublishPort",
    "SeedStrategyBootstrap",
]


class SeedBootstrapStatus(StrEnum):
    """Outcome for one seed definition."""

    PUBLISHED = "published"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class SeedBootstrapResult:
    """Auditable outcome for one seed definition."""

    strategy_id: str
    status: SeedBootstrapStatus
    version: int | None
    created: bool = False
    published: bool = False
    differences: tuple[str, ...] = ()


class SeedCreatePort(Protocol):
    """Narrow lifecycle port for creating a seed draft."""

    def create(
        self,
        *,
        strategy_id: str,
        name: str,
        spec_json: dict[str, object],
        tags: tuple[str, ...],
    ) -> int:
        """Create a seed draft and return its version."""
        ...


class SeedPublishPort(Protocol):
    """Narrow lifecycle port for publishing one seed version."""

    def publish(self, *, strategy_id: str, version: int) -> None:
        """Publish one existing seed version."""
        ...


def _canonical_json(value: object) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def _differences(
    *,
    existing_name: str,
    existing_spec: dict[str, object],
    existing_tags: tuple[str, ...],
    expected_name: str,
    expected_spec: dict[str, object],
    expected_tags: tuple[str, ...],
) -> tuple[str, ...]:
    fields: list[str] = []
    if existing_name != expected_name:
        fields.append("name")
    if _canonical_json(existing_spec) != _canonical_json(expected_spec):
        fields.append("spec_json")
    if existing_tags != expected_tags:
        fields.append("tags")
    return tuple(fields)


class SeedStrategyBootstrap:
    """Create and publish missing seeds while failing closed on ID conflicts."""

    def __init__(
        self,
        *,
        catalog: StrategyCatalogReader,
        create_port: SeedCreatePort,
        publish_port: SeedPublishPort,
    ) -> None:
        self._catalog = catalog
        self._create_port = create_port
        self._publish_port = publish_port

    def run(self) -> tuple[SeedBootstrapResult, ...]:
        """Bootstrap all built-in seeds in deterministic registry order."""
        results: list[SeedBootstrapResult] = []
        for strategy_id, seed in SEED_STRATEGY_SPECS.items():
            expected_spec = asdict(seed)
            existing = self._catalog.get_spec(strategy_id)
            if existing is None:
                version = self._create_port.create(
                    strategy_id=strategy_id,
                    name=seed.name,
                    spec_json=expected_spec,
                    tags=seed.tags,
                )
                self._publish_port.publish(
                    strategy_id=strategy_id,
                    version=version,
                )
                results.append(
                    SeedBootstrapResult(
                        strategy_id=strategy_id,
                        status=SeedBootstrapStatus.PUBLISHED,
                        version=version,
                        created=True,
                        published=True,
                    )
                )
                continue

            differences = _differences(
                existing_name=existing.name,
                existing_spec=existing.spec_json,
                existing_tags=existing.tags,
                expected_name=seed.name,
                expected_spec=expected_spec,
                expected_tags=seed.tags,
            )
            if differences:
                results.append(
                    SeedBootstrapResult(
                        strategy_id=strategy_id,
                        status=SeedBootstrapStatus.CONFLICT,
                        version=existing.version,
                        differences=differences,
                    )
                )
                continue

            if existing.status != "published":
                self._publish_port.publish(
                    strategy_id=strategy_id,
                    version=existing.version,
                )
                status = SeedBootstrapStatus.PUBLISHED
                published = True
            else:
                status = SeedBootstrapStatus.UNCHANGED
                published = False
            results.append(
                SeedBootstrapResult(
                    strategy_id=strategy_id,
                    status=status,
                    version=existing.version,
                    published=published,
                )
            )
        return tuple(results)
