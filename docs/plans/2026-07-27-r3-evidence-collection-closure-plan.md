# R3 Evidence Collection 闭环 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 接通 R3 evidence collection 链路,让一个真实 experiment 从 EVIDENCE stage 产出非空、hard gate 客观判定的 immutable review packet(含真实 walk-forward 统计证据),驱动 governance publish 走完整 promote 链路。

**Architecture:** coordinator 在 EVIDENCE stage 内联触发 `ExperimentEvidenceCollector`——读 experiment snapshot + preflight authority + fold artifacts + backtest reports,装配 `CandidateFoldEvidence` → `build_candidate_comparison` → `aggregate_walk_forward`(接通 Task 11 孤儿链)→ 真实 metric_values,装配 11 个 hard gate(analysis 纯函数投影)+ ReviewPacketInput,调 `assemble_review_packet` → `publish_review_packet`,最后 `transition_experiment(target_status=COMPLETED, target_stage=EVIDENCE)`。契约层零改动。

**Tech Stack:** Python 3.13、frozen dataclass/Protocol、orjson、Polars、SQLite、Dishka、Pytest;TDD(RED→GREEN→REFACTOR)。

---

> **设计事实源**:[evidence collection 闭环 design](2026-07-27-r3-evidence-collection-closure-design.md)(数据流/18 字段装配表/11 gate 判定/失败语义) · [R3 主计划](2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md) Task 14
>
> **计划状态**:READY FOR EXECUTION
>
> **跨仓库**:全部在后端 `/home/chevy/projects/ditto`,分支 `docs/r3-research-governance-design`。

## 实施规则

- 每个遵循 RED → GREEN → REFACTOR,形成独立提交。
- 先精确测试,再所属 package test,波次结束 `pixi run -e dev check`。
- 不新增第二套 evidence/gate/artifact/metric 类型系统;复用 Task 14 既有契约(`ReviewPacketInput`/`HardGateEvidence`/`assemble_review_packet`/`publish_review_packet` 零改动)。
- `analysis` 禁止依赖生产包;collector 装配在 application,hard gate 投影是 analysis 纯函数。
- 不绕过 basedpyright/ruff/pre-commit;不滥用 `# type: ignore`(重构解决)。
- **formatter 删 unused import 坑**:用法先于 import 加(先加用符号的代码,再加 import)。

## 已确认的施工接口(写 plan 前已验证)

| 接口 | 签名/位置 |
|------|----------|
| 终态推进 | `transition_experiment(target_status=COMPLETED, target_stage=EVIDENCE)`,非 `advance_stage`(COMPLETED 是 `ExperimentStatus` 非 `ExperimentStage`) |
| EVIDENCE 插入点 | `coordinator.py:651-652`(`return WAITING` 死端) |
| coordinator `__init__` | `coordinator.py:173`,加 `evidence_collector` kwarg |
| coordinator DI | `providers_process.py:321` `experiment_execution_coordinator`,加依赖 + 转发 |
| publish_review_packet | `ExperimentWriterProtocol` `protocols.py:288`,参数 `lease.fence`(SchedulerLease.fence)+ `now_epoch_us()` + `occurred_at`,都在 `_advance_completed_stages` 作用域内 |
| load_snapshot | `ExperimentSchedulerStore.load_snapshot(experiment_id)` `scheduler_store.py:211` |
| artifact 读取 | `ExperimentReaderProtocol.get_artifact(id)`/`get_artifact_by_relative_path(path)`;**无集合查询**,靠 `list_experiment_attempts`+`list_folds` 遍历 |
| snapshot_hash | `list_status_events` 过滤 `preflight_passed` → `decode_preflight_authority` → `snapshot_manifest_hash` |
| registry_hash | preflight detail payload(`preflight_authority.py:487`),非顶层字段——**缺口,Task 2 探索** |
| objective_payload_hash | `promotion_objective_content_hash(launch_spec.promotion_objective)` `trial_ledger.py:459` |
| aggregation 链 | `CandidateFoldEvidence`(backtest_report Optional)→ `build_candidate_comparison` `comparison.py:714` → `aggregate_walk_forward` `walk_forward.py:663` → `aggregation.candidates[i].metrics`,**全孤儿,collector 首个生产 caller** |
| metric 提取 | `ScalarEvidence.metric_value: ResearchMetricValue | None`(`_comparison_evidence.py:261`),None 跳过→NOT_EVALUATED |

