# R3 A 股日频研究与策略治理 Beta Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在现有 R2 certified data、因子、StrategySpec 和单次回测主干上，交付个股多因子与 ETF 双黄金路径的可复现实验、一次性 holdout、策略治理、真实工作台和 G2 evidence。

**Architecture:** `ditto_analysis.experiments` 拥有纯研究控制面，`ditto_strategy` 拥有类型化 StrategySpec 和生产治理控制面，`ditto_application` 负责编排 experiment、backtest、features、evidence 与 promotion，`ditto_apps` 只暴露 API/CLI/job。R1 只读取 strategy active pointer，不依赖 analysis；大体量证据使用内容寻址 Parquet/JSON，SQLite 只保存状态、identity、hash 和索引。

**Tech Stack:** Python 3.13、frozen dataclass/Protocol、orjson、Polars、SQLite、Parquet、Dishka、FastAPI、Prefect、Pytest；React 19、TypeScript strict、TanStack Query/Router、Zustand、Tailwind v4、Vitest/RTL、Playwright。

---

> **设计事实源**：[2026-07-19 R3 design](2026-07-19-r3-a-share-research-strategy-governance-design.md)<br>
> **计划状态**：READY FOR EXECUTION；数据库 schema、新依赖、架构边界和环境配置仍须在对应 task 前单独批准<br>
> **跨仓库规则**：后端路径相对 `/home/chevy/projects/ditto`；标记为 `ditto-app` 的路径相对 `/home/chevy/projects/ditto-app`；两个仓库分别建分支、分别提交和验证。

## 实施规则

- 执行时使用独立开发分支或 worktree，不直接在 `main` 提交。
- 每个 task 遵循 RED → GREEN → REFACTOR，并形成独立提交。
- 先运行精确测试，再运行所属 package test；波次结束运行 `pixi run -e dev check`。
- 数据库 schema task 开始前展示最终 DDL、dry-run migration 和 backup plan，获得显式批准。
- 不新增前端 graph/DnD 依赖；若实现证明必须新增，暂停并请求批准。
- 默认测试使用确定性 fixture；真实 provider 和浏览器 acceptance 单独标记，不伪造 live evidence。
- R2 live Gate 与 W0–W4 并行，未关闭时只能形成 research-only evidence，不能通过 G2。
- `analysis` 不得导入 strategy/backtest；strategy 不得导入 features/data/backtest/execution。
- 不建立第二套回测、factor engine、checkpoint、artifact 或 API 类型系统。
- API 类型以 OpenAPI codegen 为准；禁止手改 `ditto-app/src/types/generated/api.d.ts`。

## W0：契约与确定性基座

### Task 1: StrategySpec v2、节点 value objects 与 canonical hash

**Files:**

- Create: `packages/strategy/src/ditto_strategy/alpha/nodes.py`
- Create: `packages/strategy/src/ditto_strategy/alpha/spec_codec.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/specs.py`
- Modify: `packages/strategy/src/ditto_strategy/models.py`
- Modify: `packages/application/src/ditto_application/builders/deserialization.py`
- Modify: `packages/backtest/src/ditto_backtest/manifest_build.py`
- Test: `packages/strategy/tests/unit/alpha/test_specs_unit.py`
- Create: `packages/strategy/tests/unit/alpha/test_nodes_unit.py`
- Create: `packages/strategy/tests/unit/alpha/test_spec_codec_unit.py`
- Test: `packages/backtest/tests/unit/test_manifest_unit.py`

**Step 1: Write the failing domain tests**

覆盖固定 category、`node_type@version`、唯一 `node_id`、合法 sequence、canonical key ordering、相同语义同 hash、任意执行字段变化必改 hash，以及 UI metadata 不参与执行 hash。

**Step 2: Run tests to verify RED**

Run:

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha/test_nodes_unit.py packages/strategy/tests/unit/alpha/test_spec_codec_unit.py packages/backtest/tests/unit/test_manifest_unit.py -q
```

Expected: FAIL，节点 value objects 和完整 canonical hash 尚不存在。

**Step 3: Implement the minimal contract**

定义 `NodeCategory`、`NodeRef`、`NodeInstance`、`PipelineSpec` 和 StrategySpec v2；codec 使用 `orjson.OPT_SORT_KEYS` 生成 canonical bytes 和 SHA-256。保留显式 legacy adapter，只用于旧 seed migration，不在新 API 接受松散 spec。

**Step 4: Replace the partial manifest hash**

让 manifest builder 接收 canonical `spec_hash`，删除仅 hash `strategy_id|version|rebalance_freq` 的语义；audit 时间和 run ID 不进入 reproduction fingerprint。

**Step 5: Run tests to verify GREEN**

Run: 同 Step 2。

Expected: PASS。

**Step 6: Run package regression and commit**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha packages/backtest/tests/unit/test_manifest_unit.py -q
git add packages/strategy packages/application/src/ditto_application/builders/deserialization.py packages/backtest docs/plans
git commit -m "feat(strategy): add canonical strategy spec v2"
```

### Task 2: NodeDescriptor registry 与受约束流水线编译器

**Files:**

- Create: `packages/strategy/src/ditto_strategy/alpha/node_registry.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/pipeline.py`
- Create: `packages/application/src/ditto_application/builders/node_pipeline_builder.py`
- Modify: `packages/application/src/ditto_application/builders/template_builders.py`
- Modify: `packages/application/src/ditto_application/builders/runtime_builder.py`
- Modify: `packages/application/src/ditto_application/providers_builder.py`
- Create: `packages/strategy/tests/unit/alpha/test_node_registry_unit.py`
- Test: `packages/strategy/tests/unit/alpha/test_pipeline_unit.py`
- Create: `packages/application/tests/unit/process/strategy/test_node_pipeline_builder_unit.py`
- Test: `packages/application/tests/unit/process/strategy/test_backtest_runtime_builder_unit.py`

**Step 1: Write the failing registry/compiler tests**

证明 built-in descriptor 具有 typed I/O/config schema、固定顺序和 cardinality；`Filter*` 可重复，其他黄金节点唯一；unknown node/version、非 builtin origin、端口不匹配和非法排序均 fail closed。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha/test_node_registry_unit.py packages/application/tests/unit/process/strategy/test_node_pipeline_builder_unit.py -q
```

Expected: FAIL，registry/compiler 模块不存在。

**Step 3: Implement NodeDescriptor and registry manifest**

冻结 descriptor 字段、registry lookup 和 manifest hash。显示文案不影响 identity；executor 只通过稳定 `implementation_key` 解析，禁止动态 import。

**Step 4: Adapt existing template builders**

将现有 stock/ETF stage factory 作为 built-in implementation adapter；`NodePipelineBuilder` 只按 compiled sequence 构造既有 `DecisionStage`，不实现第二套 DAG runner。

**Step 5: Run tests to verify GREEN**

Run: 同 Step 2。

Expected: PASS。

**Step 6: Run architecture checks and commit**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha/test_pipeline_unit.py packages/application/tests/unit/process/strategy/test_backtest_runtime_builder_unit.py -q
pixi run -e dev arch-check
git add packages/strategy packages/application
git commit -m "feat(strategy): compile constrained typed pipelines"
```

### Task 3: Typed parameter binding 与 ResearchRuntimeBuilder

**Files:**

