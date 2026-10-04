"""#446 备份配方集成测试：非空根 备份→恢复→校验 演练（票面验收）."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ditto_apps.scripts.workstation_backup_recipe import (
    RecipeError,
    backup_workstation_state,
    main,
    restore_workstation_state,
    verify_workstation_state,
)

pytestmark = pytest.mark.integration

_REQUIRED_DB_SEEDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "trading/trading.sqlite",
        (
            "CREATE TABLE paper_sessions (session_id TEXT PRIMARY KEY)",
            "CREATE TABLE account_journal_events ("
            "event_id TEXT PRIMARY KEY, amount REAL)",
            "INSERT INTO paper_sessions VALUES ('paper-001')",
            "INSERT INTO account_journal_events VALUES ('evt-001', 10000.0)",
        ),
    ),
    (
        "metadata/metadata.sqlite",
        (
            "CREATE TABLE strategy_active_pointer (strategy_id TEXT PRIMARY KEY)",
            "CREATE TABLE strategy_activation_event ("
            "event_id TEXT PRIMARY KEY, strategy_id TEXT)",
            "INSERT INTO strategy_active_pointer VALUES ('strat-active')",
            "INSERT INTO strategy_activation_event VALUES ('evt-1', 'strat-active')",
        ),
    ),
    (
        "research/research.sqlite",
        (
            "CREATE TABLE holdout_claim (claim_id TEXT PRIMARY KEY, consumed_at TEXT)",
            "INSERT INTO holdout_claim VALUES ('claim-1', '2026-10-01')",
        ),
    ),
    (
        "agent/agent.sqlite",
        (
            "CREATE TABLE agent_sessions ("
            "session_id TEXT PRIMARY KEY, created_at_us INTEGER)",
            "INSERT INTO agent_sessions VALUES ('sess-1', 1)",
        ),
    ),
    (
        "agent/agent-presentation.sqlite3",
        ("CREATE TABLE presentation_state (key TEXT PRIMARY KEY)",),
    ),
    (
        "agent/agent-shadow/decision-opinion.sqlite",
        ("CREATE TABLE decision_opinion (opinion_id TEXT PRIMARY KEY)",),
    ),
)


def _seed_non_empty_root(root: Path, *, with_artifacts: bool = True) -> None:
    for relative, statements in _REQUIRED_DB_SEEDS:
        database = root / relative
        database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database) as connection:
            for statement in statements:
                connection.execute(statement)
    if with_artifacts:
        artifacts = root / "research" / "artifacts" / "exp-001"
        artifacts.mkdir(parents=True)
        (artifacts / "result.parquet").write_bytes(b"legacy-experiment-artifact")


class TestWorkstationBackupRecipeDrill:
    """票面验收：临时非空根完成一次备份→恢复，业务事实可用."""

    def test_backup_restore_verify_round_trip(self, tmp_path: Path) -> None:
        source_root = tmp_path / "state"
        backup_dir = tmp_path / "backups" / "2026-10-04"
        restored_root = tmp_path / "restored"
        _seed_non_empty_root(source_root)

        manifest = backup_workstation_state(
            data_root=source_root, backup_dir=backup_dir
        )
        entry_paths = {entry["path"] for entry in manifest["entries"]}
        assert entry_paths >= {
            "metadata/metadata.sqlite",
            "research/research.sqlite",
            "trading/trading.sqlite",
            "agent/agent.sqlite",
            "research/artifacts",
        }

        restore_report = restore_workstation_state(
            backup_dir=backup_dir, data_root=restored_root
        )
        restored_paths = {item["path"] for item in restore_report["restored"]}
        assert "research/artifacts" in restored_paths

        summary = verify_workstation_state(data_root=restored_root)
        statuses = {(item["check"], item["status"]) for item in summary["results"]}
        assert summary["passed"] is True
        # 每域业务事实核对（不只检查库能打开/行数相同）
        assert ("fact:paper/manual 账本会话", "PASS") in statuses
        assert ("fact:账户事件日志", "PASS") in statuses
        assert ("fact:当前策略激活指针", "PASS") in statuses
        assert ("fact:策略激活事件", "PASS") in statuses
        assert ("fact:holdout 消费事实", "PASS") in statuses
        assert ("fact:agent 会话状态", "PASS") in statuses
        assert ("integrity", "PASS") in statuses
        # 旧实验 artifact 恢复且 holdout 事实未被清零
        assert (
            restored_root / "research" / "artifacts" / "exp-001" / "result.parquet"
        ).read_bytes() == b"legacy-experiment-artifact"
        with sqlite3.connect(restored_root / "research" / "research.sqlite") as conn:
            assert conn.execute("SELECT COUNT(*) FROM holdout_claim").fetchone()[0] == 1

    def test_missing_required_database_fails_verification(self, tmp_path: Path) -> None:
        """当前运行必需文件缺失 → 明确失败."""
        source_root = tmp_path / "state"
        backup_dir = tmp_path / "backup"
        restored_root = tmp_path / "restored"
        _seed_non_empty_root(source_root)
        backup_workstation_state(data_root=source_root, backup_dir=backup_dir)
        restore_workstation_state(backup_dir=backup_dir, data_root=restored_root)

        (restored_root / "trading" / "trading.sqlite").unlink()

        summary = verify_workstation_state(data_root=restored_root)
        assert summary["passed"] is False
        failures = [item for item in summary["results"] if item["status"] == "FAIL"]
        assert any(item["check"] == "file_present" for item in failures)

    def test_missing_optional_artifacts_do_not_block_recovery(
        self, tmp_path: Path
    ) -> None:
        """可选旧 artifact 缺失不阻断当前恢复, 但旧实验显式不可重放."""
        source_root = tmp_path / "state"
        backup_dir = tmp_path / "backup"
        restored_root = tmp_path / "restored"
        _seed_non_empty_root(source_root, with_artifacts=False)

        manifest = backup_workstation_state(
            data_root=source_root, backup_dir=backup_dir
        )
        artifacts_entry = next(
            entry
            for entry in manifest["entries"]
            if entry["path"] == "research/artifacts"
        )
        assert artifacts_entry["present"] is False

        restore_report = restore_workstation_state(
            backup_dir=backup_dir, data_root=restored_root
        )
        artifacts_restore = next(
            item
            for item in restore_report["restored"]
            if item["path"] == "research/artifacts"
        )
        assert artifacts_restore["restored"] is False
        assert "不可重放" in artifacts_restore["note"]

        summary = verify_workstation_state(data_root=restored_root)
        assert summary["passed"] is True
        # holdout 消费事实不能因旧 artifact 缺失被清零
        with sqlite3.connect(restored_root / "research" / "research.sqlite") as conn:
            assert conn.execute("SELECT COUNT(*) FROM holdout_claim").fetchone()[0] == 1

    def test_backup_refuses_existing_backup_dir(self, tmp_path: Path) -> None:
        source_root = tmp_path / "state"
        backup_dir = tmp_path / "backup"
        _seed_non_empty_root(source_root)
        backup_dir.mkdir(parents=True)
        with pytest.raises(RecipeError, match="already exists"):
            backup_workstation_state(data_root=source_root, backup_dir=backup_dir)

    def test_restore_refuses_non_empty_target_root(self, tmp_path: Path) -> None:
        source_root = tmp_path / "state"
        backup_dir = tmp_path / "backup"
        restored_root = tmp_path / "restored"
        _seed_non_empty_root(source_root)
        backup_workstation_state(data_root=source_root, backup_dir=backup_dir)
        restored_root.mkdir()
        (restored_root / "stale-file").write_bytes(b"x")
        with pytest.raises(RecipeError, match="must be empty"):
            restore_workstation_state(backup_dir=backup_dir, data_root=restored_root)


def test_cli_verify_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """CLI 入口: verify 失败时非零退出, 输出核对明细."""
    root = tmp_path / "state"
    _seed_non_empty_root(root)
    assert main(["verify", "--data-root", str(root)]) == 0

    (root / "agent" / "agent.sqlite").unlink()
    assert main(["verify", "--data-root", str(root)]) == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.out
