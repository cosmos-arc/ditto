"""
ReplayProcess 单元测试 — 回测重放编排.

覆盖：replay() 成功流程、FileNotFoundError、_load_manifest、
_build_config、_extract_nav、_load_report、_find_artifact_dir。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import orjson
import pytest
from ditto_backtest.manifest import RunManifest, RunMode
from ditto_backtest.replay import ManifestDiff, ReplayValidationResult
from ditto_backtest.statistics import BacktestReport

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_manifest_raw(
    *,
    run_id: str = "run-original",
    strategy_id: str = "strat-1",
    strategy_version: str = "3",
    mode: str = "backtest",
    created_at: str = "2026-04-10T00:00:00Z",
    config_hash: str = "hash-abc",
    engine_version: str = "0.1.0",
    **overrides: object,
) -> dict[str, object]:
    """构建 manifest.json 的原始 dict."""
    raw: dict[str, object] = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "mode": mode,
        "created_at": created_at,
        "input_refs": [],
        "input_ref_details": [],
        "parameter_overrides": [],
        "rule_refs": [],
        "artifacts": [],
        "config_hash": config_hash,
        "engine_version": engine_version,
        "rule_resolution_policy": "as_of_date",
        "universe_hash": "",
        "spec_hash": "",
        "dependency_versions": [],
        "random_seed": None,
    }
    raw.update(overrides)
    return raw


def _make_report_dict(
    *,
    period_start: str = "2026-01-01",
    period_end: str = "2026-03-31",
    initial_cash: float = 1_000_000.0,
    final_nav: float = 1_050_000.0,
    rebalance_freq: str = "weekly",
    nav_series: list[float] | None = None,
) -> dict[str, object]:
    """构建 backtest_report.json 的原始 dict."""
    report: dict[str, object] = {
        "period": {"start": period_start, "end": period_end},
        "initial_cash": initial_cash,
        "final_nav": final_nav,
        "rebalance_freq": rebalance_freq,
    }
    if nav_series is not None:
        report["nav_series"] = nav_series
    return report


def _make_replay_validation_result(
    *,
    is_reproducible: bool = True,
    nav_correlation: float = 1.0,
    max_nav_diff_bps: float = 0.0,
) -> ReplayValidationResult:
    """构建 ReplayValidationResult."""
    return ReplayValidationResult(
        is_reproducible=is_reproducible,
        nav_correlation=nav_correlation,
        max_nav_diff_bps=max_nav_diff_bps,
        manifest_diff=ManifestDiff(),
        input_data_match=True,
    )


def _make_backtest_report(
    *,
    run_id: str = "run-replay",
    final_nav: float = 1_050_000.0,
    nav_series: tuple[tuple[str, float], ...] | None = None,
) -> BacktestReport:
    """构建 BacktestReport mock 对象."""
    report = MagicMock(spec=BacktestReport)
    report.run_id = run_id
    report.final_nav = final_nav
    report.nav_series = nav_series or ()
    return report


# ---------------------------------------------------------------------------
# _load_manifest 测试
# ---------------------------------------------------------------------------


class TestLoadManifest:
    """ReplayProcess._load_manifest — 从 artifact 目录加载 manifest.json."""

    def test_load_manifest_success(self, tmp_path: Path) -> None:
        """正常加载 manifest.json."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        raw = _make_manifest_raw()
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_bytes(orjson.dumps(raw))

        manifest = ReplayProcess._load_manifest(tmp_path)

        assert isinstance(manifest, RunManifest)
        assert manifest.run_id == "run-original"
        assert manifest.strategy_id == "strat-1"
        assert manifest.strategy_version == "3"

    def test_load_manifest_file_not_found(self, tmp_path: Path) -> None:
        """manifest.json 不存在时抛出 FileNotFoundError."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        with pytest.raises(FileNotFoundError, match=r"manifest\.json not found"):
            ReplayProcess._load_manifest(tmp_path)

    def test_load_manifest_defaults(self, tmp_path: Path) -> None:
        """最小 manifest — 使用默认值."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        raw = {}  # 空字典
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_bytes(orjson.dumps(raw))

        manifest = ReplayProcess._load_manifest(tmp_path)

        assert manifest.run_id == ""
        assert manifest.mode == RunMode.BACKTEST
        assert manifest.input_refs == ()
        assert manifest.parameter_overrides == ()
        assert manifest.random_seed is None


