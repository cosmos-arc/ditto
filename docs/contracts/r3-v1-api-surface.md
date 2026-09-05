# R3 v1 API Surface 分类（已批准）

> 状态：`APPROVED`
> runtime 事实源：`ditto_apps.main.app.openapi()`（2026-08-01 当前分支，只读生成）
> 设计事实源：R3 设计 §12.2（37 operations）与 W5 页面接线设计
> 机器可读事实源：[`r3-v1-api-surface.json`](r3-v1-api-surface.json)
>
> JSON canonical SHA-256: `13d0f234c2b240be0a1bd103525b19b54967b67425d234d9b23807545e9c89f7`

Task 4 classification 已由用户批准；批准 reference 为
`user-message:2026-07-31:final-task4-classification-approved`。Task 9 candidate
evidence bundle proposal 也已独立批准；批准 reference 为
`user-message:2026-08-01:task9-artifact-proposal-approved`。
JSON 是规范事实源；本 Markdown 是便于审批的派生说明。上述 SHA-256 对 JSON
执行 UTF-8、对象 key 排序、无多余空白的 canonical serialization 后计算，
用于证明本文绑定的是当前 machine-readable snapshot。

## 1. 结论

当前 runtime 有 39 个 R3 research/strategy operations；设计 §12.2 有 37 个。
清单共 40 项：37 个设计 operation，加 3 个 W5/runtime-only operation。

| 分类 | 数量 | 含义 |
|---|---:|---|
| `IMPLEMENT / IMPLEMENTED` | 33 | 精确路径与完整读写语义均已实现并通过 runtime reconciliation |
| `EQUIVALENT / IMPLEMENTED` | 6 | runtime replacement 已存在且 recorded replacement 已批准 |
| `DEFER / PLANNED` | 1 | 已批准仅延期重复 launch alias；collection create-launch 保留功能 |

<!-- BEGIN MACHINE-DERIVED APPROVAL SUMMARY -->
```json
{
  "classification_counts": {
    "DEFER/PLANNED": 1,
    "EQUIVALENT/IMPLEMENTED": 6,
    "IMPLEMENT/IMPLEMENTED": 34
  },
  "runtime_contract_count": 40,
  "defer_operation_ids": [
    "design_research_experiment_launch_alias"
  ],
  "equivalent_operation_ids": [
    "design_strategy_create_version",
    "design_strategy_review_decisions",
    "design_strategy_reactivate",
    "design_research_experiment_report",
    "design_research_retry_fold",
    "design_research_review_detail"
  ],
  "implement_scope_operation_ids": [
    "design_research_factor_diagnostics",
    "design_strategy_version_detail",
    "design_strategy_events",
    "design_research_candidate_selection",
    "design_research_holdout_evaluations",
    "design_research_candidate_selections",
    "design_research_candidate_exclusions",
    "design_research_candidate_factor_contributions"
  ],
  "local_state_decisions": [
    "candidate comparison pins are session-local UI state capped at four; they are not candidate-selection or holdout state"
  ],
  "artifact_approval_proposal_ids": [
    "candidate_evidence_bundle_proposal"
  ],
  "classification_approval_state": "APPROVED",
  "candidate_bundle_proposal_state": "APPROVED"
}
```
<!-- END MACHINE-DERIVED APPROVAL SUMMARY -->

`implementation_state` 对 `EQUIVALENT` 只表达 replacement 已存在；例如 durable
idempotency 仍可由 Task 7 加固，但不能因此把 replacement 伪标为不存在。
`DEFER` 不设置 closing task。

审批使用两个独立状态机，当前真实快照为 `APPROVED / APPROVED`：

1. Task 4 classification approval：`approval_state=PENDING` 时
   `approval_required` 与全部 `DEFER/EQUIVALENT.user_approval` 都必须为
   `PENDING`，其 `decision/reference=null`。
2. 用户已批准完整 classification：顶层、`approval_required` 与上述每个 entry
   已同步为 `APPROVED`，并记录非空 decision/reference。
3. Task 9 单独 artifact checkpoint 后，proposal 才能变为 `APPROVED` 或
   `NOT_REQUIRED`。前者必须记录单独批准 reference；后者必须记录
   `schema unchanged`、复用 generic envelope 的证据 reference。classification
   尚未 `APPROVED` 时，proposal 不得离开 `PENDING`。当前 proposal 已按前者
   独立转为 `APPROVED`。

## 2. APPROVED CLASSIFICATION DECISION

