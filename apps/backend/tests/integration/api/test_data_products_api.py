"""Integration contract for the R2 data-products workbench API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.queries.data_products import (
    DataProductCheckView,
    DataProductCoverageView,
    DataProductEvidenceView,
    DataProductLicenseView,
    DataProductQualityView,
    DataProductRunView,
    DataProductsQueryFacade,
    DataProductView,
)
from ditto_application.queries.data_specimen import DataSpecimenQuery
from ditto_apps.api.errors import APIError
from ditto_apps.api.routes.data_products import router
from ditto_apps.middleware import api_error_handler
from ditto_data.catalog.specimen import DataSpecimen, SpecimenSource
from ditto_data.catalog.specimen_store import SQLiteSpecimenStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def facade() -> MagicMock:
    """Return a facade with one complete product projection."""
    mock = MagicMock(spec=DataProductsQueryFacade)
    check = DataProductCheckView(
        name="row_count",
        evidence_uri="evidence://dq/stock_daily/row-count",
        passed=True,
    )
    mock.list_products.return_value = (
        DataProductView(
            dataset_id="stock_daily",
            r2_scope="hard",
            maturity="stable",
            schedule="trade_daily",
            owner="market-data",
            schema_version="market.stock_daily.v1",
            frequency="trading_daily",
            timezone="Asia/Shanghai",
            currency="CNY",
            raw_target_from="1990-12-19",
            certified_target_from="2005-01-04",
            active_certification_report_id="report-1",
        ),
    )
    mock.coverage_for_product.return_value = DataProductCoverageView(
        dataset_id="stock_daily",
        profile="research_daily",
        raw_from=date(1990, 12, 19),
        complete_from=date(2005, 1, 4),
        certified_from=date(2005, 1, 4),
        expected_partitions=5_000,
        actual_partitions=5_000,
        gaps=(),
        unapproved_gaps=(),
    )
    mock.quality_for_product.return_value = DataProductQualityView(
        dataset_id="stock_daily",
        profile="research_daily",
        report_id="report-1",
        dq_rule_version="r2-v1",
        dq_results=(check,),
        pit_replay_results=(check,),
        freshness_results=(check,),
        recovery_results=(check,),
        consumer_results=(check,),
    )
    mock.runs_for_product.return_value = (
        DataProductRunView(
            dataset_id="stock_daily",
            profile="research_daily",
            report_id="report-1",
            generated_at=datetime(2026, 7, 18, tzinfo=UTC),
            content_hash="sha256:abc",
            status="approved",
            reviewed_by="data-owner",
            reviewed_at=datetime(2026, 7, 18, 1, tzinfo=UTC),
            revocation_reason=None,
        ),
    )
    mock.evidence_for_product.return_value = DataProductEvidenceView(
        dataset_id="stock_daily",
        profile="research_daily",
        report_id="report-1",
        content_hash="sha256:abc",
        source_ids=("tushare",),
        schema_versions=("stock-daily-v1",),
        snapshot_ids=("snapshot-1",),
        fallback_history=("tushare",),
        override_history=(),
    )
    mock.license_for_product.return_value = DataProductLicenseView(
        dataset_id="stock_daily",
        profile="research_daily",
        report_id="report-1",
        license_record_ids=("license-1",),
    )
    return mock


@pytest.fixture
def app(facade: MagicMock) -> FastAPI:
    """Create a test app with the data-products facade injected."""

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def data_products_query_facade(self) -> DataProductsQueryFacade:
            return facade

    test_app = FastAPI()
    setup_dishka(container=make_async_container(TestProvider()), app=test_app)
    test_app.include_router(router, prefix="/api/v1")
    test_app.add_exception_handler(APIError, api_error_handler)
    return test_app


@pytest.mark.integration
def test_all_data_product_read_models_are_exposed(app: FastAPI) -> None:
    """Expose overview, coverage, quality, runs, evidence, and license facts."""
    with TestClient(app) as client:
        overview = client.get(
            "/api/v1/data-products",
            params={"profile": "research_daily"},
        )
        coverage = client.get(
            "/api/v1/data-products/stock_daily/coverage",
            params={"profile": "research_daily"},
        )
        quality = client.get(
            "/api/v1/data-products/stock_daily/quality",
            params={"profile": "research_daily"},
        )
        runs = client.get(
            "/api/v1/data-products/stock_daily/runs",
            params={"profile": "research_daily"},
        )
        evidence = client.get(
            "/api/v1/data-products/stock_daily/evidence",
            params={"profile": "research_daily"},
        )
        license_response = client.get(
            "/api/v1/data-products/stock_daily/license",
            params={"profile": "research_daily"},
        )

    responses = (overview, coverage, quality, runs, evidence, license_response)
    assert all(response.status_code == 200 for response in responses)
    assert overview.json()["data"][0]["dataset_id"] == "stock_daily"
    assert coverage.json()["data"]["expected_partitions"] == 5_000
    assert quality.json()["data"]["pit_replay_results"][0]["passed"] is True
    assert runs.json()["data"][0]["status"] == "approved"
    assert evidence.json()["data"]["snapshot_ids"] == ["snapshot-1"]
    assert license_response.json()["data"]["license_record_ids"] == ["license-1"]


@pytest.mark.integration
def test_openapi_contains_complete_data_product_schemas(app: FastAPI) -> None:
    """Keep generated frontend types complete and operation IDs stable."""
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/data-products" in paths
    assert "/api/v1/data-products/{dataset_id}/coverage" in paths
    assert "/api/v1/data-products/{dataset_id}/quality" in paths
    assert "/api/v1/data-products/{dataset_id}/runs" in paths
    assert "/api/v1/data-products/{dataset_id}/evidence" in paths
    assert "/api/v1/data-products/{dataset_id}/license" in paths
    component_names = schema["components"]["schemas"]
    for model_name in (
        "DataProductViewResponse",
        "DataProductCoverageResponse",
        "DataProductQualityResponse",
        "DataProductRunResponse",
        "DataProductEvidenceResponse",
        "DataProductLicenseResponse",
    ):
        assert model_name in component_names


@pytest.mark.integration
def test_missing_product_report_returns_404(
    app: FastAPI,
    facade: MagicMock,
) -> None:
    """Do not manufacture empty coverage when no immutable report exists."""
    facade.coverage_for_product.return_value = None
    with TestClient(app) as client:
        response = client.get("/api/v1/data-products/unknown/coverage")
    assert response.status_code == 404


@pytest.mark.integration
def test_specimens_expose_all_five_categories_with_explicit_gaps(
    tmp_path: Path,
) -> None:
    """The specimen endpoint keeps missing categories explicitly unverified."""
    from ditto_platform.foundation import SQLiteClient, SQLitePool

    pool = SQLitePool(str(tmp_path / "catalog.sqlite"))
    client = SQLiteClient(pool)
    try:
        SQLiteSpecimenStore(client).append_specimen(
            DataSpecimen(
                category="cross_border_etf",
                dataset_id="etf_nav",
                anchor="513100.SH",
                sources=(SpecimenSource(source="tushare"),),
                gaps=("REAL_SAMPLE_NOT_COLLECTED",),
                procurement=(),
            )
        )
        query = DataSpecimenQuery(
            specimens=SQLiteSpecimenStore(client),
            snapshots=MagicMock(),
            licenses=MagicMock(),
        )
    finally:
        pool.close_all()

    class SpecimenProvider(Provider):
        scope = Scope.APP

        @provide
        def data_specimen_query(self) -> DataSpecimenQuery:
            return query

    specimen_app = FastAPI()
    setup_dishka(container=make_async_container(SpecimenProvider()), app=specimen_app)
    specimen_app.include_router(router, prefix="/api/v1")
    specimen_app.add_exception_handler(APIError, api_error_handler)

    with TestClient(specimen_app) as test_client:
        response = test_client.get("/api/v1/data-products/specimens")

    assert response.status_code == 200
    categories = response.json()["data"]
    assert [item["category"] for item in categories] == [
        "financial_restatement",
        "delisted_security",
        "index_rebalance",
        "dividend_etf",
        "cross_border_etf",
    ]
    cross_border = categories[-1]
    assert cross_border["collected"] is True
    assert cross_border["latest"]["verification_status"] == "unverified"
    assert cross_border["unresolved_gaps"] == ["REAL_SAMPLE_NOT_COLLECTED"]
    for item in categories[:-1]:
        assert item["collected"] is False
        assert item["latest"] is None
        assert item["unresolved_gaps"] == ["SPECIMEN_NOT_COLLECTED"]
