"""Strategy Studio Author preview exposes all detached compiler stages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from ditto_application.queries.authoring_preview import AuthoringPreviewFacade
from ditto_application.queries.authoring_preview_contracts import (
    AuthoringPreviewKind,
    AuthoringPreviewReadModel,
)
from ditto_application.queries.evidence_contracts import EvidencePayloadReadModel
from ditto_apps.api.routes.strategy_author_preview import preview_strategy_author
from ditto_apps.models.common import APIResponse
from ditto_apps.models.strategy import (
    StrategyAuthorExpressionRequest,
    StrategyAuthorPreviewRequest,
    StrategyAuthorPreviewResponse,
)


def _unwrap(function: Callable[..., Any]) -> Callable[..., Any]:
    return cast(Callable[..., Any], getattr(function, "__dishka_orig_func__", function))


def _preview(
    kind: AuthoringPreviewKind,
    *,
    valid: bool = True,
    canonical_hash: str | None = "a" * 64,
) -> AuthoringPreviewReadModel:
    payload: dict[str, object] = {
        "operation": kind.value,
        "valid": valid,
        "changed": kind is AuthoringPreviewKind.DIFF,
        "publishable": False,
        "diagnostics": () if valid else ({"code": "INVALID"},),
    }
    if kind is not AuthoringPreviewKind.COMPILE and canonical_hash is not None:
        payload["canonical_hash"] = canonical_hash
    sealed = EvidencePayloadReadModel.seal(schema_version=1, value=payload)
    return AuthoringPreviewReadModel(
        kind=kind,
        subject_id="strategy-1",
        subject_version="3",
        valid=valid,
        changed=kind is AuthoringPreviewKind.DIFF,
        payload=sealed,
        lineage=(f"author-preview:sha256:{sealed.payload_hash}",),
    )


@pytest.mark.asyncio
async def test_author_preview_runs_draft_compile_validate_diff_and_tests() -> None:
    facade = MagicMock(spec=AuthoringPreviewFacade)
    facade.create_draft.return_value = _preview(AuthoringPreviewKind.DRAFT)
    facade.compile_expression.return_value = _preview(
        AuthoringPreviewKind.COMPILE,
        canonical_hash=None,
    )
    facade.validate_strategy.return_value = _preview(AuthoringPreviewKind.VALIDATE)
    facade.diff_strategy.return_value = _preview(AuthoringPreviewKind.DIFF)
    route = cast(Callable[..., Any], _unwrap(preview_strategy_author))
    request = StrategyAuthorPreviewRequest(
        spec_json={"strategy_family_id": "strategy-1", "schema_version": 2},
        expressions=[
            StrategyAuthorExpressionRequest(
                derived_id="momentum_1m",
                version=1,
                expression="close / lag(close, 20) - 1",
            )
        ],
    )

    response = cast(
        APIResponse[StrategyAuthorPreviewResponse],
        await route(
            strategy_id="strategy-1",
            version=3,
            request=request,
            facade=facade,
        ),
    )

    assert response.data.valid is True
    assert response.data.publishable is False
    assert response.data.canonical_hash == "a" * 64
    assert response.data.draft.kind == "draft"
    assert response.data.compile[0].kind == "compile"
    assert response.data.validation.kind == "validate"
    assert response.data.diff.kind == "diff"
    assert {item.name for item in response.data.tests} == {
        "draft_valid",
        "expressions_compile",
        "candidate_valid",
        "candidate_diff",
        "canonical_hash_consistent",
        "preview_non_publishable",
    }
    assert all(item.passed for item in response.data.tests)
    facade.create_draft.assert_called_once_with(spec_json=dict(request.spec_json))
    facade.compile_expression.assert_called_once_with(
        derived_id="momentum_1m",
        version=1,
        expression="close / lag(close, 20) - 1",
    )
    facade.validate_strategy.assert_called_once_with(
        strategy_id="strategy-1",
        base_version=3,
        spec_json=dict(request.spec_json),
    )
    facade.diff_strategy.assert_called_once_with(
        strategy_id="strategy-1",
        base_version=3,
        spec_json=dict(request.spec_json),
    )


@pytest.mark.asyncio
async def test_author_preview_fails_closed_on_hash_conflict_without_mutation() -> None:
    facade = MagicMock(spec=AuthoringPreviewFacade)
    facade.create_draft.return_value = _preview(AuthoringPreviewKind.DRAFT)
    facade.validate_strategy.return_value = _preview(
        AuthoringPreviewKind.VALIDATE,
        canonical_hash="b" * 64,
    )
    facade.diff_strategy.return_value = _preview(AuthoringPreviewKind.DIFF)
    route = cast(Callable[..., Any], _unwrap(preview_strategy_author))

    response = cast(
        APIResponse[StrategyAuthorPreviewResponse],
        await route(
            strategy_id="strategy-1",
            version=3,
            request=StrategyAuthorPreviewRequest(spec_json={"schema_version": 2}),
            facade=facade,
        ),
    )

    assert response.data.valid is False
    assert response.data.canonical_hash is None
    consistency = next(
        item for item in response.data.tests if item.name == "canonical_hash_consistent"
    )
    assert consistency.passed is False
    assert response.data.publishable is False