- Create: `packages/strategy/src/ditto_strategy/alpha/parameters.py`
- Create: `packages/application/src/ditto_application/builders/research_runtime_builder.py`
- Modify: `packages/application/src/ditto_application/commands/backtest.py`
- Modify: `packages/application/src/ditto_application/processes/execution/backtest_process.py`
- Modify: `packages/application/src/ditto_application/processes/execution/backtest_audit.py`
- Modify: `packages/application/src/ditto_application/builders/service_factory.py`
- Modify: `packages/application/src/ditto_application/providers_builder.py`
- Create: `packages/strategy/tests/unit/alpha/test_parameters_unit.py`
- Modify: `packages/application/tests/unit/commands/test_backtest_unit.py`
- Create: `packages/application/tests/unit/process/strategy/test_research_runtime_builder_unit.py`
- Modify: `packages/application/tests/unit/process/strategy/test_backtest_service_unit.py`

**Step 1: Write the failing binding tests**

覆盖 JSON path、bool/int/float/string/enum、范围、未知参数、重复参数、canonical value、parameter hash，以及 `top_k`/lookback 覆盖后实际 pipeline config 变化。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha/test_parameters_unit.py packages/application/tests/unit/process/strategy/test_research_runtime_builder_unit.py packages/application/tests/unit/commands/test_backtest_unit.py -q
```

Expected: FAIL，当前 override 只记录而未绑定到 resolved spec。

**Step 3: Implement ParameterSchema and binder**

参数展开后创建新的 frozen resolved spec，不修改 base version；未知 path、类型错误和越界抛稳定 `SPEC_INVALID` details。

**Step 4: Add an explicit research builder**

`ResearchRuntimeBuilder` 接收显式 draft/review version、candidate parameters 和 snapshot；生产 `StrategyRuntimeBuilder` 继续只构建 active published version，禁止增加 `allow_unpublished` 布尔开关。

**Step 5: Wire manifest and audit to effective values**

manifest 同时保存 base spec hash、resolved spec hash、parameter hash 和 canonical effective values；API/CLI 的旧字符串 override 在边界解析后立即转 typed DTO。

**Step 6: Run tests and commit**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha/test_parameters_unit.py packages/application/tests/unit/commands/test_backtest_unit.py packages/application/tests/unit/process/strategy/test_research_runtime_builder_unit.py packages/application/tests/unit/process/strategy/test_backtest_service_unit.py -q
git add packages/strategy packages/application
git commit -m "feat(research): bind typed candidate parameters"
```

## W1：核心因子与选股解释

### Task 4: 冻结 R3 核心因子目录与 preprocessing contract

**Files:**

- Create: `packages/features/src/ditto_features/factors/core_daily.py`
- Modify: `packages/features/src/ditto_features/factors/momentum.py`
- Modify: `packages/features/src/ditto_features/factors/factor_specs.py`
- Modify: `packages/features/src/ditto_features/factors/production_guard.py`
- Modify: `packages/features/src/ditto_features/evaluation/report.py`
- Create: `packages/features/tests/unit/factors/test_r3_core_factor_catalog_unit.py`
- Test: `packages/features/tests/unit/factors/test_factor_definitions.py`
- Test: `packages/features/tests/unit/factors/test_factor_data_availability.py`
- Test: `packages/features/tests/unit/evaluation/test_report_builder_unit.py`

**Step 1: Write failing core-catalog tests**

断言恰好 12 个 core descriptor、stock/ETF lane tags、required datasets、lookback、PIT requirement 和 preprocessing capability；基本面未认证时 unavailable，不能回填当前值。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/features/tests/unit/factors/test_r3_core_factor_catalog_unit.py packages/features/tests/unit/factors/test_factor_data_availability.py -q
```

Expected: FAIL，受控核心目录和 `relative_strength_60d` 尚不存在。

**Step 3: Reuse existing factor specs**

核心目录引用 `momentum_1m`、`momentum_3m`、`reversal_1w`、`volatility_factor`、`vol_ratio`、`liquidity`、`ep_ttm`、`bp_ratio`、`quality_roe`、`revenue_growth` 和 `log_free_float_cap`；只新增缺失的 benchmark-relative `relative_strength_60d`。

**Step 4: Freeze preprocessing descriptors**

建模 missing policy、winsorization、standardization、industry/size neutralization 和适用 lane；所有配置进入 resolved spec/hash，规模因子禁止 size-neutralize。

**Step 5: Extend diagnostics projection**

复用现有 evaluator 输出 coverage、IC/ICIR、decay、quantile、turnover、cost 和 exposure，不在 strategy 包复制因子统计。

**Step 6: Run tests and commit**

```bash
pixi run -e dev pytest packages/features/tests/unit/factors/test_r3_core_factor_catalog_unit.py packages/features/tests/unit/factors/test_factor_definitions.py packages/features/tests/unit/evaluation/test_report_builder_unit.py -q
git add packages/features
git commit -m "feat(features): curate r3 daily factor catalog"
```

### Task 5: 候选池、排除原因与 factor contribution evidence

**Files:**

- Create: `packages/strategy/src/ditto_strategy/alpha/selection_evidence.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/builtins/filtering.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/builtins/selection.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/pipeline.py`
- Modify: `packages/application/src/ditto_application/processes/execution/backtest_serialization.py`
- Create: `packages/strategy/tests/unit/alpha/test_selection_evidence_unit.py`
- Modify: `packages/strategy/tests/unit/alpha/test_pipeline_unit.py`
- Modify: `packages/strategy/tests/unit/alpha/test_stock_selection_trend_unit.py`
- Modify: `packages/application/tests/unit/process/execution/test_backtest_serialization_unit.py`

**Step 1: Write failing evidence tests**

覆盖 initial universe、每级 exclusion、稳定 reason code、缺失数据、流动性/ST/停牌过滤、低于 top-k、原始/处理后 factor value、weight、contribution、score、rank 和 selected state。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha/test_selection_evidence_unit.py packages/strategy/tests/unit/alpha/test_stock_selection_trend_unit.py -q
```

Expected: FAIL，当前 filter 直接丢行且 selector 只排序取 `head(top_k)`。

**Step 3: Add immutable evidence records**

让 stage 返回业务输出和窄 evidence sink/event，不把 DataFrame 持久化细节放入 strategy；reason code 使用 typed enum，message 只作展示。

**Step 4: Preserve pipeline compatibility**

未注入 evidence sink 时保持原有策略结果；注入时保证 evidence 不影响排序、权重或运行确定性。

**Step 5: Serialize columnar artifacts**

application 将 selection/exclusion/contribution 转为稳定 Polars schema，供后续 Parquet writer 使用。

**Step 6: Run tests and commit**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha/test_selection_evidence_unit.py packages/strategy/tests/unit/alpha/test_pipeline_unit.py packages/application/tests/unit/process/execution/test_backtest_serialization_unit.py -q
git add packages/strategy packages/application
git commit -m "feat(strategy): emit auditable selection evidence"
```

## W2：Experiment 控制面与本机调度

### Task 6: Experiment、candidate、fold 与 attempt 领域契约

**Files:**

- Create: `packages/analysis/src/ditto_analysis/experiments/models.py`
- Create: `packages/analysis/src/ditto_analysis/experiments/specs.py`
- Create: `packages/analysis/src/ditto_analysis/experiments/protocols.py`
- Modify: `packages/analysis/src/ditto_analysis/experiments/__init__.py`
- Modify: `packages/analysis/src/ditto_analysis/errors.py`
- Modify: `packages/analysis/tests/unit/test_placeholder_honesty_unit.py`
- Create: `packages/analysis/tests/unit/experiments/test_models_unit.py`
- Create: `packages/analysis/tests/unit/experiments/test_specs_unit.py`
- Create: `packages/analysis/tests/unit/experiments/test_state_machine_unit.py`

**Step 1: Write failing domain tests**

覆盖 experiment/candidate/fold/attempt identity、immutable launch spec、合法状态迁移、`blocked` 与 `failed` 区分、stable ordinal、baseline 计入 candidate count、desired state 和 failure code。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments packages/analysis/tests/unit/test_placeholder_honesty_unit.py -q
```

