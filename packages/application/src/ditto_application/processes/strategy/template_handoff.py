"""
Propose a strategy-version draft from one exact SelectionRun and template.

The proposal is side-effect free: it binds the persisted run identity and its
content-addressed selection policy to one of the three committed research
templates, converts what the template can faithfully express (factor weights,
top-k), and explains every source condition the template cannot represent
instead of silently dropping it or applying it to the wrong template.
Persistence happens through the existing strategy create command with the
proposed ``spec_json``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_strategy.alpha.validation import validate_spec_params
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    SelectionRun,
    SelectionRunStatus,
    StockSelectionSpec,
)
from ditto_strategy.selection.identity import canonical_selection_run_hash
from ditto_strategy.selection.policy_store import SelectionPolicyReader
from ditto_strategy.selection.store import SelectionRunReader

from ditto_application.exceptions import AppProcessError
from ditto_application.queries.strategy_templates import (
    StrategyTemplateCatalogEntry,
    StrategyTemplateCatalogQuery,
)
from ditto_application.research_case_contracts import ResearchCaseReader
from ditto_application.strategy_spec_legacy_deserialization import (
    deserialize_strategy_spec,
)

__all__ = [
    "HandoffConversion",
    "HandoffGap",
    "ProposeStrategyTemplateDraft",
    "StrategyTemplateDraftProposal",
    "StrategyTemplateHandoffRequest",
]


def _error(message: str, *, reason: str, **details: object) -> AppProcessError:
    return AppProcessError(message, details={"reason": reason, **details})


@dataclass(frozen=True, slots=True)
class StrategyTemplateHandoffRequest:
    """One template choice bound to an exact saved run."""

    selection_run_id: str
    template_id: str
    research_case_id: str | None = None
    #: 来源运行的名义池 ID；运行本体只持久化内容寻址 universe 快照，
    #: 名义池由调用方（筛选工作面）在知道时显式携带。
    universe_id: str | None = None


@dataclass(frozen=True, slots=True)
class HandoffConversion:
    """One source field the template faithfully expresses."""

    source: str
    detail: str


@dataclass(frozen=True, slots=True)
class HandoffGap:
    """One source condition the template cannot express, with its explanation."""

    source: str
    reason_code: str
    explanation: str
    detail: str


@dataclass(frozen=True, slots=True)
class StrategyTemplateDraftProposal:
    """Complete, saveable draft plus conversion evidence and frozen lineage."""

    template_id: str
    spec_json: dict[str, object]
    converted: tuple[HandoffConversion, ...]
    unconverted: tuple[HandoffGap, ...]
    lineage: dict[str, object]


def _factor_detail(policy: StockSelectionSpec | EtfSelectionSpec) -> str:
    return ", ".join(f"{item.name}x{item.weight:g}" for item in policy.factor_weights)


def _condition_detail(policy: StockSelectionSpec | EtfSelectionSpec) -> str:
    if not policy.filter_groups:
        return ""
    groups = (
        " AND ".join(item.describe() for item in group)
        for group in policy.filter_groups
    )
    return "; ".join(f"({group})" for group in groups)


class ProposeStrategyTemplateDraft:
    """Bind one exact run and template into a saveable strategy draft."""

    def __init__(
        self,
        *,
        run_reader: SelectionRunReader,
        policy_reader: SelectionPolicyReader,
        case_reader: ResearchCaseReader,
        catalog: StrategyTemplateCatalogQuery | None = None,
    ) -> None:
        self._run_reader = run_reader
        self._policy_reader = policy_reader
        self._case_reader = case_reader
        self._catalog = (
            catalog if catalog is not None else StrategyTemplateCatalogQuery()
        )

    def propose(
        self, request: StrategyTemplateHandoffRequest
    ) -> StrategyTemplateDraftProposal:
        """Build the proposal or fail closed on unusable or mismatched input."""
        if not request.selection_run_id.strip():
            raise _error(
                "selection run identity is required",
                reason="invalid_selection_run_id",
            )
        template = self._catalog.entry(request.template_id)
        if template is None:
            raise _error(
                f"unknown strategy template: {request.template_id}",
                reason="unknown_strategy_template",
                template_id=request.template_id,
                known_template_ids=[
                    entry.template_id for entry in self._catalog.list_entries()
                ],
            )
        run = self._run_reader.get(request.selection_run_id)
        if run is None:
            raise _error(
                "selection run not found",
                reason="selection_run_not_found",
                selection_run_id=request.selection_run_id,
            )
        if run.status is SelectionRunStatus.BLOCKED or not run.candidates:
            raise _error(
                "blocked SelectionRun cannot hand off to a strategy template",
                reason="selection_run_blocked",
                selection_run_id=run.run_id,
            )
        if run.asset_kind.value != template.asset_class:
            # 资产类别不匹配时明确拒绝，不把股票条件套给 ETF 模板或反之。
            raise _error(
                "template asset class does not match the selection run",
                reason="template_asset_class_mismatch",
                template_id=template.template_id,
                template_asset_class=template.asset_class,
                run_asset_kind=run.asset_kind.value,
            )
        if request.universe_id is not None and request.universe_id != template.universe:
            # 名义池已知且与模板池不同：草稿按模板池回测会静默换池，拒绝。
            raise _error(
                "template universe does not match the selection run universe",
                reason="template_universe_mismatch",
                template_id=template.template_id,
                template_universe=template.universe,
                run_universe_id=request.universe_id,
            )
        policy = self._policy_reader.policy_by_hash(run.spec_hash)
        if policy is None:
            message = (
                "the exact selection policy snapshot was never persisted; "
                "re-run the selection to hand off with conditions and weights"
            )
            raise _error(
                message,
                reason="selection_policy_snapshot_missing",
                selection_spec_hash=run.spec_hash,
                selection_run_id=run.run_id,
            )
        objective, research_case_id = self._objective(request, run)
        unavailable = [
            item.name
            for item in policy.factor_weights
            if item.name not in ALL_FACTOR_SPECS
        ]
        if unavailable:
            raise _error(
                "selection factor is no longer registered for research execution",
                reason="selection_factor_unavailable",
                factor_names=tuple(unavailable),
            )
        return self._build(
            template=template,
            run=run,
            policy=policy,
            objective=objective,
            research_case_id=research_case_id,
            universe_id=request.universe_id,
        )

    def _objective(
        self, request: StrategyTemplateHandoffRequest, run: SelectionRun
    ) -> tuple[str, str | None]:
        if request.research_case_id is None:
            return run.spec_id, None
        if not request.research_case_id.strip():
            raise _error(
                "research case identity must be non-empty when provided",
                reason="invalid_research_case_id",
            )
        case = self._case_reader.get(request.research_case_id)
        if case is None:
            raise _error(
                "research case not found",
                reason="research_case_not_found",
                research_case_id=request.research_case_id,
            )
        if case.selection_run_id != run.run_id:
            raise _error(
                "research case belongs to a different SelectionRun",
                reason="research_case_run_mismatch",
                research_case_id=request.research_case_id,
                case_selection_run_id=case.selection_run_id,
                requested_run_id=run.run_id,
            )
        return case.objective, case.case_id

    def _assert_runnable(
        self, strategy_id: str, name: str, spec_json: dict[str, object]
    ) -> None:
        """
        Prove the assembled draft deserializes and passes template limits.

        提案在这里预演保存与运行会执行的同一套校验（legacy 反序列化 + 模板
        注入的参数约束）：参数越界在建草稿之前就得到可读反馈，而不是保存后
        在回测里失败。processes 不得依赖 builders，模板 config 装配由回测
        路径的同源反序列化保证。
        """
        try:
            spec = deserialize_strategy_spec(
                StrategySpecRecord(
                    strategy_id=strategy_id,
                    name=name,
                    spec_json=spec_json,
                )
            )
            validate_spec_params(spec)
        except StrategySpecError as exc:
            raise AppProcessError(
                f"proposed template draft is not runnable: {exc}",
                details={
                    "reason": "template_draft_not_runnable",
                    **exc.details,
                },
            ) from exc

    def _build(
        self,
        *,
        template: StrategyTemplateCatalogEntry,
        run: SelectionRun,
        policy: StockSelectionSpec | EtfSelectionSpec,
        objective: str,
        research_case_id: str | None,
        universe_id: str | None,
    ) -> StrategyTemplateDraftProposal:
        name = f"研究: {objective}"
        run_digest = run.run_id.rsplit(":", 1)[-1][:8]
        strategy_id = f"handoff-{template.template_id}-{run_digest}"
        tags: list[str] = ["handoff", f"selection-spec:{policy.spec_id}"]
        if research_case_id is not None:
            tags.append(f"research-case:{research_case_id.rsplit(':', 1)[-1][:12]}")
        spec_json: dict[str, object] = {
            "strategy_id": strategy_id,
            "name": name,
            "template": template.template_id,
            "universe": template.universe,
            "asset_class": template.asset_class,
            "benchmark": template.benchmark,
            # rank 是模板原生 ScoringMethod；多因子合成发生在信号表达式层
            # （FactorBridge 加权合成 signal_value），评分阶段只做截面排名。
            "scorer": {"method": "rank", "params": {}},
            "selector": {"method": "top_k", "params": {"k": policy.top_k}},
            "execution": {
                "frequency": template.default_frequency,
                "method": "calendar",
                "default_order_type": "market",
            },
            "constraints": _template_constraints(template.template_id),
            "params": _template_params(template, policy),
            "tags": tags,
            "signal_expressions": [item.name for item in policy.factor_weights],
            "signal_weights": [item.weight for item in policy.factor_weights],
            "required_datasets": list(template.required_datasets),
        }
        self._assert_runnable(strategy_id, name, spec_json)
        constraint_names = {item["name"] for item in template.param_constraints}
        top_k_detail = f"入选数量转入选取器 top_k={policy.top_k}"
        if "max_positions" in constraint_names and "top_k" not in constraint_names:
            top_k_detail = (
                f"入选数量转入模板参数 max_positions={policy.top_k}"
                f"(选取器 top_k={policy.top_k})"
            )
        converted = (
            HandoffConversion(
                source="factor_weights",
                detail=(
                    "因子与权重转入信号表达式(运行时同一受控因子注册表编译): "
                    f"{_factor_detail(policy)}"
                ),
            ),
            HandoffConversion(source="top_k", detail=top_k_detail),
        )
        unconverted = [
            HandoffGap(
                source="filter_groups",
                reason_code="selection_filter_group_not_convertible",
                explanation=(
                    "筛选条件是决策日截面分数秩阈值, 回测模板没有对应的硬性"
                    "过滤阶段; 条件保留在来源运行证据中, 不自动套用。"
                ),
                detail=_condition_detail(policy),
            ),
            HandoffGap(
                source="min_average_turnover",
                reason_code="min_average_turnover_not_convertible",
                explanation=(
                    "最低平均成交额是入池流动性门槛; 回测按自身交易规则与费用"
                    "执行, 不复制该门槛。"
                ),
                detail=f"{policy.min_average_turnover:g} CNY",
            ),
            HandoffGap(
                source="min_listing_days",
                reason_code="min_listing_days_not_convertible",
                explanation="上市天数门槛属于筛选入池条件, 回测模板不支持。",
                detail=f"{policy.min_listing_days} days",
            ),
            HandoffGap(
                source="excluded_limit_states",
                reason_code="excluded_limit_states_not_convertible",
                explanation=(
                    "涨跌停排除在回测中由适用交易规则与状态数据决定, "
                    "不复制筛选排除集合。"
                ),
                detail=", ".join(item.value for item in policy.excluded_limit_states),
            ),
        ]
        if (
            isinstance(policy, EtfSelectionSpec)
            and policy.max_tracking_error is not None
        ):
            unconverted.append(
                HandoffGap(
                    source="max_tracking_error",
                    reason_code="max_tracking_error_not_convertible",
                    explanation="ETF 跟踪误差上限是筛选入池条件, 回测模板不支持。",
                    detail=f"{policy.max_tracking_error:g}",
                )
            )
        lineage: dict[str, object] = {
            "selection_run_id": run.run_id,
            "selection_run_hash": canonical_selection_run_hash(run),
            "selection_spec_hash": run.spec_hash,
            "asset_kind": run.asset_kind.value,
            "as_of": run.as_of,
            "knowledge_cutoff": run.knowledge_cutoff,
            "universe_snapshot_id": run.universe_snapshot_id,
            "candidate_count": len(run.candidates),
        }
        if universe_id is not None:
            lineage["universe_id"] = universe_id
        else:
            # 名义池未随请求携带：池身份无法核对，向用户明示而不是静默换池。
            unconverted.append(
                HandoffGap(
                    source="universe",
                    reason_code="universe_membership_not_transferable",
                    explanation=(
                        f"草稿适用池为模板池 {template.universe}; 来源运行的池成员"
                        "身份冻结在其 universe 快照中, 不能自动转换。回测按模板池"
                        "执行, 请确认候选与模板池的适用范围一致。"
                    ),
                    detail=run.universe_snapshot_id,
                )
            )
        if research_case_id is not None:
            lineage["research_case_id"] = research_case_id
        return StrategyTemplateDraftProposal(
            template_id=template.template_id,
            spec_json=spec_json,
            converted=converted,
            unconverted=tuple(unconverted),
            lineage=lineage,
        )


def _template_params(
    template: StrategyTemplateCatalogEntry,
    policy: StockSelectionSpec | EtfSelectionSpec,
) -> dict[str, object]:
    """
    Build template params strictly from the template's constraint names.

    草稿只携带模板声明的参数（键集 ⊆ 约束名集）：etf_trend_swing 没有
    top_k 约束, 入选数量改写其 max_positions, 避免与派生逻辑双写。
    """
    constraint_names = {item["name"] for item in template.param_constraints}
    params: dict[str, object] = {}
    if "top_k" in constraint_names:
        params["top_k"] = policy.top_k
    if "max_positions" in constraint_names:
        params["max_positions"] = policy.top_k
    return params


def _template_constraints(template_id: str) -> list[dict[str, object]]:
    """Seed-aligned risk constraints per template so a draft runs unchanged."""
    if template_id == "stock_selection":
        max_weight, max_turnover = 0.10, 0.30
    elif template_id == "etf_rotation":
        max_weight, max_turnover = 0.30, 0.50
    else:
        max_weight, max_turnover = 0.40, 0.60
    return [
        {"type": "max_weight_per_instrument", "params": {"max_weight": max_weight}},
        {"type": "max_turnover", "params": {"max_turnover": max_turnover}},
    ]