### 2.1 唯一 DEFER

`POST /research/experiments/{experiment_id}/launch`：当前 completion plan
   选择 `POST /research/experiments` 作为唯一 create-launch；保留第二个 alias
   会产生第二个 operation/idempotency namespace。用户已批准仅延期该重复 alias；
   collection create-launch 功能保留。影响 DoD 3、6、17。

### 2.2 已闭环的新增 IMPLEMENT

为满足“完成所有功能”，以下 8 项不再 DEFER：

- Task 8：strategy version detail、append-only strategy events；backend query/store/
  route 与 Studio/governance audit consumer 同步完成。
- Task 9：factor diagnostics、candidate-selection、holdout-evaluations，以及
  selections/exclusions/factor-contributions 三个 arbitrary candidate drill-down；
  backend evidence/command/read routes 与 factor/Experiment 页面同步完成。
- 三个 candidate drill-down 统一使用 typed opaque-cursor page：
  `experiment_id` 必填、`cursor` 可选、`limit=1..100`（默认 20）。cursor 编码
  `content_hash + offset`；格式非法返回
  `422 INVALID_CANDIDATE_EVIDENCE_CURSOR`，与当前 artifact hash 不一致返回
  `409 EVIDENCE_STALE`，`next_cursor=null` 表示结束。
- candidate-selection 与 holdout mutation 复用 Task 7 durable idempotency，
  `implementation_tasks=[7,9]`、唯一 closing task=9。

这 8 项的新增 scope、跨层文件和前端依赖已按 completion plan 全部实现，并已
从 approved Task 4 classification 的 `PLANNED` 状态收口为 `IMPLEMENTED`。

**Candidate immutable bundle/manifest proposal（Task 9 已独立批准）：**

- manifest identity 为
  `experiment_id + candidate_id + comparison_payload_hash + comparison_revision`；
- `fold_sources` 按 `(validation_fold_ordinal, fold_id)` 稳定排序；每 fold 必须
  由 current comparison lineage 显式选定 terminal successful committed
  `attempt_id/run_id`，禁止按 latest/max 猜测，失败 attempt 与旧 retry attempt
  必须排除；
- 每 fold 显式引用 selection/exclusion/contribution 的
  artifact id/hash/kind/version；三类 page 的唯一 artifact identity 是聚合后的
  `candidate_bundle_artifact_id/content_hash`，不是任一单 fold artifact；
- selection items 排序为
  `(validation_fold_ordinal, fold_id, trade_date, rank, instrument_id)`；
  exclusion items 为
  `(validation_fold_ordinal, fold_id, trade_date, instrument_id, stage,
  reason_code)`；contribution items 为
  `(validation_fold_ordinal, fold_id, trade_date, instrument_id, factor_id)`；
- 无 cursor 首次请求解析 current comparison 明确引用的 bundle。retry 成功产生
  新 comparison revision 与新 immutable bundle，旧 bundle 保留；旧 cursor
  绑定的 hash 若不再是 current comparison bundle，返回 `409 EVIDENCE_STALE`；
- `next_cursor` 绑定 bundle hash、resource kind、offset，禁止 selections、
  exclusions、factor-contributions 之间复用；
- 必须覆盖 2+ folds、retry 新旧 attempts、stable order、page boundary/no
  duplicate、cross-kind cursor rejection、hash drift 和 restart parity。

批准结论为：ArtifactManifest v1 与 Research SQLite Schema v1 均保持不变并
复用既有 generic content-addressed envelope/index；不新增 DDL、migration、
backfill、architecture allowance 或环境配置。新增 artifact kind 为
`fold_selection_trace_exposures_v1` 与 `candidate_evidence_bundle_v1`；新写入使用
ReviewPacket v3，v1/v2/v3 均可读，v1/v2 只读且不迁移、不回填。ETF proving lane
显式记录 `NOT_APPLICABLE / ETF_LANE`。批准 reference 为
`user-message:2026-08-01:task9-artifact-proposal-approved`。

### 2.3 六个 EQUIVALENT

1. 版本创建：设计 `POST /strategies/{id}/versions` → runtime
   `PUT /strategies/{id}`。PUT 以 body `version` 作 parent optimistic lock，
   创建 immutable child draft，不覆盖历史。
2. 审查决定：设计单个 `review-decisions` → runtime 独立 `approve` 与 `reject`。
   action 从 body discriminator 移到明确 action path；两者写不同 typed event。