Expected: FAIL，`experiments` 仍是 reserved placeholder。

**Step 3: Implement pure analysis contracts**

只使用 analysis/kernel/platform 类型；strategy version、backtest run 和 snapshot 以 opaque ID/hash/value objects 保存，禁止导入生产包。

**Step 4: Replace placeholder honesty assertions**

删除“experiments 必须为空”的旧断言，改为验证 public surface 不暴露 application 行为或生产依赖。

**Step 5: Run tests and commit**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments packages/analysis/tests/unit/test_analysis_import_boundary_unit.py -q
pixi run -e dev arch-check
git add packages/analysis
git commit -m "feat(analysis): define experiment control-plane"
```

### Task 7: Research SQLite、insert-only stores 与 scheduler lease

> **Approval checkpoint:** 在执行本 task 前，提交最终 DDL、`data/research/research.sqlite` 路径、旧库零破坏证明、backup/restore 命令和 rollback 方案，获得数据库 schema 显式批准。

**Files:**

- Create: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/database.py`
- Create: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/schema.py`
- Create: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/reader.py`
- Create: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/writer.py`
- Create: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/__init__.py`
- Modify: `packages/analysis/src/ditto_analysis/di/storage.py`
- Create: `packages/analysis/tests/unit/experiments/test_sqlite_store_unit.py`
- Create: `packages/analysis/tests/unit/experiments/test_scheduler_lease_unit.py`
- Create: `packages/analysis/tests/integration/test_experiment_database_migration.py`

**Step 1: Write failing persistence tests**

覆盖 insert-only experiment spec、candidate parameter uniqueness、fold/attempt lineage、append-only status event、CAS revision、单 slot lease、过期 lease reclaim、并发 claim 和 holdout unique constraints 的 schema 基础。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_sqlite_store_unit.py packages/analysis/tests/unit/experiments/test_scheduler_lease_unit.py packages/analysis/tests/integration/test_experiment_database_migration.py -q
```

Expected: FAIL，独立 research DB 和 stores 不存在。

**Step 3: Implement the dedicated pool wrapper**

在 analysis 内部封装 `SQLitePool` 为独立 `ResearchExperimentDatabase`，固定路径为 `data_root/research/research.sqlite`；通过 Dishka 生命周期关闭，避免与 metadata pool 类型冲突。

**Step 4: Implement additive schema and stores**

创建 experiment、candidate、fold、attempt、event、gate、holdout、artifact 和 scheduler slot 表；immutable payload 禁止 `INSERT OR REPLACE`，projection 只通过 CAS 更新。

**Step 5: Verify migration and concurrency**

Run: 同 Step 2。

Expected: PASS；重复 init no-op，旧 metadata DB 零 diff，lease concurrency 只有一个 winner。

**Step 6: Commit**

```bash
git add packages/analysis
git commit -m "feat(analysis): persist experiment control-plane"
```

### Task 8: 96 月 validation compiler、矩阵展开与预算 preflight

**Files:**

- Create: `packages/application/src/ditto_application/processes/experiments/__init__.py`
- Create: `packages/application/src/ditto_application/processes/experiments/planning.py`
- Create: `packages/application/src/ditto_application/processes/experiments/validation_protocol.py`
- Create: `packages/application/src/ditto_application/commands/experiments.py`
- Create: `packages/application/src/ditto_application/queries/experiments.py`
- Modify: `packages/application/src/ditto_application/providers_process.py`
- Create: `packages/application/tests/unit/process/experiments/test_planning_unit.py`
- Create: `packages/application/tests/unit/process/experiments/test_validation_protocol_unit.py`
- Create: `packages/application/tests/unit/commands/test_experiments_unit.py`

**Step 1: Write failing planning tests**

覆盖 strategy-eligible start、逐标的 listing/warmup、至少 60+24+12 月、两个年度 fold、动态 purge/embargo、research-only 降级、baseline、笛卡尔积、128 上限、worker 2/4 上限和预算估算。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_planning_unit.py packages/application/tests/unit/process/experiments/test_validation_protocol_unit.py packages/application/tests/unit/commands/test_experiments_unit.py -q
```

Expected: FAIL，planning process 尚不存在。

**Step 3: Implement deterministic candidate expansion**

按 parameter name 和 canonical value 稳定排序，baseline 先展开且计入 128；超限返回 `MATRIX_TOO_LARGE`，禁止截断或随机抽样。

**Step 4: Compile calendar-aware folds**

使用交易日历把完整月转换为具体日期；purge/embargo 取 forward horizon、holding period 和 execution lag 的真实最大语义，并固化到 fold rows。

**Step 5: Add preflight read model**

返回每项 pass/fail/warn、候选数、fold/run 数、估算交易日、磁盘预算和明确 remediation；blocked preflight 不写 run attempt。

**Step 6: Run tests and commit**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments packages/application/tests/unit/commands/test_experiments_unit.py -q
git add packages/application
git commit -m "feat(research): plan bounded walk-forward experiments"
```

### Task 9: Durable experiment coordinator 与 2–4 worker 调度

**Files:**

- Create: `packages/application/src/ditto_application/processes/experiments/coordinator.py`
- Create: `packages/application/src/ditto_application/processes/experiments/worker.py`
- Modify: `packages/application/src/ditto_application/providers_process.py`
- Create: `packages/apps/src/ditto_apps/jobs/flows/experiments.py`
- Create: `packages/application/tests/unit/process/experiments/test_coordinator_unit.py`
- Create: `packages/application/tests/unit/process/experiments/test_worker_unit.py`
- Create: `packages/apps/tests/unit/jobs/flows/test_experiment_flow_unit.py`
- Create: `packages/application/tests/integration/test_experiment_scheduler_integration.py`

**Step 1: Write failing scheduler tests**

证明一次只有一个 experiment 持有 lease、默认 2/最大 4 worker、candidate/fold 按 ordinal 派发、重复 tick 不重复 claim、lease lost 停止派发、局部失败隔离、系统错误 fail-fast。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_coordinator_unit.py packages/application/tests/unit/process/experiments/test_worker_unit.py packages/application/tests/integration/test_experiment_scheduler_integration.py -q
```

Expected: FAIL，durable coordinator 不存在。

**Step 3: Implement lease-based coordination**

coordinator 用 owner token/revision/lease_until 持有唯一 slot；worker 通过 CAS claim fold，调用现有 `BacktestProcess`，不使用无界默认 executor。

**Step 4: Add stable progress projection**

进度来自持久 fold/attempt 状态，不从内存 future 推测；candidate/experiment outcome 由 child 状态确定性聚合。

