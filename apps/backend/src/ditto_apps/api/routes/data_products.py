"""R2 data-products workbench read API."""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.data_products import DataProductsQueryFacade
from fastapi import APIRouter, Query

from ditto_apps.api.errors import NotFoundError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.data_products import (
    DataProductCoverageResponse,
    DataProductEvidenceResponse,
    DataProductLicenseResponse,
    DataProductQualityResponse,
    DataProductRunResponse,
    DataProductViewResponse,
    to_data_product_coverage,
    to_data_product_evidence,
    to_data_product_license,
    to_data_product_quality,
    to_data_product_run,
    to_data_product_view,
)

router = APIRouter(prefix="/data-products", tags=["data-products"])

Profile = Annotated[
    str,
    Query(
        min_length=1,
        max_length=64,
        description="Certification consumer profile",
    ),
]


@router.get(
    "",
    response_model=APIResponse[list[DataProductViewResponse]],
    operation_id="data_products_list_data_products",
)
@inject
async def list_data_products(
    facade: Annotated[DataProductsQueryFacade, FromComponent()],
    profile: Profile = "research_daily",
) -> APIResponse[list[DataProductViewResponse]]:
    """List the 22 independent R2 dataset specs and active reports."""
    rows = await asyncio.to_thread(facade.list_products, profile=profile)
    return APIResponse(data=[to_data_product_view(row) for row in rows])


@router.get(
    "/{dataset_id}/coverage",
    response_model=APIResponse[DataProductCoverageResponse],
    operation_id="data_products_get_data_product_coverage",
)
@inject
async def get_data_product_coverage(
    dataset_id: str,
    facade: Annotated[DataProductsQueryFacade, FromComponent()],
    profile: Profile = "research_daily",
) -> APIResponse[DataProductCoverageResponse]:
    """Return frozen raw/complete/certified coverage and current gaps."""
    value = await asyncio.to_thread(
        facade.coverage_for_product,
        dataset_id,
        profile=profile,
    )
    if value is None:
        raise NotFoundError(f"No certification report for data product: {dataset_id}")
    return APIResponse(data=to_data_product_coverage(value))


@router.get(
    "/{dataset_id}/quality",
    response_model=APIResponse[DataProductQualityResponse],
    operation_id="data_products_get_data_product_quality",
)
@inject
async def get_data_product_quality(
    dataset_id: str,
    facade: Annotated[DataProductsQueryFacade, FromComponent()],
    profile: Profile = "research_daily",
) -> APIResponse[DataProductQualityResponse]:
    """Return DQ, PIT replay, freshness, recovery, and consumer checks."""
    value = await asyncio.to_thread(
        facade.quality_for_product,
        dataset_id,
        profile=profile,
    )
    if value is None:
        raise NotFoundError(f"No certification report for data product: {dataset_id}")
    return APIResponse(data=to_data_product_quality(value))


@router.get(
    "/{dataset_id}/runs",
    response_model=APIResponse[list[DataProductRunResponse]],
    operation_id="data_products_list_data_product_runs",
)
@inject
async def list_data_product_runs(
    dataset_id: str,
    facade: Annotated[DataProductsQueryFacade, FromComponent()],
    profile: Profile = "research_daily",
) -> APIResponse[list[DataProductRunResponse]]:
    """Return immutable certification generations and review status."""
    values = await asyncio.to_thread(
        facade.runs_for_product,
        dataset_id,
        profile=profile,
    )
    return APIResponse(data=[to_data_product_run(value) for value in values])


@router.get(
    "/{dataset_id}/evidence",
    response_model=APIResponse[DataProductEvidenceResponse],
    operation_id="data_products_get_data_product_evidence",
)
@inject
async def get_data_product_evidence(
    dataset_id: str,
    facade: Annotated[DataProductsQueryFacade, FromComponent()],
    profile: Profile = "research_daily",
) -> APIResponse[DataProductEvidenceResponse]:
    """Return provider, schema, snapshot, fallback, and override evidence."""
    value = await asyncio.to_thread(
        facade.evidence_for_product,
        dataset_id,
        profile=profile,
    )
    if value is None:
        raise NotFoundError(f"No certification report for data product: {dataset_id}")
    return APIResponse(data=to_data_product_evidence(value))


@router.get(
    "/{dataset_id}/license",
    response_model=APIResponse[DataProductLicenseResponse],
    operation_id="data_products_get_data_product_license",
)
@inject
async def get_data_product_license(
    dataset_id: str,
    facade: Annotated[DataProductsQueryFacade, FromComponent()],
    profile: Profile = "research_daily",
) -> APIResponse[DataProductLicenseResponse]:
    """Return reviewed license records bound to the latest report."""
    value = await asyncio.to_thread(
        facade.license_for_product,
        dataset_id,
        profile=profile,
    )
    if value is None:
        raise NotFoundError(f"No certification report for data product: {dataset_id}")
    return APIResponse(data=to_data_product_license(value))
