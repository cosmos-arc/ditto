"""策略 API 模型."""

from __future__ import annotations

from typing import Annotated, Literal

from ditto_platform.foundation.json_types import JsonValue
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

type NonBlankStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class CreateStrategyRequest(BaseModel):
    """创建策略请求."""

    strategy_id: str = Field(description="策略 ID")
    name: str = Field(description="策略名称")
    spec_json: dict[str, JsonValue] = Field(description="策略定义 JSON")
    tags: list[str] = Field(default_factory=list, description="标签")

    model_config = ConfigDict(strict=True, extra="ignore")


class UpdateStrategyRequest(BaseModel):
    """更新策略请求."""

    name: str = Field(description="策略名称")
    spec_json: dict[str, JsonValue] = Field(description="策略定义 JSON")
    tags: list[str] = Field(default_factory=list, description="标签")
    version: int | None = Field(default=None, description="版本号(乐观锁)")

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyResponse(BaseModel):
    """策略响应."""

    strategy_id: str
    name: str
    spec_json: dict[str, JsonValue]
    version: int
    status: str
    created_at: str = ""
    tags: list[str] = []

    model_config = ConfigDict(strict=True, extra="ignore")


# ---------------------------------------------------------------------------
# Strategy governance (R3) — review/publish/reactivate control plane
# ---------------------------------------------------------------------------


class GovernanceDecisionRequest(BaseModel):
    """Shared actor + reason body for one governance state-machine decision."""

    actor: str = Field(description="决策执行者")
    reason: str = Field(description="决策原因")

    model_config = ConfigDict(strict=True, extra="ignore")


class SubmitReviewRequest(GovernanceDecisionRequest):
    """Evidence-bound request to move one immutable draft into review."""

    bundle_hash: str = Field(min_length=1, description="持久化 review packet hash")


class ReactivateStrategyRequest(GovernanceDecisionRequest):
    """Reactivate one published version with an optimistic pointer CAS guard."""

    reason: NonBlankStr = Field(description="重新激活原因")
    confirmation: str = Field(
        min_length=1,
        description="与目标版本及 pointer revision 精确绑定的确认语句",
    )
    impact_summary: NonBlankStr = Field(description="当前版本切换到目标版本的影响摘要")
    expected_pointer_revision: int = Field(
        ge=0, description="最后读到的 active pointer revision (optimistic CAS)"
    )


class StrategyVersionResponse(BaseModel):
    """One immutable governance version (list-versions view, no payload bytes)."""

    strategy_id: str
    version: int
    parent_version: int | None
    spec_hash: str
    state: str
    review_outcome: str
    created_at: str
    experiment_id: str | None = None

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyVersionDetailResponse(BaseModel):
    """One immutable canonical strategy payload and governance state."""

    strategy_id: str
    version: int
    canonical_spec: dict[str, JsonValue]
    spec_hash: str
    parent_version: int | None
    state: str
    review_outcome: str
    created_at: str

    model_config = ConfigDict(strict=True, extra="forbid")


class StrategyGovernanceEventResponse(BaseModel):
    """Exact append-only decision or activation event projection."""

    event_id: str
    strategy_id: str
    event_type: str
    target_version: int
    decision_or_activation_kind: str
    actor: str
    reason: str
    occurred_at: str

    model_config = ConfigDict(strict=True, extra="forbid")