**Step 5: Run tests and commit**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments packages/application/tests/integration/test_experiment_scheduler_integration.py packages/apps/tests/unit/jobs/flows/test_experiment_flow_unit.py -q
git add packages/application packages/apps
git commit -m "feat(research): schedule durable local experiments"
```

### Task 10: Pause、cancel、checkpoint、retry 与 crash recovery

**Files:**

- Modify: `packages/application/src/ditto_application/processes/experiments/coordinator.py`
- Modify: `packages/application/src/ditto_application/processes/experiments/worker.py`
- Modify: `packages/application/src/ditto_application/commands/experiments.py`
- Modify: `packages/application/src/ditto_application/processes/execution/backtest_process.py`
- Modify: `packages/application/src/ditto_application/processes/execution/replay_process.py`
- Create: `packages/application/tests/unit/process/experiments/test_recovery_unit.py`
- Modify: `packages/application/tests/unit/process/execution/test_replay_process_unit.py`
- Create: `packages/application/tests/integration/test_experiment_crash_recovery.py`

**Step 1: Write failing recovery tests**

覆盖 pause 停止新 dispatch、running child cooperative cancel、每日 checkpoint、resume 新 attempt、retry 保留 parent、cancel 不自动恢复、进程崩溃后 lease reclaim 和同 fold 不产生两个 live attempt。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_recovery_unit.py packages/application/tests/integration/test_experiment_crash_recovery.py -q
```

Expected: FAIL，experiment desired-state 与现有 backtest checkpoint 尚未接通。

**Step 3: Wire cooperative control**

pause/cancel 先持久化 desired state，再通知 child run；checkpoint 继续使用现有 strategy run checkpoint，不新增 experiment checkpoint payload。

**Step 4: Preserve attempt lineage**

resume/retry 必须创建新 attempt，并记录 `parent_attempt_id`、`resume_from_run_id` 和原 reproduction fingerprint；旧 artifact 只读保留。

**Step 5: Run tests and commit**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_recovery_unit.py packages/application/tests/unit/process/execution/test_replay_process_unit.py packages/application/tests/integration/test_experiment_crash_recovery.py -q
git add packages/application
git commit -m "feat(research): recover interrupted experiment runs"
```

## W3：Walk-forward、holdout 与不可变 evidence

### Task 11: Baseline comparison、walk-forward 聚合与 multiple-testing ledger

**Files:**

- Create: `packages/application/src/ditto_application/processes/experiments/comparison.py`
- Create: `packages/application/src/ditto_application/processes/experiments/walk_forward.py`
- Create: `packages/analysis/src/ditto_analysis/experiments/trial_ledger.py`
- Modify: `packages/features/src/ditto_features/evaluation/report.py`
- Create: `packages/application/tests/unit/process/experiments/test_comparison_unit.py`
- Create: `packages/application/tests/unit/process/experiments/test_walk_forward_unit.py`
- Create: `packages/analysis/tests/unit/experiments/test_trial_ledger_unit.py`

**Step 1: Write failing aggregation tests**

覆盖 stock equal-weight、ETF current-active baseline、两个 fold、net return、drawdown、turnover、cost drag、capacity、factor diagnostics、失败候选、全部 trial count、预注册 objective 和 tie-break 顺序。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_comparison_unit.py packages/application/tests/unit/process/experiments/test_walk_forward_unit.py packages/analysis/tests/unit/experiments/test_trial_ledger_unit.py -q
```

Expected: FAIL，跨 run comparison 与 trial ledger 尚不存在。

**Step 3: Implement deterministic comparison projection**

按 frozen metric schema 聚合现有 backtest/features reports；缺失证据显式为 `not_evaluated`，不把失败 candidate 从 trial count 删除。

**Step 4: Add adjusted evidence**

计算可支持的 Deflated Sharpe evidence；PBO 仅在分区数量满足方法前提时计算，否则返回带原因的 `not_evaluated`，不得伪造数值。

**Step 5: Run tests and commit**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_comparison_unit.py packages/application/tests/unit/process/experiments/test_walk_forward_unit.py packages/analysis/tests/unit/experiments/test_trial_ledger_unit.py -q
git add packages/application packages/analysis packages/features
git commit -m "feat(research): compare walk-forward candidates"
```

### Task 12: Atomic HoldoutClaim 与唯一候选消费

**Files:**

- Create: `packages/analysis/src/ditto_analysis/experiments/holdout.py`
- Modify: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/writer.py`
- Modify: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/reader.py`
- Create: `packages/application/src/ditto_application/processes/experiments/holdout.py`
- Modify: `packages/application/src/ditto_application/commands/experiments.py`
- Create: `packages/analysis/tests/unit/experiments/test_holdout_unit.py`
- Create: `packages/application/tests/unit/process/experiments/test_holdout_unit.py`
- Create: `packages/application/tests/integration/test_holdout_claim_integration.py`

**Step 1: Write failing holdout tests**

覆盖 claim 在运行前写入、同一 research cycle 唯一 candidate、clone/rename/参数变化不能重置、并发 claim 只有一个 winner、失败后只能恢复同一 logical run，以及 deterministic replay 不创建第二 claim。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_holdout_unit.py packages/application/tests/unit/process/experiments/test_holdout_unit.py packages/application/tests/integration/test_holdout_claim_integration.py -q
```

Expected: FAIL，holdout ledger 与 command 不存在。

**Step 3: Implement claim-before-dispatch**

在 SQLite transaction 内校验 experiment stage、candidate selection、snapshot/window 和 existing claim；成功后分配 logical run ID，再允许 scheduler dispatch。

**Step 4: Enforce recovery invariants**

retry/resume 必须比较 candidate、resolved spec、snapshot、window 和 reproduction fingerprint；任一漂移返回 `HOLDOUT_ALREADY_CLAIMED` 或 `INPUT_HASH_MISMATCH`。

**Step 5: Run tests and commit**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_holdout_unit.py packages/application/tests/unit/process/experiments/test_holdout_unit.py packages/application/tests/integration/test_holdout_claim_integration.py -q
git add packages/analysis packages/application
git commit -m "feat(research): enforce one-time holdout claims"
```

### Task 13: 内容寻址 artifact index、atomic writes 与 replay fingerprint

**Files:**

- Create: `packages/analysis/src/ditto_analysis/experiments/artifact_manifest.py`
- Modify: `packages/analysis/src/ditto_analysis/research/artifact_service.py`
- Modify: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/writer.py`
- Modify: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/reader.py`
- Modify: `packages/backtest/src/ditto_backtest/manifest_types.py`
- Modify: `packages/backtest/src/ditto_backtest/replay.py`
- Modify: `packages/application/src/ditto_application/processes/execution/backtest_lineage.py`
- Modify: `packages/application/src/ditto_application/processes/execution/replay_process.py`
- Create: `packages/analysis/tests/unit/experiments/test_artifact_manifest_unit.py`
- Modify: `packages/analysis/tests/unit/test_artifact_service_unit.py`
- Modify: `packages/backtest/tests/unit/test_replay_unit.py`
- Modify: `packages/application/tests/integration/test_replay_evidence_summary_golden.py`

**Step 1: Write failing artifact tests**

证明临时写入不会出现在 index、成功写入含 SHA-256/schema hash/row count、checksum 冲突 fail closed、retry 不覆盖旧路径、review evidence pin、损坏文件读取失败，以及 replay 忽略 audit 时间但比较决定性语义。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_artifact_manifest_unit.py packages/analysis/tests/unit/test_artifact_service_unit.py packages/backtest/tests/unit/test_replay_unit.py -q
```

