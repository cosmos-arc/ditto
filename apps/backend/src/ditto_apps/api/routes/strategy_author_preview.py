"""Detached governed Author preview route for Strategy Studio."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.authoring_preview import AuthoringPreviewFacade
from ditto_application.queries.authoring_preview_contracts import (
    AuthoringPreviewReadModel,
)
from fastapi import APIRouter, Path

from ditto_apps.api.errors import APIError
from ditto_apps.api.json_values import to_json_mapping, to_object_mapping
from ditto_apps.models.common import APIResponse
from ditto_apps.models.strategy import (
    StrategyAuthorOperationResponse,
    StrategyAuthorPreviewRequest,
    StrategyAuthorPreviewResponse,
    StrategyAuthorTestResponse,
)

__all__ = ["preview_strategy_author", "router"]

router = APIRouter(prefix="/strategies", tags=["strategies"])

_AUTHOR_HASH_STAGE_COUNT = 3


async def _run_blocking[**P, R](
    function: Callable[P, R], *args: P.args, **kwargs: P.kwargs
) -> R:
    return await asyncio.to_thread(function, *args, **kwargs)


def _author_operation(
    info: AuthoringPreviewReadModel,
) -> StrategyAuthorOperationResponse:
    """Map a verified Application preview without widening its authority."""
    if info.payload.value.get("publishable") is not False:
        raise APIError(
            "Author preview attempted to expose publishable output",
            status_code=500,
            error_code="AUTHOR_PREVIEW_AUTHORITY_INVALID",
        )
    return StrategyAuthorOperationResponse(
        kind=info.kind.value,
        subject_id=info.subject_id,
        subject_version=info.subject_version,
        valid=info.valid,
        changed=info.changed,
        publishable=False,
        payload_hash=info.payload.payload_hash,
        payload=to_json_mapping(info.payload.value),
        lineage=list(info.lineage),
    )


def _author_test(name: str, passed: bool, detail: str) -> StrategyAuthorTestResponse:
    return StrategyAuthorTestResponse(name=name, passed=passed, detail=detail)


@router.post(
    "/{strategy_id}/versions/{version}/author-preview",
    response_model=APIResponse[StrategyAuthorPreviewResponse],
    operation_id="strategies_preview_strategy_author",
)
@inject
async def preview_strategy_author(
    strategy_id: str,
    version: Annotated[int, Path(ge=1)],
    request: StrategyAuthorPreviewRequest,
    facade: Annotated[AuthoringPreviewFacade, FromComponent()],
) -> APIResponse[StrategyAuthorPreviewResponse]:
    """Run detached draft/compile/validate/diff stages without any mutation."""
    spec_json = to_object_mapping(request.spec_json)
    draft = await _run_blocking(facade.create_draft, spec_json=spec_json)
    compiled = tuple(
        [
            await _run_blocking(
                facade.compile_expression,
                derived_id=expression.derived_id,
                version=expression.version,
                expression=expression.expression,
            )
            for expression in request.expressions
        ]
    )
    validation = await _run_blocking(
        facade.validate_strategy,
        strategy_id=strategy_id,
        base_version=version,
        spec_json=spec_json,
    )
    diff = await _run_blocking(
        facade.diff_strategy,
        strategy_id=strategy_id,
        base_version=version,
        spec_json=spec_json,
    )
    operations = (draft, *compiled, validation, diff)
    hashes = tuple(
        value
        for item in (draft, validation, diff)
        if isinstance((value := item.payload.value.get("canonical_hash")), str)
    )
    hash_consistent = len(hashes) == _AUTHOR_HASH_STAGE_COUNT and len(set(hashes)) == 1
    non_publishable = all(
        item.payload.value.get("publishable") is False for item in operations
    )
    tests = (
        _author_test("draft_valid", draft.valid, "detached draft canonicalization"),
        _author_test(
            "expressions_compile",
            all(item.valid for item in compiled),
            f"{len(compiled)} detached expression(s)",
        ),
        _author_test("candidate_valid", validation.valid, "exact-base validation"),
        _author_test("candidate_diff", diff.valid, "exact-base canonical diff"),
        _author_test(
            "canonical_hash_consistent",
            hash_consistent,
            "draft, validate, and diff must authenticate one candidate",
        ),
        _author_test(
            "preview_non_publishable",
            non_publishable,
            "preview surface has no save, review, or publish authority",
        ),
    )
    return APIResponse(
        data=StrategyAuthorPreviewResponse(
            strategy_id=strategy_id,
            base_version=version,
            valid=all(item.passed for item in tests),
            publishable=False,
            canonical_hash=hashes[0] if hash_consistent else None,
            draft=_author_operation(draft),
            compile=[_author_operation(item) for item in compiled],
            validation=_author_operation(validation),
            diff=_author_operation(diff),
            tests=list(tests),
        )
    )
