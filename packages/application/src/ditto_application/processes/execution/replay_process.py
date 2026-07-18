"""
ReplayProcess — 回测重放编排.

从原始运行的 manifest.json 恢复配置，重新执行回测，
使用 ReplayValidator 对比结果，并记录血统关系.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, cast

import orjson
import polars as pl
from ditto_backtest.config import validate_spec_hash
from ditto_backtest.manifest import InputRef, RuleRef, RunManifest, RunMode
from ditto_backtest.replay import (
    AccountStateComparison,
    FillComparison,
    ManifestDiff,
    ReplayStateProof,
    ReplayValidationResult,
    ReplayValidator,
)
from ditto_backtest.result import BacktestAccountStateSnapshot
from ditto_backtest.statistics import BacktestReport
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_platform.foundation import atomic_bytes_write
from ditto_portfolio.accounting import AccountView, CashBook, Position
from ditto_portfolio.accounting.fills import FillEvent
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.runs.models import StrategyRunRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.config import DEFAULT_INITIAL_CASH
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import BacktestServiceConfig
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.queries.artifact_utils import find_artifact

__all__ = ["ReplayProcess", "ReplayResult"]


class ReplayRunConfigReader(Protocol):
    """Narrow read port for original run-control config during replay."""

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        """Return a run record by ID."""
        ...


@dataclass(frozen=True)
class ReplayResult:
    """
    重放结果.

    Attributes:
        new_run_id: 新运行的 run_id
        validation: 复现性验证结果
        original_manifest: 原始 manifest
        replay_manifest: 重放 manifest

    """

    new_run_id: str
    validation: ReplayValidationResult
    original_manifest: RunManifest
    replay_manifest: RunManifest


class ReplayProcess:
    """
    回测重放编排 — 从原始运行恢复配置并重新执行.

    职责：
    1. 加载原始 manifest.json
    2. 从 backtest_report.json 恢复运行配置
    3. 使用 StrategyFacade 重新执行回测
    4. 使用 ReplayValidator 对比两次运行结果
    5. 返回 ReplayResult
    """

    def __init__(
        self,
        strategy_facade: StrategyFacade,
        artifact_service: StrategyArtifactService,
        run_model: ReplayRunConfigReader | None = None,
    ) -> None:
        self._facade = strategy_facade
        self._artifact_service = artifact_service
        self._run_model = run_model

    def replay(self, original_run_id: str) -> ReplayResult:
        """
        基于原始运行重放回测.

        Args:
            original_run_id: 原始运行的 run_id

        Returns:
            ReplayResult 包含验证结果

        Raises:
            FileNotFoundError: manifest.json 不存在
            ValueError: 无法从报告中恢复配置

        """
        # 1. 加载原始 manifest.json
        artifact_dir = self._find_artifact_dir(original_run_id)
        original_manifest = self._load_manifest(artifact_dir)

        # 2. 从 backtest_report.json 恢复配置
        report = self._load_report(artifact_dir)
        original_run_config = self._load_run_config(original_run_id)
        config = self._build_config(
            original_manifest,
            report,
            parent_run_id=original_run_id,
            run_config=original_run_config,
        )

        # 3. 执行重放
        replay_report = self._facade.run_backtest_from_catalog(
            config=config,
            version=int(original_manifest.strategy_version)
            if original_manifest.strategy_version.isdigit()
            else None,
        )

        # 4. 加载重放 manifest（从新运行的 artifact 目录）
        new_run_id = replay_report.run_id
        replay_artifact_dir = self._find_artifact_dir(new_run_id)
        replay_manifest = self._load_manifest(replay_artifact_dir)

        # 5. 提取 NAV 序列进行对比
        original_nav = self._extract_nav(report)
        replay_nav = self._extract_nav_from_report(replay_report)
        state_proof = _build_state_proof(
            original_fills=_load_fill_log(artifact_dir),
            original_account=_load_final_account_state(report),
            replay_report=replay_report,
        )

        # 6. 验证复现性
        validation = ReplayValidator.validate(
            original_manifest,
            replay_manifest,
            original_nav,
            replay_nav,
            state_proof=state_proof,
        )
        self._persist_replay_proof(
            original_run_id=original_run_id,
            replay_run_id=new_run_id,
            original_manifest=original_manifest,
            validation=validation,
            original_resume_provenance=_load_resume_provenance(report),
            replay_artifact_dir=replay_artifact_dir,
        )

        return ReplayResult(
            new_run_id=new_run_id,
            validation=validation,
            original_manifest=original_manifest,
            replay_manifest=replay_manifest,
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _find_artifact_dir(self, run_id: str) -> Path:
        """查找运行对应的 artifact 目录."""
        record = find_artifact(
            self._artifact_service,
            run_id,
            ArtifactKind.BACKTEST_REPORT,
        )
        if record is None:
            msg = f"Artifact directory not found for run: {run_id}"
            raise FileNotFoundError(msg)
        return Path(record.file_path)

    @staticmethod
    def _load_manifest(artifact_dir: Path) -> RunManifest:
        """从 artifact 目录加载 manifest.json."""
        manifest_path = artifact_dir / "manifest.json"
        if not manifest_path.exists():
            msg = f"manifest.json not found: {manifest_path}"
            raise FileNotFoundError(msg)
        raw: dict[str, Any] = orjson.loads(manifest_path.read_bytes())
        return _deserialize_manifest(raw)

    @staticmethod
    def _load_report(artifact_dir: Path) -> dict[str, Any]:
        """从 artifact 目录加载 backtest_report.json."""
        report_path = artifact_dir / "backtest_report.json"
        if not report_path.exists():
            msg = f"backtest_report.json not found: {report_path}"
            raise FileNotFoundError(msg)
        return orjson.loads(report_path.read_bytes())

    @staticmethod
    def _build_config(
        manifest: RunManifest,
        report: dict[str, Any],
        *,
        parent_run_id: str = "",
        run_config: dict[str, object] | None = None,
    ) -> BacktestServiceConfig:
        """从 manifest + report 恢复 BacktestServiceConfig."""
        period = report.get("period", {})
        return BacktestServiceConfig(
            strategy_id=manifest.strategy_id,
            strategy_version=manifest.strategy_version,
            spec_hash=manifest.spec_hash,
            parent_run_id=parent_run_id,
            start_date=period.get("start", ""),
            end_date=period.get("end", ""),
            initial_cash=_initial_cash_from_config_or_report(run_config, report),
            parameter_overrides=manifest.parameter_overrides,
            rebalance_freq=_extract_rebalance_freq(report),
            engine_version=manifest.engine_version,
            execution_delay=_int_config_field(run_config, "execution_delay"),
            resume_from_run_id=_str_config_field(run_config, "resume_from_run_id"),
            resume_checkpoint_trade_date=_str_config_field(
                run_config,
                "resume_checkpoint_trade_date",
            ),
            resume_checkpoint_completed_days=_int_config_field(
                run_config,
                "resume_checkpoint_completed_days",
            ),
            resume_checkpoint_total_days=_int_config_field(
                run_config,
                "resume_checkpoint_total_days",
            ),
            resume_checkpoint_nav=_float_config_field(
                run_config,
                "resume_checkpoint_nav",
            ),
            resume_checkpoint_order_count=_int_config_field(
                run_config,
                "resume_checkpoint_order_count",
            ),
            resume_checkpoint_fill_count=_int_config_field(
                run_config,
                "resume_checkpoint_fill_count",
            ),
            resume_account_state_json=_str_config_field(
                run_config,
                "resume_account_state_json",
            ),
            resume_account_state_hash=_str_config_field(
                run_config,
                "resume_account_state_hash",
            ),
            resume_settlement_state_json=_str_config_field(
                run_config,
                "resume_settlement_state_json",
            ),
            resume_settlement_state_hash=_str_config_field(
                run_config,
                "resume_settlement_state_hash",
            ),
            resume_runtime_state_json=_str_config_field(
                run_config,
                "resume_runtime_state_json",
            ),
            resume_runtime_state_hash=_str_config_field(
                run_config,
                "resume_runtime_state_hash",
            ),
        )

    @staticmethod
    def _extract_nav(report: dict[str, Any]) -> list[float]:
        """从 backtest_report 提取 NAV 序列."""
        nav_data = report.get("nav_series")
        if nav_data is not None:
            return [float(v) for v in nav_data]
        # 退而求其次 — 用单个 final_nav
        final_nav = report.get("final_nav")
        if final_nav is not None:
            return [float(final_nav)]
        return []

    @staticmethod
    def _extract_nav_from_report(report: BacktestReport) -> list[float]:
        """从 BacktestReport 对象提取 NAV 序列."""
        if report.nav_series:
            return [float(v) for _, v in report.nav_series]
        if report.final_nav:
            return [float(report.final_nav)]
        return []

    def _load_run_config(self, run_id: str) -> dict[str, object] | None:
        """Load original run-control config JSON when a run model is available."""
        if self._run_model is None:
            return None
        record = self._run_model.get_run(run_id)
        if record is None or not record.config_json:
            return None
        try:
            raw = orjson.loads(record.config_json)
        except orjson.JSONDecodeError as exc:
            msg = f"Invalid config_json for replay run: {run_id}"
            raise AppProcessError(msg) from exc
        if not isinstance(raw, dict):
            msg = f"config_json for replay run must be an object: {run_id}"
            raise AppProcessError(msg)
        data = cast(dict[object, object], raw)
        return {str(key): value for key, value in data.items()}

    def _persist_replay_proof(
        self,
        *,
        original_run_id: str,
        replay_run_id: str,
        original_manifest: RunManifest,
        validation: ReplayValidationResult,
        original_resume_provenance: dict[str, object] | None,
        replay_artifact_dir: Path,
    ) -> None:
        """写出 replay proof JSON 并登记 strategy artifact 记录."""
        replay_artifact_dir.mkdir(parents=True, exist_ok=True)
        proof_path = replay_artifact_dir / "replay_proof.json"
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = _build_replay_proof_payload(
            original_run_id=original_run_id,
            replay_run_id=replay_run_id,
            validation=validation,
            original_resume_provenance=original_resume_provenance,
            created_at=created_at,
        )
        atomic_bytes_write(
            orjson.dumps(payload, option=orjson.OPT_INDENT_2),
            proof_path,
        )

        metadata: dict[str, object] = {
            "original_run_id": original_run_id,
            "replay_run_id": replay_run_id,
            "is_reproducible": validation.is_reproducible,
            "nav_correlation": validation.nav_correlation,
            "max_nav_diff_bps": validation.max_nav_diff_bps,
            "input_data_match": validation.input_data_match,
            "manifest_has_diff": validation.manifest_diff.has_diff,
            "fill_match": validation.fill_match,
            "account_state_match": validation.account_state_match,
            "proof_path": str(proof_path),
        }
        metadata.update(_resume_provenance_metadata(original_resume_provenance))

        self._artifact_service.save_artifact(
            StrategyArtifactRecord(
                artifact_id=f"replay-proof-{replay_run_id}",
                strategy_id=original_manifest.strategy_id,
                run_id=replay_run_id,
                artifact_type=ArtifactKind.REPLAY_PROOF,
                file_path=str(replay_artifact_dir),
                metadata=metadata,
                created_at=created_at,
            ),
        )


def _deserialize_manifest(raw: dict[str, Any]) -> RunManifest:
    """从 JSON dict 反序列化 RunManifest."""
    raw_spec_hash = raw.get("spec_hash")
    try:
        spec_hash = validate_spec_hash(raw_spec_hash)
    except ValueError as exc:
        raise AppProcessError(
            str(exc),
            field_name="spec_hash",
            reason="invalid_canonical_identity",
        ) from exc

    input_ref_details = tuple(
        InputRef(
            instrument_id=ref["instrument_id"],
            data_hash=ref.get("data_hash", ""),
            date_range=tuple(ref.get("date_range", ("", ""))),
            source=ref.get("source", ""),
            source_snapshot_id=ref.get("source_snapshot_id", ""),
        )
        for ref in raw.get("input_ref_details", [])
    )

    rule_refs = tuple(
        RuleRef(
            instrument_id=ref["instrument_id"],
            definition_version=ref.get("definition_version", ""),
            trading_rule_as_of=ref.get("trading_rule_as_of", ""),
            fee_schedule_as_of=ref.get("fee_schedule_as_of", ""),
            trading_rule_effective_to=ref.get("trading_rule_effective_to", ""),
            fee_schedule_effective_to=ref.get("fee_schedule_effective_to", ""),
        )
        for ref in raw.get("rule_refs", [])
    )

    return RunManifest(
        run_id=raw.get("run_id", ""),
        strategy_id=raw.get("strategy_id", ""),
        strategy_version=raw.get("strategy_version", ""),
        mode=RunMode(raw.get("mode", "backtest")),
        created_at=raw.get("created_at", ""),
        input_refs=tuple(raw.get("input_refs", ())),
        input_ref_details=input_ref_details,
        parameter_overrides=tuple(raw.get("parameter_overrides", ())),
        rule_refs=rule_refs,
        artifacts=tuple(raw.get("artifacts", ())),
        config_hash=raw.get("config_hash", ""),
        engine_version=raw.get("engine_version", ""),
        rule_resolution_policy=raw.get("rule_resolution_policy", "as_of_date"),
        universe_hash=raw.get("universe_hash", ""),
        spec_hash=spec_hash,
        dependency_versions=tuple(raw.get("dependency_versions", ())),
        random_seed=raw.get("random_seed"),
    )


def _extract_rebalance_freq(report: dict[str, Any]) -> str:
    """从报告中提取调仓频率."""
    freq = report.get("rebalance_freq")
    if isinstance(freq, str) and freq:
        return freq
    return "daily"


def _str_config_field(config: dict[str, object] | None, key: str) -> str:
    """Read an optional run-config string field."""
    if config is None:
        return ""
    value = config.get(key)
    return value if isinstance(value, str) else ""


def _int_config_field(config: dict[str, object] | None, key: str) -> int:
    """Read an optional run-config int field without treating bool as int."""
    if config is None:
        return 0
    value = config.get(key)
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _float_config_field(config: dict[str, object] | None, key: str) -> float:
    """Read an optional run-config numeric field."""
    value = _optional_float_config_field(config, key)
    return value if value is not None else 0.0


def _optional_float_config_field(
    config: dict[str, object] | None,
    key: str,
) -> float | None:
    """Read an optional run-config numeric field as a nullable value."""
    if config is None:
        return None
    value = config.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _initial_cash_from_config_or_report(
    run_config: dict[str, object] | None,
    report: dict[str, Any],
) -> float:
    """Use original run config cash when available, falling back to report cash."""
    config_cash = _optional_float_config_field(run_config, "initial_cash")
    if config_cash is not None:
        return config_cash
    return float(report.get("initial_cash", DEFAULT_INITIAL_CASH))


def _build_replay_proof_payload(
    *,
    original_run_id: str,
    replay_run_id: str,
    validation: ReplayValidationResult,
    original_resume_provenance: dict[str, object] | None = None,
    created_at: str,
) -> dict[str, object]:
    """构建可持久化的 replay proof JSON 载荷."""
    payload: dict[str, object] = {
        "proof_version": 1,
        "created_at": created_at,
        "original_run_id": original_run_id,
        "replay_run_id": replay_run_id,
        "is_reproducible": validation.is_reproducible,
        "nav_correlation": validation.nav_correlation,
        "max_nav_diff_bps": validation.max_nav_diff_bps,
        "input_data_match": validation.input_data_match,
        "manifest_diff": _manifest_diff_to_payload(validation.manifest_diff),
        "fill_match": validation.fill_match,
        "account_state_match": validation.account_state_match,
        "fill_comparison": _fill_comparison_to_payload(validation.fill_comparison),
        "account_state_comparison": _account_comparison_to_payload(
            validation.account_state_comparison,
        ),
    }
    if original_resume_provenance is not None:
        payload["original_resume_provenance"] = original_resume_provenance
    return payload


def _load_resume_provenance(report: dict[str, Any]) -> dict[str, object] | None:
    """Load restored-run provenance from backtest_report.json when available."""
    payload = report.get("resume_provenance")
    if payload is None:
        return None
    if not isinstance(payload, dict):
        msg = "Invalid resume_provenance payload in backtest_report.json"
        raise AppProcessError(msg)
    raw = cast(dict[object, object], payload)
    return {str(key): value for key, value in raw.items()}


def _resume_provenance_metadata(
    provenance: dict[str, object] | None,
) -> dict[str, object]:
    """Flatten original restored-run provenance into replay artifact metadata."""
    if provenance is None:
        return {}
    return {
        "original_resume_from_run_id": provenance.get("from_run_id", ""),
        "original_resume_checkpoint_trade_date": provenance.get(
            "checkpoint_trade_date",
            "",
        ),
        "original_resume_checkpoint_completed_days": provenance.get(
            "checkpoint_completed_days",
            0,
        ),
        "original_resume_checkpoint_total_days": provenance.get(
            "checkpoint_total_days",
            0,
        ),
        "original_resume_checkpoint_nav": provenance.get("checkpoint_nav", 0.0),
        "original_resume_checkpoint_order_count": provenance.get(
            "checkpoint_order_count",
            0,
        ),
        "original_resume_checkpoint_fill_count": provenance.get(
            "checkpoint_fill_count",
            0,
        ),
        "original_resume_account_state_hash": provenance.get(
            "account_state_hash",
            "",
        ),
        "original_resume_settlement_state_hash": provenance.get(
            "settlement_state_hash",
            "",
        ),
        "original_resume_runtime_state_hash": provenance.get(
            "runtime_state_hash",
            "",
        ),
    }


def _build_state_proof(
    *,
    original_fills: tuple[FillEvent, ...] | None,
    original_account: AccountView | None,
    replay_report: BacktestReport,
) -> ReplayStateProof | None:
    """Build replay state proof from persisted original evidence when available."""
    if original_fills is None and original_account is None:
        return None
    return ReplayStateProof(
        original_fills=original_fills,
        replay_fills=tuple(replay_report.fill_log)
        if original_fills is not None
        else None,
        original_account=original_account,
        replay_account=replay_report.final_account_state
        if original_account is not None
        else None,
    )


def _load_final_account_state(report: dict[str, Any]) -> AccountView | None:
    """Load persisted final_account_state from backtest_report.json when available."""
    payload = report.get("final_account_state")
    if payload is None:
        return None
    try:
        snapshot = BacktestAccountStateSnapshot.from_payload(payload)
    except ValueError as exc:
        msg = "Invalid final_account_state payload in backtest_report.json"
        raise AppProcessError(msg) from exc
    return _account_view_from_snapshot(snapshot)


def _account_view_from_snapshot(snapshot: BacktestAccountStateSnapshot) -> AccountView:
    """Convert persisted account-state snapshot into an AccountView."""
    positions = {
        position.instrument_id: Position(
            instrument_id=position.instrument_id,
            quantity=position.quantity,
            available_quantity=position.available_quantity,
            average_cost=position.average_cost,
            market_value=position.market_value,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
            total_fees=position.total_fees,
        )
        for position in snapshot.positions
    }
    return AccountView(
        positions=MappingProxyType(positions),
        cash=CashBook(
            available=snapshot.cash_available,
            settled=snapshot.cash_settled,
            frozen=snapshot.cash_frozen,
        ),
        total_value=snapshot.total_value,
        nav=snapshot.nav,
        exposure=snapshot.exposure,
    )


def _load_fill_log(artifact_dir: Path) -> tuple[FillEvent, ...] | None:
    """Load persisted fill_log.parquet as replay state evidence when available."""
    fill_log_path = artifact_dir / "fill_log.parquet"
    if not fill_log_path.exists():
        return None
    df = pl.read_parquet(fill_log_path)
    return tuple(_fill_from_row(row) for row in df.to_dicts())


def _fill_from_row(row: dict[str, Any]) -> FillEvent:
    """Deserialize one persisted fill_log row into a FillEvent."""
    correlation_id_raw = row.get("correlation_id")
    correlation_id = str(correlation_id_raw) if correlation_id_raw is not None else None
    return FillEvent(
        fill_id=str(row["fill_id"]),
        order_id=str(row["order_id"]),
        instrument_id=InstrumentId(int(row["instrument_id"])),
        direction=OrderSide(str(row["direction"])),
        filled_quantity=int(row["filled_quantity"]),
        fill_price=float(row["fill_price"]),
        fee=float(row["fee"]),
        slippage=float(row["slippage"]),
        event_time=_parse_fill_event_time(row["event_time"]),
        cumulative_quantity=int(row["cumulative_quantity"]),
        leaves_quantity=int(row["leaves_quantity"]),
        correlation_id=correlation_id,
    )


def _parse_fill_event_time(value: object) -> datetime:
    """Parse persisted fill event time from parquet-compatible values."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            msg = f"Unsupported fill event_time value: {value!r}"
            raise AppProcessError(msg) from exc
    msg = f"Unsupported fill event_time value: {value!r}"
    raise AppProcessError(msg)