Expected: FAIL，当前 artifact service 仍依赖 glob/mtime 且缺少 index/hash 校验。

**Step 3: Implement atomic content-addressed writes**

Parquet/JSON 先写 sibling temp path，fsync/close 后计算 hash 和 schema，原子 rename，再 insert artifact index；路径必须位于 artifact root 内，禁止 traversal。

**Step 4: Separate audit manifest and fingerprint**

audit manifest 保留 run/attempt/time；fingerprint 仅包括 commit/environment、canonical spec、registry、snapshot、factor versions、seed、cost、execution、PIT 和 input hashes。

**Step 5: Run tests and commit**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/test_artifact_service_unit.py packages/backtest/tests/unit/test_replay_unit.py packages/application/tests/integration/test_replay_evidence_summary_golden.py -q
git add packages/analysis packages/backtest packages/application
git commit -m "feat(research): index immutable experiment artifacts"
```

### Task 14: 两层 gate、review packet 与 immutable evidence bundle

**Files:**

- Create: `packages/analysis/src/ditto_analysis/experiments/gates.py`
- Create: `packages/analysis/src/ditto_analysis/experiments/evidence.py`
- Create: `packages/application/src/ditto_application/processes/experiments/evidence.py`
- Modify: `packages/application/src/ditto_application/queries/experiments.py`
- Create: `packages/analysis/tests/unit/experiments/test_gates_unit.py`
- Create: `packages/analysis/tests/unit/experiments/test_evidence_unit.py`
- Create: `packages/application/tests/unit/process/experiments/test_evidence_unit.py`
- Create: `packages/application/tests/unit/query/test_experiment_review_packet_unit.py`

**Step 1: Write failing gate tests**

覆盖 certified data、96 月、PIT、split、reproduction、cost、baseline、trial declaration、holdout 和 artifact completeness 的 hard gate；统计证据缺失只能是 fail/warn/not-evaluated 的显式结果，不能隐式通过。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_gates_unit.py packages/analysis/tests/unit/experiments/test_evidence_unit.py packages/application/tests/unit/process/experiments/test_evidence_unit.py -q
```

Expected: FAIL，gate policy 和 immutable bundle 不存在。

**Step 3: Implement versioned gate policies**

每个 evaluation 保存 `rule_id`、policy version、layer、outcome、observed/policy JSON 和 artifact ref；hard/evidence 层不得由 UI 推断。

**Step 4: Assemble and hash review packets**

bundle 包含 experiment/candidate/fold lineage、spec/snapshot/registry hashes、gate results、comparison、candidate rationale、holdout、selection evidence 和 R1 impact；保存后 payload 只读，promotion 使用 bundle hash 防止 stale evidence。

**Step 5: Run tests and commit**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_gates_unit.py packages/analysis/tests/unit/experiments/test_evidence_unit.py packages/application/tests/unit/process/experiments/test_evidence_unit.py packages/application/tests/unit/query/test_experiment_review_packet_unit.py -q
git add packages/analysis packages/application
git commit -m "feat(research): assemble governed promotion evidence"
```

## W4：Strategy governance 与 R1 active pointer

### Task 15: Immutable version、review event 与 active-pointer storage

> **Approval checkpoint:** 在执行本 task 前，展示 metadata SQLite 最终 DDL、legacy dry-run 映射、当前 latest-published → active-pointer 结果、备份/恢复与失败回滚方案，获得数据库 schema 显式批准。

**Files:**

- Create: `packages/strategy/src/ditto_strategy/governance/models.py`
- Create: `packages/strategy/src/ditto_strategy/governance/protocols.py`
- Create: `packages/strategy/src/ditto_strategy/governance/service.py`
- Create: `packages/strategy/src/ditto_strategy/storage/sqlite/strategy_governance_store.py`
- Create: `packages/strategy/src/ditto_strategy/storage/sqlite/strategy_governance_migration.py`
- Modify: `packages/strategy/src/ditto_strategy/models.py`
- Modify: `packages/strategy/src/ditto_strategy/contracts.py`
- Modify: `packages/strategy/src/ditto_strategy/storage/sqlite/strategy_spec_store.py`
- Modify: `packages/strategy/src/ditto_strategy/storage/sqlite/services/strategy_catalog_service.py`
- Modify: `packages/strategy/src/ditto_strategy/di/storage.py`
- Create: `packages/strategy/tests/unit/governance/test_models_unit.py`
- Create: `packages/strategy/tests/unit/governance/test_service_unit.py`
- Create: `packages/strategy/tests/unit/storage/sqlite/test_strategy_governance_store_unit.py`
- Create: `packages/strategy/tests/integration/test_strategy_governance_migration.py`

**Step 1: Write failing governance tests**

覆盖 immutable version insert、draft→review→published→deprecated、review pending/approved/rejected、rejected version 只能 clone、append-only decision、multiple published/one active、deprecated 不能激活、CAS conflict 和 event/projection 原子性。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/governance packages/strategy/tests/unit/storage/sqlite/test_strategy_governance_store_unit.py packages/strategy/tests/integration/test_strategy_governance_migration.py -q
```

Expected: FAIL，当前只有 draft/published 和 `INSERT OR REPLACE`/任意 status update。

**Step 3: Implement append-only stores**

新 version 只允许 INSERT；decision/activation 只 append；projection 使用 `state_revision`/`pointer_revision` CAS。禁止已存在 payload replace，禁止 generic `update_status` 绕过状态机。

**Step 4: Implement legacy dry-run migration**

读取旧 records，生成 StrategySpec v2/hash、`legacy_import` event 和每个 strategy 的 active mapping；dry-run 无写入，apply 前验证 backup，重复 apply no-op。

**Step 5: Run tests and commit**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/governance packages/strategy/tests/unit/storage/sqlite/test_strategy_governance_store_unit.py packages/strategy/tests/integration/test_strategy_governance_migration.py -q
git add packages/strategy
git commit -m "feat(strategy): persist immutable governance history"
```

### Task 16: Review/publish/reactivate commands 与 R1 active-version 集成

**Files:**

- Create: `packages/application/src/ditto_application/commands/strategy_governance.py`
- Create: `packages/application/src/ditto_application/processes/strategy/promotion.py`
- Modify: `packages/application/src/ditto_application/commands/strategy.py`
- Modify: `packages/application/src/ditto_application/queries/strategy.py`
- Modify: `packages/application/src/ditto_application/builders/runtime_builder.py`
- Modify: `packages/application/src/ditto_application/queries/daily_decision.py`
- Modify: `packages/application/src/ditto_application/processes/strategy/seed_bootstrap.py`
- Modify: `packages/application/src/ditto_application/providers_command.py`
- Modify: `packages/application/src/ditto_application/providers_strategy.py`
- Modify: `packages/apps/src/ditto_apps/jobs/flows/eod.py`
- Modify: `packages/apps/src/ditto_apps/registry/contexts/strategy.py`
- Create: `packages/application/tests/unit/commands/test_strategy_governance_unit.py`
- Create: `packages/application/tests/unit/process/strategy/test_promotion_unit.py`
- Modify: `packages/application/tests/unit/query/test_strategy_query_unit.py`
- Modify: `packages/application/tests/unit/query/test_daily_decision_query_unit.py`
- Modify: `packages/application/tests/unit/process/strategy/test_backtest_runtime_builder_unit.py`
- Modify: `packages/apps/tests/unit/jobs/flows/test_eod_flow_unit.py`

**Step 1: Write failing command and R1 tests**

证明 hard gate/evidence/holdout 不完整时无法 submit/publish；approval 后 publish 原子切 pointer；reactivate 只接受历史 published；pointer conflict 409 语义；Daily Decision/EOD 使用 pointer 而非最高 published，并在 batch 开始锁定版本。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/application/tests/unit/commands/test_strategy_governance_unit.py packages/application/tests/unit/process/strategy/test_promotion_unit.py packages/application/tests/unit/query/test_daily_decision_query_unit.py packages/apps/tests/unit/jobs/flows/test_eod_flow_unit.py -q
```