3. Reactivate：设计根级 `/strategies/{id}/reactivate` → runtime
   `/strategies/{id}/versions/{version}/reactivate`。目标版本进入 path，确认文本
   与 pointer revision 仍绑定相同 identity。
4. Experiment report：设计单 aggregate report → W5 fan-out
   detail/comparison/gates/artifacts/selection-evidence。每个 component 有 revision
   或 content hash，partial error 不被聚合响应掩盖。
5. Failed-fold retry：设计 fold 在 path → runtime `retry-fold` 且 body 同时携带
   `candidate_id`、`fold_id`、fold `expected_revision`；避免假设 fold 全局唯一。
6. Review detail：设计 `reviews/{review_id}` → runtime
   `experiments/{experiment_id}/review-packet`。这是需要明确批准的资源身份变化：
   `spec_hash` 与 rerun experiment 是 one-to-many，queue 每次查询选择“有
   review packet 的最新 experiment”。后续 rerun 会让刷新后的同一 queue item
   解析到不同 `experiment_id`；因此 `experiment_id` 只是 latest-selection
   导航结果，`bundle_hash` 才是最终不可变审计 identity。submit/publish 必须
   携带并校验操作者看到的 `bundle_hash`，陈旧 bundle 以 `EVIDENCE_STALE`
   fail closed，不能只按 `spec_hash` 继续。

每项的 request/response/error/idempotency/revision/maturity/audit 逐项证明见 JSON
对应 `equivalence.proof`；没有把语义不成立的 version detail 或 arbitrary
candidate ledger read 标成等价。

### 2.4 Candidate pin max-4

已批准：comparison 页最多 pin 4 个 candidate 是**纯本地、session-local
展示选择**，刷新可丢失，不产生服务器写入，也不代表候选预选或 holdout
消费。真正的 candidate-selection / holdout 是 server-persisted domain state，
由 Task 9 实现；local pins 永远不调用这两个 mutation。这样不会让 UI 与服务端
各自维护一套晋级状态。

## 3. 完整 operation inventory

路径均省略固定 `/api/v1` 前缀。`Idem` 表示 Idempotency-Key；`rev` 表示 body
revision/CAS，`hash` 表示 canonical/content identity。所有 response 都包在
稳定 envelope；准确地说，所有成功响应使用 `APIResponse[...]`，当前 OpenAPI
snapshot 的 transport validation `422` 使用 `HTTPValidationError`。各 entry 的
业务错误目标仍由 `contracts.error_codes` 单独冻结，不能把当前仅记录的 422
transport schema 冒充最终业务错误 envelope。

三个 candidate evidence page 的 envelope 均为 `APIResponse[...PageResponse]`。
page 固定包含 `candidate_id`、`experiment_id`、`artifact_id`、`content_hash`、
`items`、`next_cursor`；items 分别保留 selection、exclusion、factor
contribution 的 typed 字段，不以通用 JSON payload 代替。reader 必须先校验
cursor 解码、artifact content hash 与 offset 边界，再读取对应 slice。
其中 `artifact_id/content_hash` 明确指 candidate immutable bundle，而非单 fold；
cursor 还必须绑定 resource kind，不能跨三类 evidence page 复用。

### 3.1 Catalog 与 Strategy

