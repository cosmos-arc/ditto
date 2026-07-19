# R3 Task 7 Research Schema v1 专项审批包

> 日期：2026-07-19
>
> 状态：等待数据库 schema 显式批准
>
> 适用任务：Research SQLite、insert-only stores 与 scheduler lease
> DDL：[2026-07-19-r3-task7-research-schema-v1.sql](2026-07-19-r3-task7-research-schema-v1.sql)

## 1. 审批范围

本审批只授权：

- 在 analysis 内实现 experiment control-plane 专用数据库 wrapper；
- 固定数据库路径为 `{data_root}/research/research.sqlite`；
- 实现审批 DDL 中的 9 张表、14 个显式索引与 27 个完整性 trigger；
- 实现 analysis-owned canonical launch/fold/attempt codec、typed persistence DTO、reader/writer 和 CAS projection protocol；
- 修改 `packages/analysis/src/ditto_analysis/di/storage.py`，以 nominal `ResearchExperimentDatabase` 装配独立连接池；
- 在 `tmp_path` 或显式可写的临时 data root 中执行自动化测试。

本审批不授权：

- 修改 `packages/data/src/ditto_data/scripts/schema.sql`；
- 修改、迁移、复制或重新绑定现有 metadata SQLite；
- 迁移 R2 已存在的 `research_spine_*`、`research_dataset_*` 四张 catalog 表；
- 在当前开发 data root、任何现有部署库或生产库上初始化 schema；
- 修改 DataStoreSettings、环境变量、Platform、依赖或 CI；
- 注册第二个裸 `SQLitePool` 或 `SQLiteClient`；
- 执行 Task 15 的 metadata strategy-governance schema。

## 2. 路径与物理隔离

唯一 research experiment DB 路径公式：

```text
{data_root}/research/research.sqlite
```

典型解析结果：

| 环境 | 路径 |
|---|---|
| development | `data/research/research.sqlite` |
| testing | `.tmp/ditto/research/research.sqlite` |
| production default | `/data/ditto/research/research.sqlite` |

Experiment DB 必须忽略 `SQLITE_PATH`。`SQLITE_PATH` 继续只影响 metadata DB。

当前开发环境的只读证据：

- `data` 解析到 `/mnt/d/wsl/data/ditto`；
- 文件系统为只读 `9p`；
- `data/metadata/metadata.sqlite` 大小为 `6,721,536` bytes；
- 当前 metadata SHA-256 为
  `4b1958963137ab20eab905829fcbeeedb127d70200f528be74117b6ab8e698fa`；
- `data/research/research.sqlite` 当前不存在。

因此 Task 7 的实现验证不得尝试写默认 development data root。

## 3. Schema 身份与初始化算法

Schema v1 标识：

```text
application_id = 1146376755 = 0x44545233 = "DTR3"
user_version   = 1
DDL SHA-256    = 697d10854fb12e324ddcff349bad55b9b442425b244cb5f1852d7192cfb7a8fd
```

Runtime schema fingerprint 固定为：查询排除 `sqlite_%` 的
`(type, name, tbl_name, sql)`，按 `type, name` 升序；用 Python
`json.dumps(rows, ensure_ascii=False, separators=(",", ":"))` 编码为 UTF-8 后计算
SHA-256。v1 的 50 个 schema rows 指纹必须为：

```text
b4e0c52b7ef2f844987ecd65cc96ece5c5f75a3d19dc15e380c4ffdf10adc39a
```

`ResearchExperimentDatabase.initialize()` 必须使用以下算法：

1. 创建 `{data_root}/research/`，但不接触 metadata 路径。
2. 每次从专用 pool 取得线程连接时，强制设置并读回验证
   `PRAGMA foreign_keys=ON` 与 `PRAGMA recursive_triggers=ON`；随后执行
   `BEGIN IMMEDIATE`。
3. 在持有写锁后重新读取：
   - `PRAGMA application_id`；
   - `PRAGMA user_version`；
   - 排除 `sqlite_%` 后的完整 `sqlite_schema`。
4. 根据锁内证据分支：
   - `0/0` 且无用户对象：逐条执行审批 DDL；
   - 当前 marker 且 schema fingerprint 完全一致：no-op；
   - 当前 marker 但 schema 漂移：fail closed；
   - 非空无标识库、未知 application ID、marker 组合异常或未来 version：fail closed；
   - 旧受支持 version：只能执行显式注册、带 checksum 的前向 migration。
