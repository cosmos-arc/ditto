"""发布后有限刷新：复用摄取完成证据，不把空响应或迟到补齐算作准时。"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import polars as pl
from ditto_data.catalog.snapshot_completion import completed_snapshots
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_data.ingestion.published_refresh_evidence import (
    PublishedRefreshEvidenceStore,
)

from ditto_application.catalog_freshness import (
    completed_covering_snapshot,
    covering_snapshots,
    has_pending_date,
    observed_at,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.source_selection import (
    IngestionCoordinatorLike,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.provider_snapshot import ProviderSnapshotQuery

SHANGHAI = ZoneInfo("Asia/Shanghai")


class PublishedRefreshProcess:
    """既有摄取入口的发布后检查与截止留证。"""

    def __init__(
        self,
        *,
        coordinator: IngestionCoordinatorLike,
        calendar: MetadataQueryFacade,
        snapshots: ProviderSnapshotReader,
        lifecycle: PartitionLifecycleReader,
        audit: ProviderSnapshotQuery,
        evidence: PublishedRefreshEvidenceStore,
        fred_series: tuple[str, ...],
    ) -> None:
        self._coordinator = coordinator
        self._calendar = calendar
        self._snapshots = snapshots
        self._lifecycle = lifecycle
        self._audit = audit
        self._evidence = evidence
        self._fred_series = fred_series

    def margin(self, *, scheduled_day: str, finalize: bool) -> dict[str, object]:
        """只刷新上个交易日两融；09:15 后不再发起请求，完整留存每次观察。"""
        now = datetime.now(SHANGHAI)
        if now.tzinfo is None:
            raise AppProcessError("published refresh needs an aware execution time")
        now = now.astimezone(SHANGHAI)
        day = datetime.fromisoformat(scheduled_day).date()
        if not self._calendar.is_trading_day(day.isoformat()):
            return {"status": "not_trading_day", "scheduled_day": scheduled_day}
        days = self._calendar.list_trading_days("2014-01-01", day.isoformat())
        previous = [item for item in days if item < day.isoformat()]
        if not previous:
            raise AppProcessError("missing previous trading session")
        target = previous[-1]
        release = datetime.combine(day, time(8, 30), SHANGHAI)
        deadline = datetime.combine(day, time(9, 15), SHANGHAI)
        if now < release:
            raise AppProcessError("margin refresh cannot run before publication window")
        if finalize and now < deadline:
            raise AppProcessError("final margin evidence cannot precede the deadline")
        status = self._margin_evidence(target, release, deadline)
        attempted = False
        error: str | None = None
        if not status["ready"] and not finalize and now < deadline:
            attempted = True
            try:
                result = self._coordinator.ingest_date(
                    "margin_trading", target, force=True
                )
                if result.status == "failed":
                    error = result.error or result.message
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            status = self._margin_evidence(target, release, deadline)
        now = datetime.now(SHANGHAI).astimezone(SHANGHAI)
        report: dict[str, object] = {
            "dataset": "margin_trading",
            "source": "tushare",
            "trade_date": target,
            "scheduled_day": scheduled_day,
            "recorded_at": now.isoformat(),
            "deadline": deadline.isoformat(),
            "final": finalize,
            "attempted": attempted,
            "error": error,
            **status,
        }
        # 每次观察不可覆盖，尤其不能用迟到成功覆盖截止失败。
        self._evidence.record("margin", report)
        if finalize and not status["ready"]:
            raise AppProcessError(
                f"margin {target}: not ready by {deadline.isoformat()}"
            )
        return report

    def _margin_evidence(
        self, target: str, release: datetime, deadline: datetime
    ) -> dict[str, object]:
        if has_pending_date(
            self._lifecycle,
            dataset="margin_trading",
            source="tushare",
            trade_date=target,
        ):
            return {
                "ready": False,
                "status": "incomplete_revision",
                "snapshot_id": None,
            }
        candidates = completed_snapshots(
            covering_snapshots(
                self._snapshots,
                dataset="margin_trading",
                source="tushare",
                trade_date=target,
            ),
            self._lifecycle,
        )
        # 同 payload 的迟到重复观察不能抹掉准时观察；不同 payload 也不能
        # 以最新迟到版本覆盖已完成的准时证据。
        on_time_candidates = [
            item
            for item in candidates
            if any(
                release <= moment <= deadline
                for moment in (item.observations or (item.created_at,))
            )
        ]
        snapshot = max(
            on_time_candidates or candidates,
            key=lambda item: (observed_at(item), item.snapshot_id),
            default=None,
        )
        if snapshot is None or snapshot.row_count == 0:
            return {
                "ready": False,
                "status": "pending_publication",
                "snapshot_id": None,
            }
        contents = self._audit.read_for_audit(snapshot.snapshot_id)
        frame = contents.frame.filter(pl.col("trade_date").cast(pl.String) == target)
        exchanges = set(frame["source_ticker"].str.split(".").list.last().to_list())
        checkpoints = self._lifecycle.list_complete(
            dataset_id="margin_trading", source="tushare"
        )
        completed_at = [
            item.updated_at
            for item in checkpoints
            if item.complete_evidence_id == snapshot.snapshot_id
        ]
        on_time = (
            any(
                release <= moment <= deadline
                for moment in (snapshot.observations or (snapshot.created_at,))
            )
            and bool(completed_at)
            and min(completed_at) <= deadline
        )
        ready = on_time and {"SH", "SZ"}.issubset(exchanges)
        return {
            "ready": ready,
            "status": "complete" if ready else "pending_or_late",
            "snapshot_id": snapshot.snapshot_id,
            "rows": frame.height,
            "exchanges": sorted(exchanges),
            "observed_at": observed_at(snapshot).isoformat(),
            "on_time": on_time,
        }

    def fred(self, *, day: str) -> dict[str, object]:
        """FRED 已配置系列的日常有界回看；返回真实源载荷逐系列末端。"""
        if not self._fred_series:
            raise AppProcessError("FRED refresh requires configured series")
        result = self._coordinator.ingest_date("macro_indicators", day, force=True)
        if result.status == "failed":
            raise AppProcessError(result.error or result.message)
        snapshot = completed_covering_snapshot(
            self._snapshots,
            self._lifecycle,
            dataset="macro_indicators",
            source="fred",
            trade_date=day,
        )
        if snapshot is None or snapshot.row_count == 0:
            raise AppProcessError(
                "FRED refresh has no nonempty completed source evidence"
            )
        frame = self._audit.read_for_audit(snapshot.snapshot_id).frame
        latest = (
            frame.group_by("indicator_code", "frequency")
            .agg(pl.col("date").max().cast(pl.String).alias("latest_date"))
            .sort("indicator_code")
            .to_dicts()
        )
        missing = sorted(
            set(self._fred_series) - set(frame["indicator_code"].to_list())
        )
        report: dict[str, object] = {
            "recorded_at": datetime.now(SHANGHAI).isoformat(),
            "day": day,
            "source": "fred",
            "snapshot_id": snapshot.snapshot_id,
            "rows": frame.height,
            "latest": latest,
            "missing_series": missing,
        }
        self._evidence.record("fred", report)
        if missing:
            raise AppProcessError(f"FRED refresh missing configured series: {missing}")
        return report