class StrategyVersionStateResponse(BaseModel):
    """Lifecycle projection returned after one governance state-machine decision."""

    strategy_id: str
    version: int
    state: str
    review_outcome: str

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyActivePointerResponse(BaseModel):
    """Active pointer returned after a reactivate decision."""

    strategy_id: str
    active_version: int
    pointer_revision: int

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyActiveResponse(BaseModel):
    """Active pointer joined with its published payload (get-active view)."""

    strategy_id: str
    active_version: int
    pointer_revision: int
    spec: StrategyResponse

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategySpecValidateRequest(BaseModel):
    """Pre-save candidate spec validation request (Strategy Studio 编辑校验)."""

    spec_json: dict[str, JsonValue] = Field(description="candidate 策略定义 JSON")

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategySpecValidationResponse(BaseModel):
    """Canonical hash + validity + change-detection result for a candidate spec."""

    strategy_id: str
    version: int
    canonical_hash: str
    base_spec_hash: str
    changed: bool
    valid: bool
    errors: list[str] = []

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyAuthorExpressionRequest(BaseModel):
    """One detached DSL expression included in an Author workbench preview."""

    derived_id: NonBlankStr
    version: int = Field(ge=1)
    expression: NonBlankStr

    model_config = ConfigDict(strict=True, extra="forbid")


class StrategyAuthorPreviewRequest(BaseModel):
    """Detached candidate sent through every safe Author preview stage."""

    spec_json: dict[str, JsonValue]
    expressions: list[StrategyAuthorExpressionRequest] = Field(
        default_factory=list,
        max_length=64,
    )

    model_config = ConfigDict(strict=True, extra="forbid")


class StrategyAuthorOperationResponse(BaseModel):
    """One content-addressed, non-publishable Author preview result."""

    kind: Literal["draft", "compile", "validate", "diff"]
    subject_id: str
    subject_version: str
    valid: bool
    changed: bool
    publishable: Literal[False] = False
    payload_hash: str
    payload: dict[str, JsonValue]
    lineage: list[str]

    model_config = ConfigDict(strict=True, extra="forbid")


class StrategyAuthorTestResponse(BaseModel):
    """One deterministic host assertion over the four preview stages."""

    name: str
    passed: bool
    detail: str

    model_config = ConfigDict(strict=True, extra="forbid")


class StrategyAuthorPreviewResponse(BaseModel):
    """Aggregate Strategy Studio workbench response with no mutation authority."""

    strategy_id: str
    base_version: int
    valid: bool
    publishable: Literal[False] = False
    canonical_hash: str | None
    draft: StrategyAuthorOperationResponse
    compile: list[StrategyAuthorOperationResponse]
    validation: StrategyAuthorOperationResponse
    diff: StrategyAuthorOperationResponse
    tests: list[StrategyAuthorTestResponse]

    model_config = ConfigDict(strict=True, extra="forbid")


class SpecChangeResponse(BaseModel):
    """One field-level change between two canonical spec payloads."""

    path: str
    op: str
    old: JsonValue = None
    new: JsonValue = None

    model_config = ConfigDict(strict=True, extra="ignore")


class StrategyVersionDiffResponse(BaseModel):
    """Field-level canonical spec diff of one version against its parent."""

    strategy_id: str
    version: int
    parent_version: int | None
    base_spec_hash: str
    target_spec_hash: str
    changed: bool
    changes: list[SpecChangeResponse] = []

    model_config = ConfigDict(strict=True, extra="ignore")


__all__ = [
    "CreateStrategyRequest",
    "GovernanceDecisionRequest",
    "ReactivateStrategyRequest",
    "SpecChangeResponse",
    "StrategyActivePointerResponse",
    "StrategyActiveResponse",
    "StrategyAuthorExpressionRequest",
    "StrategyAuthorOperationResponse",
    "StrategyAuthorPreviewRequest",
    "StrategyAuthorPreviewResponse",
    "StrategyAuthorTestResponse",
    "StrategyGovernanceEventResponse",
    "StrategyResponse",
    "StrategySpecValidateRequest",
    "StrategySpecValidationResponse",
    "StrategyVersionDetailResponse",
    "StrategyVersionDiffResponse",
    "StrategyVersionResponse",
    "StrategyVersionStateResponse",
    "SubmitReviewRequest",
    "UpdateStrategyRequest",
]


class PublishStrategyVersionRequest(BaseModel):
    """Body for one evidence-gated strategy version publish."""

    model_config = ConfigDict(frozen=True)

    bundle_hash: str
    actor: str
    reason: str