## 两个实施风险点(plan 内标注 TDD 探索)

1. **backtest report 读取**(Task 2):`CandidateFoldEvidence.backtest_report` 是 `_BacktestReport` 类型(`_validate_report` 校验 run_id/period/result_hash 一致)。collector 要从 `AttemptProjection.backtest_run_id` 读 backtest result artifact(parquet)→ 构造 `_BacktestReport`。读取路径(reader + 转换)Task 2 Step 0 先探索。
2. **registry_hash 读取**(Task 2):`node_registry_manifest_hash` 只在 preflight detail map,非 `DecodedPreflightAuthority` 顶层字段。Task 2 Step 0 探索:深挖 detail 或扩展 authority。

---

## Task 1: analysis 纯函数 `collect_hard_gate_evidence`

**Files:**
- Create: `packages/analysis/src/ditto_analysis/experiments/hard_gate_collector.py`
- Modify: `packages/analysis/src/ditto_analysis/experiments/__init__.py`
- Create: `packages/analysis/tests/unit/experiments/test_hard_gate_collector_unit.py`

**Step 1: Write the failing tests**

```python
# test_hard_gate_collector_unit.py
from ditto_analysis.experiments import (
    ContentHash, HardGateEvidence, HardGateEvidenceView,
    collect_hard_gate_evidence, GateOutcome,
)

def _view(**overrides):
    base = dict(
        certified_snapshot=True, snapshot_id="snap-1",
        eligible_month_count=96, pit_policy="sample_time",
        purge_embargo_configured=True,
        reproduction_fingerprints=(ContentHash("a" * 64),),
        cost_config_hash=ContentHash("c" * 64),
        baseline_candidate_id="cand-baseline",
        trial_count=4, expected_trial_count=4,
        holdout_claim_id="claim-1",
        artifact_complete=True, artifact_missing=(),
    )
    base.update(overrides)
    return HardGateEvidenceView(**base)

def test_all_pass_when_evidence_satisfied():
    evidence = collect_hard_gate_evidence(_view())
    assert all(
        fact.satisfied is True for name, fact in _facts(evidence)
        if name != "r2_live_gate"
    )
    assert evidence.r2_live_gate.satisfied is None  # NOT_EVALUATED

def test_ninety_six_month_fails_below_threshold():
    evidence = collect_hard_gate_evidence(_view(eligible_month_count=80))
    assert evidence.ninety_six_month.satisfied is False

def test_artifact_completeness_fails_with_missing():
    evidence = collect_hard_gate_evidence(
        _view(artifact_complete=False, artifact_missing=("report.parquet",))
    )
    assert evidence.artifact_completeness.satisfied is False

def test_reproduction_fails_on_empty_fingerprint():
    evidence = collect_hard_gate_evidence(_view(reproduction_fingerprints=()))
    assert evidence.reproduction.satisfied is False

def test_holdout_claim_not_evaluated_when_missing():
    evidence = collect_hard_gate_evidence(_view(holdout_claim_id=None))
    assert evidence.holdout_claim.satisfied is None

def test_detail_carries_observed_fact():
    evidence = collect_hard_gate_evidence(_view(eligible_month_count=96))
    assert evidence.ninety_six_month.detail == {"eligible_months": 96, "required": 96}
```

> `_facts(evidence)` 是测试 helper,把 `HardGateEvidence` 11 字段名→fact 配对(可用 `dataclasses.asdict` 或显式列举)。

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_hard_gate_collector_unit.py -q
```
Expected: FAIL — `HardGateEvidenceView`/`collect_hard_gate_evidence` 不存在。

**Step 3: Implement minimal contract**

```python
# hard_gate_collector.py
from __future__ import annotations
from dataclasses import dataclass
from ditto_analysis.experiments.gates import HardGateEvidence, GateFact

@dataclass(frozen=True, slots=True)
class HardGateEvidenceView:
    """Typed observed facts for every hard-correctness gate (零 I/O)."""
    certified_snapshot: bool
    snapshot_id: str
    eligible_month_count: int
    pit_policy: str
    purge_embargo_configured: bool
    reproduction_fingerprints: tuple[ContentHash, ...]
    cost_config_hash: ContentHash
    baseline_candidate_id: str
    trial_count: int
    expected_trial_count: int
    holdout_claim_id: str | None
    artifact_complete: bool
    artifact_missing: tuple[str, ...]