5. DDL body 必须用 `sqlite3.complete_statement()` 识别完整语句边界（不能按分号
   朴素切割 trigger body），随后逐条调用 `Connection.execute()`；已开启事务后禁止
   调用 `Connection.executescript()`，因为它会隐式提交并丢失初始化锁。
6. 所有对象成功创建后，最后写入 `application_id` 和 `user_version`。
7. commit；任何异常显式 rollback，不允许半套 schema。
8. APP scope 关闭时调用 `SQLitePool.close_all()`，覆盖 worker 线程连接。

两个独立 wrapper 并发 initialize 时，第二个在获得锁后必须重新读取 marker，随后验证并 no-op。

## 4. 最终对象

Schema v1 精确创建 9 张业务表：

1. `experiment`
2. `experiment_candidate`
3. `experiment_fold`
4. `experiment_attempt`
5. `experiment_status_event`
6. `research_artifact`
7. `gate_evaluation`
8. `holdout_claim`
9. `experiment_scheduler_slot`

DDL 同时创建：

- 14 个显式索引；
- 27 个 conflict-reject、append-only、immutable-payload、CAS revision 或
  one-way pinning trigger。

当前 DDL 已在内存 SQLite 3.53.0 中验证：

```text
integrity_check   = ok
foreign_key_check = []
tables            = 9
indexes           = 14
triggers          = 27
application_id    = 1146376755
user_version      = 1
```

Adversarial in-memory smoke 还证明：

- ASCII/Unicode 首尾空白 opaque ID 被拒绝，词法与 Python `str.strip()` 对齐；
- 非真实 `YYYY-MM-DD` fold/holdout 日期被拒绝；
- failed/completed-with-failures projection/event 缺少 required failure code 被拒绝；
- owned scheduler state 缺少任一 lease 时间字段被拒绝；
- `../`、dot segment、backslash、drive、NUL 与 empty segment path 被拒绝；
- `INSERT OR REPLACE` 不能覆盖 status event，也不能重置 scheduler global row；
- 被拒绝操作后原 payload/revision 不变，integrity 与 foreign-key check 仍通过。

## 5. 关键数据不变量

### 5.1 Experiment aggregate

- `research_cycle_id/hash` 在 experiment 创建时冻结；clone、改名或候选参数变化不能创建伪造的新 research cycle。
- `queue_ordinal` 只允许在首次进入 queued 时从 `NULL` 分配为正整数，之后不可改变。
- queue ordinal 全局唯一；调度禁止依赖 rowid、UUID 或时间戳猜顺序。
- launch spec 使用带 schema version 的 canonical JSON；读取时重算 hash。
- experiment projection 只允许 CAS 更新，revision 必须恰好加一。
- lifecycle CAS 必须先调用 Task 6 `validate_status_transition()`，显式传入并验证
  `attempt_started` 和 `precondition_repairable`，随后在同一事务中更新 projection
  并 append status event。DDL trigger 只承担最后一道 immutable/revision 防线。

创建入口必须是原子 aggregate，而不是四个互不相关的逐行写入：

```python
create_experiment(
    cycle: ResearchCycleIdentity,
    spec: ExperimentLaunchSpec,
    initial_record: ExperimentRecord,
) -> None
```

`ResearchCycleIdentity` 是显式 typed value object，至少包含稳定的 `cycle_id` 和
canonical `cycle_hash`。它不能从 experiment 名称、candidate parameters 或随机 ID
隐式推导；cycle hash 的冻结输入是策略族、certified data cutoff 与 OOS 周期语义。

创建入口只接受 `draft + preflight + queue_ordinal NULL + revision 0`，并校验
spec/record 的 experiment ID、desired state 与 created-at 完全一致。

该事务同时写入 experiment 和全部 candidates，并证明：

- launch payload 与关系化 projection 一致；
- candidate ordinal 连续；
- candidate parameter hash 唯一；重复参数必须在领域 aggregate 构造阶段用同一
  canonical parameter codec 返回 typed `duplicate_candidate_parameters`，不能等到
  SQLite UNIQUE 才失败；
- 恰好一个 baseline；
- 任一失败时整个 aggregate 回滚。

### 5.2 Fold 与 attempt

- fold 明确区分 exploration、walk-forward 和 sealed holdout。
- walk-forward/holdout 固化训练窗口、测试窗口、purge 与 embargo sessions。
- fold relation projection 必须与 canonical `fold_spec_json/hash` 一致。
- 同一 fold 最多存在一个 queued/running attempt。
- retry 创建新 attempt，并保留 parent、resume source 与 reproduction fingerprint。
- retry/resume 必须跨行验证 parent ordinal 小于 child ordinal、experiment/candidate/fold
  完全相同、原 reproduction fingerprint 不变；任一漂移 fail closed。
