"""#418 治理因子 spec 注册：幂等复用＋身份漂移拒绝."""

from __future__ import annotations

import pytest
from ditto_features.errors import MaterializationError
from ditto_features.factors.alpha import ALPHAS
from ditto_features.models.derived import DerivedSpecRecord
from ditto_features.services import (
    build_factor_derived_spec,
    factor_spec_hash,
    register_governed_factor,
)
from ditto_features.services.derived_catalog_service import DerivedCatalogService
from ditto_features.storage.sqlite.derived import (
    SQLiteDerivedCatalogReader,
    SQLiteDerivedCatalogWriter,
)


def _catalog_service(derived_sqlite_client) -> DerivedCatalogService:
    return DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(derived_sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(derived_sqlite_client),
    )


def test_build_factor_derived_spec_uses_governed_expression() -> None:
    spec = build_factor_derived_spec("momentum_1m")
    factor = ALPHAS["momentum_1m"]
    assert spec.expression == factor.expression == "ts_pct_change(market.close, 20)"
    assert spec.role.value == "factor"
    assert spec.materialization_profile.value == "SERIES"
    assert spec.effective_time_keys == ("trade_date",)


def test_register_creates_draft_spec_and_is_idempotent(derived_sqlite_client) -> None:
    catalog = _catalog_service(derived_sqlite_client)
    first = register_governed_factor(catalog, "momentum_1m")
    second = register_governed_factor(catalog, "momentum_1m")

    assert first.action == "registered"
    assert second.action == "already_registered"
    assert first.spec_hash == second.spec_hash
    spec_record = catalog.get_spec("momentum_1m", 1)
    assert spec_record is not None
    assert spec_record.spec_hash == first.spec_hash
    version_record = catalog.get_version("momentum_1m", 1)
    assert version_record is not None
    assert version_record.status == "draft"


def test_register_refuses_spec_hash_drift(derived_sqlite_client) -> None:
    """同 (derived_id, version) 身份漂移：拒绝，修订走新版本号."""
    catalog = _catalog_service(derived_sqlite_client)
    registered = register_governed_factor(catalog, "momentum_1m")
    original = catalog.get_spec("momentum_1m", 1)
    assert original is not None
    tampered = DerivedSpecRecord(
        derived_id=original.derived_id,
        version=original.version,
        role=original.role,
        materialization_profile=original.materialization_profile,
        spec_hash="hash:tampered",
        spec_json=original.spec_json,
        created_at=original.created_at,
    )
    catalog.save_spec(tampered)

    with pytest.raises(MaterializationError, match="spec identity drift refused"):
        register_governed_factor(catalog, "momentum_1m")

    assert registered.action == "registered"


def test_register_refuses_ungoverned_factor(derived_sqlite_client) -> None:
    catalog = _catalog_service(derived_sqlite_client)
    with pytest.raises(
        MaterializationError, match="not in governed materializable set"
    ):
        register_governed_factor(catalog, "momentum_3m")


def test_factor_spec_hash_tracks_expression_identity() -> None:
    base = build_factor_derived_spec("momentum_1m")
    revised = build_factor_derived_spec("momentum_1m")
    object.__setattr__(
        revised,
        "expression",
        "ts_pct_change(market.close, 21)",
    )
    assert factor_spec_hash(base) == factor_spec_hash(
        build_factor_derived_spec("momentum_1m")
    )
    assert factor_spec_hash(base) != factor_spec_hash(revised)
