# R3 Research / Governance Backup 与 Restore

本 runbook 只处理 R3 的一个联合恢复单元：

- `${SQLITE_PATH}`：`DataStoreSettings.resolved_sqlite_path` 解析出的 metadata
  DB；未设置 override 时才是
  `<data-root>/metadata/metadata.sqlite`。它保存 strategy governance version、
  append-only review decision、activation event 与 active pointer。
- `<data-root>/research/research.sqlite`：Research Schema v1、holdout claim、
  artifact index 与 reproduction fingerprint。
- `<data-root>/research/artifacts`：indexed artifact、review packet 及其不可变
  sidecar manifest。

命令不会覆盖既有 backup 或 restore 目标。任一步失败时，只清理由本次命令新建的
partial root；已有备份、源 data root 和历史证据均不会删除。

## Deterministic acceptance 边界

Task 17 runner 只在 pytest 提供的任务专用 `tmp_path` 内执行联合 backup/restore：

```bash
pixi run -e dev pytest \
  packages/apps/tests/e2e/test_r3_governance_recovery.py::\
test_fixture_backup_restore_preserves_domain_identity \
  -q --no-cov
```

该演练会验证 metadata DB、Research DB、pinned artifacts、active pointer、review
decisions、holdout claim、review packet / artifact hash 和 reproduction fingerprint，
但不会读取或改写当前/生产 data root。它只能证明恢复实现的确定性工程闭环，不能
证明 production recovery。真实 data root、backup target、restore target 与 cutover
必须等待 Task 18 的独立授权，并严格执行下文停写与路径检查。

## 一致性边界

`sqlite_backup` 为每个 SQLite 文件生成独立 online snapshot，
`payload_backup` 为 artifact tree 生成逐文件 hash 证明；但三次复制本身不是一个
跨存储事务。标准操作必须先停止 API、scheduler、research worker 以及所有
governance/research 写入，并保持停写直到 backup `verify` 通过。

若业务不能停写，只能在三者共同的外部写屏障下执行，或先用存储系统的同一时点
snapshot 生成静态源，再对该静态源运行本工具。单独运行本工具不能证明三个活动
存储来自同一逻辑时点。

所有示例路径都必须替换成解析后的绝对路径。不要使用 `~`、仓库根目录、未解析
glob 或当前/生产 data root 作为演练 restore 目标。`--backup-root` 必须位于
`--data-root` 之外，`--destination-root` 必须位于 `--backup-root` 之外；组合层
会在任何目录创建或复制前拒绝相等/后代路径，防止递归备份和自包含恢复。
命令还会在 `resolve()` 前拒绝 source、backup、restore requested root 本身为
symlink，包括 dangling symlink。

每次操作都显式固定同一对路径，不能只改其中一个：

```bash
export DITTO_DATA_ROOT=/absolute/path/ditto-data
export SQLITE_PATH=/absolute/path/ditto-data/metadata/metadata.sqlite
```

如果部署使用位于 data root 外的 metadata override，就把 `SQLITE_PATH` 换成该
真实绝对路径。省略或遗留旧 `SQLITE_PATH` 会让进程继续读取旧 governance DB。

## 1. Dry run

停写后先检查源库完整性、表行数、artifact tree hash，并证明至少一个已 pin 的
indexed artifact 能以数据库中的 exact content hash 在文件树中找到：

```bash
pixi run -e dev python -m ditto_apps.scripts.r3_research_backup \
  dry-run \
  --data-root "${DITTO_DATA_ROOT}" \
  --sqlite-path "${SQLITE_PATH}"
```

命令非零退出时不要开始备份。先修复缺失库、schema、pinned index/file drift 或
SQLite integrity 问题。

## 2. Backup

backup root 必须不存在，且不能等于或位于 source data root 内：

```bash
pixi run -e dev python -m ditto_apps.scripts.r3_research_backup \
  backup \
  --data-root "${DITTO_DATA_ROOT}" \
  --sqlite-path "${SQLITE_PATH}" \
  --backup-root /absolute/path/backups/r3-20260728T040000Z
```

成功后的固定布局为：

```text
r3-20260728T040000Z/
├── manifest.json
├── metadata.sqlite
├── research.sqlite
└── artifacts/
```

这是独立、可搬运的 backup-unit 布局，因此将源 `${SQLITE_PATH}` 扁平保存为
unit 顶层 `metadata.sqlite`。它不改变 canonical runtime data-root 路径；
restore 时会重新放回
`metadata/metadata.sqlite`。

