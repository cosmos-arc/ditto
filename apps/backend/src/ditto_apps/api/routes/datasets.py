"""
数据集覆盖限制 API 路由（#628 P4 限制传播）.

maturity: experimental
"""

from __future__ import annotations

from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.dataset_coverage import DatasetCoverageQueryFacade
from fastapi import APIRouter

from ditto_apps.models.common import APIResponse, DataCoverageInfo

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get(
    "/coverage",
    response_model=APIResponse[list[DataCoverageInfo]],
    operation_id="datasets_list_coverage",
)
@inject
async def list_coverage(
    facade: Annotated[DatasetCoverageQueryFacade, FromComponent()],
) -> APIResponse[list[DataCoverageInfo]]:
    """
    列出全部数据集覆盖限制（latest_available 注册表读，测量时点快照）.

    来源为 #622 覆盖合同的运行时蒸馏（docs/data/coverage-contract.yaml），
    measured_at 为测量时点而非实时状态；消费方（API/图表/导出）据此区分
    「正常空」与「不覆盖」，受限研究不包装为严格 PIT。状态词表：
    ready=预期范围完整且当前 / partial=起点末端味道品种有缺 / empty=本地零行。
    """
    return APIResponse(
        data=[DataCoverageInfo.from_view(limit) for limit in facade.list()]
    )
