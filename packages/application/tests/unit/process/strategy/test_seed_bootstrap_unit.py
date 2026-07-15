"""Seed strategy bootstrap process tests."""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

from ditto_application.processes.strategy.seed_bootstrap import (
    SeedBootstrapStatus,
    SeedStrategyBootstrap,
)
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.models import StrategySpecRecord


def _bootstrap() -> tuple[SeedStrategyBootstrap, MagicMock, MagicMock, MagicMock]:
    catalog = MagicMock()
    create_port = MagicMock()
    create_port.create.return_value = 1
    publish_port = MagicMock()
    process = SeedStrategyBootstrap(
        catalog=catalog,
        create_port=create_port,
        publish_port=publish_port,
    )
    return process, catalog, create_port, publish_port


def test_empty_catalog_creates_and_publishes_all_seeds() -> None:
    process, catalog, create_port, publish_port = _bootstrap()
    catalog.get_spec.return_value = None

    result = process.run()

    assert [item.strategy_id for item in result] == list(SEED_STRATEGY_SPECS)
    assert {item.status for item in result} == {SeedBootstrapStatus.PUBLISHED}
    assert create_port.create.call_count == 3
    assert publish_port.publish.call_count == 3


def test_second_run_is_unchanged() -> None:
    process, catalog, create_port, publish_port = _bootstrap()

    def existing(strategy_id: str, version: int | None = None) -> StrategySpecRecord:
        del version
        spec = SEED_STRATEGY_SPECS[strategy_id]
        return StrategySpecRecord(
            strategy_id=strategy_id,
            name=spec.name,
            spec_json=asdict(spec),
            version=1,
            status="published",
            tags=spec.tags,
        )

    catalog.get_spec.side_effect = existing

    result = process.run()

    assert {item.status for item in result} == {SeedBootstrapStatus.UNCHANGED}
    create_port.create.assert_not_called()
    publish_port.publish.assert_not_called()


def test_existing_different_seed_fails_closed_with_diff() -> None:
    process, catalog, create_port, publish_port = _bootstrap()
    seed_id = next(iter(SEED_STRATEGY_SPECS))
    catalog.get_spec.side_effect = lambda strategy_id, version=None: (
        StrategySpecRecord(
            strategy_id=strategy_id,
            name="operator strategy",
            spec_json={"template": "different"},
            version=1,
            status="published",
        )
        if strategy_id == seed_id
        else None
    )

    result = process.run()

    conflict = next(item for item in result if item.strategy_id == seed_id)
    assert conflict.status == SeedBootstrapStatus.CONFLICT
    assert conflict.differences
    create_port.create.assert_called()
    publish_port.publish.assert_called()