- self-parent 被 DDL 拒绝。
- running/completed attempt 必须已有 backtest run identity。

### 5.3 Append-only audit

- status event、gate evaluation 与 holdout claim 在数据库层拒绝 UPDATE/DELETE。
- 所有 9 张表都在 `BEFORE INSERT` 阶段拒绝 identity/UNIQUE 冲突，避免 SQLite
  `INSERT OR REPLACE` 在默认或错误 pragma 下先删除旧事实；scheduler global row 也
  不能被 REPLACE 重置 revision。
- Store SQL 禁止 `INSERT OR REPLACE`、`INSERT OR IGNORE` 和冲突 UPSERT。幂等命令
  必须在 `BEGIN IMMEDIATE` 内先 SELECT 并比较 canonical payload hash：完全相同则
  返回既有事实，任何漂移 fail closed；不存在时只执行 plain `INSERT`。
- event 使用类型化 experiment/fold/attempt lineage，不使用无 FK 的多态 subject string。
- fold/attempt event 不能持久化 experiment-only status。
- gate 的 candidate/fold/attempt/artifact 必须属于同一 experiment。
- artifact 内容和 lineage 不可修改；只允许一次 `unpinned -> pinned` CAS。
- artifact service 必须拒绝 absolute、drive、backslash 和 traversal path；校验基于
  resolved canonical path 的 root containment，SQLite writer 不得绕过该 validator。
- artifact 发布顺序固定为 sibling temp write → fsync/close → hash/schema/row-count →
  atomic rename → index insert；任何失败不得让 partial 文件进入 index。

### 5.4 Holdout

- 同一 research cycle 只能有一个 claim。
- 同一 experiment、logical run 和 holdout fold 都只能有一个 claim。
- claim 通过复合 FK 绑定 experiment cycle 与 `fold_role='holdout'` 的真实 fold。
- 保存 operator confirmation、selection rationale 与 claim payload hash。
- deterministic replay 冲突时比较 payload hash；完全一致返回原 claim，任何漂移 fail closed。

### 5.5 Scheduler lease

- scheduler table 只有固定 `slot_id='global'` 一行。
- lease 时间统一为 UTC epoch microseconds，避免字符串时区或精度比较错误。
- claim/reclaim/renew/release 必须同时使用 owner token、expected revision 与 expiry fencing。
- fold claim、attempt/checkpoint/result 的每次 CAS 也必须验证当前 global slot 的
  owner token、revision 与未过期 lease；失去 lease 的旧 worker 不能继续写结果。
- reclaim 边界固定为 `lease_until_epoch_us <= now_epoch_us`。
- 成功更新 revision 恰好加一，旧 owner/revision 永远不能继续派发。

### 5.6 Tasks 8–14 固定持久化映射

Schema v1 冻结后，Tasks 8–14 不得以“方便查询”为由新增控制表：

- Task 8 preflight 与 Task 12 candidate-selection 作为 experiment status event 的
  canonical、hashed `detail_json`；
- Task 11 trial family 与 PromotionObjective 位于 versioned canonical launch spec；
- Task 11 comparison 和 multiple-testing ledger 保存为 content-addressed artifact；
- Task 14 immutable review bundle 保存为 experiment-scope、one-way pinned
  `research_artifact`，其 `content_hash` 就是 bundle hash；
- Task 13/14 的大型明细继续存 Parquet/JSON，SQLite 只保存 identity、hash、状态与索引。

## 6. Task 6 契约衔接

现有 `ExperimentWriterProtocol.add_*` 只接收简化 record，不能填满最终持久化模型。
Task 7 获批后会在 analysis 内补齐：

- versioned canonical launch codec；
- `get_launch_spec()` 与 hash-on-read；
- atomic aggregate create protocol；
- typed fold persistence spec；
- typed immutable attempt payload；
- 带 revision 的 projection DTO 和 CAS protocol；
- append-only status event reader。

最终持久化边界将替换现有信息不足的逐行 `add_*` surface，不保留两套并行真源。
核心 typed key/DTO 至少为：

