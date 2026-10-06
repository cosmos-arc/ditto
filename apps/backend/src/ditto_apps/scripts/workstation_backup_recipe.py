"""
#446 工作站备份配方：停写→按真实运行时清单备份→校验→恢复演练.

单用户本地工作站的唯一备份入口。恢复边界＝灾后恢复当前可用状态：
账本/agent/策略治理/holdout 消费事实必须可恢复；旧实验 artifact 是
可选树，缺失不阻断恢复但旧实验显式不可重放。不提供自动调度、引用
垃圾回收或云备份。

用法（详见 docs/operations/workstation-backup-recipe.md）::

    python -m ditto_apps.scripts.workstation_backup_recipe backup \
        --data-root <root> --backup-dir <dir>
    python -m ditto_apps.scripts.workstation_backup_recipe restore \
        --backup-dir <dir> --data-root <root>
    python -m ditto_apps.scripts.workstation_backup_recipe verify \
        --data-root <root>
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import orjson
from ditto_platform.foundation.storage.payload_backup import (
    PayloadBackupError,
    backup_payload_tree,
    inspect_payload_tree,
    restore_payload_tree,
)
from ditto_platform.foundation.storage.sqlite_backup import (
    SQLiteBackupError,
    backup_database,
    inspect_database,
    restore_database,
)

__all__ = [
    "OPTIONAL_TREES",
    "RECIPE_DATABASES",
    "backup_workstation_state",
    "main",
    "restore_workstation_state",
    "verify_workstation_state",
]


# 真实运行时物理库清单（#446：6 个物理 SQLite 文件，非三个逻辑域）。
# env 覆盖（SQLITE_PATH/DITTO_TRADING_SQLITE_PATH）的部署在文档中
# 单独说明：本配方按默认相对路径操作，覆盖部署须先停写并显式传根。
RECIPE_DATABASES: tuple[str, ...] = (
    "metadata/metadata.sqlite",  # 数据 catalog + 策略治理/激活事实
    "research/research.sqlite",  # 实验规格/run + holdout 消费事实
    "trading/trading.sqlite",  # paper/manual 账本与账户事件日志
    "agent/agent.sqlite",  # agent 运行状态
    "agent/agent-presentation.sqlite3",
    "agent/agent-shadow/decision-opinion.sqlite",
)

# 可选恢复对象：缺失不阻断当前恢复，但旧实验不可重放。
OPTIONAL_TREES: tuple[str, ...] = ("research/artifacts",)

# 每库一条必须可读的业务事实检查（不只检查库能打开/行数相同）。
# (数据库相对路径, 事实名称, 查询)
REQUIRED_FACTS: tuple[tuple[str, str, str], ...] = (
    (
        "trading/trading.sqlite",
        "paper/manual 账本会话",
        "SELECT COUNT(*) FROM paper_sessions",
    ),
    (
        "trading/trading.sqlite",
        "账户事件日志",
        "SELECT COUNT(*) FROM account_journal_events",
    ),
    (
        "metadata/metadata.sqlite",
        "当前策略激活指针",
        "SELECT COUNT(*) FROM strategy_active_pointer",
    ),
    (
        "metadata/metadata.sqlite",
        "策略激活事件",
        "SELECT COUNT(*) FROM strategy_activation_event",
    ),
    (
        "research/research.sqlite",
        "holdout 消费事实",
        "SELECT COUNT(*) FROM holdout_claim",
    ),
    ("agent/agent.sqlite", "agent 会话状态", "SELECT COUNT(*) FROM agent_sessions"),
)


class RecipeError(RuntimeError):
    """备份配方执行失败（fail closed）。"""


def _require_dir(path: Path) -> Path:
    if not path.is_dir():
        raise RecipeError(f"directory does not exist: {path}")
    return path


def backup_workstation_state(
    *,
    data_root: Path,
    backup_dir: Path,
) -> dict[str, Any]:
    """按清单备份全部物理库与可选树，写 manifest 并逐项校验."""
    data_root = _require_dir(data_root)
    if backup_dir.exists():
        raise RecipeError(f"backup dir already exists: {backup_dir}")
    backup_dir.mkdir(parents=True)
    entries: list[dict[str, Any]] = []
    try:
        for relative in RECIPE_DATABASES:
            source = data_root / relative
            if not source.exists():
                raise RecipeError(f"required database missing: {source}")
            report = backup_database(source, backup_dir / relative)
            entries.append(
                {
                    "kind": "database",
                    "path": relative,
                    "sha256": report.sha256,
                    "size_bytes": report.size_bytes,
                    "logical_sha256": report.logical_sha256,
                    "integrity_check": report.integrity_check,
                }
            )
        for relative in OPTIONAL_TREES:
            source = data_root / relative
            if not source.exists():
                entries.append(
                    {"kind": "optional_tree", "path": relative, "present": False}
                )
                continue
            report = backup_payload_tree(source, backup_dir / relative)
            entries.append(
                {
                    "kind": "optional_tree",
                    "path": relative,
                    "present": True,
                    "sha256": report.root_sha256,
                    "file_count": len(report.files),
                }
            )
        manifest = {
            "schema": "ditto.workstation-backup-recipe.v1",
            "data_root": str(data_root),
            "entries": entries,
        }
        (backup_dir / "manifest.json").write_bytes(
            orjson.dumps(manifest, option=orjson.OPT_INDENT_2)
        )
    except (RecipeError, SQLiteBackupError, PayloadBackupError):
        raise
    except OSError as exc:
        raise RecipeError(f"backup failed: {exc}") from exc
    return manifest


def restore_workstation_state(
    *,
    backup_dir: Path,
    data_root: Path,
) -> dict[str, Any]:
    """按 manifest 恢复全部物理库；可选树缺失时显式声明不可重放."""
    backup_dir = _require_dir(backup_dir)
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RecipeError(f"manifest missing: {manifest_path}")
    manifest = _read_manifest(manifest_path)
    entries = manifest["entries"]
    _preflight(backup_dir, entries)
    if data_root.exists() and any(data_root.iterdir()):
        raise RecipeError(
            f"restore target must be empty: {data_root} "
            + "(move the old root aside, verify after restore)"
        )
    restored: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise RecipeError("malformed manifest entry")
        relative = str(entry.get("path"))
        source = backup_dir / relative
        if entry.get("kind") == "database":
            if not source.exists():
                raise RecipeError(f"required backup missing: {source}")
            report = restore_database(source, data_root / relative)
            if report.logical_sha256 != entry["logical_sha256"]:
                raise RecipeError(f"restored business facts mismatch: {relative}")
            restored.append(
                {
                    "path": relative,
                    "sha256": report.sha256,
                    "integrity_check": report.integrity_check,
                }
            )
        elif entry.get("kind") == "optional_tree":
            if entry.get("present") is False or not source.exists():
                restored.append(
                    {
                        "path": relative,
                        "restored": False,
                        "note": "旧实验 artifact 缺失: 当前状态可恢复, 旧实验不可重放",
                    }
                )
                continue
            report = restore_payload_tree(source, data_root / relative)
            restored.append({"path": relative, "restored": True})
        else:
            raise RecipeError(f"unknown manifest entry kind: {entry.get('kind')!r}")
    (data_root / "restore-manifest.json").write_bytes(orjson.dumps(manifest))
    return {"restored": restored}


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = orjson.loads(path.read_bytes())
    except (OSError, orjson.JSONDecodeError) as exc:
        raise RecipeError(f"invalid manifest: {path}") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "ditto.workstation-backup-recipe.v1"
    ):
        raise RecipeError("unsupported backup manifest schema")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise RecipeError("manifest has no entries")
    expected = {
        **dict.fromkeys(RECIPE_DATABASES, "database"),
        **dict.fromkeys(OPTIONAL_TREES, "optional_tree"),
    }
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RecipeError("malformed manifest entry")
        relative = entry.get("path")
        if (
            not isinstance(relative, str)
            or relative not in expected
            or relative in seen
        ):
            raise RecipeError(f"invalid or duplicate manifest path: {relative!r}")
        if entry.get("kind") != expected[relative]:
            raise RecipeError(f"incorrect manifest kind: {relative}")
        seen.add(relative)
        _validate_entry_identity(entry, relative)
    if not set(RECIPE_DATABASES).issubset(seen):
        raise RecipeError("required database manifest entry missing")
    return manifest


def _validate_entry_identity(entry: dict[str, Any], relative: str) -> None:
    """Require complete typed identities for each retained object."""
    keys = ("sha256", "logical_sha256")
    if entry["kind"] == "optional_tree":
        if type(entry.get("present")) is not bool:
            raise RecipeError(f"invalid optional presence: {relative}")
        keys = ("sha256",) if entry["present"] else ()
    if any(
        not re.fullmatch(r"sha256:[0-9a-f]{64}", str(entry.get(key))) for key in keys
    ):
        raise RecipeError(f"missing or invalid content identity: {relative}")


def _preflight(backup_dir: Path, entries: list[dict[str, Any]]) -> None:
    """Validate every required object before creating any restore target."""
    for entry in entries:
        relative = entry["path"]
        source = backup_dir / relative
        if source.resolve() != backup_dir.resolve() / relative:
            raise RecipeError(f"backup path escapes or follows a symlink: {relative}")
        try:
            if entry["kind"] == "database":
                if not source.is_file():
                    raise RecipeError(f"required backup missing: {relative}")
                report = inspect_database(source)
                if (report.sha256, report.logical_sha256, report.size_bytes) != (
                    entry["sha256"],
                    entry["logical_sha256"],
                    entry.get("size_bytes"),
                ):
                    raise RecipeError(f"backup identity mismatch: {relative}")
            elif entry.get("present") and source.exists():
                if inspect_payload_tree(source).root_sha256 != entry.get("sha256"):
                    raise RecipeError(f"backup identity mismatch: {relative}")
        except (SQLiteBackupError, PayloadBackupError) as exc:
            raise RecipeError(f"invalid backup object: {relative}: {exc}") from exc


def verify_workstation_state(
    *,
    data_root: Path,
) -> dict[str, Any]:
    """校验恢复结果：完整性＋每域必须可读的业务事实."""
    data_root = _require_dir(data_root)
    results: list[dict[str, Any]] = []
    expected = {}
    manifest_path = data_root / "restore-manifest.json"
    if manifest_path.exists():
        expected = {
            entry["path"]: entry
            for entry in _read_manifest(manifest_path)["entries"]
            if entry["kind"] == "database"
        }
    failed = False
    for relative in RECIPE_DATABASES:
        database = data_root / relative
        if not database.exists():
            results.append(
                {"path": relative, "check": "file_present", "status": "FAIL"}
            )
            failed = True
            continue
        try:
            report = inspect_database(database)
        except SQLiteBackupError:
            results.append({"path": relative, "check": "integrity", "status": "FAIL"})
            failed = True
            continue
        if relative in expected:
            matches = report.logical_sha256 == expected[relative]["logical_sha256"]
            results.append(
                {
                    "path": relative,
                    "check": "restored_content",
                    "status": "PASS" if matches else "FAIL",
                }
            )
            failed = failed or not matches
        results.append(
            {
                "path": relative,
                "check": "integrity",
                "status": "PASS",
                "sha256": report.sha256,
                "tables": len(report.table_row_counts),
            }
        )
    for database_relative, fact_name, query in REQUIRED_FACTS:
        database = data_root / database_relative
        if not database.exists():
            continue  # 缺库已在上方 FAIL
        try:
            with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
                count = connection.execute(query).fetchone()[0]
        except sqlite3.Error as exc:
            missing_table = "no such table" in str(exc)
            results.append(
                {
                    "path": database_relative,
                    "check": f"fact:{fact_name}",
                    "status": "WARN" if missing_table else "FAIL",
                    "error": str(exc),
                    **({"note": "该域未初始化(无此表)"} if missing_table else {}),
                }
            )
            failed = failed or not missing_table
            continue
        if count is None:
            results.append(
                {
                    "path": database_relative,
                    "check": f"fact:{fact_name}",
                    "status": "FAIL",
                    "error": "query returned no row",
                }
            )
            failed = True
            continue
        status = "PASS" if count > 0 else "WARN"
        results.append(
            {
                "path": database_relative,
                "check": f"fact:{fact_name}",
                "status": status,
                "rows": count,
                **({"note": "该域当前无记录"} if count == 0 else {}),
            }
        )
    summary = {"results": results, "passed": not failed}
    return summary


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup", help="停写后按清单备份")
    backup.add_argument("--data-root", type=Path, required=True)
    backup.add_argument("--backup-dir", type=Path, required=True)
    restore = sub.add_parser("restore", help="恢复到空目标根")
    restore.add_argument("--backup-dir", type=Path, required=True)
    restore.add_argument("--data-root", type=Path, required=True)
    verify = sub.add_parser("verify", help="校验恢复结果")
    verify.add_argument("--data-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """执行配方子命令, verify 失败时以非零退出."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.command == "backup":
            payload = backup_workstation_state(
                data_root=args.data_root, backup_dir=args.backup_dir
            )
        elif args.command == "restore":
            payload = restore_workstation_state(
                backup_dir=args.backup_dir, data_root=args.data_root
            )
        else:
            payload = verify_workstation_state(data_root=args.data_root)
    except RecipeError as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 1
    sys.stdout.write(orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode() + "\n")
    if args.command == "verify" and not payload["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