def _manifest_diff_to_payload(diff: ManifestDiff) -> dict[str, object]:
    """将 ManifestDiff 转成稳定 JSON 结构."""
    return {
        "config_diffs": list(diff.config_diffs),
        "data_diffs": list(diff.data_diffs),
        "version_diffs": list(diff.version_diffs),
        "seed_diffs": list(diff.seed_diffs),
        "has_diff": diff.has_diff,
    }


def _fill_comparison_to_payload(
    comparison: FillComparison | None,
) -> dict[str, object] | None:
    """将 FillComparison 转成稳定 JSON 结构."""
    if comparison is None:
        return None
    return {
        "identical": comparison.identical,
        "mismatch_count": comparison.mismatch_count,
        "length_mismatch": comparison.length_mismatch,
        "point_count": comparison.point_count,
    }


def _account_comparison_to_payload(
    comparison: AccountStateComparison | None,
) -> dict[str, object] | None:
    """将 AccountStateComparison 转成稳定 JSON 结构."""
    if comparison is None:
        return None
    return {
        "identical": comparison.identical,
        "nav_diff": comparison.nav_diff,
        "available_cash_diff": comparison.available_cash_diff,
        "settled_cash_diff": comparison.settled_cash_diff,
        "frozen_cash_diff": comparison.frozen_cash_diff,
        "position_count_diff": comparison.position_count_diff,
    }