Expected: FAIL，active pointer commands 和生产读取尚不存在。

**Step 3: Implement promotion orchestration**

application 读取 analysis evidence bundle，经 hash/gate/holdout 校验后只把 approved version 和 activation event 写入 strategy；R1 永远不读取 analysis store。

**Step 4: Replace production lookup**

新增 `get_active_published()`；Daily Decision、EOD 和 production runtime builder 统一使用 active pointer。无 pointer 时保持现有 `NO_ACTIVE_STRATEGY` fail-closed。

**Step 5: Implement reactivate semantics**

要求 reason、confirmation、expected pointer revision 和 impact summary；只切 pointer，不修改历史 spec 或把 deprecated 版本复活。

**Step 6: Run tests and commit**

```bash
pixi run -e dev pytest packages/application/tests/unit/commands/test_strategy_governance_unit.py packages/application/tests/unit/process/strategy/test_promotion_unit.py packages/application/tests/unit/query/test_strategy_query_unit.py packages/application/tests/unit/query/test_daily_decision_query_unit.py packages/apps/tests/unit/jobs/flows/test_eod_flow_unit.py -q
git add packages/strategy packages/application packages/apps
git commit -m "feat(strategy): govern active strategy publication"
```

### Task 17: Research/strategy REST API、CLI、DI 与 OpenAPI contract

**Files:**

- Create: `packages/apps/src/ditto_apps/models/research.py`
- Create: `packages/apps/src/ditto_apps/api/routes/research.py`
- Create: `packages/apps/src/ditto_apps/api/routes/research_experiment_routes.py`
- Create: `packages/apps/src/ditto_apps/api/routes/research_catalog_routes.py`
- Create: `packages/apps/src/ditto_apps/cli/commands/research.py`
- Modify: `packages/apps/src/ditto_apps/cli/commands/__init__.py`
- Modify: `packages/apps/src/ditto_apps/cli/main.py`
- Create: `packages/apps/src/ditto_apps/registry/contexts/research.py`
- Modify: `packages/apps/src/ditto_apps/models/strategy.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/strategy.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/__init__.py`
- Modify: `packages/apps/src/ditto_apps/main.py`
- Modify: `packages/apps/src/ditto_apps/registry/container.py`
- Modify: `packages/apps/src/ditto_apps/registry/contexts/bundle.py`
- Modify: `packages/apps/src/ditto_apps/api/maturity.py`
- Create: `packages/apps/tests/unit/api/routes/test_research_experiment_routes_unit.py`
- Create: `packages/apps/tests/unit/api/routes/test_research_catalog_routes_unit.py`
- Modify: `packages/apps/tests/unit/api/routes/test_strategy_routes_unit.py`
- Create: `packages/apps/tests/unit/cli/commands/test_research_unit.py`
- Create: `packages/apps/tests/integration/api/test_research_api_integration.py`

**Step 1: Write failing route/contract tests**