_NINETY_SIX = 96

def collect_hard_gate_evidence(view: HardGateEvidenceView) -> HardGateEvidence:
    """Project typed observed facts into 11 hard gate facts (pure)."""
    return HardGateEvidence(
        certified_snapshot=GateFact(view.certified_snapshot, {"snapshot_id": view.snapshot_id}),
        ninety_six_month=GateFact(
            view.eligible_month_count >= _NINETY_SIX,
            {"eligible_months": view.eligible_month_count, "required": _NINETY_SIX},
        ),
        pit_known_at=GateFact(view.pit_policy == "sample_time", {"pit_policy": view.pit_policy}),
        split_purge_embargo=GateFact(view.purge_embargo_configured, None),
        reproduction=GateFact(len(view.reproduction_fingerprints) > 0, None),
        cost_assumptions=GateFact(True, {"cost_config_hash": str(view.cost_config_hash)}),
        baseline_declared=GateFact(bool(view.baseline_candidate_id), {"baseline_candidate_id": view.baseline_candidate_id}),
        trial_declaration=GateFact(view.trial_count == view.expected_trial_count, {"trial_count": view.trial_count, "expected": view.expected_trial_count}),
        holdout_claim=GateFact(None if view.holdout_claim_id is None else True, {"claim_id": view.holdout_claim_id}),
        artifact_completeness=GateFact(view.artifact_complete, {"missing": list(view.artifact_missing)}),
        r2_live_gate=GateFact(None, None),  # NOT_EVALUATED (Beta, G2 live 才关闭)
    )
```

> 各 gate 的精确阈值/语义(certified_snapshot 判定源、pit_policy 合法值集合、cost_assumptions 一致性等)按 design doc §6 表 + TDD 逐步精确化。上表是骨架,满足 Step 1 测试。

**Step 4: Export and run GREEN**

修改 `experiments/__init__.py` 加 `HardGateEvidenceView`、`collect_hard_gate_evidence` 到 `__all__` + import(用法先于 import)。

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_hard_gate_collector_unit.py -q
```
Expected: PASS。

**Step 5: Run package regression and commit**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments -q
pixi run -e dev arch-check
git add packages/analysis
git commit -m "feat(analysis): project hard gate evidence from typed facts"
```

---

## Task 2: `CandidateFoldEvidence` 装配 + 输入 readers(范围 B 核心)

> 这是接通 aggregation 孤儿链的关键 task。collector 要从 experiment snapshot + preflight + artifact + backtest report 装配 `CandidateFoldEvidence`,并解决两个风险点。

**Files:**
- Create: `packages/application/src/ditto_application/processes/experiments/_evidence_inputs.py`(装配 helpers)
- Modify: `packages/application/src/ditto_application/processes/experiments/__init__.py`(如需导出)
- Create: `packages/application/tests/unit/process/experiments/test_evidence_inputs_unit.py`

**Step 0: 探索 backtest report 读取 + registry_hash(RED 前确认)**

```bash
# backtest report 读取路径
grep -rn "_BacktestReport\b" packages/application/src/ditto_application/processes/experiments/comparison.py  # 确认类型 + 构造
grep -rn "backtest_report_content_hash" packages/application/src  # result_hash 计算源
grep -rn "def.*backtest_report\|BacktestReportReader\|read_backtest" packages/application/src  # 既有 reader
# registry_hash 读取
grep -rn "node_registry_manifest_hash\|registry_hash" packages/analysis/src packages/application/src
```

确认:(a) `_BacktestReport` 怎么从 backtest result artifact 构造(有无现成 reader/adapter);(b) `registry_hash` 能否从 preflight detail map 读,或需扩展 `DecodedPreflightAuthority` 加顶层字段。把结论写进 Task 2/3 的装配代码。

**Step 1: Write failing assembly tests**

```python
# test_evidence_inputs_unit.py
def test_assemble_candidate_fold_evidence_from_views(monkeypatch):
    # 给定 AttemptView + FoldView + ArtifactRecord + _BacktestReport(mock)
    # 调 assemble_candidate_fold_evidence(...) -> CandidateFoldEvidence
    # 断言:identity 字段(execution_binding/snapshot_hash/result_hash/artifact_hash)正确
    #       backtest_report 透传,result_hash == backtest_report_content_hash(report)
    ...