```python
@dataclass(frozen=True, slots=True)
class ResearchCycleIdentity:
    cycle_id: str
    cycle_hash: ContentHash

@dataclass(frozen=True, slots=True)
class FoldKey:
    experiment_id: ExperimentId
    candidate_id: CandidateId
    fold_id: FoldId

@dataclass(frozen=True, slots=True)
class ExperimentProjection:
    record: ExperimentRecord
    queue_ordinal: int | None
    revision: int
    updated_at: datetime

@dataclass(frozen=True, slots=True)
class FoldPersistenceSpec:
    key: FoldKey
    ordinal: int
    fold_role: FoldRole
    train_window: DateWindow | None
    test_window: DateWindow
    purge_sessions: int
    embargo_sessions: int
    canonical_payload: bytes
    payload_hash: ContentHash

@dataclass(frozen=True, slots=True)
class FoldProjection:
    key: FoldKey
    status: ExperimentStatus
    claim_owner_token: str | None
    created_at: datetime
    updated_at: datetime
    revision: int

@dataclass(frozen=True, slots=True)
class FoldView:
    spec: FoldPersistenceSpec
    projection: FoldProjection

@dataclass(frozen=True, slots=True)
class AttemptPersistenceSpec:
    attempt_id: AttemptId
    fold_key: FoldKey
    ordinal: int
    parent_attempt_id: AttemptId | None
    resume_from_run_id: BacktestRunId | None
    reproduction_fingerprint: ContentHash
    created_at: datetime

@dataclass(frozen=True, slots=True)
class AttemptProjection:
    attempt_id: AttemptId
    status: ExperimentStatus
    backtest_run_id: BacktestRunId | None
    checkpoint_ref: CheckpointRef | None
    failure_code: ExperimentFailureCode | None
    created_at: datetime
    updated_at: datetime
    revision: int

@dataclass(frozen=True, slots=True)
class AttemptView:
    spec: AttemptPersistenceSpec
    projection: AttemptProjection
```

`add_fold` 的初始 projection 只能是 queued、unclaimed、revision 0 且
`updated_at == created_at`，并且 `initial.key == spec.key`。`add_attempt` 的初始
projection 只能是 queued、revision 0、`backtest_run_id is None` 且
`updated_at == created_at`；writer 必须验证 `initial.attempt_id == spec.attempt_id`、
`initial.created_at == spec.created_at`，并以 `spec.fold_key` 作为唯一的
experiment/candidate/fold 真源。Retry 还需在事务内验证 parent ordinal、lineage 与
fingerprint。

最终 reader/writer 语义：

```python
create_experiment(cycle, spec, initial_record) -> None
get_launch_spec(experiment_id) -> ExperimentLaunchSpec | None
get_experiment_projection(experiment_id) -> ExperimentProjection | None
transition_experiment(..., expected_revision, ...) -> ExperimentProjection

add_fold(spec: FoldPersistenceSpec, initial: FoldProjection) -> None
get_fold(key: FoldKey) -> FoldView | None
list_folds(experiment_id) -> tuple[FoldView, ...]
claim_fold(..., expected_revision, lease_fence, ...) -> FoldProjection
transition_fold(..., expected_revision, lease_fence, ...) -> FoldProjection

add_attempt(spec: AttemptPersistenceSpec, initial: AttemptProjection) -> None
get_attempt(attempt_id) -> AttemptView | None
list_attempts(key: FoldKey) -> tuple[AttemptView, ...]
transition_attempt(..., expected_revision, lease_fence, ...) -> AttemptProjection
```

Experiment、fold、attempt 三类 projection 的初建，以及每一次成功 CAS，都必须在
同一 SQLite transaction 中 append 恰好一个相同 subject revision 的 status event；
缺 event、重复 event 或 projection/event revision 不一致都必须整体 rollback。

SQLite store 不再把旧的 `add_experiment(record)`、`add_candidate(record)`、
`add_fold(record)`、`list_attempts(fold_id)` 当作完整 persistence surface。仓库内部
消费者同步迁移到 typed aggregate/key API，不保留有损兼容层。

这不会把 scheduler、application orchestration 或生产域依赖放入 analysis；只是让 Task 6 的纯领域合同具有类型安全的持久化适配边界。

## 7. Metadata 零破坏证明

集成测试必须在 `tmp_path` 中：

1. 创建 `data_root/metadata/metadata.sqlite` sentinel 表与记录。
2. 记录 metadata 主文件及 sidecar 的：
   - 文件集合；
   - SHA-256；
   - size；
   - mtime_ns；
   - sqlite_schema；
   - 逐表行数与 sentinel payload。
3. 初始化 experiment DB 两次，并执行双 wrapper 并发初始化。
4. 断言 metadata 上述证据逐字节零差异。
5. 断言 metadata 中没有 Task 7 表。
6. 断言 research DB 中没有 metadata sentinel。
7. 断言 `PRAGMA database_list` 只包含 research 主库，无 `ATTACH`。
8. 设置任意 `SQLITE_PATH`，仍必须创建到 `{data_root}/research/research.sqlite`。
9. 验证 `integrity_check=ok`、`foreign_key_check=[]` 和 schema fingerprint。