| Design operation | 分类 / runtime | Request identity | Response DTO | Error / Idem / revision | Maturity / 页面 / DoD |
|---|---|---|---|---|---|
| `GET /research/node-descriptors` | IMPLEMENTED / exact | registry catalog | `list[NodeDescriptorResponse]` | read；descriptor version/registry hash | experimental；Studio node library；4,5,17 |
| `GET /research/factors` | IMPLEMENTED / exact | factor catalog | `list[FactorDescriptorResponse]` | read；factor_id+version | experimental；Studio/factor catalog；4,5,10,17 |
| `GET /research/factors/{factor_id}/diagnostics` | IMPLEMENTED（Task 9） | factor+snapshot/window+registry hash | `FactorDiagnosticsResponse` 含 provenance/artifact/content hash | 404 FACTOR_NOT_FOUND、422 scope/snapshot identity；read | experimental；factor detail；10,17 |
| `POST /strategies` | IMPLEMENTED（Task 7） | strategy_id+canonical spec+Idem | `StrategyResponse` | 409 identity/Idem；422 spec；version=1 | initial-focus；Studio create；4,14,17 |
| `POST /strategies/{id}/versions` | EQUIVALENT → `PUT /strategies/{id}` | path id + body parent version | `StrategyResponse` 新 draft | 409 stale/Idem；422 spec；parent version CAS | initial-focus；Studio save；4,14,17 |
| `GET /strategies/{id}/versions` | IMPLEMENTED / exact | strategy_id | `list[StrategyVersionResponse]` | read；immutable version/spec_hash | initial-focus；versions/review join；11,14,17 |
| `GET /strategies/{id}/versions/{v}` | IMPLEMENTED（Task 8） | strategy_id+version | `StrategyVersionDetailResponse` 含 canonical spec/hash/state | 404 STRATEGY_VERSION_NOT_FOUND；immutable hash | initial-focus；Studio/governance detail；4,11,17 |
| `GET /strategies/{id}/versions/{v}/diff` | IMPLEMENTED / exact | strategy_id+version | `StrategyVersionDiffResponse` | 404 version；target/parent spec hashes | initial-focus；versions/review diff；4,11,17 |
| `POST /strategies/{id}/versions/{v}/validate` | IMPLEMENTED / exact | id/version+candidate spec | `StrategySpecValidationResponse` | invalid spec=200 `valid=false`；零写无需 Idem；candidate hash | initial-focus；Studio validation；4,5,17 |
| `POST .../{v}/submit-review` | IMPLEMENTED（Task 8） | id/version+actor/reason+bundle_hash+Idem | `StrategyVersionStateResponse` | 409 state/Idem；422 packet/gate/evidence；immutable version | initial-focus；review panel；12,13,14,17 |
| `POST .../{v}/review-decisions` | EQUIVALENT → `approve` + `reject` | action path+actor/reason+Idem | `StrategyVersionStateResponse` | 409 state/Idem；422 validation；version target | initial-focus；review controls；12,13,14,17 |
| `POST .../{v}/publish` | IMPLEMENTED（Task 7） | id/version+bundle_hash+actor/reason+Idem | `StrategyActivePointerResponse` | 409 state/pointer/Idem；422 gates/review/evidence；pointer rev | initial-focus；publish dialog；11,12,14,17 |
| `POST .../{v}/deprecate` | IMPLEMENTED（Task 7） | id/version+actor/reason+Idem | `StrategyVersionStateResponse` | 409 state/Idem；422；immutable version | initial-focus；governance；11,14 |
| `GET /strategies/{id}/active` | IMPLEMENTED / exact | strategy_id | `StrategyActiveResponse` | 404 no pointer；pointer_revision CAS identity | initial-focus；detail/dialogs；11,14,17 |
| `POST /strategies/{id}/reactivate` | EQUIVALENT → `.../versions/{v}/reactivate` | id/version+actor/reason/impact/confirmation+expected pointer rev+Idem | `StrategyActivePointerResponse` | 409 ACTIVE_POINTER_CONFLICT/Idem；422 confirmation；pointer CAS | initial-focus；reactivate dialog；11,14,17 |
| `GET /strategies/{id}/events` | IMPLEMENTED（Task 8） | strategy_id+after_event_id+bounded limit | `list[StrategyGovernanceEventResponse]`，仅含 event_id/strategy_id/event_type/target_version/decision_or_activation_kind/actor/reason/occurred_at | 404/INVALID_EVENT_CURSOR；append-only event_id；schema unchanged | initial-focus；audit history；11,14,15,17 |

### 3.2 Experiment 与 evidence

