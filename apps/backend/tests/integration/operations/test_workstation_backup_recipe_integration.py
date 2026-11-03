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
            # 数据层不可重拉事实（#630）：目录/摄取证据账本/完成证据/快照链
            "CREATE TABLE data_catalog_entries (dataset_id TEXT PRIMARY KEY)",
            "INSERT INTO data_catalog_entries VALUES ('stock_daily')",
            "CREATE TABLE ingestion_log (id INTEGER PRIMARY KEY)",
            "INSERT INTO ingestion_log VALUES (1)",
            "CREATE TABLE ingestion_partition_checkpoints (chunk_id TEXT PRIMARY KEY)",
            "INSERT INTO ingestion_partition_checkpoints VALUES ('chunk-1')",
            "CREATE TABLE provider_snapshots (snapshot_id TEXT PRIMARY KEY)",
            "INSERT INTO provider_snapshots VALUES ('snap-1')",
            "CREATE TABLE instrument (instrument_id INTEGER PRIMARY KEY)",
            "INSERT INTO instrument VALUES (1)",
            "CREATE TABLE trading_calendar (trade_date TEXT PRIMARY KEY)",
            "INSERT INTO trading_calendar VALUES ('2026-10-30')",
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
    payloads = root / "provider_payloads" / "tushare" / "stock_daily"
    payloads.mkdir(parents=True)
    (payloads / "abc.parquet").write_bytes(b"raw-provider-payload")


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


@pytest.mark.parametrize(
    "damage",
    [
        "amount",
        "missing_entry",
        "duplicate",
        "traversal",
        "schema",
        "missing_file",
        "symlink",
    ],
)
def test_restore_preflight_rejects_damaged_backup_without_writing_target(
    tmp_path: Path, damage: str
) -> None:
    import orjson

    source, backup, target = (
        tmp_path / name for name in ("source", "backup", "target")
    )
    _seed_non_empty_root(source)
    manifest = backup_workstation_state(data_root=source, backup_dir=backup)
    database = backup / "trading/trading.sqlite"
    if damage == "amount":
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE account_journal_events SET amount = 1")
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    elif damage == "missing_entry":
        manifest["entries"] = manifest["entries"][1:]
    elif damage == "duplicate":
        manifest["entries"].append(manifest["entries"][0])
    elif damage == "traversal":
        manifest["entries"][0]["path"] = "../source/metadata/metadata.sqlite"
    elif damage == "schema":
        manifest["schema"] = "wrong"
    elif damage == "missing_file":
        database.unlink()
    else:
        database.unlink()
        database.symlink_to(source / "trading/trading.sqlite")
    (backup / "manifest.json").write_bytes(orjson.dumps(manifest))
    with pytest.raises(RecipeError):
        restore_workstation_state(backup_dir=backup, data_root=target)
    assert not target.exists()
    with sqlite3.connect(source / "trading/trading.sqlite") as conn:
        assert (
            conn.execute("SELECT amount FROM account_journal_events").fetchone()[0]
            == 10000
        )


def test_verify_detects_restored_business_fact_drift(tmp_path: Path) -> None:
    source, backup, target = (
        tmp_path / name for name in ("source", "backup", "target")
    )
    _seed_non_empty_root(source)
    backup_workstation_state(data_root=source, backup_dir=backup)
    restore_workstation_state(backup_dir=backup, data_root=target)
    for relative, query, expected in (
        (
            "trading/trading.sqlite",
            "SELECT event_id, amount FROM account_journal_events",
            ("evt-001", 10000.0),
        ),
        (
            "metadata/metadata.sqlite",
            "SELECT event_id, strategy_id FROM strategy_activation_event",
            ("evt-1", "strat-active"),
        ),
        (
            "metadata/metadata.sqlite",
            "SELECT dataset_id FROM data_catalog_entries",
            ("stock_daily",),
        ),
        (
            "research/research.sqlite",
            "SELECT * FROM holdout_claim",
            ("claim-1", "2026-10-01"),
        ),
        ("agent/agent.sqlite", "SELECT * FROM agent_sessions", ("sess-1", 1)),
    ):
        with sqlite3.connect(target / relative) as conn:
            assert conn.execute(query).fetchone() == expected
    with sqlite3.connect(target / "trading/trading.sqlite") as conn:
        conn.execute("UPDATE account_journal_events SET amount = 1")
    assert not verify_workstation_state(data_root=target)["passed"]


