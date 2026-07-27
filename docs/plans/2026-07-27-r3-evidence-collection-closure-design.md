# R3 Evidence Collection 闭环设计（Task 14 收尾）

> **事实源**：[R3 主设计](2026-07-19-r3-a-share-research-strategy-governance-design.md) §9.1/§9.2/§14 · [R3 实施计划](2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md) Task 14 · [Task 16b/17 wiring 设计](2026-07-24-r3-task16b-17-wiring-design.md)
>
> **状态**：READY FOR EXECUTION（待 implementation plan / TDD 拆分）

## 1. 背景与目标

R3 计划 22 task 名义完成 ~19 个，但**核心价值链断开**：experiment tick 跑完 backtest 后，evidence collection 链路完全断开——`assemble_review_packet` / `publish_review_packet` 零生产 caller，`HardGateEvidenceCollector` 不存在。后果是 review packet 在真实运行里为空，Task 17 的 evidence-gated publish 路由虽通但无真实 packet 可消费，R3 北极星「不可篡改的证据驱动治理」在生产中不成立。

**本设计的目标**：补齐 evidence collection 闭环（Task 14 的真正未完成部分），
让一个真实 experiment 能从 EVIDENCE stage 产出**非空、11 个 hard gate
客观判定**的 immutable review packet，并让 Task 22 后端 e2e 如实验证
promotion 语义：deterministic fixture 的 `r2_live_gate=NOT_EVALUATED` 必须阻断
publish/activate，只有 explicit live G2 closure 后才能成功。

**非目标（§13 详述）**：前端 W5、live G2 acceptance（需 R2 live Gate 关闭）、`r1_impact` 真实归因、第二套 evidence 类型系统。

## 2. 现状断点（精确）

| 组件 | 状态 | 位置 |
|------|------|------|
| `ReviewPacketInput` / `HardGateEvidence` / `assemble_review_packet` | ✅ 契约就绪，纯函数 | `application/processes/experiments/evidence.py:33-86`、`analysis/experiments/gates.py:108-160` |
| `evaluate_hard_gates` / `evaluate_evidence_gates` | ✅ 纯函数 | `analysis/experiments/gates.py:136,197` |
| `publish_review_packet` | ✅ 实现 + Protocol + DI 就绪，**零生产 caller** | `ExperimentWriterProtocol` `protocols.py:288`；writer mixin `writer.py:136`；store `_review_packet_store.py:30` |
| `get_review_packet` | ✅ 就绪（evidence-gated publish 已用） | `ExperimentReaderProtocol` `protocols.py:101`；`reader.py:630` |
| `HardGateEvidenceCollector` | ❌ 不存在 | — |
| coordinator EVIDENCE 分支 | ❌ 死端：`return WAITING` | `coordinator.py:651-652` |
| `_NEXT_STAGE[EVIDENCE]` | ❌ 无条目（EVIDENCE 无后继 stage） | `coordinator.py:107-111` |

**断点性质**：契约层零改动；缺口是「谁装配 18 字段输入 + 谁在 EVIDENCE 触发」。

## 3. 核心架构决策

### 3.1 终态语义：status=COMPLETED，不是 stage advance

`ExperimentStage` 只有 6 值（PREFLIGHT / EXPLORATION / WALK_FORWARD / CANDIDATE_SELECTION / HOLDOUT / EVIDENCE），**没有 COMPLETED**。`COMPLETED` 是 `ExperimentStatus`（`models.py:145`）。因此闭环终点是：

```
collect → assemble → publish_review_packet → transition_experiment(target_status=COMPLETED, target_stage=EVIDENCE)
```

走 `transition_scheduled_experiment` / `transition_experiment`（`scheduler_store.py:262,273`），不是 `advance_stage`。`advance_stage` 只用于 EVIDENCE 之前的 stage 推进。

### 3.2 触发模型：coordinator 内联同步（用户已确认）

把 `coordinator._advance_completed_stages` 的 EVIDENCE 分支从 `return WAITING` 改为：

1. 前置校验：walk-forward 结构可重建、holdout_claim 存在；artifact 缺失由 packet 内的 `artifact_completeness` gate 如实记录。
2. 调 `ExperimentEvidenceCollector.collect(experiment_id)` → 产出并 publish review packet。
3. `transition_experiment(target_status=COMPLETED, target_stage=EVIDENCE)`。
4. 返回 `SchedulerTickState.COMPLETED`（或等价终态信号）。