覆盖 descriptor/factor catalog、strategy versions/diff/validate/review/publish/reactivate、experiment CRUD/control/comparison/gates/artifacts、selection evidence、Idempotency-Key、expected revision、409/422 和稳定 error envelope。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/apps/tests/unit/api/routes/test_research_experiment_routes_unit.py packages/apps/tests/unit/api/routes/test_research_catalog_routes_unit.py packages/apps/tests/unit/api/routes/test_strategy_routes_unit.py packages/apps/tests/integration/api/test_research_api_integration.py -q -n0
```

Expected: FAIL，新 routes/DTO 不存在。

**Step 3: Implement thin HTTP and CLI adapters**

routes 只解析 DTO、调用 application command/query 和映射 typed errors；不得直接访问 SQLite、artifact files 或 capability internals。单次运行继续使用 `/backtests/runs`。

**Step 4: Register DI and maturity metadata**

将 research context 注入 container，增加稳定 OpenAPI operation IDs 和 maturity manifest；CLI 复用同一 application commands，不复制规则。

**Step 5: Run tests, architecture check and commit**

```bash
pixi run -e dev pytest packages/apps/tests/unit/api/routes/test_research_experiment_routes_unit.py packages/apps/tests/unit/api/routes/test_research_catalog_routes_unit.py packages/apps/tests/unit/api/routes/test_strategy_routes_unit.py packages/apps/tests/integration/api/test_research_api_integration.py -q -n0
pixi run -e dev arch-check
git add packages/apps packages/application
git commit -m "feat(api): expose governed research workflows"
```

## W5：真实前端与双黄金路径

> 以下 task 在 `ditto-app` 独立分支执行；路径均相对 `/home/chevy/projects/ditto-app`。

### Task 18: 修复 research 路由层级并实现 Strategy Studio

**Files:**

- Modify: `src/routes/research/strategies.tsx`
- Create: `src/routes/research/strategies/index.tsx`
- Modify: `src/routes/research/strategies/$id.tsx`
- Create: `src/routes/research/strategies/$id/index.tsx`
- Keep: `src/routes/research/strategies/$id/studio.tsx`
- Create: `src/features/strategy/api/query-keys.ts`
- Create: `src/features/strategy/api/node-descriptors.ts`
- Create: `src/features/strategy/api/strategies.ts`
- Create: `src/features/strategy/api/strategy-lifecycle.ts`
- Create: `src/features/strategy/state/strategy-studio-store.ts`
- Create: `src/features/strategy/types.ts`
- Create: `src/features/strategy/components/strategy-studio-toolbar.tsx`
- Create: `src/features/strategy/components/node-library.tsx`
- Create: `src/features/strategy/components/strategy-spec-form.tsx`
- Create: `src/features/strategy/components/strategy-pipeline-view.tsx`
- Create: `src/features/strategy/components/node-inspector.tsx`
- Create: `src/features/strategy/components/strategy-validation-panel.tsx`
- Modify: `src/features/strategy/components/strategy-page.tsx`
- Modify: `src/features/strategy/components/studio-mode-bar.tsx`
- Modify: `src/features/strategy/components/strategy-header.tsx`
- Remove after migration: `src/features/strategy/components/strategy-editor.tsx`
- Create: `src/features/strategy/state/strategy-studio-store.test.ts`
- Create: `src/features/strategy/components/strategy-studio-page.test.tsx`
- Create: `src/features/strategy/components/strategy-spec-roundtrip.test.tsx`
- Create: `src/features/strategy/components/strategy-pipeline-keyboard.test.tsx`

**Step 1: Write failing route and store tests**

证明嵌套 routes 通过 `<Outlet />` 渲染，working copy 与 server version 分离，表单/流水线切换保持相同 canonical DTO，unknown descriptor 只读，保存创建新 draft 而非覆盖。

**Step 2: Run tests to verify RED**

```bash
bunx vitest run src/features/strategy/state/strategy-studio-store.test.ts src/features/strategy/components/strategy-studio-page.test.tsx src/features/strategy/components/strategy-spec-roundtrip.test.tsx
```

Expected: FAIL，新 routes/store/components 不存在。

**Step 3: Implement the shared working-copy model**

所有字段和节点使用稳定 JSON path；后端 descriptor/config schema 是事实源；server 返回 canonical spec/hash 后才清除 dirty state。

**Step 4: Replace Code Editor with constrained pipeline**

只允许合法 slot 中的 add/remove/enable/configure/reorder，edge 自动生成；拖拽必须有按钮和 keyboard 等价路径，Allocator 不展示 R4 optimizer。

**Step 5: Cover responsive and failure states**

实现 loading/empty/stale/404/409/422/503/unknown descriptor；小于 900px 使用全宽有序节点列表，不依赖图缩放。

**Step 6: Run tests and commit**

```bash
bunx vitest run src/features/strategy
git add src/routes/research/strategies src/features/strategy
git commit -m "feat(research): build constrained strategy studio"
```

### Task 19: Experiment catalog、create flow、queue 与 candidate comparison

**Files:**

- Modify: `src/routes/research/experiments.tsx`
- Create: `src/routes/research/experiments/index.tsx`
- Create: `src/routes/research/experiments/new.tsx`
- Create: `src/routes/research/experiments/$id.tsx`
- Create: `src/features/research/api/query-keys.ts`
- Create: `src/features/research/api/experiments.ts`
- Create: `src/features/research/hooks/use-experiments.ts`
- Create: `src/features/research/hooks/use-experiment.ts`
- Create: `src/features/research/hooks/use-experiment-mutations.ts`
- Create: `src/features/research/components/experiment-create-page.tsx`
- Create: `src/features/research/components/experiment-detail-page.tsx`
- Create: `src/features/research/components/experiment-table.tsx`
- Create: `src/features/research/components/experiment-config-form.tsx`
- Create: `src/features/research/components/experiment-run-controls.tsx`
- Create: `src/features/research/components/candidate-comparison.tsx`
- Create: `src/features/research/components/experiment-validation-view.tsx`
- Create: `src/features/research/components/experiment-evidence-view.tsx`
- Modify: `src/features/research/components/experiment-list-page.tsx`
- Modify: `src/features/research/components/research-page.tsx`
- Modify: `src/components/data/data-table/data-table.tsx`
- Create: `src/features/research/api/__tests__/experiments.test.ts`
- Create: `src/features/research/components/experiment-list-page.test.tsx`
- Create: `src/features/research/components/experiment-create-page.test.tsx`
- Create: `src/features/research/components/experiment-detail-page.test.tsx`
- Create: `src/features/research/components/experiment-run-recovery.test.tsx`

**Step 1: Write failing API and page tests**

覆盖真实 endpoint、polling server truth、96 月可视化、候选/128 预算、2/4 worker、单 active experiment、pause/cancel/resume、最多 pin 4 个 candidate、partial failures 和刷新恢复。

**Step 2: Run tests to verify RED**

```bash
bunx vitest run src/features/research/api/__tests__/experiments.test.ts src/features/research/components/experiment-list-page.test.tsx src/features/research/components/experiment-create-page.test.tsx src/features/research/components/experiment-detail-page.test.tsx
```

Expected: FAIL，现有列表仍有 hardcoded rows/live prototype empty。

**Step 3: Implement catalog and creation task page**

使用 `CatalogLayout`/`DataTable`；创建页分段固定 version、snapshot、objective、baseline、matrix、validation、cost/seed/worker 和 preflight，不塞入 modal。

**Step 4: Implement candidate and recovery views**

复用 backtest KPI/returns/trades primitives；所有进度、retry/resume capability 和 holdout state 只来自 API，失联时停止动画和伪进度。

**Step 5: Run tests and commit**

```bash
bunx vitest run src/features/research src/components/data/data-table/data-table.test.tsx
git add src/routes/research/experiments src/features/research src/components/data/data-table
git commit -m "feat(research): add live experiment workbench"
```

### Task 20: Review queue、publish 与 historical-version reactivate UI

**Files:**

- Create: `src/routes/research/reviews.tsx`
- Create: `src/routes/research/reviews/index.tsx`
- Create: `src/routes/research/reviews/$id.tsx`
- Create: `src/features/research/api/reviews.ts`
- Create: `src/features/research/hooks/use-reviews.ts`
- Create: `src/features/research/hooks/use-review.ts`
- Create: `src/features/research/hooks/use-review-decision.ts`
- Create: `src/features/research/components/review-list-page.tsx`
- Create: `src/features/research/components/review-detail-page.tsx`
- Create: `src/features/research/components/review-decision-banner.tsx`
- Create: `src/features/research/components/research-gate-report.tsx`
- Create: `src/features/research/components/strategy-spec-diff.tsx`
- Create: `src/features/research/components/review-decision-form.tsx`
- Create: `src/features/strategy/components/publish-version-dialog.tsx`
- Create: `src/features/strategy/components/reactivate-version-dialog.tsx`
- Create: `src/features/strategy/components/active-version-panel.tsx`
- Modify: `src/features/strategy/components/strategy-detail-page.tsx`
- Modify: `src/features/strategy/components/strategy-versions-view.tsx`
- Create: `src/features/research/components/review-hard-gates.test.tsx`
- Create: `src/features/strategy/components/strategy-publish.test.tsx`
- Create: `src/features/strategy/components/strategy-reactivate.test.tsx`

**Step 1: Write failing review tests**

证明 hard gate fail 禁用 decision/publish、软证据不自动裁决、rejected version 只允许 clone、publish 与 approval 分步、reactivate 要求原因/确认/expected revision，mutation 后精确 invalidate active/version/review queries。

**Step 2: Run tests to verify RED**

```bash
bunx vitest run src/features/research/components/review-hard-gates.test.tsx src/features/strategy/components/strategy-publish.test.tsx src/features/strategy/components/strategy-reactivate.test.tsx
```

Expected: FAIL，Review 工作台和 governance mutations 不存在。

**Step 3: Implement evidence-first review detail**

按 Decision Banner → hard gates → statistical evidence → spec diff → rationale → lineage → R1 impact → decision form 排列；宽屏 persistent detail，窄屏 Sheet。

**Step 4: Implement guarded publish/reactivate dialogs**

危险操作无快捷键；Dialog 显示 current/target、impact、evidence hash、required confirmation，并处理 409 stale pointer。

**Step 5: Run tests and commit**

```bash
bunx vitest run src/features/research/components src/features/strategy/components/strategy-publish.test.tsx src/features/strategy/components/strategy-reactivate.test.tsx
git add src/routes/research/reviews src/features/research src/features/strategy
git commit -m "feat(research): govern strategy review and activation"
```

### Task 21: OpenAPI codegen、page contracts 与彻底移除 live mock fallback

**Files:**

- Generated: `src/types/generated/api.d.ts`
- Modify: `src/types/research.ts`
- Modify: `src/types/index.ts`
- Modify: `src/mocks/handlers/research.ts`
- Modify: `src/mocks/handlers/strategy.ts`
- Modify: `src/mocks/fixtures/research.ts`
- Modify: `src/mocks/fixtures/strategy.ts`
- Modify: `docs/contracts/pages/strategy-studio.contract.json`
- Modify: `docs/contracts/pages/experiment-list.contract.json`
- Create: `docs/contracts/pages/experiment-create.contract.json`
- Create: `docs/contracts/pages/experiment-detail.contract.json`
- Create: `docs/contracts/pages/review-list.contract.json`
- Create: `docs/contracts/pages/review-detail.contract.json`
- Generated: `src/features/shell/page-contracts.generated.ts`
- Modify: `src/features/research/components/research-components.test.tsx`
- Modify: `src/features/strategy/components/strategy-components.test.tsx`

**Step 1: Start the real backend and generate types**

Run in backend:

```bash
pixi run -e dev uvicorn ditto_apps.main:app --host 127.0.0.1 --port 8000
```

Run in `ditto-app`:

```bash
OPENAPI_URL=http://127.0.0.1:8000/openapi.json bun run gen:api
```

Expected: generated API includes node, strategy governance, experiment, review and evidence resources.

**Step 2: Write failing live-boundary tests**

证明 `VITE_USE_MOCK=false` 不注册 research/strategy MSW fallback，不显示 `PrototypeOnlyEmpty`，API 失败进入 typed error state；宽松手写 Strategy/Experiment/Review DTO 不再是业务事实源。

**Step 3: Replace handwritten contracts**

API adapters 直接引用 generated operation/schema types；`research.ts` 只保留纯 UI view types，删除 `unknown` config/code editor 契约。

**Step 4: Update and generate page contracts**

```bash
bun run generate-contracts
bun run audit:routes
bun run prototype:gates
```

Expected: PASS，新增 routes 与 layouts 符合 page contracts。

**Step 5: Verify generated files are stable**

```bash
bun run gen:api
git diff --exit-code -- src/types/generated/api.d.ts
bun run generate-contracts
git diff --exit-code -- src/features/shell/page-contracts.generated.ts
```

Expected: 两次 codegen 均无 diff。

**Step 6: Run frontend checks and commit**

```bash
bun run check
bun run build
git add src docs/contracts package.json
git commit -m "feat(research): consume live r3 api contracts"
```

### Task 22: 双黄金路径、恢复、备份与 G2 release evidence

**Files:**

- Create: `packages/apps/src/ditto_apps/scripts/r3_research_acceptance.py`
- Create: `packages/apps/tests/e2e/test_r3_stock_selection_golden.py`
- Create: `packages/apps/tests/e2e/test_r3_etf_research_golden.py`
- Create: `packages/apps/tests/e2e/test_r3_governance_recovery.py`
- Create: `packages/apps/tests/e2e/test_r3_scheduler_capacity.py`
- Create: `docs/runbooks/backup-restore.md`
- Create: `docs/evidence/r3/README.md`
- Create: `docs/evidence/r3/manifest.json`
- `ditto-app` Create: `scripts/r3-research-acceptance.ts`
- `ditto-app` Create: `scripts/r3-research-acceptance.test.ts`
- `ditto-app` Modify: `package.json`
- Runtime evidence: `artifacts/acceptance/r3-report.json`
- `ditto-app` Runtime evidence: `docs/review/r3-research-acceptance/`

**Step 1: Write failing golden E2E tests**

个股线覆盖 typed spec、真实 certified snapshot、walk-forward、唯一 candidate、holdout、候选/排除/贡献/暴露、review、publish 和 R1 active signal；ETF 线覆盖当前 R1 baseline、同协议、publish、reactivate 和语义回归。

**Step 2: Add scheduler and recovery acceptance**

用 128 个轻量 deterministic candidate 验证预检、2/4 worker、单 slot、pause/resume、进程重启、lease reclaim、无重复 claim 和 artifact lineage；不要求黄金策略本身必须使用 128 个参数。

**Step 3: Add backup/restore acceptance**

备份 metadata DB、research DB 和 pinned artifacts，在临时 data root 恢复；验证 active pointer、review decisions、holdout claim、artifact hashes 和 replay fingerprint。

**Step 4: Run deterministic backend acceptance**

```bash
pixi run -e dev pytest packages/apps/tests/e2e/test_r3_stock_selection_golden.py packages/apps/tests/e2e/test_r3_etf_research_golden.py packages/apps/tests/e2e/test_r3_governance_recovery.py packages/apps/tests/e2e/test_r3_scheduler_capacity.py -m e2e --no-cov -q -n0
```

Expected: PASS；fixture evidence 明确标记 deterministic，不冒充 live provider。

**Step 5: Run explicit live acceptance when R2 Gate is ready**

```bash
DITTO_RUN_REAL_DATA_ACCEPTANCE=1 pixi run -e dev python -m ditto_apps.scripts.r3_research_acceptance --real-data --require-certified --require-both-golden-lanes --output artifacts/acceptance/r3-report.json
```

Expected: exit 0；报告证明 96 月、双线、holdout、replay、governance、backup/restore 和 R2 live Gate 均已关闭。凭证或 entitlement 缺失时必须非零退出并列明 blocker。

**Step 6: Run real browser acceptance**

Run backend and frontend with live API, then:

```bash
VITE_USE_MOCK=false bun run acceptance:r3-research -- --react-base http://127.0.0.1:5173 --api-base http://127.0.0.1:8000
```

Expected: 两条黄金线完整；刷新恢复；holdout duplicate 被阻止；review/publish/reactivate 成功；0 console/page error；保留 evidence JSON、report 和 screenshots。

**Step 7: Run final repository gates**

Backend:

```bash
pixi run -e dev arch-check
pixi run -e dev check
```

Frontend:

```bash
bun run check
bun run build
```

Expected: 所有命令 exit 0；OpenAPI/page-contract codegen 零 diff；两个 worktree clean。

**Step 8: Reconcile Definition of Done and commit evidence**

逐项对账设计文档 23 条 G2 Definition of Done；任何 live blocker 保持 `RELEASE ACCEPTANCE BLOCKED`，不得用 fixture 标记 G2 PASS。

```bash
git add packages/apps docs/evidence/r3 docs/runbooks/backup-restore.md artifacts/acceptance/r3-report.json
git commit -m "test(release): certify r3 research beta"
```

在 `ditto-app`：

```bash
git add scripts package.json docs/review/r3-research-acceptance
git commit -m "test(release): capture r3 browser evidence"
```

## 波次退出门禁

| 波次 | 必须证明 |
|---|---|
| W0 | 完整 canonical hash；typed override 真实生效；unknown node fail closed |
| W1 | 双黄金 spec 可编译；12 因子目录受控；个股选择 evidence 完整 |
| W2 | 128 上限、2/4 worker、单 active experiment、crash recovery 均由服务端证明 |
| W3 | 96 月、动态 purge/embargo、trial ledger、一次性 holdout 和 immutable bundle 通过 |
| W4 | review/publish/reactivate append-only；R1/EOD 只读取 active pointer |
| W5 | `VITE_USE_MOCK=false` 双黄金闭环、备份恢复、真实 browser/live evidence 和 G2 |

## Execution Handoff

计划执行有两种方式：

1. **Subagent-Driven（当前会话）**：使用 `superpowers:subagent-driven-development`，按 task 派发新 subagent，并在每个 task 后做 spec/compliance review。
2. **Parallel Session（独立会话）**：在专用 worktree 中使用 `superpowers:executing-plans`，按波次执行并在 W0–W5 Exit Gate 检查点复核。

无论选择哪种方式，Task 7 和 Task 15 的数据库 schema approval、任何新前端依赖、架构边界或环境配置变更都必须暂停并单独请求授权。