def test_assemble_candidate_fold_evidence_without_report():
    # backtest_report=None → CandidateFoldEvidence.backtest_report=None(校验通过)
    ...

def test_snapshot_manifest_projection_from_preflight_event():
    # 给定 preflight_passed status event(detail 含 snapshot_manifest_hash + registry_hash + pit_policy)
    # 调 project_snapshot_manifest(event_detail) -> SnapshotManifestProjection
    # 断言三个字段
    ...
```

**Step 2: Run tests to verify RED**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_evidence_inputs_unit.py -q
```
Expected: FAIL — 装配 helpers 不存在。

**Step 3: Implement assembly helpers**

```python
# _evidence_inputs.py
from __future__ import annotations
from dataclasses import dataclass
from ditto_analysis.experiments import ContentHash

@dataclass(frozen=True, slots=True)
class SnapshotManifestProjection:
    snapshot_hash: ContentHash
    registry_hash: ContentHash
    pit_policy: str

def project_snapshot_manifest(preflight_detail: Mapping[str, object]) -> SnapshotManifestProjection:
    """Read snapshot/registry hashes + pit policy from preflight authority detail."""
    # Step 0 确认 detail key;registry_hash 若无顶层,深挖 preflight detail map
    ...

def assemble_candidate_fold_evidence(
    attempt: AttemptView,
    fold: FoldView,
    result_artifact: ArtifactRecord,
    backtest_report: _BacktestReport | None,
    *,
    snapshot_hash: ContentHash,
) -> CandidateFoldEvidence:
    """Assemble one fold's execution+input+result+artifact identity."""
    # 从 attempt/fold 投影 execution_binding(PersistedFoldExecutionEvidence)
    # result_ref/result_hash/artifact_ref/artifact_hash 从 result_artifact
    # parameter_hash/resolved_spec_hash 从 launch_spec.execution_bindings
    ...
```

> `PersistedFoldExecutionEvidence` 的字段装配(从 AttemptView+FoldView 投影 experiment_id/candidate_id/fold_id/fold_ordinal/attempt_id/run_id/test_window/reproduction_fingerprint/outcome)按其 dataclass 定义精确化。

**Step 4: Run GREEN**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_evidence_inputs_unit.py -q
```
Expected: PASS。

**Step 5: Commit**

```bash
git add packages/application
git commit -m "feat(research): assemble candidate fold evidence inputs"
```

---

## Task 3: `ExperimentEvidenceCollector` + publish 接线

**Files:**
- Create: `packages/application/src/ditto_application/processes/experiments/evidence_collector.py`
- Modify: `packages/application/src/ditto_application/providers_process.py`(注册 provider)
- Create: `packages/application/tests/unit/process/experiments/test_evidence_collector_unit.py`

**Step 1: Write failing collector tests**

```python
# test_evidence_collector_unit.py
def test_collect_assembles_review_packet_with_real_metrics(monkeypatch):
    # mock: scheduler_store.load_snapshot → snapshot(holdout_claim + walk-forward folds + launch_spec)
    #       reader.list_status_events → [preflight_passed event]
    #       reader.list_experiment_attempts/list_folds → fold views
    #       reader.get_artifact → result artifacts
    #       backtest_report_reader → mock _BacktestReport per fold
    # 调 collector.collect(experiment_id, lease_fence=..., now_epoch_us=..., created_at=...)
    # 断言返回 ReviewPacket:
    #   - lineage.candidate_id == holdout_claim.candidate_id
    #   - fold_ids == walk-forward fold ids(非 holdout 单 fold)
    #   - metric_values 非空(NET_RETURN 等,来自 aggregate_walk_forward)
    #   - hard gate 10 个 satisfied(r2_live_gate NOT_EVALUATED)
    #   - comparison_payload_hash 非 None
    #   - r1_impact_payload_hash is None
    ...

def test_collect_skips_none_metrics_to_not_evaluated():
    # 某 fold backtest_report=None → 该 metric metric_value=None → 不入 mapping
    ...