**为什么内联而非独立 worker**：evidence collection 是「读已完成的 fold 结果 + 聚合 + hash」(非 backtest 级重计算)，且只在「所有 fold 完成、stage=EVIDENCE」触发一次，没有并发 fold 语义，不需要 worker/lease 模型。coordinator 已在 tick 里做 store I/O，内联可接受。

**失败语义（§9）**：collector 抛 typed error → tick fail-fast → experiment 卡在 EVIDENCE 并记 `failure_code`，不推进 COMPLETED。

### 3.3 分层：analysis 纯函数 + application collector

守住 analysis 纯净边界（`ditto_analysis` 禁止依赖生产包）：

- **analysis 层** `collect_hard_gate_evidence(view: HardGateEvidenceView) -> HardGateEvidence`：纯函数，从 typed 输入投影 11 个 `GateFact`，零 I/O。输入 `HardGateEvidenceView` 是 analysis 自有的 frozen dataclass，只含 gate 判定所需的 typed 事实（不暴露 application/store 类型）。
- **application 层** `ExperimentEvidenceCollector`（`processes/experiments/evidence_collector.py`）：编排 collector——读 snapshot + attempts + artifacts + snapshot manifest + walk-forward aggregation → 装配 `HardGateEvidenceView`（调 analysis 纯函数得 `HardGateEvidence`）+ 装配 `ReviewPacketInput` → 调 `assemble_review_packet` → 经 `ExperimentWriterProtocol.publish_review_packet` 持久化。

## 4. 数据流

```
coordinator.tick
  └─ _advance_completed_stages
       └─ stage == EVIDENCE
            └─ ExperimentEvidenceCollector.collect(experiment_id)
                 ├─ 读 ExperimentSchedulerSnapshot（projection + folds + attempts + holdout_claim + launch_spec）
                 ├─ 读 snapshot manifest → snapshot_hash / registry_hash / pit_policy
                 ├─ 读 artifact index（ArtifactRecord by candidate_id+fold_id+attempt_id）
                 ├─ 读 walk-forward aggregation → metric_values（per selected candidate）
                 ├─ 装配 HardGateEvidenceView → collect_hard_gate_evidence() → HardGateEvidence
                 ├─ 装配 ReviewPacketInput（18 字段，§5）
                 ├─ assemble_review_packet(input) → ReviewPacket
                 └─ writer.publish_review_packet(packet, lease_fence=...) → ArtifactRecord
            └─ store.transition_experiment(target_status=COMPLETED, target_stage=EVIDENCE)
       └─ return SchedulerTickState.COMPLETED
```

**candidate 粒度**：review packet 是 per-candidate。EVIDENCE 产 packet 的 candidate = `holdout_claim.candidate_id`（= CANDIDATE_SELECTION 选中、HOLDOUT claimed 的 candidate）。进 EVIDENCE 前 holdout_claim 必存在（HOLDOUT done 的前提）。

## 5. ReviewPacketInput 18 字段装配表

| 字段 | 来源 | 备注 |
|------|------|------|
| `experiment_id` | `snapshot.projection.record.experiment_id` | |
| `candidate_id` | `snapshot.holdout_claim.candidate_id` | selected candidate |
| `fold_ids` | selected candidate 的两个 canonical assembler source row | 与 `attempt_ids` 成对（§8.3） |
| `attempt_ids` | selected candidate source row 绑定的精确终态 attempt | 与 `fold_ids` 成对（§8.4） |
| `spec_hash` | `encode_launch_spec(launch_spec).content_hash` | 参考 `trial_evidence_bridge.py:443-447` |
| `resolved_spec_hash` | `launch_spec.execution_bindings[selected].resolved_spec_hash` | |
| `parameter_hash` | `CandidateSpec.parameter_hash`（selected candidate） | `specs.py:218` |
| `snapshot_hash` | 唯一 `preflight_passed` 事件中的 snapshot manifest projection | §8.1 |
| `registry_hash` | 唯一 `preflight_passed` 事件中的 registry manifest hash | §8.1 |
| `objective` | `launch_spec.promotion_objective` | |
| `objective_payload_hash` | `promotion_objective.canonical_payload()` hash | **collector 定义**（§8.5） |
| `hard_evidence` | `collect_hard_gate_evidence(view)` | analysis 纯函数 |
| `metric_values` | walk-forward aggregation（selected candidate），提取 `.metric_value`，跳过 None | **类型转换**（§8.2） |
| `comparison_payload_hash` | selected candidate 的 walk-forward comparison canonical hash | **collector 定义** |
| `r1_impact_payload_hash` | `None`（第一版 NOT_EVALUATED） | 用户已确认 |
| `selection_evidence_artifact_id` | durable selection-ledger artifact | C2b 仍为 `None`，后续 selection-evidence slice 接通 |
| `holdout_claim_id` | `snapshot.holdout_claim.claim_id` | |
| `candidate_rationale` | parameter delta vs baseline 模板 | **collector 定义**（§8.5） |