任何 metadata diff 都立即阻止 Task 7 继续。

## 8. 备份与恢复命令

以下命令是部署操作手册，不属于当前代码实施授权。执行前必须停止 API、scheduler 和 worker，并确认目标文件系统可写。

### 8.1 迁移前 metadata 防御性备份

```bash
pixi run -e dev python -m ditto_apps.cli.main ops verify-sqlite \
  --database /data/ditto/metadata/metadata.sqlite

pixi run -e dev python -m ditto_apps.cli.main ops backup-sqlite \
  --source /data/ditto/metadata/metadata.sqlite \
  --destination /data/ditto/backups/r3-task7-20260719/metadata.sqlite
```

如果部署环境已经存在 research DB，再执行：

```bash
pixi run -e dev python -m ditto_apps.cli.main ops backup-sqlite \
  --source /data/ditto/research/research.sqlite \
  --destination /data/ditto/backups/r3-task7-20260719/research.pre-task.sqlite
```

当前 research DB 不存在，因此不得伪造空备份。

### 8.2 初始化后的恢复演练

```bash
pixi run -e dev python -m ditto_apps.cli.main ops verify-sqlite \
  --database /data/ditto/research/research.sqlite

pixi run -e dev python -m ditto_apps.cli.main ops backup-sqlite \
  --source /data/ditto/research/research.sqlite \
  --destination /data/ditto/backups/r3-task7-20260719/research.sqlite

pixi run -e dev python -m ditto_apps.cli.main ops restore-sqlite \
  --backup /data/ditto/backups/r3-task7-20260719/research.sqlite \
  --destination /data/ditto/restore-drills/r3-task7-20260719/research.sqlite

pixi run -e dev python -m ditto_apps.cli.main ops verify-sqlite \
  --database /data/ditto/restore-drills/r3-task7-20260719/research.sqlite
```

现有工具使用 SQLite online backup、执行 integrity check、输出 SHA-256 和逐表行数，并拒绝覆盖已有目标。

## 9. Rollback

### 首次安装前不存在 research DB

1. 停止所有 writers。
2. 调用 `close_all()`。
3. 把新建的 `research/` 整体移动为带时间戳的 `research.failed-*` 证据目录。
4. 回退 Task 7 代码提交。
5. 不删除失败库。

### 已存在 research DB

1. 停止所有 writers 并关闭连接池。
2. 把失败库整体移动到独立 evidence 路径。
3. 将 pre-task backup 恢复到新的 canonical 路径。
4. 执行 verify、逐表行数与应用查询验证。
5. 失败库和备份均保留。

Metadata 如果出现任何差异必须 fail closed；本审批不授权直接覆盖 canonical metadata。

## 10. 获批后的 TDD 与验收门禁

Task 7 严格执行 RED → GREEN → REFACTOR：

- fresh init、重复 init、双 wrapper 并发 init；
- unknown/future/drifted schema fail closed；
- atomic aggregate create 与 rollback；
- canonical round-trip/hash mismatch；
- baseline 与 candidate parameter uniqueness；
- fold/attempt typed lineage；
- append-only triggers；
- `INSERT OR REPLACE`/IGNORE/UPSERT 覆盖 event、candidate、artifact、holdout 与
  scheduler slot 的负测，旧 payload/revision 必须保持不变；
- 每个 worker 线程连接都验证 `foreign_keys=ON`、`recursive_triggers=ON`；
- projection CAS 与 status-event 原子提交；
- 2-owner、8-owner 并发 lease 精确一个 winner；
- 到期前不可 reclaim，边界到期可 reclaim；
- stale owner/revision 无法 renew、release 或派发；
- metadata byte-for-byte 零差异；
- analysis unit/integration、type、architecture、lint；
- 完成后独立规范复审与质量复审。

目标测试命令：

```bash
pixi run -e dev pytest \
  packages/analysis/tests/unit/experiments/test_sqlite_store_unit.py \
  packages/analysis/tests/unit/experiments/test_scheduler_lease_unit.py \
  packages/analysis/tests/integration/test_experiment_database_migration.py \
  -q -n0 --no-cov
```

## 11. 所需显式批准

只有收到以下明确授权，才开始 Task 7 的 RED 测试和实现：

```text
批准 Task 7 Research Schema v1，仅授权仓库代码、tmp_path 测试和临时可写 data root，不操作当前或生产数据库。
```