def test_collect_publishes_via_writer(monkeypatch):
    # 断言 writer.publish_review_packet 被调,参数 lease_fence/now_epoch_us/created_at 透传
    ...

def test_collect_objective_payload_hash_via_promotion_objective_content_hash():
    # 断言 objective_payload_hash == promotion_objective_content_hash(launch_spec.promotion_objective)
    ...
```

**Step 2: Run RED**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_evidence_collector_unit.py -q
```
Expected: FAIL — collector 不存在。

**Step 3: Implement collector**

```python
# evidence_collector.py
@dataclass(frozen=True, slots=True)
class _CollectorDeps:
    scheduler_store: ExperimentSchedulerStoreProtocol
    reader: ExperimentReaderProtocol
    writer: ExperimentWriterProtocol
    backtest_report_reader: BacktestReportReader  # Task 2 Step 0 确认的 reader Protocol
    # + clock/now helper

class ExperimentEvidenceCollector:
    def __init__(self, deps: _CollectorDeps) -> None: ...

    def collect(
        self, experiment_id: ExperimentId, *,
        lease_fence: LeaseFence, now_epoch_us: int, created_at: datetime,
    ) -> ReviewPacket:
        snapshot = self._deps.scheduler_store.load_snapshot(experiment_id)
        manifest = self._read_manifest(snapshot)
        fold_evidence = self._assemble_fold_evidence(snapshot, manifest)  # Task 2 helpers
        comparison = build_candidate_comparison(self._baseline(snapshot), fold_evidence)
        aggregation = aggregate_walk_forward(comparison)
        packet_input = self._assemble_packet_input(snapshot, manifest, aggregation)
        packet = assemble_review_packet(packet_input)
        self._deps.writer.publish_review_packet(
            packet, lease_fence=lease_fence, now_epoch_us=now_epoch_us, created_at=created_at,
        )
        return packet

    def _assemble_packet_input(self, snapshot, manifest, aggregation) -> ReviewPacketInput:
        selected = snapshot.holdout_claim.candidate_id
        candidate_metrics = self._metrics_for(aggregation, selected)  # 提取非 None metric_value
        return ReviewPacketInput(
            experiment_id=...,
            candidate_id=selected,
            fold_ids=self._walk_forward_fold_ids(snapshot),
            attempt_ids=self._walk_forward_attempt_ids(snapshot),
            spec_hash=encode_launch_spec(snapshot.launch_spec).content_hash,
            resolved_spec_hash=self._binding(snapshot, selected).resolved_spec_hash,
            parameter_hash=...,
            snapshot_hash=manifest.snapshot_hash,
            registry_hash=manifest.registry_hash,
            objective=snapshot.launch_spec.promotion_objective,
            objective_payload_hash=promotion_objective_content_hash(snapshot.launch_spec.promotion_objective),
            hard_evidence=collect_hard_gate_evidence(self._hard_gate_view(snapshot, manifest)),
            metric_values=candidate_metrics,
            comparison_payload_hash=self._comparison_hash(aggregation, selected),
            r1_impact_payload_hash=None,  # 第一版 NOT_EVALUATED
            selection_evidence_artifact_id=self._selection_artifact(snapshot),
            holdout_claim_id=snapshot.holdout_claim.claim_id,
            candidate_rationale=self._rationale(snapshot, selected),
        )
```

> 18 字段装配按 design doc §5 表 + 已确认接口精确化。`_hard_gate_view` 从 snapshot+manifest+artifact 装配 `HardGateEvidenceView`(Task 1)。`_rationale` 从 parameter delta vs baseline 生成模板文本。

**Step 4: Register DI provider**

`providers_process.py` 加 `experiment_evidence_collector` provider(注入 scheduler_store + reader + writer + backtest_report_reader)。

