"""
ReplayProcess — 回测重放编排.

从原始运行的 manifest.json 恢复配置，重新执行回测，
使用 ReplayValidator 对比结果，并记录血统关系.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_engine.backtest.manifest import InputRef, RuleRef, RunManifest, RunMode
from ditto_engine.backtest.replay import ReplayValidationResult, ReplayValidator
from ditto_engine.backtest.statistics import BacktestReport

from ditto_app.config import DEFAULT_INITIAL_CASH
from ditto_app.process.execution.backtest_process import BacktestServiceConfig
from ditto_app.process.execution.strategy_run_process import StrategyFacade
from ditto_app.query._artifact_utils import find_artifact

__all__ = ["ReplayProcess", "ReplayResult"]


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
    ) -> None:
        self._facade = strategy_facade
        self._artifact_service = artifact_service

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
        config = self._build_config(
            original_manifest,
            report,
            parent_run_id=original_run_id,
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

        # 6. 验证复现性
        validation = ReplayValidator.validate(
            original_manifest,
            replay_manifest,
            original_nav,
            replay_nav,
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
        record = find_artifact(self._artifact_service, run_id)
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
    ) -> BacktestServiceConfig:
        """从 manifest + report 恢复 BacktestServiceConfig."""
        period = report.get("period", {})
        return BacktestServiceConfig(
            strategy_id=manifest.strategy_id,
            strategy_version=manifest.strategy_version,
            parent_run_id=parent_run_id,
            start_date=period.get("start", ""),
            end_date=period.get("end", ""),
            initial_cash=float(report.get("initial_cash", DEFAULT_INITIAL_CASH)),
            parameter_overrides=manifest.parameter_overrides,
            rebalance_freq=_extract_rebalance_freq(report),
            engine_version=manifest.engine_version,
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


def _deserialize_manifest(raw: dict[str, Any]) -> RunManifest:
    """从 JSON dict 反序列化 RunManifest."""
    input_ref_details = tuple(
        InputRef(
            instrument_id=ref["instrument_id"],
            data_hash=ref.get("data_hash", ""),
            date_range=tuple(ref.get("date_range", ("", ""))),
            source=ref.get("source", ""),
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
        spec_hash=raw.get("spec_hash", ""),
        dependency_versions=tuple(raw.get("dependency_versions", ())),
        random_seed=raw.get("random_seed"),
    )


def _extract_rebalance_freq(report: dict[str, Any]) -> str:
    """从报告中提取调仓频率."""
    freq = report.get("rebalance_freq")
    if isinstance(freq, str) and freq:
        return freq
    return "daily"