## 6. 11 个 HardGate 判定逻辑

每个 `GateFact = {satisfied: bool|None, detail: object}`。`satisfied=None` → `NOT_EVALUATED`。

| gate | satisfied 逻辑 | detail | 证据源 |
|------|------|------|------|
| `certified_snapshot` | snapshot manifest 标记 certified | snapshot_id + cert 状态 | snapshot manifest |
| `ninety_six_month` | 已验证 preflight 可用连续月份 ≥ 96 月 | eligible 月数 | `reconstruct_preflight_report(...).eligible_month_count` |
| `pit_known_at` | manifest pit_policy 一致且非 unsafe | pit_policy | snapshot manifest |
| `split_purge_embargo` | 所有 walk-forward fold 都配置正数 purge 或 embargo | purge/embargo 配置 | `FoldPersistenceSpec.purge_sessions` / `embargo_sessions` |
| `reproduction` | selected candidate 所有 attempt 有 reproduction_fingerprint | fingerprint | `AttemptPersistenceSpec.reproduction_fingerprint` |
| `cost_assumptions` | 全部 walk-forward fold 的真实 execution policy hash 非空、非全零且唯一一致 | ordered hashes + unique hashes | `ResearchExecutionSemantics.policy.canonical_hash`（Task 5e 已闭合） |
| `baseline_declared` | launch_spec 恰好一个 `is_baseline=True` 且与 `promotion_objective.baseline_candidate_id` 一致 | baseline_candidate_id | `launch_spec.candidates` / `promotion_objective.baseline_candidate_id` |
| `trial_declaration` | durable trial ledger 的 observed/declared family count 一致 | declared/observed trial count | immutable `selection_evidence` artifact（Task 5d 已闭合） |
| `holdout_claim` | `snapshot.holdout_claim` 非空 | claim_id | `snapshot.holdout_claim` |
| `artifact_completeness` | 所有应产 artifact 存在、content_hash/schema_hash/row_count 齐全 | artifact count + 缺失项 | `ArtifactRecord` index |
| `r2_live_gate` | `None`（NOT_EVALUATED） | None | Beta 阶段，design §9.2 允许；G2 live acceptance 才关闭 |

**状态更新（2026-07-27）**：C2b 最初的两个 interim 项已经由后续切片关闭：
Task 5d 使用 durable selection ledger 提供真实 trial declaration，Task 5e 使用
每个 fold 的 execution-policy canonical hash 提供真实 cost consistency。
`r2_live_gate` 仍为 `NOT_EVALUATED`，因此 deterministic fixture 只能证明
packet/evidence 闭环；promotion 必须返回 `hard_gate_blocked`，active pointer 与
R1 active version 不变，不得表述为 R3 live release PASS。

Promotion target binding 同时 fail closed：Schema V1 的 `packet.spec_hash`
字段承载 canonical launch-spec hash；handler 必须由 lineage experiment 读回
exact launch，核对 `strategy_id@version` 与 launch hash，再把
`launch.strategy_spec_hash` 交给 promotion 对照 immutable governance version。
这样不修改 Research Schema V1，也禁止 packet 跨策略/版本重放。

> 每个 gate 的精确判定（如 ninety_six_month 的月数计算、artifact_completeness 的「应产」清单来源）在 TDD 时按 `HardGateEvidenceView` 的 typed 字段精确化；design 在此给出判定方向与证据源。

## 7. metric_values / comparison / rationale 来源