class TestDataLayerDrill:
    """#630 数据层分支：未初始化域＋provider payload 证据树."""

    @staticmethod
    def _seed_data_layer_root(root: Path, *, with_payloads: bool = True) -> None:
        """只有 catalog＋账本的数据根（research/agent 域从未初始化）."""
        for relative in ("metadata/metadata.sqlite", "trading/trading.sqlite"):
            statements = next(
                seeds for path, seeds in _REQUIRED_DB_SEEDS if path == relative
            )
            database = root / relative
            database.parent.mkdir(parents=True)
            with sqlite3.connect(database) as connection:
                for statement in statements:
                    connection.execute(statement)
        if with_payloads:
            payloads = root / "provider_payloads" / "tushare"
            payloads.mkdir(parents=True)
            (payloads / "raw.parquet").write_bytes(b"payload-bytes")

    def test_data_layer_drill_with_uninitialized_domains(self, tmp_path: Path) -> None:
        source_root = tmp_path / "state"
        backup_dir = tmp_path / "backup"
        restored_root = tmp_path / "restored"
        self._seed_data_layer_root(source_root)

        manifest = backup_workstation_state(
            data_root=source_root, backup_dir=backup_dir
        )
        by_path = {entry["path"]: entry for entry in manifest["entries"]}
        assert by_path["research/research.sqlite"]["present"] is False
        assert by_path["agent/agent.sqlite"]["present"] is False
        assert by_path["provider_payloads"]["present"] is True

        restore_report = restore_workstation_state(
            backup_dir=backup_dir, data_root=restored_root
        )
        notes = {item["path"]: item for item in restore_report["restored"]}
        assert notes["research/research.sqlite"]["restored"] is False
        assert "域未初始化" in notes["research/research.sqlite"]["note"]

        summary = verify_workstation_state(data_root=restored_root)
        statuses = {
            (item["check"], item["status"], item["path"]) for item in summary["results"]
        }
        assert summary["passed"] is True
        # 数据层业务身份核对（不只库能打开）
        for fact in (
            "数据目录条目",
            "摄取证据账本",
            "分区完成证据",
            "供应商快照证据",
            "证券身份",
            "交易日历",
        ):
            assert (
                f"fact:{fact}",
                "PASS",
                "metadata/metadata.sqlite",
            ) in statuses
        # 未初始化域是 WARN，不是 FAIL
        assert ("file_present", "WARN", "research/research.sqlite") in statuses
        assert ("file_present", "WARN", "agent/agent.sqlite") in statuses
        # 不可重拉 payload 证据树原样恢复
        assert (
            restored_root / "provider_payloads" / "tushare" / "raw.parquet"
        ).read_bytes() == b"payload-bytes"

    def test_required_database_missing_in_initialized_domain_fails(
        self, tmp_path: Path
    ) -> None:
        """域目录存在而库缺失＝必需对象缺失，备份明确失败."""
        source_root = tmp_path / "state"
        self._seed_data_layer_root(source_root)
        (source_root / "research").mkdir()
        with pytest.raises(RecipeError, match="required database missing"):
            backup_workstation_state(
                data_root=source_root, backup_dir=tmp_path / "backup"
            )

    def test_absent_payload_tree_explicitly_non_replayable(
        self, tmp_path: Path
    ) -> None:
        """payload 留存缺失不阻断恢复，但对账/审计锚显式不可重放."""
        source_root = tmp_path / "state"
        self._seed_data_layer_root(source_root, with_payloads=False)

        manifest = backup_workstation_state(
            data_root=source_root, backup_dir=tmp_path / "backup"
        )
        by_path = {entry["path"]: entry for entry in manifest["entries"]}
        assert by_path["provider_payloads"]["present"] is False

        restore_report = restore_workstation_state(
            backup_dir=tmp_path / "backup", data_root=tmp_path / "restored"
        )
        payload_restore = next(
            item
            for item in restore_report["restored"]
            if item["path"] == "provider_payloads"
        )
        assert payload_restore["restored"] is False
        assert "不可重放" in payload_restore["note"]
        assert "对账" in payload_restore["note"]

    def test_tampered_payload_backup_rejected_before_restore(
        self, tmp_path: Path
    ) -> None:
        source, backup, target = (
            tmp_path / name for name in ("source", "backup", "target")
        )
        self._seed_data_layer_root(source)
        backup_workstation_state(data_root=source, backup_dir=backup)
        (backup / "provider_payloads" / "tushare" / "raw.parquet").write_bytes(
            b"tampered"
        )
        with pytest.raises(RecipeError, match="identity mismatch"):
            restore_workstation_state(backup_dir=backup, data_root=target)
        assert not target.exists()

    def test_v1_manifest_rejected(self, tmp_path: Path) -> None:
        import orjson

        source, backup = tmp_path / "source", tmp_path / "backup"
        self._seed_data_layer_root(source)
        backup_workstation_state(data_root=source, backup_dir=backup)
        manifest_path = backup / "manifest.json"
        manifest = orjson.loads(manifest_path.read_bytes())
        manifest["schema"] = "ditto.workstation-backup-recipe.v1"
        manifest_path.write_bytes(orjson.dumps(manifest))
        with pytest.raises(RecipeError, match="unsupported"):
            restore_workstation_state(backup_dir=backup, data_root=tmp_path / "t")
