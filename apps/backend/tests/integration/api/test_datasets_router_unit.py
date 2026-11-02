"""Tests for datasets coverage API router（#628 P4 限制传播）.

使用真实 DatasetCoverageQueryFacade（无状态注册表读），验证
覆盖限制经 API 可得且与数据层蒸馏真源一致。
"""

from __future__ import annotations

import pytest
from ditto_application.queries.dataset_coverage import DatasetCoverageQueryFacade
from ditto_apps.api.routes.datasets import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """创建测试客户端（真实无状态 facade）."""
    from dishka import Provider, Scope, make_async_container, provide
    from dishka.integrations.fastapi import setup_dishka

    app = FastAPI()

    class TestProvider(Provider):
        scope = Scope.REQUEST

        @provide
        def get_coverage_facade(self) -> DatasetCoverageQueryFacade:
            return DatasetCoverageQueryFacade()

    container = make_async_container(TestProvider())
    setup_dishka(container=container, app=app)
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


@pytest.mark.integration
class TestListCoverage:
    def test_returns_full_registry_with_measured_at(self, client: TestClient) -> None:
        """全量注册表 + measured_at 测量时点（非实时声明）."""
        response = client.get("/api/v1/datasets/coverage")

        assert response.status_code == 200
        body = response.json()
        entries = body["data"]
        assert len(entries) == len(DatasetCoverageQueryFacade().list())
        by_dataset = {entry["dataset"]: entry for entry in entries}
        assert by_dataset["etf_nav"]["status"] == "partial"
        assert by_dataset["etf_nav"]["measured_end"] == "2026-10-26"
        assert by_dataset["fx_daily"]["status"] == "empty"
        assert by_dataset["stock_daily"]["status"] == "ready"
        assert all(entry["measured_at"] == "2026-10-30" for entry in entries)

    def test_partial_entries_carry_gap_reasons(self, client: TestClient) -> None:
        """partial 条目携带缺口说明：空数据与不覆盖可区分（#628 验收条款）."""
        response = client.get("/api/v1/datasets/coverage")

        by_dataset = {entry["dataset"]: entry for entry in response.json()["data"]}
        assert by_dataset["etf_nav"]["gaps"]
        assert by_dataset["hk_hold"]["gaps"]
        assert by_dataset["fx_daily"]["status"] == "empty"
        assert by_dataset["fx_daily"]["gaps"]