| Design operation | 分类 / runtime | Request identity | Response DTO | Error / Idem / revision | Maturity / 页面 / DoD |
|---|---|---|---|---|---|
| `POST /research/experiments` | IMPLEMENTED（Tasks 6→7） | canonical document experiment_id+confirmed_plan_hash+Idem | `ExperimentLaunchResponse` | 409 plan/existing/Idem；422 preflight；plan_hash+rev | experimental；create flow；3,6,7,15,17 |
| `GET /research/experiments` | IMPLEMENTED / exact | local catalog | `list[ExperimentSummaryResponse]` | read；每项 revision | experimental；catalog；6,15,17 |
| `GET /research/experiments/{id}` | IMPLEMENTED / exact | experiment_id | `ExperimentDetailResponse` | 404；revision | experimental；detail/polling；3,6,15,17 |
| `POST .../{id}/preflight` | IMPLEMENTED（Task 6） | path/body experiment_id exact | `ExperimentPreflightResponse` | 409 identity；422 spec/matrix/budget/history/leakage；零写；plan_hash | experimental；preflight panel；3,6,8,17 |
| `POST .../{id}/launch` | DEFER | 与 collection launch 重复 | 与 launch 重复 | 第二 Idem namespace 有漂移风险 | experimental；无页面消费者；3,6,17 |
| `POST .../{id}/pause` | IMPLEMENTED（Task 7） | id+expected rev+Idem | `ExperimentControlReceiptResponse` | 404；409 stale/state/Idem；receipt rev | experimental；controls；6,15,17 |
| `POST .../{id}/resume` | IMPLEMENTED（Task 7） | id+expected rev+Idem | `ExperimentControlReceiptResponse` | 404；409 stale/state/Idem；receipt rev | experimental；controls；6,15,17 |
| `POST .../{id}/cancel` | IMPLEMENTED（Task 7） | id+expected rev+Idem | `ExperimentControlReceiptResponse` | 404；409 stale/state/Idem；receipt rev | experimental；controls；6,15,17 |
| `GET .../{id}/candidates` | IMPLEMENTED / exact | experiment_id | `list[ExperimentCandidateResponse]` | 404；immutable plan candidates | experimental；comparison；6,9,17 |
| `GET .../{id}/comparison` | IMPLEMENTED / exact | experiment_id | `ExperimentComparisonResponse` | 404；content-addressed projection | experimental；comparison；7,8,13,17 |
| `GET .../{id}/gates` | IMPLEMENTED / exact | experiment_id | `list[ExperimentGateResponse]` | read；evaluation IDs/payload hashes | experimental；validation/review；8,12,13,17 |
| `GET .../{id}/report` | EQUIVALENT → 5-resource fan-out | same experiment_id | detail+comparison+gates+artifacts+selection evidence | component 404/typed partial errors；revision+hashes | experimental；detail sections；3,6,7,8,10,17 |
| `GET .../{id}/artifacts` | IMPLEMENTED / exact | experiment_id | `list[ExperimentArtifactResponse]` | 404；artifact/content hash+rev | experimental；evidence/lineage；7,10,16,17,23 |
| `POST .../{id}/folds/{fold}/retry` | EQUIVALENT → `.../{id}/retry-fold` | path id + body candidate/fold/expected fold rev+Idem | `ExperimentControlReceiptResponse` | 404；409 stale/terminal/Idem；fold rev | experimental；recovery；6,15,17,22 |
| `POST .../{id}/candidate-selection` | IMPLEMENTED（Tasks 7→9） | experiment+candidate+rationale/evidence+rev+Idem | `CandidateSelectionReceiptResponse` | 409 selection/rev/Idem、422 eligibility/evidence | experimental；promotion selection；9,12,17 |
| `POST .../{id}/holdout-evaluations` | IMPLEMENTED（Tasks 7→9） | experiment+selection/claim/evidence+rev+Idem | `HoldoutEvaluationReceiptResponse` | 409 HOLDOUT_ALREADY_CLAIMED/Idem、422 identity/evidence | experimental；holdout state；3,9,12,17 |
| `GET /research/candidates/{id}/selections` | IMPLEMENTED（Task 9） | candidate_id path + required experiment_id + optional opaque cursor + bounded limit | `CandidateSelectionPageResponse`：candidate/experiment/candidate-bundle id/hash、typed selection items、next_cursor | 404 evidence；422 mismatch/INVALID_CANDIDATE_EVIDENCE_CURSOR；409 EVIDENCE_STALE；cursor=bundle hash+kind+offset | experimental；drill-down；10,17 |
| `GET /research/candidates/{id}/exclusions` | IMPLEMENTED（Task 9） | candidate_id path + required experiment_id + optional opaque cursor + bounded limit | `CandidateExclusionPageResponse`：candidate/experiment/candidate-bundle id/hash、typed exclusion items、next_cursor | 404 evidence；422 mismatch/INVALID_CANDIDATE_EVIDENCE_CURSOR；409 EVIDENCE_STALE；cursor=bundle hash+kind+offset | experimental；drill-down；10,17 |
| `GET /research/candidates/{id}/factor-contributions` | IMPLEMENTED（Task 9） | candidate_id path + required experiment_id + optional opaque cursor + bounded limit | `CandidateFactorContributionPageResponse`：candidate/experiment/candidate-bundle id/hash、typed contribution items、next_cursor | 404 evidence；422 mismatch/INVALID_CANDIDATE_EVIDENCE_CURSOR；409 EVIDENCE_STALE；cursor=bundle hash+kind+offset | experimental；drill-down；10,17 |
| `GET /research/reviews` | IMPLEMENTED / exact | current local queue | `list[StrategyVersionResponse]` | read；version/spec_hash | experimental；review queue；12,13,17 |
| `GET /research/reviews/{review_id}` | EQUIVALENT → latest experiment review-packet（已批准） | one-to-many spec_hash lookup → latest packet-bearing experiment_id；刷新后可能变化 | `ExperimentReviewPacketResponse` | 404 packet；bundle_hash 是最终 identity；stale bundle 必须 EVIDENCE_STALE | experimental；review detail；9,10,12,13,17 |

