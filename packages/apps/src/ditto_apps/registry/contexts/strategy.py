"""策略上下文工厂。"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from ditto_application.processes.execution.manual_sizing import (
    AShareTradeDateResolver,
    ManualSizingContextBuilder,
)
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.processes.strategy.seed_bootstrap import SeedStrategyBootstrap
from ditto_application.queries.data_readiness import DataReadinessQueryFacade
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
    StrategyRunWriterProtocol,
)

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.bundle import StrategyBundle

_SEED_VERSION = 1
_SEED_ACTOR = "seed"
_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _utc_now_iso() -> str:
    """Stable ISO-8601 UTC timestamp for governance events."""
    return datetime.now(UTC).strftime(_UTC_FMT)


@dataclass(frozen=True)
class _SeedCreateAdapter:
    """
    Governance-backed seed draft creation port.

    Writes the immutable spec payload and a draft governance version atomically
    via :meth:`GovernanceService.create_draft`, so a seed lands as a content-
    addressed payload plus a governable version rather than a free-standing
    catalog row. ``spec_hash`` is derived from the canonical V2 form so it
    matches the backtest reproduction fingerprint.
    """

    governance: GovernanceService

    def create(
        self,
        *,
        strategy_id: str,
        name: str,
        spec_json: dict[str, object],
        tags: tuple[str, ...],
    ) -> int:
        now = _utc_now_iso()
        record = StrategySpecRecord(
            strategy_id=strategy_id,
            name=name,
            spec_json=spec_json,
            tags=tags,
            version=_SEED_VERSION,
            created_at=now,
        )
        record = replace(record, spec_hash=canonical_spec_hash_for_record(record))
        self.governance.create_draft(
            strategy_id=strategy_id,
            version=_SEED_VERSION,
            spec_record=record,
            created_at=now,
        )
        return _SEED_VERSION


@dataclass(frozen=True)
class _SeedPublishAdapter:
    """Governance-backed seed publish/activate port (idempotent)."""

    governance: GovernanceService

    def publish(self, *, strategy_id: str, version: int) -> None:
        self.governance.publish_and_activate(
            strategy_id=strategy_id,
            version=version,
            actor=_SEED_ACTOR,
            reason="seed bootstrap publish and activate",
            decided_at=_utc_now_iso(),
        )


@contextmanager
def create_strategy_bundle() -> Generator[StrategyBundle]:
    """创建策略上下文组合包（单容器）。"""
    container = make_app_container()
    try:
        catalog_service = container.get(StrategyCatalogService)
        governance = container.get(GovernanceService)
        yield StrategyBundle(
            strategy_facade=container.get(StrategyFacade),
            catalog_service=catalog_service,
            run_service=container.get(StrategyRunLifecycleStore),
            run_writer=container.get(StrategyRunWriterProtocol),
            signal_package_publisher=container.get(SignalPackagePublisher),
            sizing_context_builder=container.get(ManualSizingContextBuilder),
            trade_date_resolver=container.get(AShareTradeDateResolver),
            data_readiness_query=container.get(DataReadinessQueryFacade),
            seed_bootstrap=SeedStrategyBootstrap(
                catalog=catalog_service,
                create_port=_SeedCreateAdapter(governance),
                publish_port=_SeedPublishAdapter(governance),
            ),
        )
    finally:
        container.close()