- **metric_values**：复用 `aggregate_walk_forward`（`walk_forward.py:663`）已计算的 `WalkForwardCandidate.metrics`（8 个 metric id：NET_RETURN / RELATIVE_NET_RETURN / SHARPE_RATIO / CALMAR_RATIO / MAX_DRAWDOWN / TURNOVER / COST_DRAG / CAPACITY）。collector 取 selected candidate 的 metrics，从每个 `ScalarEvidence.metric_value` 提取 `ResearchMetricValue`，**跳过 None**（缺失 metric 不放入 mapping → `evaluate_evidence_gates` 自然判 `NOT_EVALUATED`，符合 design §9.2）。
- **comparison_payload_hash**：对 selected candidate 的 `WalkForwardCandidate`（或其 FoldComparison 序列）做 canonical encoding（orjson `OPT_SORT_KEYS` + SHA-256），与 Task 13 artifact content-addressing 同源。
- **candidate_rationale**：第一版模板文本，从 selected candidate 的 `parameters` delta vs baseline `parameters` 生成（如 `"candidate <id>: top_k=<x> (baseline <y>), momentum_3m_weight=<z>"`）。design §9.2 明确 message 只作展示，不参与 gate 裁决。

## 8. 输入缺口处理

### 8.1 snapshot_hash / registry_hash（不在 scheduler snapshot）

`ExperimentSchedulerSnapshot` 不含这两个 hash。collector 从唯一
`preflight_passed` 事件投影 `snapshot_hash` + `registry_hash` + `pit_policy`，
并先调用 `reconstruct_preflight_report` 重验完整 preflight payload；96 个月门禁
使用重构报告的 `eligible_month_count`，不再把两个 walk-forward test window
误当成完整 96 个月研究协议。

### 8.2 metric_values 类型转换

聚合器输出 `ScalarEvidence`（`metric_value: ResearchMetricValue | None`），`ReviewPacketInput` 要 `Mapping[ResearchMetricId, ResearchMetricValue]`。collector 提取非 None 的 `metric_value` 组 mapping；None 的跳过（→ NOT_EVALUATED）。

### 8.3 fold_ids 装配

`holdout_claim.fold_id` 是单个 holdout fold。`ReviewPacketInput.lineage.fold_ids`
来自 selected candidate 的两个 canonical walk-forward source rows；collector
要求它们与 selected aggregation folds 精确相等、互不重复且均为
`COMPLETED`。

### 8.4 attempt_ids 装配

直接使用上述两个 source rows 各自绑定的精确终态 `attempt_id`，保持与
`fold_ids` 同序成对；retry 的旧 attempt 不进入 packet lineage。

### 8.5 objective_payload_hash / candidate_rationale（无生产源）

- `objective_payload_hash`：用 `promotion_objective` 的 canonical encoding hash（`promotion_objective.canonical_payload()` 若存在；否则 collector 定义 canonical orjson encoding）。
- `candidate_rationale`：见 §7 模板。

## 9. 失败语义

| 失败场景 | 处理 |
|---------|------|
| artifact 缺失 | collector 正常产出并持久化 packet，`artifact_completeness` gate 标 `satisfied=False`（FAIL）→ governance promote 时 hard gate 阻断 |
| metric 缺失（None） | 跳过，gate 标 `NOT_EVALUATED`（不失败） |
| snapshot manifest 读取失败 | collector 抛 typed `AppProcessError` → tick fail-fast → experiment 卡 EVIDENCE，记 `failure_code` |
| `publish_review_packet` 失败（lease/IO） | collector 抛 typed error → tick fail-fast → 不推进 COMPLETED，下个 tick 重试 |
| `transition_experiment` CAS 冲突 | tick 重试（既有 lease CAS 机制） |

**关键**：artifact/metric 缺失**不阻断 packet 产出**（gate 客观记录 fail/not_evaluated），只有结构性错误（manifest 读失败、publish IO 失败）才 fail-fast。这保证 review packet 如实反映证据状态，而非「凑不齐就不产」。

## 10. 分层与 Protocol 接线

- **analysis**（`analysis/experiments/`）：
  - 新增 `HardGateEvidenceView`（frozen dataclass，gate 判定所需 typed 事实）。
  - 新增 `collect_hard_gate_evidence(view) -> HardGateEvidence`（纯函数，零 I/O）。
  - 导出经 `experiments/__init__.py`。
- **application**（`application/processes/experiments/evidence_collector.py`）：
  - 新增 `ExperimentEvidenceCollector`，注入：`ExperimentSchedulerStore`（读 snapshot）、`ExperimentReaderProtocol`（读唯一 preflight event）、`ExperimentWriterProtocol`（publish）和 `WalkForwardEvidenceAssembler`（verified indexed reports + persisted execution semantics）。
  - `collect(experiment_id, *, lease) -> ReviewPacket`。
- **coordinator**（`coordinator.py`）：
  - EVIDENCE 分支注入 `ExperimentEvidenceCollector`，调 `collect` → `transition_experiment(COMPLETED)`。