### 3.3 W5/runtime-only operations

| Runtime operation | 分类 | Request identity | Response DTO | Error / revision | 页面 / DoD |
|---|---|---|---|---|---|
| `GET /strategies` | IMPLEMENTED | limit/offset | `list[StrategyResponse]` | 422 pagination；current version | Strategy catalog；17 |
| `GET /strategies/{id}` | IMPLEMENTED | strategy_id | `StrategyResponse` | 404；current version/spec | Strategy detail/Studio；4,17 |
| `POST /strategies/{id}/versions/{v}/author-preview` | IMPLEMENTED | strategy_id+immutable version+validated preview request | `StrategyAuthorPreviewResponse` | 422 validation；read-only preview evidence | Research Agent Author preview；4,14,17 |
| `GET /research/experiments/{id}/selection-evidence` | IMPLEMENTED（Task 9） | experiment_id resolves selected/published ledger | `ExperimentSelectionEvidenceResponse`（typed payload） | 404；artifact_id/content_hash/pinned | Experiment/Review evidence；10,17,23 |

这些 runtime-only operation 不是遗漏的“设计完成”：它们以 `origins` 明确标记
`W5`/`RUNTIME_ONLY`，contract test 仍把它们纳入完整 runtime reconciliation。

## 4. Runtime reconciliation 与 closure 规则

- Contract test 直接读取 `app.openapi()`，不启动 server、不访问 DB。
- JSON `runtime_contracts` 保存当前 40 个 operation 的 exact observed projection：
  `operationId`、method/path、request body schema（无 body 为 `null`）、全部
  response status/schema、全部 path/query/header parameter 的
  name/in/required/schema，以及 `x-ditto-maturity`。Task 9 的 candidate-selection
  与 holdout-evaluations 已观测到 required `Idempotency-Key` string header；其余
  operation 同样记录 optional `X-Ditto-API-Contract-Version: v1` fail-closed
  assertion header，只保存当前 OpenAPI 真实值，不伪造未来状态。
- runtime 的 40 个 R3 operation 必须全部被 exact entry 或
  `equivalence.runtime_operations` 覆盖；多一个或少一个都会失败。
- Closure mode 要求全部非 `DEFER` entry 为 `IMPLEMENTED`，且 primary runtime
  method/path、operationId、request/response/status/parameters/maturity 均精确匹配；
  任一非 `DEFER / PLANNED` 会直接使 contract test 失败。
- 上述投影只在进程内调用 `ditto_apps.main.app.openapi()`，按 path/method 排序并
  提取 operationId、request/response、全部 parameters 与 maturity；不启动
  server、不构造 registry、不访问任何 DB。
- `EQUIVALENT` 必须 `IMPLEMENTED` 且 replacement operationId/method/path 当场解析。
- `DEFER` 必须与顶层 classification approval 同步，记录 decision/reference、
  列出受影响 DoD，且不得有 runtime path 或 closing task。
- 当前 `runtime_contracts` 已与 frozen OpenAPI 重新对账；Task 7 mutation 已观测到
  required `Idempotency-Key` header 及其 string schema，不依赖文字声明代替契约。

已完成职责按 completion plan 核对如下：

- Task 6 已交付 preflight 与 collection create-launch 的 route/DTO/CLI；
- Task 7 已为 launch、experiment controls 与 governance mutations 实施 durable
  Idempotency-Key，并将 `CreateStrategyHandler` / `UpdateStrategyHandler` 纳入同一
  机制，代表性 create/update/deprecate 用例已覆盖；
- Task 8 已关闭 submit-review 的 bundle identity 与 hard-gate fail-closed；
- Task 9 已关闭 aggregate selection-evidence 的非空 contribution 与
  industry/size exposure；
- Task 10 保持 literal 128 scheduler recovery 边界；Task 12–15 已消费这些
  runtime contracts，Task 16 冻结 typed DTO/OpenAPI closure。