# ---------------------------------------------------------------------------
# _load_report 测试
# ---------------------------------------------------------------------------


class TestLoadReport:
    """ReplayProcess._load_report — 从 artifact 目录加载 backtest_report.json."""

    def test_load_report_success(self, tmp_path: Path) -> None:
        """正常加载 backtest_report.json."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report_dict = _make_report_dict()
        report_path = tmp_path / "backtest_report.json"
        report_path.write_bytes(orjson.dumps(report_dict))

        report = ReplayProcess._load_report(tmp_path)

        assert report["initial_cash"] == 1_000_000.0
        assert report["period"]["start"] == "2026-01-01"

    def test_load_report_file_not_found(self, tmp_path: Path) -> None:
        """backtest_report.json 不存在时抛出 FileNotFoundError."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        with pytest.raises(FileNotFoundError, match=r"backtest_report\.json not found"):
            ReplayProcess._load_report(tmp_path)


# ---------------------------------------------------------------------------
# _build_config 测试
# ---------------------------------------------------------------------------


class TestBuildConfig:
    """ReplayProcess._build_config — 从 manifest + report 恢复配置."""

    def test_build_config_defaults(self) -> None:
        """默认值 — period 为空时使用空字符串, initial_cash 默认 100 万."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        manifest = MagicMock(spec=RunManifest)
        manifest.strategy_id = "strat-1"
        manifest.strategy_version = "3"
        manifest.parameter_overrides = ()
        manifest.engine_version = "0.1.0"

        report = {"period": {}, "rebalance_freq": ""}

        config = ReplayProcess._build_config(
            manifest,
            report,
            parent_run_id="run-orig",
        )

        assert config.strategy_id == "strat-1"
        assert config.strategy_version == "3"
        assert config.parent_run_id == "run-orig"
        assert config.start_date == ""
        assert config.end_date == ""
        assert config.initial_cash == pytest.approx(1_000_000.0)
        assert config.rebalance_freq == "daily"  # 空字符串回退到 daily

    def test_build_config_with_values(self) -> None:
        """完整配置 — 从 report 恢复 period / cash / freq."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        manifest = MagicMock(spec=RunManifest)
        manifest.strategy_id = "strat-1"
        manifest.strategy_version = "3"
        manifest.parameter_overrides = ("--lookback=20",)
        manifest.engine_version = "0.2.0"

        report = _make_report_dict(
            period_start="2026-01-01",
            period_end="2026-06-30",
            initial_cash=500_000.0,
            rebalance_freq="monthly",
        )

        config = ReplayProcess._build_config(
            manifest,
            report,
            parent_run_id="run-orig",
        )

        assert config.start_date == "2026-01-01"
        assert config.end_date == "2026-06-30"
        assert config.initial_cash == pytest.approx(500_000.0)
        assert config.rebalance_freq == "monthly"
        assert config.parameter_overrides == ("--lookback=20",)
        assert config.engine_version == "0.2.0"


# ---------------------------------------------------------------------------
# _extract_nav 测试
# ---------------------------------------------------------------------------


class TestExtractNav:
    """ReplayProcess._extract_nav — 从 backtest_report dict 提取 NAV 序列."""

    def test_extract_nav_series(self) -> None:
        """有 nav_series 时直接返回."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = {"nav_series": [1.0, 1.01, 1.02, 1.015]}
        nav = ReplayProcess._extract_nav(report)
        assert nav == [1.0, 1.01, 1.02, 1.015]

    def test_extract_nav_final_only(self) -> None:
        """无 nav_series 时退而求其次用 final_nav."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = {"final_nav": 1.05}
        nav = ReplayProcess._extract_nav(report)
        assert nav == [1.05]

    def test_extract_nav_empty(self) -> None:
        """无 nav_series 也无 final_nav 时返回空列表."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report: dict[str, object] = {}
        nav = ReplayProcess._extract_nav(report)
        assert nav == []

    def test_extract_nav_series_priority_over_final(self) -> None:
        """nav_series 优先级高于 final_nav."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = {"nav_series": [1.0, 1.1], "final_nav": 1.05}
        nav = ReplayProcess._extract_nav(report)
        assert nav == [1.0, 1.1]


