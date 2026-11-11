"""Cross-plane orchestration for industry rotation and security selection."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationInputBundle,
    IndustryRotationSnapshot,
)
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.industry_rotation.store import IndustryRotationWriter
from ditto_strategy.selection.contracts import SelectionInputBundle, SelectionRun
from ditto_strategy.selection.pipeline import SelectionPipeline
from ditto_strategy.selection.policy_store import SelectionPolicyWriter
from ditto_strategy.selection.store import SelectionRunWriter

from ditto_application.exceptions import AppProcessError

__all__ = [
    "RunIndustryAndSecuritySelection",
    "RunIndustryAndSecuritySelectionReceipt",
    "RunIndustryAndSecuritySelectionRequest",
]


@dataclass(frozen=True, slots=True)
class RunIndustryAndSecuritySelectionRequest:
    """Prepared strategy-owned inputs adapted by the application boundary."""

    rotation_input: IndustryRotationInputBundle
    selection_input: SelectionInputBundle


@dataclass(frozen=True, slots=True)
class RunIndustryAndSecuritySelectionReceipt:
    """Exact rotation and saved selection artifacts from one orchestration."""

    industry_rotation: IndustryRotationSnapshot
    selection_run: SelectionRun


class RunIndustryAndSecuritySelection:
    """Bind exact rotation evidence into selection before durable save."""

    def __init__(
        self,
        *,
        rotation_service: IndustryRotationService,
        selection_pipeline: SelectionPipeline,
        rotation_writer: IndustryRotationWriter,
        run_writer: SelectionRunWriter,
        policy_writer: SelectionPolicyWriter,
    ) -> None:
        self._rotation_service = rotation_service
        self._selection_pipeline = selection_pipeline
        self._rotation_writer = rotation_writer
        self._run_writer = run_writer
        self._policy_writer = policy_writer

    def execute(
        self,
        request: RunIndustryAndSecuritySelectionRequest,
    ) -> RunIndustryAndSecuritySelectionReceipt:
        """Run both stages after enforcing one cross-plane temporal identity."""
        rotation_input = request.rotation_input
        selection_input = request.selection_input
        rotation_times = (
            rotation_input.as_of,
            rotation_input.knowledge_cutoff,
            rotation_input.publication_cutoff,
        )
        selection_times = (
            selection_input.as_of,
            selection_input.knowledge_cutoff,
            selection_input.publication_cutoff,
        )
        if rotation_times != selection_times:
            raise AppProcessError(
                "industry and security selection temporal identity drift",
                details={"reason": "selection_temporal_identity_drift"},
            )
        rotation = self._rotation_service.run(rotation_input)
        declared_rotation_id = selection_input.industry_rotation_snapshot_id
        if (
            declared_rotation_id is not None
            and declared_rotation_id != rotation.snapshot_id
        ):
            raise AppProcessError(
                "selection input references a stale rotation snapshot",
                details={
                    "reason": "selection_rotation_snapshot_drift",
                    "declared_snapshot_id": declared_rotation_id,
                    "computed_snapshot_id": rotation.snapshot_id,
                },
            )
        bound_selection_input = replace(
            selection_input,
            industry_rotation_snapshot_id=rotation.snapshot_id,
        )
        selection_run = self._selection_pipeline.run(bound_selection_input)
        self._rotation_writer.save_rotation(rotation)
        # 条件快照与固定运行同身份落库（spec_hash 内容寻址、重放 no-op）：
        # 之后的模板交接可以按运行的精确策略读回权重与条件，不依赖创建页面。
        self._policy_writer.save_policy(selection_input.spec)
        self._run_writer.save(selection_run)
        return RunIndustryAndSecuritySelectionReceipt(
            industry_rotation=rotation,
            selection_run=selection_run,
        )