`manifest.json` 是无多余空白、key 排序的 canonical JSON，schema 为
`ditto.r3-research-backup`、version 为 `1`。它包含两个 SQLite integrity /
checksum / table-row-count report、完整 artifact tree report，以及按
`artifact_id` 排序的 pinned artifact exact path、byte size、content hash 和
reproduction fingerprint。manifest 还绑定 governance 与 Research Schema v1
的 `application_id`、`user_version`、完整 schema fingerprint、required
table/trigger 清单，以及 active pointer + active version、完整 decision
history、holdout claim 和 pinned review packet 的 domain recovery evidence。

## 3. Verify backup

仍在停写窗口内独立复验备份。命令会拒绝非 canonical manifest、额外/缺失顶层
文件、任意 symlink、非 regular 的 metadata/research/manifest、非 directory 的
artifacts、SQLite drift、artifact tree drift、pinned index/file hash drift：

```bash
pixi run -e dev python -m ditto_apps.scripts.r3_research_backup \
  verify \
  --backup-root /absolute/path/backups/r3-20260728T040000Z
```

只有该命令 exit `0` 后，备份才可进入受控、只读的 evidence storage。不要手工
修改 backup root；需要重跑时使用新的 root 名称。

## 4. Restore 与恢复验证

restore 始终写入一个全新的 data root；目标只要已存在、等于 backup root 或位于
backup root 内就会拒绝：

```bash
pixi run -e dev python -m ditto_apps.scripts.r3_research_backup \
  restore \
  --backup-root /absolute/path/backups/r3-20260728T040000Z \
  --destination-root /absolute/path/restore-drills/r3-20260728T040000Z
```

restore 会先复验 backup manifest，再恢复 canonical data-root 布局，并重新比较
两个 SQLite 的逻辑行数、artifact tree root hash 和全部 pinned artifact exact
identity。随后运行独立的 `verify-restored`：它会通过 `GovernanceService` 重开
active version/pointer，通过 canonical research DB reader 重开 holdout claim、
pinned artifact 和 review packet，并与 manifest 的 domain evidence 比较：

```text
r3-20260728T040000Z/
├── metadata/
│   └── metadata.sqlite
└── research/
    ├── research.sqlite
    └── artifacts/
```

```bash
RESTORED_DATA_ROOT=/absolute/path/restore-drills/r3-20260728T040000Z
RESTORED_SQLITE_PATH="${RESTORED_DATA_ROOT}/metadata/metadata.sqlite"

pixi run -e dev python -m ditto_apps.scripts.r3_research_backup \
  verify-restored \
  --backup-root /absolute/path/backups/r3-20260728T040000Z \
  --destination-root "${RESTORED_DATA_ROOT}" \
  --sqlite-path "${RESTORED_SQLITE_PATH}"

DITTO_DATA_ROOT="${RESTORED_DATA_ROOT}" \
SQLITE_PATH="${RESTORED_SQLITE_PATH}" \
pixi run -e dev python -m ditto_apps.cli.main ops status --json
```

`verify-restored` exit `0` 才构成 stores/domain 恢复证明；只看到文件存在或只跑
`ops status` 不构成恢复成功。

## 5. Cutover 与 rollback

Cutover 前保留原 data root 为只读，不移动、不覆盖、不删除：

```bash
DITTO_DATA_ROOT="${RESTORED_DATA_ROOT}" \
SQLITE_PATH="${RESTORED_SQLITE_PATH}" \
pixi run -e dev python -m ditto_apps.cli.main ops status --json
```

当前 composition root 同时读取 `DITTO_DATA_ROOT` 和 `SQLITE_PATH`。由部署系统
以一个原子配置变更把二者切到新路径后再启动单一 writer。若启动检查或业务
验收失败，停止所有新 root writer，并把配置切回仍保留的原 root：

```bash
ORIGINAL_DATA_ROOT=/absolute/path/original-ditto-data
ORIGINAL_SQLITE_PATH="${ORIGINAL_DATA_ROOT}/metadata/metadata.sqlite"

DITTO_DATA_ROOT="${ORIGINAL_DATA_ROOT}" \
SQLITE_PATH="${ORIGINAL_SQLITE_PATH}" \
pixi run -e dev python -m ditto_apps.scripts.r3_research_backup \
  dry-run \
  --data-root "${ORIGINAL_DATA_ROOT}" \
  --sqlite-path "${ORIGINAL_SQLITE_PATH}"

DITTO_DATA_ROOT="${ORIGINAL_DATA_ROOT}" \
SQLITE_PATH="${ORIGINAL_SQLITE_PATH}" \
pixi run -e dev python -m ditto_apps.cli.main ops status --json
```

Rollback 是配置指针回切，不是把文件复制回原路径。失败的新 root 和 backup
manifest 应保留为 incident evidence；确认保留策略前不要删除。