**Step 5: Run GREEN + commit**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_evidence_collector_unit.py -q
pixi run -e dev arch-check
git add packages/application
git commit -m "feat(research): collect and publish governed review packets"
```

---

## Task 4: coordinator EVIDENCE 接通 + transition COMPLETED

**Files:**
- Modify: `packages/application/src/ditto_application/processes/experiments/coordinator.py`(`__init__` + `_advance_completed_stages` EVIDENCE 分支)
- Modify: `packages/application/src/ditto_application/providers_process.py`(`experiment_execution_coordinator` 注入 collector)
- Modify: `packages/application/tests/unit/process/experiments/test_coordinator_unit.py`

**Step 1: Write failing coordinator tests**

```python
def test_evidence_stage_collects_and_transitions_to_completed():
    # 给定 experiment stage=EVIDENCE + 所有 fold COMPLETED + holdout_claim 存在
    # mock evidence_collector.collect → ReviewPacket
    # 调 coordinator.tick(occurred_at=...)
    # 断言:experiment.status == COMPLETED, stage == EVIDENCE
    #       collector.collect 被调,参数 lease.fence/now_epoch_us/occurred_at
    #       writer.publish_review_packet 被调
    ...

def test_evidence_stage_fail_fast_on_collector_error():
    # collector.collect 抛 typed error → tick fail-fast → experiment 卡 EVIDENCE + failure_code
    # 不推进 COMPLETED
    ...

def test_evidence_no_op_when_holdout_not_claimed():
    # stage=EVIDENCE 但前置校验失败(如 fold 未终态)→ 不调 collector,返回 WAITING/阻塞信号
    ...
```

**Step 2: Run RED**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_coordinator_unit.py -q -k evidence
```
Expected: FAIL — EVIDENCE 分支仍 `return WAITING`。

**Step 3: Wire coordinator**

`coordinator.py:173` `__init__` 加:
```python
evidence_collector: ExperimentEvidenceCollector | None = None,  # 新 kwarg
```
→ `self._evidence_collector = evidence_collector`

`coordinator.py:651-652` EVIDENCE 分支改为:
```python
if stage is ExperimentStage.EVIDENCE:
    if self._evidence_collector is None:
        return snapshot, SchedulerTickState.WAITING  # 未配置 collector(测试/降级)
    self._evidence_collector.collect(
        snapshot.projection.record.experiment_id,
        lease_fence=lease.fence,
        now_epoch_us=now_epoch_us(),
        created_at=occurred_at,
    )
    self._store.transition_experiment(
        snapshot.projection,
        target_status=ExperimentStatus.COMPLETED,
        target_stage=ExperimentStage.EVIDENCE,
        lease=lease,
        now_epoch_us=now_epoch_us(),
        occurred_at=occurred_at,
    )
    return self._load_snapshot(lease.experiment_id), SchedulerTickState.COMPLETED
```

> `transition_experiment` 的精确签名(`transition_scheduled_experiment` / `transition_experiment`,`scheduler_store.py:262,273`)Step 3 按实际方法名调。collector 抛错时 fail-fast(不 catch,让 tick 既有 error 路径处理 + 记 failure_code)。

**Step 4: Wire DI**

`providers_process.py:321` `experiment_execution_coordinator` 加 `evidence_collector: ExperimentEvidenceCollector` 依赖 + 转发给 `__init__`。

