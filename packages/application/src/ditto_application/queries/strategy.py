"""Strategy query facade — 封装 StrategyCatalogReader 只读查询."""

from __future__ import annotations

from dataclasses import replace

from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.governance.models import (
    StrategyVersion,
    StrategyVersionState,
)
from ditto_strategy.governance.protocols import (
    InvalidStrategyGovernanceEventCursor,
    StrategyGovernanceEventIntegrityError,
    StrategyGovernanceEventReader,
    StrategyGovernanceEventStrategyNotFound,
    StrategyGovernanceVersionReader,
    StrategyVersionStateReader,
)
from ditto_strategy.models import StrategySpecRecord

from ditto_application.contracts import (
    ExperimentIdResolver,
    StrategyActiveInfo,
    StrategyGovernanceEventInfo,
    StrategySpecInfo,
    StrategySpecValidationInfo,
    StrategyVersionDetailInfo,
    StrategyVersionDiffInfo,
    StrategyVersionInfo,
    to_spec_info,
)
from ditto_application.exceptions import AppBuilderError, AppQueryError
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
    canonical_spec_payload_for_record,
    diff_canonical_payloads,
)

__all__ = ["StrategyQueryFacade"]


class StrategyQueryFacade:
    """
    策略只读查询 facade.

    封装 StrategyCatalogReader，对外只暴露 App DTO。``StrategySpecInfo.status``
    由 governance version state 投影（active/draft/review/published/...）；
    未注入 state reader 时标记 ``unknown``（governance 是唯一状态源）。
    """

    def __init__(
        self,
        catalog_service: StrategyCatalogReader,
        version_state_reader: StrategyVersionStateReader | None = None,
        governance_version_reader: StrategyGovernanceVersionReader | None = None,
        experiment_resolver: ExperimentIdResolver | None = None,
        governance_event_reader: StrategyGovernanceEventReader | None = None,
    ) -> None:
        self._service = catalog_service
        self._version_state_reader = version_state_reader
        self._governance_version_reader = governance_version_reader
        self._experiment_resolver = experiment_resolver
        self._governance_event_reader = governance_event_reader

    def list_specs(self) -> list[StrategySpecInfo]:
        """列出所有策略（最新版本）."""
        return [self._to_info(r) for r in self._service.list_specs()]

    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecInfo | None:
        """获取策略详情，version=None 返回最新版本."""
        record = self._service.get_spec(strategy_id, version)
        return self._to_info(record) if record is not None else None

    def get_active_published(self, strategy_id: str) -> StrategySpecInfo | None:
        """
        获取 governance active pointer 指向的 published payload.

        生产读取（R1/EOD）的唯一入口：无 active pointer 返回 None，
        由调用方走 NO_ACTIVE_STRATEGY fail-closed。
        """
        record = self._service.get_active_published(strategy_id)
        return to_spec_info(record, status="active") if record is not None else None

    def get_version_detail(
        self,
        strategy_id: str,
        version: int,
    ) -> StrategyVersionDetailInfo | None:
        """Join one immutable canonical payload with its governance state."""
        record = self._service.get_spec(strategy_id, version)
        if record is None or self._version_state_reader is None:
            return None
        state = self._version_state_reader.get_state(strategy_id, version)
        if state is None:
            return None
        try:
            canonical_spec = canonical_spec_payload_for_record(record)
            canonical_hash = canonical_spec_hash_for_record(record)
        except (AppBuilderError, StrategySpecError, ValueError) as exc:
            raise AppQueryError(
                f"Invalid immutable strategy version payload: {strategy_id} v{version}",
                details={
                    "code": "STRATEGY_VERSION_SPEC_INVALID",
                    "strategy_id": strategy_id,
                    "version": version,
                },
            ) from exc
        if canonical_hash != record.spec_hash:
            raise AppQueryError(
                f"Immutable strategy version hash mismatch: {strategy_id} v{version}",
                details={
                    "code": "STRATEGY_VERSION_SPEC_HASH_MISMATCH",
                    "strategy_id": strategy_id,
                    "version": version,
                },
            )
        return StrategyVersionDetailInfo(
            strategy_id=record.strategy_id,
            version=record.version,
            canonical_spec=canonical_spec,
            spec_hash=record.spec_hash,
            parent_version=record.parent_version,
            state=str(state.state),
            review_outcome=str(state.review_outcome),
            created_at=record.created_at,
        )

    def list_governance_events(
        self,
        strategy_id: str,
        *,
        after_event_id: str | None,
        limit: int,
    ) -> list[StrategyGovernanceEventInfo]:
        """Project the stable merged governance stream through application DTOs."""
        if self._governance_event_reader is None:
            raise AppQueryError(
                "strategy governance event reader is not configured",
                details={"code": "STRATEGY_GOVERNANCE_READER_UNAVAILABLE"},
            )
        try:
            events = self._governance_event_reader.list_governance_events(
                strategy_id,
                after_event_id=after_event_id,
                limit=limit,
            )
        except InvalidStrategyGovernanceEventCursor as exc:
            raise AppQueryError(
                str(exc),
                details={"code": "INVALID_EVENT_CURSOR"},
            ) from exc
        except StrategyGovernanceEventStrategyNotFound as exc:
            raise AppQueryError(
                str(exc),
                details={"code": "STRATEGY_NOT_FOUND"},
            ) from exc
        except StrategyGovernanceEventIntegrityError as exc:
            raise AppQueryError(
                str(exc),
                details={"code": "STRATEGY_GOVERNANCE_EVENT_INTEGRITY_ERROR"},
            ) from exc
        return [
            StrategyGovernanceEventInfo(
                event_id=event.event_id,
                strategy_id=event.strategy_id,
                event_type=event.event_type,
                target_version=event.target_version,
                decision_or_activation_kind=event.decision_or_activation_kind,
                actor=event.actor,
                reason=event.reason,
                occurred_at=event.occurred_at,
            )
            for event in events
        ]

    def list_versions(self, strategy_id: str) -> list[StrategyVersionInfo]:
        """
        列出策略的所有 governance 版本（newest first）.

        投影 governance version + lifecycle state，不拉取 payload bytes。
        未注入 governance reader 时返回空列表（降级，不伪造状态）。
        """
        if (
            self._governance_version_reader is None
            or self._version_state_reader is None
        ):
            return []
        versions = self._governance_version_reader.list_versions(strategy_id)
        return self._project_version_infos(versions, self._version_state_reader)

    def list_reviews(self) -> list[StrategyVersionInfo]:
        """
        列出跨 strategy 所有 state=REVIEW 的版本（review queue，newest first）.

        REVIEW 状态同时覆盖「待审查」（review_outcome=PENDING）与「已批准待发布」
        （review_outcome=APPROVED，publish 前不离开 REVIEW）。当 experiment resolver
        注入时，按 spec_hash 桥接为每条补 ``experiment_id``（指向持有 review packet
        的 experiment），供前端 review queue → review-detail 导航 + evidence-gated
        publish。未注入 governance reader 时返回空列表（降级，不伪造状态）。
        """
        if (
            self._governance_version_reader is None
            or self._version_state_reader is None
        ):
            return []
        versions = self._governance_version_reader.list_versions_by_state(
            StrategyVersionState.REVIEW
        )
        infos = self._project_version_infos(versions, self._version_state_reader)
        if self._experiment_resolver is None:
            return infos
        return [
            replace(
                info,
                experiment_id=self._experiment_resolver.resolve_experiment_id_by_spec_hash(
                    info.spec_hash
                ),
            )
            for info in infos
        ]

    def validate_spec(
        self,
        strategy_id: str,
        version: int,
        spec_json: dict[str, object],
    ) -> StrategySpecValidationInfo | None:
        """
        校验 candidate ``spec_json``，返回 hash + 合法性 + 变更检测.

        candidate 非法是 pre-save 校验的正常路径，返回 ``valid=False`` + errors，
        不抛错；仅当 governance reader 未注入或 version 不存在时返回 None（route
        映射 404）。canonical hash 与 governance version 的 spec_hash 同源，故
        ``changed`` 判定可信。
        """
        if self._governance_version_reader is None:
            return None
        versions = self._governance_version_reader.list_versions(strategy_id)
        base = self._find_version(versions, version)
        if base is None:
            return None
        base_hash = base.spec_hash
        candidate_record = StrategySpecRecord(
            strategy_id=strategy_id,
            name="",
            spec_json=spec_json,
        )
        try:
            candidate_hash = canonical_spec_hash_for_record(candidate_record)
        except (AppBuilderError, StrategySpecError, ValueError) as exc:
            return StrategySpecValidationInfo(
                strategy_id=strategy_id,
                version=version,
                canonical_hash="",
                base_spec_hash=base_hash,
                changed=False,
                valid=False,
                errors=(str(exc),),
            )
        return StrategySpecValidationInfo(
            strategy_id=strategy_id,
            version=version,
            canonical_hash=candidate_hash,
            base_spec_hash=base_hash,
            changed=candidate_hash != base_hash,
            valid=True,
            errors=(),
        )

    def diff_version(
        self,
        strategy_id: str,
        version: int,
    ) -> StrategyVersionDiffInfo | None:
        """
        计算 version ``version`` 相对 parent_version 的 canonical spec 字段级 diff.

        一次 ``catalog.list_versions`` 取回该策略全部版本 record（含 spec_json/
        spec_hash/parent_version），按键定位 target/parent，避免逐版本 ``get_spec``
        往返。基于 ``canonical_spec_payload_for_record`` 做递归 diff，与 canonical
        hash 同源。target/parent 同 spec_hash 时短路返回空 diff；首版本（无 parent）
        返回空 diff；version 不存在返回 None（route 映射 404）。
        """
        records = self._service.list_versions(strategy_id)
        target = self._find_record(records, version)
        if target is None:
            return None
        target_hash = target.spec_hash
        if target.parent_version is None:
            return StrategyVersionDiffInfo(
                strategy_id=strategy_id,
                version=version,
                parent_version=None,
                base_spec_hash="",
                target_spec_hash=target_hash,
                changed=False,
                changes=(),
            )
        parent = self._find_record(records, target.parent_version)
        if parent is None:
            return None
        base_hash = parent.spec_hash
        if target_hash == base_hash:
            return StrategyVersionDiffInfo(
                strategy_id=strategy_id,
                version=version,
                parent_version=target.parent_version,
                base_spec_hash=base_hash,
                target_spec_hash=target_hash,
                changed=False,
                changes=(),
            )
        changes = diff_canonical_payloads(
            canonical_spec_payload_for_record(parent),
            canonical_spec_payload_for_record(target),
        )
        return StrategyVersionDiffInfo(
            strategy_id=strategy_id,
            version=version,
            parent_version=target.parent_version,
            base_spec_hash=base_hash,
            target_spec_hash=target_hash,
            changed=bool(changes),
            changes=changes,
        )

    @staticmethod
    def _find_version(
        versions: tuple[StrategyVersion, ...],
        version: int,
    ) -> StrategyVersion | None:
        """从 governance versions 中按 version 号查找单个版本."""
        for item in versions:
            if item.version == version:
                return item
        return None

    @staticmethod
    def _find_record(
        records: list[StrategySpecRecord],
        version: int,
    ) -> StrategySpecRecord | None:
        """从 catalog records 中按 version 号查找单个版本 record."""
        for record in records:
            if record.version == version:
                return record
        return None

    @staticmethod
    def _project_version_infos(
        versions: tuple[StrategyVersion, ...],
        state_reader: StrategyVersionStateReader,
    ) -> list[StrategyVersionInfo]:
        """Project governance versions + lifecycle state into StrategyVersionInfo."""
        infos: list[StrategyVersionInfo] = []
        for version in versions:
            state = state_reader.get_state(version.strategy_id, version.version)
            if state is None:
                continue
            infos.append(
                StrategyVersionInfo(
                    strategy_id=version.strategy_id,
                    version=version.version,
                    parent_version=version.parent_version,
                    spec_hash=version.spec_hash,
                    state=str(state.state),
                    review_outcome=str(state.review_outcome),
                    created_at=version.created_at,
                )
            )
        return infos

    def get_active(self, strategy_id: str) -> StrategyActiveInfo | None:
        """
        返回 active pointer + published payload；无 pointer/payload 返回 None.

        与 ``get_active_published`` 互补：后者只返回 payload，本方法额外暴露
        ``pointer_revision`` 供 governance UI 的乐观锁（reactivate）。
        """
        if self._governance_version_reader is None:
            return None
        pointer = self._governance_version_reader.get_active_pointer(strategy_id)
        if pointer is None:
            return None
        record = self._service.get_active_published(strategy_id)
        if record is None:
            return None
        return StrategyActiveInfo(
            strategy_id=pointer.strategy_id,
            active_version=pointer.active_version,
            pointer_revision=pointer.pointer_revision,
            spec=to_spec_info(record, status="active"),
        )

    def _to_info(self, record: StrategySpecRecord) -> StrategySpecInfo:
        return to_spec_info(record, status=self._resolve_status(record))

    def _resolve_status(self, record: StrategySpecRecord) -> str:
        if self._version_state_reader is None:
            return "unknown"
        state = self._version_state_reader.get_state(record.strategy_id, record.version)
        if state is None:
            return "unknown"
        return str(state.state)
