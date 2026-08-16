"""Authoring preview facade fail-closed and deterministic contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import cast

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.providers_strategy import AppStrategyQueryProvider
from ditto_application.queries.authoring_preview import AuthoringPreviewFacade
from ditto_application.queries.authoring_preview_contracts import AuthoringPreviewKind
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
    deserialize_strategy_spec,
)
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.alpha.spec_codec import (
    adapt_legacy_strategy_spec,
    canonical_spec_payload,
)
from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.models import StrategySpecRecord


def _base_record() -> StrategySpecRecord:
    seed = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
    record = StrategySpecRecord(
        strategy_id=seed.strategy_id,
        name=seed.name,
        spec_json=asdict(seed),
        version=3,
        tags=seed.tags,
    )
    return StrategySpecRecord(
        **{
            **asdict(record),
            "spec_hash": canonical_spec_hash_for_record(record),
        }
    )


def _v2_candidate() -> dict[str, object]:
    spec = adapt_legacy_strategy_spec(deserialize_strategy_spec(_base_record()))
    return {
        **deepcopy(canonical_spec_payload(spec)),
        "name": spec.name,
        "metadata": dict(spec.metadata),
        "tags": list(spec.tags),
    }


class _Catalog:
    def __init__(self, record: StrategySpecRecord | None = None) -> None:
        self.record = record or _base_record()
        self.calls: list[tuple[str, int | None]] = []

    def get_spec(
        self,
        strategy_id: str,
        version: int | None = None,
    ) -> StrategySpecRecord | None:
        self.calls.append((strategy_id, version))
        if strategy_id == self.record.strategy_id and version == self.record.version:
            return self.record
        return None

    def list_specs(self) -> list[StrategySpecRecord]:
        raise AssertionError("authoring preview must not list or resolve latest specs")

    def list_versions(self, strategy_id: str) -> list[StrategySpecRecord]:
        raise AssertionError(f"authoring preview must not list versions: {strategy_id}")

    def get_active_published(self, strategy_id: str) -> StrategySpecRecord | None:
        raise AssertionError(f"authoring preview must not read active: {strategy_id}")


def _facade(catalog: _Catalog | None = None) -> AuthoringPreviewFacade:
    return AuthoringPreviewFacade(
        catalog=cast(StrategyCatalogReader, catalog or _Catalog()),
    )


def test_application_provider_wires_authoring_preview_from_catalog_reader() -> None:
    catalog = _Catalog()

    facade = AppStrategyQueryProvider().authoring_preview_facade(
        catalog_service=cast(StrategyCatalogReader, catalog)
    )

    result = facade.create_draft(spec_json=_v2_candidate())
    assert result.valid is True
    assert result.payload.value["canonical_hash"] == catalog.record.spec_hash


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda payload: payload["pipeline"]["nodes"][1].update(
                {"node_type": "unknown.generated_node"}
            ),
            "unknown_node_descriptor",
        ),
        (
            lambda payload: payload["pipeline"]["nodes"][3]["config"].update(
                {"params": "top-k=20"}
            ),
            "invalid_node_config_type",
        ),
    ],
)
def test_draft_rejects_unknown_nodes_and_config_type_mismatches(
    mutate: object,
    reason: str,
) -> None:
    candidate = _v2_candidate()
    cast("object", mutate)(candidate)

    result = _facade().create_draft(spec_json=candidate)

    assert result.kind is AuthoringPreviewKind.DRAFT
    assert result.valid is False
    assert result.changed is False
    diagnostic = result.payload.value["diagnostics"][0]
    assert diagnostic["details"]["reason"] == reason
    assert "canonical_spec" not in result.payload.value


@pytest.mark.parametrize(
    ("expression", "error_code"),
    [
        ("ts_meanx(market.close, 20)", "E021_UNKNOWN_OPERATOR"),
        ('ts_mean(market.close, "20)', "E002_UNTERMINATED_STRING"),
        ('ts_mean(market.close, "20")', "E031_TYPE_MISMATCH"),
    ],
)
def test_compile_returns_ditto_diagnostics_for_invalid_dsl(
    expression: str,
    error_code: str,
) -> None:
    result = _facade().compile_expression(
        derived_id="author.momentum",
        version=1,
        expression=expression,
    )

    assert result.kind is AuthoringPreviewKind.COMPILE
    assert result.valid is False
    assert result.payload.value["diagnostics"][0]["code"] == error_code
    assert "compile_identity" not in result.payload.value


def test_compile_golden_is_deterministic_and_contains_compiler_identity() -> None:
    facade = _facade()

    first = facade.compile_expression(
        derived_id="author.momentum",
        version=1,
        expression="ts_mean(market.close, 20)",
    )
    second = facade.compile_expression(
        derived_id="author.momentum",
        version=1,
        expression="ts_mean(market.close, 20)",
    )

    assert first == second
    assert first.valid is True
    assert first.payload.payload_hash == second.payload.payload_hash
    assert first.payload.value["analysis"]["lookback"] == 21
    assert len(first.payload.value["compile_identity"]["cache_key"]) == 64


def test_structured_draft_preview_is_content_addressed_and_replayable() -> None:
    catalog = _Catalog()
    facade = _facade(catalog)
    candidate = _v2_candidate()

    first = facade.create_draft(spec_json=candidate)
    second = facade.create_draft(spec_json=deepcopy(candidate))

    assert first == second
    assert first.valid is True
    assert first.changed is False
    assert first.payload.value["publishable"] is False
    assert first.payload.value["canonical_hash"] == catalog.record.spec_hash
    assert first.payload.payload_hash == second.payload.payload_hash
    assert catalog.calls == []


@pytest.mark.parametrize("forbidden", ["code", "python_code", "explanation"])
def test_draft_rejects_model_smuggled_code_or_explanation(forbidden: str) -> None:
    candidate = _v2_candidate()
    candidate["metadata"] = {forbidden: "trust my generated implementation"}

    result = _facade().create_draft(spec_json=candidate)

    assert result.valid is False
    assert result.payload.value["diagnostics"][0]["code"] == (
        "AUTHORING_FORBIDDEN_FIELD"
    )
    assert result.payload.value["diagnostics"][0]["details"]["field"] == (
        f"metadata.{forbidden}"
    )


def test_validate_accepts_legacy_contract_without_mutation() -> None:
    catalog = _Catalog()

    result = _facade(catalog).validate_strategy(
        strategy_id=catalog.record.strategy_id,
        base_version=catalog.record.version,
        spec_json=deepcopy(catalog.record.spec_json),
    )

    assert result.kind is AuthoringPreviewKind.VALIDATE
    assert result.valid is True
    assert result.changed is False
    assert result.payload.value["canonical_hash"] == catalog.record.spec_hash
    assert catalog.calls == [(catalog.record.strategy_id, catalog.record.version)]


def test_validate_fails_closed_when_candidate_identity_changes() -> None:
    catalog = _Catalog()
    candidate = _v2_candidate()
    candidate["strategy_family_id"] = "smuggled-strategy"

    result = _facade(catalog).validate_strategy(
        strategy_id=catalog.record.strategy_id,
        base_version=catalog.record.version,
        spec_json=candidate,
    )

    assert result.valid is False
    assert result.changed is False
    assert result.payload.value["diagnostics"][0]["code"] == (
        "AUTHORING_IDENTITY_MISMATCH"
    )
    assert "canonical_spec" not in result.payload.value


def test_diff_is_canonical_replayable_and_reads_only_exact_base() -> None:
    catalog = _Catalog()
    candidate = _v2_candidate()
    nodes = candidate["pipeline"]["nodes"]
    selector = next(node for node in nodes if node["node_id"] == "legacy_selector")
    selector["config"]["params"]["k"] = 21
    facade = _facade(catalog)

    first = facade.diff_strategy(
        strategy_id=catalog.record.strategy_id,
        base_version=catalog.record.version,
        spec_json=candidate,
    )
    second = facade.diff_strategy(
        strategy_id=catalog.record.strategy_id,
        base_version=catalog.record.version,
        spec_json=deepcopy(candidate),
    )

    assert first == second
    assert first.kind is AuthoringPreviewKind.DIFF
    assert first.valid is True
    assert first.changed is True
    assert first.payload.value["changes"] == (
        {
            "path": "pipeline.nodes[legacy_selector].config.params.k",
            "op": "changed",
            "old_value": 20,
            "new_value": 21,
        },
    )
    assert catalog.calls == [
        (catalog.record.strategy_id, catalog.record.version),
        (catalog.record.strategy_id, catalog.record.version),
    ]


def test_exact_base_missing_or_hash_tampered_fails_closed() -> None:
    catalog = _Catalog()
    facade = _facade(catalog)
    with pytest.raises(AppQueryError, match="exact base strategy version not found"):
        facade.validate_strategy(
            strategy_id=catalog.record.strategy_id,
            base_version=99,
            spec_json=_v2_candidate(),
        )

    catalog.record = StrategySpecRecord(
        **{**asdict(catalog.record), "spec_hash": "f" * 64}
    )
    with pytest.raises(AppQueryError, match="base strategy hash mismatch"):
        facade.diff_strategy(
            strategy_id=catalog.record.strategy_id,
            base_version=catalog.record.version,
            spec_json=_v2_candidate(),
        )