**Step 5: Run GREEN + commit**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_coordinator_unit.py -q
pixi run -e dev arch-check
git add packages/application
git commit -m "feat(research): drive evidence collection at EVIDENCE stage"
```

---

## Task 5: Task 22 后端 e2e(deterministic fixture)

> **范围校准（2026-07-27，基于实施审计 + 用户决策）**
>
> **实施审计发现**：Task 1-4 已完成(commit `734fbbe6`→`5db77b73`)，但 Task 3 的 `evidence_collector` 做了 **V1 简化**——`metric_values={}`、`comparison_payload_hash=None`、`selection_evidence_artifact_id=None`、aggregation 链(`build_candidate_comparison`/`aggregate_walk_forward`)**完全未接通**、Task 2 产的 `assemble_candidate_fold_evidence` 是**孤儿函数**(仅测试 caller)。collector docstring 自承"deferred to Task 3b"。这与 design §7(要求真实 NET_RETURN/SHARPE 等 8 metric)和原 Task 5 验收标准(metric_values 非空)冲突。
>
> **覆盖度审计结论**(application/integration 全量审计):Task 5 的 4 个场景均为真实缺口——stock_selection 完整闭环/evidence collection→promote/reactivate 语义/governance recovery append+stale 409/scheduler 容量组装场景,在 integration 层**零覆盖**(Task 1-4 公共接口仅 unit 测试)。`_owned_coordinator` 未注入 `evidence_collector`,故现有 integration 的 EVIDENCE 分支都 `WAITING` 降级。
>
> **用户决策**(2026-07-27):
> 1. **V1-first 渐进策略**——先验证闭环(5a),再补真实 metric(5b),最后升级 golden(5c)。TDD 友好、风险最低。
> 2. **归属层调整**:`apps/tests/e2e/` → `application/tests/integration/`(5 个同类 experiment 测试 + fixture 高度可复用 + experiment 闭环是 application 内部流程 + `integration` marker 语义准确)。

### Task 5a: V1 golden 闭环(本次实施)

验证真实 experiment tick 从 EVIDENCE 产出**非空 ReviewPacket**(V1:`metric_values={}` 可接受 → evidence gate NOT_EVALUATED)→ governance promote 闭环 → `status=COMPLETED`。注入 `evidence_collector` 的 coordinator + 真实 SQLite fixture(复用 `test_holdout_claim_integration.py` 的 `_persist_candidate_selection`/`_complete_fold`/`_owned_coordinator` 模式)。

**Files:**
- Create: `packages/application/tests/integration/test_r3_evidence_closure_golden.py`

### Task 5b: Task 3b aggregation 真实化（已完成，2026-07-27）

collector 接通 `assemble_candidate_fold_evidence` → `build_candidate_comparison` → `aggregate_walk_forward`;实现 backtest report reader(从 artifact 构造 `BacktestReport`,满足 `_validate_report` 的 run_id/result_hash 一致性);`metric_values` 真实化 + `comparison_payload_hash`。

实现还将 96 个月门禁纠正为唯一 preflight 事件经
`reconstruct_preflight_report` 验证后的 `eligible_month_count`；artifact
completeness 使用全 candidate family 的 fold 终态与 report 缺失引用，不再使用
attempt-status 代理。selection artifact 与 trial-ledger count 已在 Task 5d
闭合；真实 cost hash 仍按后续任务保留。

### Task 5c: golden 升级验证真实 metric（已完成，2026-07-27）

5a golden 已升级为真实 preflight 重构、两组 candidate family × 两个共享
walk-forward fold 的 4 个 indexed backtest report，并断言 selected candidate 的
NET_RETURN / SHARPE 非空、canonical `comparison_payload_hash`、两组
fold/attempt paired lineage 以及 artifact completeness PASS。fixture 仍明确为
deterministic；cost hash 保持 interim，`r2_live_gate` 保持
`NOT_EVALUATED`。

### Task 5d: durable selection evidence 与真实 trial count（已完成，2026-07-27）

coordinator 在进入并重载 `CANDIDATE_SELECTION` 后，以阶段完成事件的时间与
revision 为唯一发布身份，原子发布固定路径的 content-addressed
`selection_evidence`。holdout claim 必须携带该 artifact 的 exact content hash，
collector 重新验证同一 artifact 后把真实 artifact ID、observed/declared trial
count 写入 ReviewPacket。重启、晚时钟 replay 以及
`CANDIDATE_SELECTION → PAUSED → QUEUED → RUNNING` 恢复均重新绑定原始阶段
完成事件，保持 artifact ID、created_at、canonical bytes 与 index 行数不变；
artifact 丢失、manifest/bytes 漂移、claim hash 漂移和 claim 时间倒退均 fail
closed。该链路由真实 `tmp_path` SQLite golden 覆盖，未使用手造 selection
ledger。

### Task 5e: 其余后端闭环场景（后续）

governance recovery 已由
`packages/application/tests/integration/test_r3_governance_recovery_golden.py`
覆盖 append-only review decision、active pointer CAS/reactivate 与 stale
conflict，不再列为待实施项。剩余按依赖顺序推进：

1. 以每个 fold 的 execution policy canonical hash 替换 interim cost hash，
   一致才 PASS、漂移即 FAIL；
2. stock/ETF 双 lane golden，并在 `r2_live_gate=NOT_EVALUATED` 下如实断言
   promotion 被阻断且 active pointer 不变；
3. `test_r3_scheduler_capacity`：128 预检、2/4 worker、单 slot、lease reclaim、
   无重复 claim 与 artifact lineage。

**Step 1: Write golden e2e tests**

覆盖真实闭环:typed spec → certified snapshot(deterministic fixture)→ planning → exploration → walk-forward → candidate_selection → holdout claim → **evidence collection(review packet 非空 + 10 hard gate + 真实 metric)** → governance publish → R1 active signal。

```python
# test_r3_stock_selection_golden.py
@pytest.mark.e2e
def test_stock_selection_full_research_to_governance_closure(tmp_path):
    # deterministic fixture: certified snapshot + typed stock spec + 96 月 fold protocol
    # 跑 experiment tick 循环直到 stage=EVIDENCE + status=COMPLETED
    # 断言:review packet 已 publish(bundle_hash 可读)
    #       10 hard gate satisfied(r2_live_gate NOT_EVALUATED)
    #       metric_values 含 NET_RETURN/SHARPE(非空)
    #       governance publish 经 StrategyPromotionProcess.promote 成功(active pointer 切换)
    ...
