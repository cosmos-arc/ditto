"""Validation tests for immutable dataset product contracts."""

from dataclasses import replace

import pytest
from ditto_data.catalog.dataset_spec import resolve_dataset_spec

pytestmark = pytest.mark.unit


def test_dataset_spec_rejects_blank_required_identity() -> None:
    spec = resolve_dataset_spec("stock_daily")

    with pytest.raises(ValueError, match="product contract dataset_id"):
        replace(spec, dataset_id="")


def test_dataset_spec_rejects_empty_or_duplicate_key_contracts() -> None:
    spec = resolve_dataset_spec("stock_daily")

    with pytest.raises(ValueError, match="product contract primary_key"):
        replace(spec, primary_key=())


def test_dataset_spec_rejects_whitespace_in_contract_items() -> None:
    spec = resolve_dataset_spec("stock_daily")

    with pytest.raises(ValueError, match="product contract primary_key"):
        replace(spec, primary_key=("instrument_id", " trade_date"))


def test_dataset_spec_requires_an_operations_runbook() -> None:
    spec = resolve_dataset_spec("stock_daily")

    with pytest.raises(ValueError, match="product contract runbook"):
        replace(spec, runbook="docs/architecture/stock-daily.md")


def test_dataset_spec_rejects_an_unversioned_schema_contract() -> None:
    spec = resolve_dataset_spec("stock_daily")

    with pytest.raises(ValueError, match="product contract schema_version"):
        replace(spec, schema_version="market.stock_daily.latest")


def test_hard_scope_dataset_spec_requires_both_coverage_targets() -> None:
    spec = resolve_dataset_spec("stock_daily")

    with pytest.raises(
        ValueError,
        match="Hard-scope product requires coverage targets",
    ):
        replace(spec, certified_target_from=None)
