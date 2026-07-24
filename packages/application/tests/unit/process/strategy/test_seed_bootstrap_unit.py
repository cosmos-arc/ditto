"""Seed strategy bootstrap process tests."""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

from ditto_application.builders.deserialization import deserialize_strategy_spec
from ditto_application.processes.strategy.seed_bootstrap import (
    SeedBootstrapStatus,
    SeedStrategyBootstrap,
)
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.alpha.validation import validate_spec_params
from ditto_strategy.models import StrategySpecRecord


def _bootstrap() -> tuple[SeedStrategyBootstrap, MagicMock, MagicMock, MagicMock]:
    catalog = MagicMock()
    catalog.get_active_published.return_value = None
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
    assert all(item.created for item in result)
    assert all(item.published for item in result)
    assert create_port.create.call_count == 3
    assert publish_port.publish.call_count == 3


def test_stock_selection_seed_declares_runtime_data_dependencies() -> None:
    """Seed dependency evidence must cover every dataset read by its factors."""
    spec = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]

    assert spec.required_datasets == (
        "stock_daily",
        "adj_factor",
        "balance_sheet",
        "income_statement",
    )


def test_stock_selection_seed_is_runtime_valid_after_catalog_round_trip() -> None:
    """A successfully published built-in seed must also be executable."""
    seed = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
    record = StrategySpecRecord(
        strategy_id=seed.strategy_id,
        name=seed.name,
        spec_json=asdict(seed),
        version=1,
        status="published",
        tags=seed.tags,
    )

    runtime_spec = deserialize_strategy_spec(record)

    validate_spec_params(runtime_spec)


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
    catalog.get_active_published.side_effect = existing

    result = process.run()

    assert {item.status for item in result} == {SeedBootstrapStatus.UNCHANGED}
    assert not any(item.created for item in result)
    assert not any(item.published for item in result)
    create_port.create.assert_not_called()
    publish_port.publish.assert_not_called()


def test_matching_draft_is_published_without_being_created() -> None:
    process, catalog, create_port, publish_port = _bootstrap()

    def existing(strategy_id: str, version: int | None = None) -> StrategySpecRecord:
        del version
        spec = SEED_STRATEGY_SPECS[strategy_id]
        return StrategySpecRecord(
            strategy_id=strategy_id,
            name=spec.name,
            spec_json=asdict(spec),
            version=2,
            status="draft",
            tags=spec.tags,
        )

    catalog.get_spec.side_effect = existing

    result = process.run()

    assert {item.status for item in result} == {SeedBootstrapStatus.PUBLISHED}
    assert not any(item.created for item in result)
    assert all(item.published for item in result)
    create_port.create.assert_not_called()
    assert publish_port.publish.call_count == 3


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
    assert conflict.created is False
    assert conflict.published is False
    create_port.create.assert_called()
    publish_port.publish.assert_called()