```

- `test_r3_etf_research_golden.py`:ETF lane 同协议 + reactivate 语义回归。
- `test_r3_governance_recovery.py`:review decision append-only、active pointer 切换、reactivate expected_revision、stale pointer 409。
- `test_r3_scheduler_capacity.py`:128 candidate preflight、2/4 worker、单 slot lease、pause/resume、lease reclaim、无重复 claim、artifact lineage。

> fixture evidence 明确标 deterministic,不冒充 live provider。R2 live Gate 未关闭 → `r2_live_gate` NOT_EVALUATED,golden 接受。

**Step 2: Run e2e**

```bash
pixi run -e dev pytest packages/apps/tests/e2e/test_r3_stock_selection_golden.py packages/apps/tests/e2e/test_r3_etf_research_golden.py packages/apps/tests/e2e/test_r3_governance_recovery.py packages/apps/tests/e2e/test_r3_scheduler_capacity.py -m e2e --no-cov -q -n0
```
Expected: PASS。

**Step 3: Commit**

```bash
git add packages/apps docs/evidence/r3
git commit -m "test(research): certify r3 evidence collection closure"
```

---

## 波次退出门禁

| 门禁 | 必须证明 |
|------|---------|
| Task 1 | `collect_hard_gate_evidence` 纯函数,11 gate 投影(satisfied True/False/None),analysis 零生产依赖 |
| Task 2 | `CandidateFoldEvidence` 装配 + `SnapshotManifestProjection`,aggregation 孤儿链首次接通,两个风险点(backtest report/registry_hash)已解决 |
| Task 3 | collector 装配 18 字段 ReviewPacketInput,metric_values 真实(非 None),publish 经 writer,objective_payload_hash 真实 |
| Task 4 | coordinator EVIDENCE → collect → transition COMPLETED,失败 fail-fast,DI 注入 |
| Task 5 | stock/ETF 双黄金 + governance recovery + scheduler capacity 全绿(deterministic),review packet 非空 + governance promote 闭环 |

## 最终验收(对账 design doc §14)

```bash
pixi run -e dev arch-check
pixi run -e dev check   # lint + fmt + type + test --fast
```

- [ ] 真实 experiment tick 产出非空 ReviewPacket,10 hard gate 客观(r2_live_gate NOT_EVALUATED),metric_values 真实
- [ ] packet 经 `POST /strategies/{id}/versions/{v}/publish` 驱动 `StrategyPromotionProcess.promote`(pass/fail)
- [ ] EVIDENCE 后 `experiment.status == COMPLETED`
- [ ] artifact/metric 缺失时 packet 仍产出(gate fail/not_evaluated),manifest/publish 结构性错误 fail-fast
- [ ] 37 contracts + arch-smells + type/lint + test 全绿

## Execution Handoff

计划执行有两种方式:

1. **Subagent-Driven(当前会话)**:使用 `superpowers:subagent-driven-development`,按 task 派发新 subagent,每个 task 后做 spec/compliance review。
2. **Parallel Session(独立会话)**:在 worktree 中使用 `superpowers:executing-plans`,按 task 执行并在波次 Exit Gate 复核。

Task 2 的两个风险点(backtest report 读取、registry_hash)必须在 Step 0 探索确认后再 RED;若探索发现需要扩展 reader/authority(架构边界/契约微调),暂停并请求授权。