- **DI**（`providers_process.py`）：注册 `experiment_evidence_collector` provider，注入 coordinator。

## 11. commit 节奏

参考既有 commit 节奏（每个 commit 独立 GREEN + pixi check 全绿）：

1. **commit 1（analysis）**：`HardGateEvidenceView` + `collect_hard_gate_evidence` 纯函数 + 单测（11 gate 各 satisfied True/False/None）。
2. **commit 2（application collector）**：`ExperimentEvidenceCollector` + `ReviewPacketInput` 装配 + `publish_review_packet` 接线 + 单测（mock reader/writer，验证 18 字段装配 + metric 类型转换 + fold_ids 装配）。
3. **commit 3（coordinator 接通）**：EVIDENCE 分支接入 collector + `transition_experiment(COMPLETED)` + 单测（验证 tick 推进、失败 fail-fast、CAS 重试）。
4. **commit 4（Task 22 后端 e2e）**：`test_r3_stock_selection_golden` +
   `test_r3_etf_research_golden` + `test_r3_governance_recovery` +
   `test_r3_scheduler_capacity`（deterministic fixture，验证真实 experiment →
   packet → promotion `hard_gate_blocked`，active pointer/R1 active 不变）。

## 12. Task 22 e2e 衔接

evidence 闭环补完后，Task 22 的 4 个后端 e2e（commit 4）可跑通真实闭环：
- **stock/ETF 双黄金**：typed spec → certified snapshot → walk-forward → holdout
  claim → **evidence collection → review packet** → promotion
  `hard_gate_blocked` → active pointer/R1 active version 保持不变。
- **governance recovery**：review decision append-only、active pointer 切换、reactivate。
- **scheduler capacity**：128 candidate preflight、2/4 worker、单 slot、pause/resume、lease reclaim。

e2e 用 deterministic fixture（不冒充 live provider），因此只验 packet 产出与
honest promotion block；publish/activate success 仅由 R2 live Gate 关闭后的
explicit live G2 acceptance 证明（§13 非目标）。

## 13. 非目标

- ❌ 前端 W5（Task 18-22 的 ditto-app 部分）——独立后续。
- ❌ live G2 acceptance（需 R2 live Gate 关闭）——`r2_live_gate` 第一版 NOT_EVALUATED。
- ❌ `r1_impact_payload_hash` 真实归因（candidate vs active strategy）——第一版 None（用户已确认）。
- ❌ 第二套 evidence/gate/artifact 类型系统——复用 Task 14 既有契约。
- ❌ 修改 `ReviewPacketInput` / `HardGateEvidence` / `assemble_review_packet` / `publish_review_packet` 契约——零改动。

## 14. 验收标准

- [ ] 一个真实 experiment tick（planning → exploration → walk-forward →
      candidate_selection → holdout → **evidence**）产出非空 `ReviewPacket`，
      11 个 hard gate 客观判定（10 个 PASS，`r2_live_gate=NOT_EVALUATED`）。
- [ ] deterministic packet 经
      `POST /strategies/{id}/versions/{v}/publish`（Task 17 #6c）驱动
      `StrategyPromotionProcess.promote` 返回 `hard_gate_blocked`，active
      pointer、R1 active version 与 activation history 均不变。
- [ ] packet lineage → persisted launch hash/`strategy_id@version` →
      governance version `spec_hash` 三段身份完全一致；缺失或漂移在任何
      governance 写入前以 typed error 阻断。
- [ ] 只有 explicit live G2 acceptance 将 `r2_live_gate` 关闭为 PASS 后，才能
      验证 publish/activate 成功；任何 live blocker 都不得由 fixture 替代。
- [ ] EVIDENCE stage 后 `experiment.status == COMPLETED`。
- [ ] artifact/metric 缺失时 packet 仍产出（gate 如实 fail/not_evaluated），不 fail-fast。
- [ ] manifest/publish 结构性错误时 tick fail-fast，experiment 卡 EVIDENCE，记 failure_code。
- [ ] commit 1-3 单测全绿；commit 4 的 4 个 e2e 用 deterministic fixture 全绿。
- [ ] `pixi run -e dev check` 全绿（37 contracts + arch-smells + type/lint + test）。

## 15. 与 R4 的关系

R4（组合优化 + 风险 + 复盘）**不硬依赖**本闭环——R4 消费 R1 signal + R3 `StrategySpec`/active version 契约，不吃 review packet。本闭环纯粹为闭环 R3 自身价值。R4 启动前需独立 code exploration + mini-design（roadmap §18）。