# ---------------------------------------------------------------------------
# _extract_nav_from_report 测试
# ---------------------------------------------------------------------------


class TestExtractNavFromReport:
    """ReplayProcess._extract_nav_from_report — 从 BacktestReport 对象提取 NAV."""

    def test_extract_from_report_with_nav_series(self) -> None:
        """有 nav_series 时返回对应 NAV 值."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = _make_backtest_report(
            nav_series=(("2026-01-01", 1.0), ("2026-01-02", 1.02)),
        )

        nav = ReplayProcess._extract_nav_from_report(report)
        assert nav == [1.0, 1.02]

    def test_extract_from_report_final_nav_fallback(self) -> None:
        """无 nav_series 时用 final_nav."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = _make_backtest_report(
            final_nav=1.05,
            nav_series=(),
        )

        nav = ReplayProcess._extract_nav_from_report(report)
        assert nav == [1.05]

    def test_extract_from_report_empty(self) -> None:
        """无 nav_series 且无 final_nav 时返回空列表."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = _make_backtest_report(final_nav=0.0, nav_series=())

        nav = ReplayProcess._extract_nav_from_report(report)
        assert nav == []


# ---------------------------------------------------------------------------
# _find_artifact_dir 测试
# ---------------------------------------------------------------------------


class TestFindArtifactDir:
    """ReplayProcess._find_artifact_dir — 查找运行对应的 artifact 目录."""

    def test_find_success(self) -> None:
        """找到匹配的 artifact 记录."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        mock_artifact_service = MagicMock()
        mock_record = MagicMock()
        mock_record.run_id = "run-123"
        mock_record.file_path = "/data/artifacts/run-123"
        mock_artifact_service.list_artifacts.return_value = [mock_record]

        process = ReplayProcess(
            strategy_facade=MagicMock(),
            artifact_service=mock_artifact_service,
        )

        result = process._find_artifact_dir("run-123")

        assert result == Path("/data/artifacts/run-123")

    def test_find_not_found_raises(self) -> None:
        """找不到匹配的 artifact 时抛出 FileNotFoundError."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        mock_artifact_service = MagicMock()
        mock_artifact_service.list_artifacts.return_value = []

        process = ReplayProcess(
            strategy_facade=MagicMock(),
            artifact_service=mock_artifact_service,
        )

        with pytest.raises(FileNotFoundError, match="Artifact directory not found"):
            process._find_artifact_dir("run-unknown")


# ---------------------------------------------------------------------------
# replay() 完整流程测试
# ---------------------------------------------------------------------------


class TestReplaySuccess:
    """ReplayProcess.replay — 完整成功流程."""

    def test_replay_happy_path(self, tmp_path: Path) -> None:
        """端到端成功重放."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        # --- 准备 original artifact 目录 ---
        orig_dir = tmp_path / "artifacts" / "run-original"
        orig_dir.mkdir(parents=True)
        manifest_raw = _make_manifest_raw(run_id="run-original")
        report_raw = _make_report_dict(nav_series=[1.0, 1.01, 1.02])
        (orig_dir / "manifest.json").write_bytes(orjson.dumps(manifest_raw))
        (orig_dir / "backtest_report.json").write_bytes(orjson.dumps(report_raw))

        # --- 准备 replay artifact 目录 ---
        replay_dir = tmp_path / "artifacts" / "run-replay"
        replay_dir.mkdir(parents=True)
        replay_manifest_raw = _make_manifest_raw(
            run_id="run-replay",
            config_hash="hash-abc",  # 与 original 相同
        )
        (replay_dir / "manifest.json").write_bytes(orjson.dumps(replay_manifest_raw))

        # --- Mock ---
        mock_artifact_service = MagicMock()
        orig_record = MagicMock()
        orig_record.run_id = "run-original"
        orig_record.file_path = str(orig_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.file_path = str(replay_dir)
        mock_artifact_service.list_artifacts.return_value = [
            replay_record,
            orig_record,
        ]

        replay_report = _make_backtest_report(
            run_id="run-replay",
            nav_series=(
                ("2026-01-01", 1.0),
                ("2026-01-02", 1.01),
                ("2026-01-03", 1.02),
            ),
        )

        mock_facade = MagicMock()
        mock_facade.run_backtest_from_catalog.return_value = replay_report

        process = ReplayProcess(
            strategy_facade=mock_facade,
            artifact_service=mock_artifact_service,
        )

        # --- 执行 ---
        result = process.replay("run-original")

        # --- 断言 ---
        assert result.new_run_id == "run-replay"
        assert isinstance(result.validation, ReplayValidationResult)
        assert isinstance(result.original_manifest, RunManifest)
        assert isinstance(result.replay_manifest, RunManifest)

        # facade 被正确调用
        mock_facade.run_backtest_from_catalog.assert_called_once()
        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config is not None
        assert config.strategy_id == "strat-1"
        assert config.parent_run_id == "run-original"

        # version 参数正确
        version = call_kwargs.kwargs.get("version") or call_kwargs[1].get("version")
        assert version == 3  # "3" 被转为 int

    def test_replay_non_numeric_version(self, tmp_path: Path) -> None:
        """strategy_version 非数字时 version 传 None."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        orig_dir = tmp_path / "artifacts" / "run-original"
        orig_dir.mkdir(parents=True)
        manifest_raw = _make_manifest_raw(strategy_version="v3-beta")
        report_raw = _make_report_dict()
        (orig_dir / "manifest.json").write_bytes(orjson.dumps(manifest_raw))
        (orig_dir / "backtest_report.json").write_bytes(orjson.dumps(report_raw))

        replay_dir = tmp_path / "artifacts" / "run-replay"
        replay_dir.mkdir(parents=True)
        (replay_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-replay")),
        )

        mock_artifact_service = MagicMock()
        orig_record = MagicMock()
        orig_record.run_id = "run-original"
        orig_record.file_path = str(orig_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.file_path = str(replay_dir)
        mock_artifact_service.list_artifacts.return_value = [
            replay_record,
            orig_record,
        ]

        replay_report = _make_backtest_report(run_id="run-replay")
        mock_facade = MagicMock()
        mock_facade.run_backtest_from_catalog.return_value = replay_report

        process = ReplayProcess(
            strategy_facade=mock_facade,
            artifact_service=mock_artifact_service,
        )

        process.replay("run-original")

        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        version = call_kwargs.kwargs.get("version") or call_kwargs[1].get("version")
        assert version is None


# ---------------------------------------------------------------------------
# replay() 错误场景
# ---------------------------------------------------------------------------


class TestReplayErrors:
    """ReplayProcess.replay — 错误场景."""

    def test_replay_artifact_not_found(self) -> None:
        """原始运行的 artifact 不存在时抛出 FileNotFoundError."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        mock_artifact_service = MagicMock()
        mock_artifact_service.list_artifacts.return_value = []

        process = ReplayProcess(
            strategy_facade=MagicMock(),
            artifact_service=mock_artifact_service,
        )

        with pytest.raises(FileNotFoundError, match="Artifact directory not found"):
            process.replay("run-nonexistent")


# ---------------------------------------------------------------------------
# _extract_rebalance_freq 测试
# ---------------------------------------------------------------------------


class TestExtractRebalanceFreq:
    """_extract_rebalance_freq — 从 report 提取调仓频率."""

    def test_valid_string(self) -> None:
        from ditto_application.processes.execution.replay_process import (
            _extract_rebalance_freq,
        )

        assert _extract_rebalance_freq({"rebalance_freq": "weekly"}) == "weekly"

    def test_empty_string_defaults(self) -> None:
        from ditto_application.processes.execution.replay_process import (
            _extract_rebalance_freq,
        )

        assert _extract_rebalance_freq({"rebalance_freq": ""}) == "daily"

    def test_missing_key_defaults(self) -> None:
        from ditto_application.processes.execution.replay_process import (
            _extract_rebalance_freq,
        )

        assert _extract_rebalance_freq({}) == "daily"

    def test_non_string_type_defaults(self) -> None:
        from ditto_application.processes.execution.replay_process import (
            _extract_rebalance_freq,
        )

        assert _extract_rebalance_freq({"rebalance_freq": 42}) == "daily"
