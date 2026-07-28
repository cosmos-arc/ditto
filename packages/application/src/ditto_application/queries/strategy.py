"""Strategy query facade — 封装 StrategyCatalogReader 只读查询."""

from __future__ import annotations

from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.governance.models import (
    StrategyVersion,
    StrategyVersionState,
)
from ditto_strategy.governance.protocols import (
    StrategyGovernanceVersionReader,
    StrategyVersionStateReader,
)
from ditto_strategy.models import StrategySpecRecord

from ditto_application.contracts import (
    StrategyActiveInfo,
    StrategySpecInfo,
    StrategyVersionInfo,
    to_spec_info,
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
    ) -> None:
        self._service = catalog_service
        self._version_state_reader = version_state_reader
        self._governance_version_reader = governance_version_reader

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

        聚合 governance review 状态版本投影为 review queue；不拉取 payload
        bytes，不携带 experiment_id（governance 层不持有，experiment 关联键
        spec_hash 的跨域桥接留 T20 前端接线）。未注入 governance reader 时
        返回空列表（降级，不伪造状态）。
        """
        if (
            self._governance_version_reader is None
            or self._version_state_reader is None
        ):
            return []
        versions = self._governance_version_reader.list_versions_by_state(
            StrategyVersionState.REVIEW
        )
        return self._project_version_infos(versions, self._version_state_reader)

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
