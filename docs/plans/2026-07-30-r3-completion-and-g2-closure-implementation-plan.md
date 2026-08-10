# R3 剩余目标与 G2 闭环 Implementation Plan

> **执行合同：** 按 Task 顺序推进；风险变更使用对应 Ditto skill；只读且独立的工作可用宿主原生 subagents；每个波次以本文 Exit Gate 与当前 diff 的验证结果为准。

**Goal:** 从当前 R3 feature branches 出发，修复已发现的质量与契约缺陷，完成 Experiment 写路径、Strategy Studio/Experiment/Review 工作台、selection/exposure evidence、OpenAPI/page contracts、deterministic acceptance，并在 R2 live Gate 关闭后生成双黄金路径的真实 G2 release evidence。

**Architecture:** 延续既有边界：`ditto_analysis.experiments` 拥有纯研究控制面与独立 Research SQLite，`ditto_strategy` 拥有策略流水线、selection evidence 与治理领域规则，`ditto_application` 编排 planning、execution、evidence、promotion 和 live-evidence 验证，`ditto_apps` 只提供 HTTP/CLI/job/DI 适配；`ditto-app` 只消费 OpenAPI 生成类型并维护 UI view-model。deterministic closure 与 live G2 分成两个不可混淆的阶段，fixture 永远不能把 `r2_live_gate` 关闭为 PASS。

**Tech Stack:** Python 3.13、frozen dataclass/Protocol、orjson、Polars、SQLite、FastAPI、Dishka、Pytest；React 19、TypeScript strict、TanStack Router/Query、Zustand、Tailwind v4、Vitest/RTL、Playwright；TDD（RED → GREEN → REFACTOR）。

---

> **设计事实源：** [R3 design](2026-07-19-r3-a-share-research-strategy-governance-design.md) · [R3 主实施计划](2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md) · [Evidence Closure plan](2026-07-27-r3-evidence-collection-closure-plan.md) · [W5 design](2026-07-28-r3-w5-frontend-wiring-design.md)
>
> **计划状态：** READY FOR EXECUTION；数据库 schema、新依赖、架构边界、环境配置和真实数据/浏览器验收仍保留显式 approval checkpoint。
>
> **当前基线（2026-07-30）：**
> - backend `/home/chevy/projects/ditto`：`docs/r3-research-governance-design@ec180b4e`，worktree clean，本地领先远端 feature 4 commits，领先 `main` 123 commits；
> - frontend `/home/chevy/projects/ditto-app`：`feat/r3-research-wiring@1985b3a`，worktree clean，与远端 feature 同步，领先 `main` 7 commits；
> - strict G2 DoD：9 PASS / 9 PARTIAL / 5 BLOCKED；
> - 当前 backend `test-fast`：1 failed / 11724 passed / 1 xfailed，失败是 architecture allowance ownership 期望未同步；
> - 本计划编写与默认开发测试不访问当前或生产数据库，只使用 repository fixtures、`tmp_path` 和任务专用临时 data root。
>
> **跨仓库路径规则：** 未标注的路径相对 backend 根 `/home/chevy/projects/ditto`；标注 `ditto-app` 的路径相对 `/home/chevy/projects/ditto-app`。两个仓库分别提交、分别验证，禁止把一个仓库的未提交状态作为另一个仓库的完成证据。

## 0. 已核实的剩余边界

### 0.1 不能继续按“后端 17/17、T18/T20 完成”计数

当前源码证明以下内容仍未闭环：

1. backend 缺 Experiment preflight/create-launch 公共写路径；
2. mutations 缺可信的 `Idempotency-Key` 语义；
3. submit-review 不读取 ReviewPacket/hard gates；
4. stock golden 的 durable fold trace 在结构上完整，但 golden 仍发布空 `SelectionEvidenceLog()`，industry/size exposure 无生产证据；
5. static OpenAPI 比 runtime 少 72 个 operation，其中 25 个是 R3 research/strategy；
6. frontend research 父路由没有 `<Outlet />`，Studio/detail/review 源码存在但实际子路由不可呈现；
7. frontend reactivate confirmation 与 backend 精确契约不一致，真实请求必然失败；
8. T19 前端只有 experiment list，详情仍是占位；
9. `VITE_USE_MOCK=false` 下仍存在 `PrototypeOnlyEmpty`；
10. R3 live acceptance runner、`docs/evidence/r3/`、`r3-report.json` 和真实 browser artifacts 均不存在；
11. `hard_gate_collector` 当前永久输出 `r2_live_gate=NOT_EVALUATED`，没有可信 live evidence 输入。

### 0.2 本计划非目标

- 不扩展到分钟级、自动交易、AI agent 或多用户审批。
- 不新增 graph/DnD 编辑器依赖；T18 继续采用 Form + 有序类型化 Pipeline。
- 不在本轮实现“从 certified catalog 自动拼装完整 planning document”；preflight/create API 接受上游已装配且可 canonicalize 的文档，该 assembler 另行立项。
- 不重写 backtest、factor engine、artifact store、governance store 或 R1。
- 不新增第二套 Strategy/Experiment/Review DTO 事实源。
- 不用 fixture、MSW、手工布尔值或文档声明冒充 live G2 evidence。
- 不操作当前或 production DB；任何真实数据演练必须使用单独批准的隔离 data root。

## 1. 实施规则与审批门

- 每个 Task 独立执行 RED → GREEN → REFACTOR，并形成小提交。
- 修复 bug/失败时使用宿主原生调试能力；行为变化按 `ditto-test-first` 先观察 RED。
- 每个波次结束执行本文 Exit Gate，不得用历史 GREEN 代替当前 diff 的 fresh output。
- backend 精确测试后至少运行：

```bash
pixi run -e dev arch-check
pixi run -e dev check
pixi run -e dev pre-commit-run
git diff --check
```

- frontend 精确测试后至少运行：

```bash
bun run generate-contracts
bun run audit:routes
bun run prototype:gates
bun run check
bun run build
git diff --check
```

- Apps route 只能解析 DTO、调用 application command/query/process、映射 typed error；不得直接读 SQLite、artifact 文件或 capability internals。
- `analysis` 不依赖生产包；`strategy` 不依赖 application/features/data/backtest/execution；跨平面证据在 application 编排。
- OpenAPI/backend 先冻结，再生成 frontend 类型；不允许 frontend 猜测 backend shape。
- `Idempotency-Key` 不允许只做“header 存在”校验；必须证明同 key + 同请求稳定 replay、同 key + 不同请求 409、进程重启后语义仍成立。
- 每个 Task 的证据必须同时记录 `proves` 与 `does_not_prove`；Task 1–17 的 fixture/deterministic 输出不得关闭只可由 Task 18 证明的 live DoD。
- Task 4 对 design API 的任何 `DEFER` 或语义替代必须先获得用户确认。
- 若 Task 7 证明现有 append-only event/detail 无法承载 durable idempotency receipt，必须暂停并提交最终 DDL、dry-run migration、backup/rollback plan，获得 schema 显式批准后才能新增表。
- Task 9 改变 artifact schema/version 或新增 architecture allowance 前必须单独展示变更并获得批准。
- Task 11 若需要新增 live-evidence 环境配置，必须先展示设置字段、默认 fail-closed 行为和 testing/production 差异，获得环境配置显式批准。
- Task 18 的真实 provider、isolated live data root、backup/restore 和 browser acceptance 必须单独获得执行授权。

## 2. 执行波次与依赖

```text
RC0 可信基线
  Task 1 ─┬─ Task 2 ─ Task 3
          │
API surface
          └─ Task 4
              │
RC1 后端闭环
              ├─ Task 5 ─ Task 6 ─ Task 7 ─ Task 8
              │                         └─ Task 9 mutation closure
              ├─ Task 9 read/evidence
              ├─ Task 10
              └─ Task 11
                         │
RC1 contract gate        └─ OpenAPI snapshot + generated DTO
                         │
RC2 前端闭环             └─ Task 12 ─ Task 13 ─ Task 14 ─ Task 15
                         │
RC3 契约与 deterministic └─ Task 16 ─ Task 17
                                              │
Live G2                                       └─ Task 18 ─ Task 19
```

允许并行：

- Task 9 的 factor/evidence/read 部分与 Task 10–11 可并行；candidate-selection
  与 holdout mutation 必须等待 Task 7 durable idempotency value/receipt 可复用；
- RC1 Exit Gate 必须等待所有 Task 6–9、11 contract 变化完成；Task 12–15 只能消费该 gate 生成的 DTO；
- Task 8 的 durable replay 验收依赖 Task 7；
- Task 12 依赖 Task 8 的 version detail 与 Task 9 的 factor diagnostics；
- Task 13 依赖 Task 6/7 的 planning 与 idempotency contract；
- Task 14 依赖 Task 6/7/9 的 control、idempotency 与 exposure contract；
- Task 15 依赖 Task 3/8/9/14 的 reactivate、hard-gate、evidence 与 workbench 语义；
- Task 16 必须等待所有 backend endpoint 和 frontend adapter 冻结；
- Task 18 必须等待 Task 17 deterministic closure 和独立 R2 live Gate 关闭。

---

## RC0：恢复可信开发基线

### Task 1: 修复 backend architecture ownership 门禁

**Files:**

- Modify: `packages/apps/tests/unit/architecture/test_capability_semantic_ownership_unit.py`
- Verify: `scripts/architecture/check_architecture_smells.py`

**Step 1: 重现当前 RED**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_capability_semantic_ownership_unit.py::test_production_analysis_wiring_allowances_are_owned_and_reasoned -q -n0 --no-cov
```

Expected: FAIL，right set 比测试期望多：

```text
.../comparison_reader.py
.../selection_evidence_reader.py
```

**Step 2: 核实 allowance 的 owner/reason**

检查两个 reader 在 `PRODUCTION_ANALYSIS_WIRING_ALLOWANCES` 中都有非空、准确的 owner/reason；若 reason 只是“让测试通过”，先修正 production allowance 描述。

**Step 3: 更新 ownership 期望**

只把两个已经存在且经架构批准的 reader path 加入测试的 exact set，不放宽为 glob/prefix。

**Step 4: 验证 GREEN**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_capability_semantic_ownership_unit.py -q -n0 --no-cov
python scripts/architecture/check_architecture_smells.py
pixi run -e dev arch-check
pixi run -e dev test --fast
```

Expected: all pass；`test-fast` 0 failed。

**Step 5: Commit**

```bash
git add packages/apps/tests/unit/architecture/test_capability_semantic_ownership_unit.py
git commit -m "test(arch): sync r3 reader ownership allowances"
```

### Task 2: 修复 frontend research 嵌套路由

**Files (ditto-app):**

- Modify: `src/routes/research/strategies.tsx`
- Create: `src/routes/research/strategies/index.tsx`
- Modify: `src/routes/research/experiments.tsx`
- Create: `src/routes/research/experiments/index.tsx`
- Modify: `src/routes/research/reviews.tsx`
- Create: `src/routes/research/reviews/index.tsx`
- Verify generated: `src/routeTree.gen.ts`
- Create test: `src/routes/research/research-nested-routes.test.tsx`

**Step 1: 写真实 Router RED 测试**

使用 TanStack `createMemoryHistory` + `RouterProvider`，分别进入：

```text
/research/strategies/seed_stock_selection_rotation/studio
/research/experiments/exp-r3
/research/reviews/exp-r3?strategyId=seed_stock_selection_rotation&version=2
```

断言 child page marker 可见，且父列表页 marker 不覆盖 child。

**Step 2: 运行 RED**

```bash
bunx vitest run src/routes/research/research-nested-routes.test.tsx
```

Expected: FAIL，当前父 route 直接渲染列表且没有 `<Outlet />`。

**Step 3: 最小实现 parent layout + index child**

三个 parent route 只渲染：

```tsx
import { Outlet, createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/research/experiments")({
  component: Outlet,
  staticData: { title: "实验" },
});
```

列表组件迁入对应 `index.tsx`。Strategies/reviews 使用同一结构，不在 parent 中做 pathname 特判。

**Step 4: 生成路由树并验证**

```bash
bun run build
bunx vitest run src/routes/research/research-nested-routes.test.tsx
bun run audit:routes
```

Expected: child routes 均可呈现，route audit pass。

**Step 5: Commit**

```bash
git add src/routes/research src/routeTree.gen.ts
git commit -m "fix(research): restore nested workbench routes"
```

### Task 3: 对齐 Reactivate 精确契约与错误恢复

**Files (ditto-app):**

- Modify: `src/features/strategy/components/governance-dialogs.tsx`
- Modify: `src/features/strategy/components/governance-dialogs.test.tsx`
- Modify: `src/features/strategy/components/governance-actions.tsx`
- Modify: `src/features/strategy/components/governance-actions.test.tsx`
- Modify: `src/features/strategy/hooks/use-strategy-governance.test.tsx`

**Step 1: 写 RED 测试**

期望确认串：

```ts
const expected = "strategy:reactivate:s@3:pointer-revision:2:confirm";
```

同时断言：

- mutation 成功前 dialog 不关闭；
- HTTP 409 时保留 actor/reason/impact/confirmation；
- 409 后 invalidate/refetch active pointer；
- 成功后才关闭 dialog。

**Step 2: 运行 RED**

```bash
bunx vitest run \
  src/features/strategy/components/governance-dialogs.test.tsx \
  src/features/strategy/components/governance-actions.test.tsx \
  src/features/strategy/hooks/use-strategy-governance.test.tsx
```

Expected: 当前中文确认串和立即 `setDialog(null)` 导致 FAIL。

**Step 3: 最小实现**

给 `ReactivateDialog` 增加 `strategyId`，确认串只由以下纯函数生成：

```ts
export function reactivateConfirmation(
  strategyId: string,
  version: number,
  pointerRevision: number,
): string {
  return `strategy:reactivate:${strategyId}@${version}:pointer-revision:${pointerRevision}:confirm`;
}
```

使用：

```ts
governance.reactivate.mutate(variables, {
  onSuccess: () => setDialog(null),
});
```

不在 `onConfirm` 同步关闭。

**Step 4: 验证 GREEN**

```bash
bunx vitest run src/features/strategy
bun run check
```

Expected: tests/check pass。

**Step 5: Commit**

```bash
git add src/features/strategy
git commit -m "fix(strategy): bind reactivate confirmation to server contract"
```

---

## API Surface：冻结最终 R3 v1 契约

### Task 4: 冻结最终 R3 v1 API surface

**Files:**

- Create: `docs/contracts/r3-v1-api-surface.md`
- Create: `docs/contracts/r3-v1-api-surface.json`
- Create: `packages/apps/src/ditto_apps/api/app_metadata.py`
- Create: `packages/apps/src/ditto_apps/api/routes/system.py`
- Create: `packages/apps/src/ditto_apps/openapi_contract.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/__init__.py`
- Modify: `packages/apps/src/ditto_apps/main.py`
- Create: `scripts/export_openapi.py`
- Modify: `docs/openapi/v1.json`
- Create test: `packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py`
- Create test: `packages/apps/tests/unit/api/test_openapi_snapshot_unit.py`
- Modify test: `packages/apps/tests/integration/test_main_routes_integration.py`
- ditto-app Modify: `scripts/gen-api.sh`
- ditto-app Modify generated: `src/types/generated/api.d.ts`
- Verify against: `docs/plans/2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md`
- Verify against: `docs/plans/2026-07-28-r3-w5-frontend-wiring-design.md`
- Verify against: `packages/apps/src/ditto_apps/api/routes/research_experiment_routes.py`
- Verify against: `packages/apps/src/ditto_apps/api/routes/strategy.py`

**Step 1: 写 machine-readable surface RED 测试**

测试读取 `r3-v1-api-surface.json`，要求设计文档 §12.2 与 W5 页面使用到的每个 operation 都有唯一记录：

```json
{
  "operation_id": "research_experiment_preflight",
  "design_method": "POST",
  "design_path": "/api/v1/research/experiments/{experiment_id}/preflight",
  "disposition": "IMPLEMENT",
  "runtime_method": "POST",
  "runtime_path": "/api/v1/research/experiments/{experiment_id}/preflight",
  "equivalent_operation_id": null,
  "implementation_state": "PLANNED",
  "closing_task": 6,
  "dod": [3, 17, 18],
  "reason": "..."
}
```

`disposition` 只允许：

- `IMPLEMENT`：按设计方法/路径实现；
- `EQUIVALENT`：已有 surface 语义等价，必须记录 replacement 与逐项等价证明；
- `DEFER`：不进入 R3，必须记录用户批准和被影响的 DoD。

测试还要比较 runtime OpenAPI：没有清单记录的 R3 route 不得被静默当成设计完成。冻结阶段允许 `IMPLEMENT` 记录为 `implementation_state=PLANNED`，但必须指向 Task 5–16 中唯一的 `closing_task`；route 尚未落地时 primary runtime mapping 为 null 且 OpenAPI 不得已有该 exact route，route 落地后则立即写 exact method/path/operationId 与 runtime contract projection，但仍保持 `PLANNED` 到 Task 16。`implementation_state=IMPLEMENTED` 的 `IMPLEMENT` 和全部 `EQUIVALENT` 必须立即解析到 runtime OpenAPI。Task 16 将 contract test 切换到 closure mode，届时所有非 `DEFER` 记录必须为 `IMPLEMENTED` 且与 runtime method/path/DTO 一致。

**Step 2: 完整盘点争议 surface**

至少逐项冻结：

```text
experiment preflight / create-launch
strategy PUT update vs POST versions create
approve/reject endpoints vs review-decisions
factor diagnostics
strategy version detail and events
experiment report
candidate-selection
holdout-evaluations
selections / exclusions / factor-contributions
aggregate selection-evidence
review detail vs experiment-key review packet
failed-fold retry path
candidate pin max-4 semantics
```

每项明确 request identity、response DTO、error codes、idempotency、revision/ETag、maturity 和对应页面消费者。UI 的“最多 pin 4 个”必须明确是纯本地比较选择，还是 server-persisted state；禁止两端各自假设。

**Step 3: Approval checkpoint**

把完整 classification 交给用户确认。出现任一 `DEFER`，或 `EQUIVALENT` 改变原设计的资源身份、状态机、错误语义、审计证据时，必须在继续 Task 5–16 前获得显式批准。

未批准前只允许补清单和 contract test；不得让 frontend 基于暂定 shape 生成最终 adapter。若盘点产生本计划尚未列出的 `IMPLEMENT` endpoint，必须同时把 exact files、RED test、error/idempotency 语义补入其 `closing_task`，重新校对依赖后再批准，禁止把 `PLANNED` 永久留到 Task 16 才临时补 route。

用户明确批准后，先完成 classification 状态迁移再开始 Task 5：

1. 顶层 `approval_state` 与 `approval_required.status` 改为 `APPROVED`，
   `approval_required.decision/reference` 写入本次用户决定及可追溯 reference；
2. 每个 `DEFER` 与 `EQUIVALENT` entry 的 `user_approval.status` 同步改为
   `APPROVED`，分别写入非空 decision/reference；
3. `candidate_evidence_bundle_proposal` 仍保持 `PENDING`，其
   decision/reference 仍为 null，直到 Task 9 单独 checkpoint；
4. 刷新 machine summary/canonical hash，运行 surface contract test。任何状态
   不一致或缺 audit reference 都不得继续。

`test_current_task4_checkpoint_is_approved_with_task9_proposal_pending` 额外锁定
当前 `APPROVED/PENDING` snapshot 与 Task 4 approval reference；它不替代通用
状态机测试。Task 9 发生合法 proposal transition 时，必须在同一变更中显式更新
这个 checkpoint 的 expected proposal state/reference。

**Step 4: 固化契约并验证**

```bash
pixi run -e dev python scripts/export_openapi.py
pixi run -e dev pytest packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py -q -n0 --no-cov
pixi run -e dev pytest packages/apps/tests/unit/api/test_openapi_snapshot_unit.py -q -n0 --no-cov
git diff --check
```

exporter 只调用 pure
`create_openapi_app(include_debug=False).openapi()` 与 production
`canonical_openapi_bytes`；factory 不读 ambient `ENVIRONMENT`，不配置
lifespan/DI/container/CORS。runtime `main.app` 显式按真实 environment 传
`include_debug`，两者复用同一 route registration 与 system handlers，测试比较
non-debug route parity。

exporter 在目标同目录 `mkstemp`，write/flush/fsync 后 `os.replace`，finally 清理
temp，并 fsync parent directory；失败必须保留旧 snapshot。snapshot test 不复制
serializer，使用 production canonicalizer，在 `tmp_path` 调真实 exporter 并覆盖
atomic failure。Expected: 每个设计 operation 均有审计结论；所有已
`IMPLEMENTED`/`EQUIVALENT` surface 能解析到 pure non-debug OpenAPI；每个
`PLANNED` surface 有唯一 closing Task；文档、JSON 与 static OpenAPI 一致。
获得批准时，Step 4 还必须在 commit 前验证 classification 已完成上述
`APPROVED` 迁移，而 bundle proposal 仍为 `PENDING`；summary/hash 必须绑定该
状态快照。

ditto-app 的 `scripts/gen-api.sh` 增加显式 `OPENAPI_FILE` 输入；提供该变量时直接读取已冻结文件，不启动 backend、不访问任何 DB，否则保留既有 `OPENAPI_URL` 行为。file/URL 两种模式都先生成到 output 同目录 temp，成功后 atomic `mv`，trap 清理；unreadable/invalid JSON 不得破坏旧 output。验证并 stage 第一次预期更新后，再运行第二次：

```bash
OPENAPI_FILE=/home/chevy/projects/ditto/docs/openapi/v1.json bun run gen:api
git add src/types/generated/api.d.ts
OPENAPI_FILE=/home/chevy/projects/ditto/docs/openapi/v1.json bun run gen:api
git diff --exit-code -- src/types/generated/api.d.ts
bun run check
```

Expected: 第二次生成 zero unstaged diff。

**Step 5: Commit**

```bash
git add docs/contracts/r3-v1-api-surface.md \
  docs/contracts/r3-v1-api-surface.json \
  docs/plans/2026-07-30-r3-completion-and-g2-closure-implementation-plan.md \
  docs/openapi/v1.json \
  packages/apps/src/ditto_apps/api/app_metadata.py \
  packages/apps/src/ditto_apps/api/routes/__init__.py \
  packages/apps/src/ditto_apps/api/routes/system.py \
  packages/apps/src/ditto_apps/main.py \
  packages/apps/src/ditto_apps/openapi_contract.py \
  scripts/export_openapi.py \
  packages/apps/tests/integration/test_main_routes_integration.py \
  packages/apps/tests/unit/api/test_openapi_snapshot_unit.py \
  packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py
git commit -m "fix(api): harden canonical OpenAPI export"
```

ditto-app：

```bash
git add scripts/gen-api.sh src/types/generated/api.d.ts
git commit -m "fix(api): make contract generation atomic"
```

---

## RC1：完成后端写路径与证据语义

### Task 5: 实现 canonical ExperimentPlanningRequest builder

**Files:**

- Create: `packages/application/src/ditto_application/processes/experiments/planning_request_builder.py`
- Create test: `packages/application/tests/unit/process/experiments/test_planning_request_builder_unit.py`
- Modify: `packages/apps/src/ditto_apps/models/research.py`
- Create test: `packages/apps/tests/unit/models/test_research_planning_models_unit.py`

**Step 1: 冻结 transport-neutral planning document**

builder 接受 `Mapping[str, object]`，输出既有 `ExperimentPlanningRequest`；canonical document 必须完整包含：

```python
{
    "experiment_id": "...",
    "research_cycle_id": "...",
    "research_cycle_hash": "<sha256>",
    "strategy": {
        "strategy_id": "...",
        "version": 2,
        "spec_hash": "<sha256>",
        "spec_json": {...},
    },
    "snapshot": {...},
    "validation": {...},
    "matrix": {...},
    "promotion_objective": {...},
    "dataset_requirements": [...],
    "cost_model": {...},
    "budget": {...},
    "seed": 42,
    "worker_count": 2,
    "failure_policy": "fail_fast",
    "created_at": "2026-07-30T00:00:00Z",
}
```

禁止 builder 查询 catalog、SQLite 或 provider；它只做严格解码、canonical identity 校验和 typed object 装配。

**Step 2: 写 RED 测试**

至少覆盖：

- valid document 精确装配所有字段；
- unknown/missing key fail closed；
- `strategy.spec_hash` 与 canonical spec 不同失败；
- research cycle hash、snapshot identity、matrix、validation、objective 任一漂移失败；
- bool 冒充 int、NaN/Infinity、unordered/non-string map key 被拒绝；
- 输入 mapping 后续被调用方修改不影响 request。

**Step 3: 运行 RED**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/experiments/test_planning_request_builder_unit.py -q -n0 --no-cov
```

Expected: FAIL，builder 不存在。

**Step 4: 最小实现**

公开入口固定为：

```python
def build_experiment_planning_request(
    document: Mapping[str, object],
) -> ExperimentPlanningRequest:
    """Decode one complete canonical planning document without I/O."""
```

复用既有 validation/matrix/dataset/objective/cost/budget/failure-policy codecs；若私有 codec 无法安全复用，先提取到同一 process package 的命名明确叶模块，禁止从 Apps 直接导入 `_preflight_codec` 私有函数。

Apps Pydantic request 使用 strict + `extra="forbid"`，只把 `model_dump(mode="python")` 交给 builder。

**Step 5: 验证 GREEN**

```bash
pixi run -e dev pytest \
  packages/application/tests/unit/process/experiments/test_planning_request_builder_unit.py \
  packages/apps/tests/unit/models/test_research_planning_models_unit.py \
  -q -n0 --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: all pass。

**Step 6: Commit**

```bash
git add packages/application/src/ditto_application/processes/experiments/planning_request_builder.py \
  packages/application/tests/unit/process/experiments/test_planning_request_builder_unit.py \
  packages/apps/src/ditto_apps/models/research.py \
  packages/apps/tests/unit/models/test_research_planning_models_unit.py
git commit -m "feat(research): decode canonical experiment planning requests"
```

### Task 6: 暴露 preflight 与 create-launch API/CLI

**Files:**

- Modify: `packages/apps/src/ditto_apps/models/research.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/research_experiment_routes.py`
- Modify: `packages/apps/src/ditto_apps/cli/commands/research.py`
- Modify: `packages/apps/src/ditto_apps/registry/contexts/research.py` only if existing providers are not visible
- Modify test: `packages/apps/tests/unit/api/routes/test_research_experiment_routes_unit.py`
- Create integration test: `packages/apps/tests/integration/api/test_research_experiment_planning_api_integration.py`
- Modify test: `packages/apps/tests/unit/cli/commands/test_research_unit.py`

**Step 1: 写 route/CLI RED 测试**

冻结 endpoints：

```text
POST /api/v1/research/experiments/{experiment_id}/preflight
POST /api/v1/research/experiments
```

preflight request 接受 planning document；launch request 接受同一 document + `confirmed_plan_hash`。断言：

- preflight 无写入；
- path/body experiment ID 不同返回 422；
- launch 内部重新 preflight；
- stale plan hash 返回 409，code=`PLAN_HASH_MISMATCH`；
- hard preflight failure 返回 422/409 的稳定 error envelope；
- successful launch 返回 `experiment_id/status/queue_ordinal/revision/candidate_count/fold_count/plan_hash`；
- 重复同 experiment/plan 返回 durable replay；
- CLI `preflight --document PATH` 与 `launch --document PATH --confirmed-plan-hash HASH` 调用相同 application surface。

**Step 2: 运行 RED**

```bash
pixi run -e dev pytest \
  packages/apps/tests/unit/api/routes/test_research_experiment_routes_unit.py \
  packages/apps/tests/integration/api/test_research_experiment_planning_api_integration.py \
  packages/apps/tests/unit/cli/commands/test_research_unit.py \
  -q -n0 --no-cov
```

Expected: endpoints/DTO/CLI 不存在。

**Step 3: 实现 typed response mapping**

DTO 使用显式字段：

```python
class ExperimentPreflightResponse(BaseModel):
    status: str
    plan_hash: str | None
    checks: list[ExperimentPreflightCheckResponse]
    candidate_count: int
    planned_fold_count: int
    budget_run_count: int
    estimated_trading_sessions: int
    estimated_disk_bytes: int
    eligible_month_count: int
    isolation_width_sessions: int


class ExperimentLaunchResponse(BaseModel):
    experiment_id: str
    status: str
    queue_ordinal: int
    revision: int
    candidate_count: int
    fold_count: int
    plan_hash: str
```

route 只调用 `build_experiment_planning_request` + `ExperimentPlanningProcess.preflight` 或 `LaunchExperimentHandler.handle`。

**Step 4: 实现稳定错误映射**

只按 typed `details["code"]` 映射：

```text
PLAN_HASH_MISMATCH              -> 409
EXPERIMENT_ALREADY_EXISTS drift -> 409
HARD_GATE_FAILED                -> 422
SPEC_INVALID                    -> 422
```

禁止按异常类名或自由文本猜测。

**Step 5: 验证 GREEN**

```bash
pixi run -e dev pytest \
  packages/apps/tests/unit/api/routes/test_research_experiment_routes_unit.py \
  packages/apps/tests/integration/api/test_research_experiment_planning_api_integration.py \
  packages/apps/tests/unit/cli/commands/test_research_unit.py \
  -q -n0 --no-cov
pixi run -e dev arch-check
```

Expected: all pass，preflight zero-write 由 integration test 证明。

**Step 6: Commit**

```bash
git add packages/apps/src/ditto_apps/models/research.py \
  packages/apps/src/ditto_apps/api/routes/research_experiment_routes.py \
  packages/apps/src/ditto_apps/cli/commands/research.py \
  packages/apps/src/ditto_apps/registry/contexts/research.py \
  packages/apps/tests
git commit -m "feat(research): expose experiment preflight and launch"
```

### Task 7: 建立 durable `Idempotency-Key` 语义

**Files:**

- Create: `packages/application/src/ditto_application/commands/mutation_idempotency.py`
- Create test: `packages/application/tests/unit/commands/test_mutation_idempotency_unit.py`
- Modify: `packages/application/src/ditto_application/commands/experiments.py`
- Modify: `packages/application/src/ditto_application/commands/strategy_governance.py`
- Modify: `packages/application/src/ditto_application/processes/experiments/_coordinator_recovery.py`
- Modify: `packages/application/src/ditto_application/processes/experiments/coordinator.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/research_experiment_routes.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/strategy.py`
- Create integration test: `packages/apps/tests/integration/api/test_r3_mutation_idempotency_api_integration.py`
- Potential schema checkpoint only: `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/schema_v1.sql`

**Step 1: 写行为 RED 测试**

对 launch、pause/resume/cancel/retry、submit/approve/reject/publish/reactivate 选取代表性 mutation，证明：

```text
same operation + same resource + same key + same request
    => same HTTP status and canonical response, no second durable event

same operation + same resource + same key + different request hash
    => 409 IDEMPOTENCY_KEY_REUSED

missing/blank/oversized key
    => 422

restart process/container and replay
    => same result
```

**Step 2: 先验证 schema-free 方案**

首选复用 append-only event：

- key 在 application 边界 canonicalize；
- 持久化 `key_hash`，不保存 raw secret-like header；
- event/detail 同时保存 `operation_id`、`request_hash` 和足够重建 response 的 receipt payload；
- 重放先读既有 event，再做 revision/state transition；
- governance event ID 由 operation/resource/key hash 派生；
- experiment status event detail 记录 idempotency receipt，并由现有 event reader 查找。

**Step 3: Schema approval checkpoint**

若 exact tests 证明现有 event stream 无法高效、无歧义地恢复 receipt，停止。提交：

1. 最终 idempotency table DDL；
2. canonical request/response hash columns；
3. unique key；
4. dry-run migration；
5. backup/restore 与 rollback；
6. 旧 Research Schema v1 零破坏证明。

只有获得显式批准后才能修改 schema。不得先建表再补批准。

**Step 4: 最小实现**

固定 application value：

```python
@dataclass(frozen=True, slots=True)
class MutationIdempotency:
    operation_id: str
    resource_id: str
    key_hash: str
    request_hash: str
```

Apps 只解析 header 并构造 value；replay/conflict 规则在 application/process/store。

**Step 5: 验证 GREEN**

```bash
pixi run -e dev pytest \
  packages/application/tests/unit/commands/test_mutation_idempotency_unit.py \
  packages/apps/tests/integration/api/test_r3_mutation_idempotency_api_integration.py \
  -q -n0 --no-cov
pixi run -e dev arch-check
pixi run -e dev test --fast
```

Expected: all pass，restart replay 无第二 durable event。

**Step 6: Commit**

```bash
git add packages/application packages/apps packages/analysis
git commit -m "feat(api): make r3 mutations durably idempotent"
```

### Task 8: 让 submit-review 与 hard gates 一致 fail closed

**Files:**

- Modify: `packages/application/src/ditto_application/commands/strategy_governance.py`
- Modify: `packages/application/src/ditto_application/providers_command.py`
- Modify: `packages/application/src/ditto_application/contracts.py`
- Modify: `packages/application/src/ditto_application/queries/strategy.py`
- Modify: `packages/application/src/ditto_application/providers_strategy.py`
- Modify: `packages/strategy/src/ditto_strategy/governance/models.py`
- Modify: `packages/strategy/src/ditto_strategy/governance/protocols.py`
- Modify: `packages/strategy/src/ditto_strategy/storage/sqlite/strategy_governance_store.py`
- Modify: `packages/apps/src/ditto_apps/models/strategy.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/strategy.py`
- Modify: `docs/contracts/r3-v1-api-surface.json`
- Modify: `docs/contracts/r3-v1-api-surface.md`
- Modify test: `packages/application/tests/unit/commands/test_strategy_governance_commands_unit.py`
- Modify test: `packages/application/tests/unit/query/test_strategy_query_unit.py`
- Modify test: `packages/strategy/tests/unit/storage/sqlite/test_strategy_governance_store_unit.py`
- Modify test: `packages/apps/tests/unit/api/routes/test_strategy_routes_unit.py`
- Modify integration test: `packages/apps/tests/integration/api/test_r3_strategy_publish_api_integration.py`

**Step 1: 写 RED 测试**

`SubmitReviewCommand` 必须携带 `bundle_hash`。覆盖：

- packet 缺失 -> zero-write `REVIEW_PACKET_NOT_FOUND`；
- packet/launch/governance target identity drift -> zero-write；
- 任一 hard gate FAIL/NOT_EVALUATED -> `hard_gate_blocked`，版本仍 DRAFT；
- all required hard gates PASS -> DRAFT → REVIEW；
- duplicate idempotency key -> exact replay；
- soft metric 低于偏好不自动阻断 submit。
- `GET /strategies/{strategy_id}/versions/{version}` 返回 immutable canonical spec、
  `spec_hash/parent_version/state/review_outcome/created_at`，missing version 为
  `404 STRATEGY_VERSION_NOT_FOUND`；
- `GET /strategies/{strategy_id}/events?after_event_id=&limit=` 合并 decision 与
  activation append-only streams，按 `(occurred_at,event_id)` 稳定排序；非法 cursor
  为 `422 INVALID_EVENT_CURSOR`，不得从 current-state rows 反推事件；
- event DTO 只投影现有 append-only rows 可提供的
  `event_id/strategy_id/event_type/target_version/decision_or_activation_kind/actor/
  reason/occurred_at`；测试明确禁止新增 `bundle_hash/evidence_hash/
  previous_version/pointer_revision` 字段，本任务 schema unchanged。

**Step 2: 运行 RED**

```bash
pixi run -e dev pytest \
  packages/application/tests/unit/commands/test_strategy_governance_commands_unit.py \
  packages/application/tests/unit/query/test_strategy_query_unit.py \
  packages/strategy/tests/unit/storage/sqlite/test_strategy_governance_store_unit.py \
  packages/apps/tests/unit/api/routes/test_strategy_routes_unit.py \
  packages/apps/tests/integration/api/test_r3_strategy_publish_api_integration.py \
  -q -n0 --no-cov
```

Expected：

- command test 因 submit-review 尚未执行 bundle/hard-gate verifier 而 FAIL；
- query test 因 version-detail facade/DTO 尚不存在而 FAIL；
- strategy store test 因 append-only event reader/cursor 尚不存在而 FAIL；
- route test 因 version detail/events routes 尚不存在而 FAIL；
- integration test 因 submit gate 仍可绕过 persisted evidence 而 FAIL。

**Step 3: 最小实现**

提取 publish 与 submit 共用的 application verifier：

```python
def load_verified_promotion_target(
    *,
    strategy_id: str,
    version: int,
    bundle_hash: str,
    reader: ReviewPacketReader,
) -> VerifiedPromotionTarget:
    """Verify packet -> persisted launch -> governance target identity."""
```

submit 使用同一 hard gate 判定，但不切 active pointer；验证通过后才调用 governance store。

**Step 3b: 实现 strategy version detail 与 governance events**

- `StrategyQueryFacade.get_version_detail(strategy_id, version)` 组合 catalog 的
  immutable spec record 与 governance version state，返回
  `StrategyVersionDetailInfo`；不允许 route 直接读 strategy store。
- strategy-owned SQLite reader 新增 `list_governance_events(strategy_id,
  after_event_id, limit)`，从现有 decision/activation append-only rows 原样投影
  `event_id/strategy_id/event_type/target_version/decision_or_activation_kind/actor/
  reason/occurred_at`，不反推或伪造 evidence/bundle、previous version、pointer
  revision。本任务不改 governance schema。
- Apps 暴露：

```text
GET /api/v1/strategies/{strategy_id}/versions/{version}
GET /api/v1/strategies/{strategy_id}/events?after_event_id=&limit=
```

response 分别为 `APIResponse[StrategyVersionDetailResponse]` 和
`APIResponse[list[StrategyGovernanceEventResponse]]`；两者 read-only，
`Idempotency-Key=N/A`，immutable version/event ID 取代 ETag，maturity 固定
`initial-focus`。DI 只注入 application query facade/consumer-owned reader，
Apps route 不 import `ditto_strategy`。

routes 落地的同一变更必须滚动更新 Task 4 合同：为 version detail/events entry
写入 exact `runtime_method/runtime_path`，route operationId 必须等于 entry
`operation_id`；从 `ditto_apps.main.app.openapi()` 重新投影全部
`runtime_contracts`，更新 Markdown machine summary/canonical hash。
`implementation_state` 仍保持 `PLANNED` 到 Task 16。该投影只读 OpenAPI，
不启动 server、不访问 DB。

**Step 4: 验证 GREEN**

```bash
pixi run -e dev pytest packages/application/tests/unit/commands/test_strategy_governance_commands_unit.py \
  packages/application/tests/unit/query/test_strategy_query_unit.py \
  packages/strategy/tests/unit/storage/sqlite/test_strategy_governance_store_unit.py \
  packages/apps/tests/unit/api/routes/test_strategy_routes_unit.py \
  packages/apps/tests/integration/api/test_r3_strategy_publish_api_integration.py \
  packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py \
  -q -n0 --no-cov
pixi run -e dev arch-check
```

Expected: hard gate failure 下 governance current-state/event row count不变。

**Step 5: Commit**

```bash
git add packages/application/src/ditto_application/commands/strategy_governance.py \
  packages/application/src/ditto_application/providers_command.py \
  packages/application/src/ditto_application/contracts.py \
  packages/application/src/ditto_application/queries/strategy.py \
  packages/application/src/ditto_application/providers_strategy.py \
  packages/strategy/src/ditto_strategy/governance/models.py \
  packages/strategy/src/ditto_strategy/governance/protocols.py \
  packages/strategy/src/ditto_strategy/storage/sqlite/strategy_governance_store.py \
  packages/apps/src/ditto_apps/models/strategy.py \
  packages/apps/src/ditto_apps/api/routes/strategy.py \
  docs/contracts/r3-v1-api-surface.json \
  docs/contracts/r3-v1-api-surface.md \
  packages/application/tests/unit/commands/test_strategy_governance_commands_unit.py \
  packages/application/tests/unit/query/test_strategy_query_unit.py \
  packages/strategy/tests/unit/storage/sqlite/test_strategy_governance_store_unit.py \
  packages/apps/tests/unit/api/routes/test_strategy_routes_unit.py \
  packages/apps/tests/integration/api/test_r3_strategy_publish_api_integration.py
git commit -m "fix(governance): gate review submission on persisted evidence"
```

### Task 9: 产出非空 factor contribution 与 industry/size exposure

**Files:**

- Modify: `packages/strategy/src/ditto_strategy/alpha/selection_evidence.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/builtins/scoring.py`
- Modify: `packages/application/src/ditto_application/builders/template_builders.py`
- Modify: `packages/application/src/ditto_application/processes/execution/backtest_serialization.py`
- Modify: `packages/application/src/ditto_application/processes/experiments/_fold_selection_trace_artifacts.py`
- Modify: `packages/application/src/ditto_application/processes/experiments/_fold_selection_trace_artifact_validation.py`
- Modify: `packages/application/src/ditto_application/builders/fold_selection_trace_artifact_adapter.py`
- Modify: `packages/analysis/src/ditto_analysis/experiments/evidence.py`
- Modify: `packages/application/src/ditto_application/processes/experiments/evidence.py`
- Modify: `packages/application/src/ditto_application/processes/experiments/evidence_collector.py`
- Modify: `packages/application/src/ditto_application/queries/experiments.py`
- Create: `packages/application/src/ditto_application/processes/experiments/factor_diagnostics_reader.py`
- Create: `packages/application/src/ditto_application/processes/experiments/candidate_evidence_reader.py`
- Create: `packages/application/src/ditto_application/commands/candidate_selection.py`
- Modify: `packages/application/src/ditto_application/processes/experiments/holdout.py`
- Modify: `packages/application/src/ditto_application/providers_command.py`
- Modify: `packages/application/src/ditto_application/providers_process.py`
- Modify: `packages/apps/src/ditto_apps/models/research.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/research_experiment_routes.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/research_catalog_routes.py`
- Create: `packages/apps/src/ditto_apps/api/routes/research_candidate_routes.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/__init__.py`
- Modify: `packages/apps/src/ditto_apps/main.py`
- Modify: `packages/apps/src/ditto_apps/registry/contexts/research.py`
- Modify: `docs/contracts/r3-v1-api-surface.json`
- Modify: `docs/contracts/r3-v1-api-surface.md`
- Modify tests: `packages/strategy/tests/unit/alpha/test_selection_evidence_unit.py`
- Modify tests: `packages/analysis/tests/unit/experiments/test_evidence_unit.py`
- Modify tests: `packages/application/tests/unit/builders/test_fold_selection_trace_artifact_adapter_unit.py`
- Modify tests: `packages/application/tests/unit/process/experiments/test_evidence_unit.py`
- Modify tests: `packages/application/tests/unit/query/test_experiment_query_review_packet_unit.py`
- Create test: `packages/application/tests/unit/process/experiments/test_factor_diagnostics_reader_unit.py`
- Create test: `packages/application/tests/unit/process/experiments/test_candidate_evidence_reader_unit.py`
- Create test: `packages/application/tests/unit/commands/test_candidate_selection_unit.py`
- Modify test: `packages/application/tests/unit/process/experiments/test_holdout_unit.py`
- Modify test: `packages/apps/tests/unit/api/routes/test_research_catalog_routes_unit.py`
- Modify test: `packages/apps/tests/unit/api/routes/test_research_experiment_routes_unit.py`
- Create test: `packages/apps/tests/unit/api/routes/test_research_candidate_routes_unit.py`
- Create integration test: `packages/apps/tests/integration/api/test_r3_selection_holdout_api_integration.py`
- Modify golden: `packages/application/tests/integration/test_r3_evidence_closure_golden.py`

**Step 1: 写 production-path RED 测试**

禁止直接构造 evidence log。测试必须运行 stock golden 使用的真实 runtime/builder，断言：

```python
assert log.initial_universe
assert log.exclusions
assert log.selections
assert log.factor_contributions
assert exposure.industry_weights
assert exposure.size_bucket_weights
```

同时断言 ETF lane 不被迫伪造 stock exposure；不适用时必须显式 `NOT_APPLICABLE`，不是空数据冒充 PASS。

同时先写 8 个 planned surface 的 Task 9 部分 RED：

- factor diagnostics 以 `factor_id + snapshot_id/window/registry_hash` 为 request
  identity，返回 typed provenance/metric/artifact hashes；
- candidate-selection 以
  `experiment_id/candidate_id/comparison_payload_hash/expected_revision` 为 identity；
- holdout-evaluations 必须引用持久 selection_id，第二候选或第二 claim 返回
  `409 HOLDOUT_ALREADY_CLAIMED`；
- candidate selections/exclusions/factor-contributions 必须同时提供
  `candidate_id + experiment_id`，禁止只按可跨 experiment 重复的 candidate ID；
- 三个 drill-down query 统一为 required `experiment_id`、optional opaque
  `cursor`、bounded `limit=1..100`（default 20）。typed PageResponse 必须包含
  `candidate_id/experiment_id/artifact_id/content_hash/items/next_cursor`；cursor
  编码 `content_hash + offset`，格式错误为
  `422 INVALID_CANDIDATE_EVIDENCE_CURSOR`，hash drift 为
  `409 EVIDENCE_STALE`，结束页 `next_cursor=null`；
- 两个 mutation 缺失/空白 Idempotency-Key 为 422，同 key+同 request exact replay，
  同 key+不同 request 为 `409 IDEMPOTENCY_KEY_REUSED`；
- read surface 的 Idempotency-Key=N/A，以 artifact content hash/cursor 为 revision
  identity；全部 maturity=`experimental`。
- candidate bundle tests 使用 2+ validation folds，并构造 retry 前后 attempts：
  只接受 current comparison lineage 明确引用的 terminal successful committed
  `attempt_id/run_id`，排除失败与旧 retry attempt，禁止 latest/max 猜测；
- bundle/reader tests 冻结每 fold 三类 artifact id/hash/kind/version、fold stable
  order、三类 item exact sort、page boundary 无重复、cross-kind cursor 拒绝、
  current comparison hash drift 为 `EVIDENCE_STALE`，以及 restart bytes/hash/
  order/cursor parity。

**Step 2: 运行 RED**

```bash
pixi run -e dev pytest \
  packages/strategy/tests/unit/alpha/test_selection_evidence_unit.py \
  packages/analysis/tests/unit/experiments/test_evidence_unit.py \
  packages/application/tests/unit/builders/test_fold_selection_trace_artifact_adapter_unit.py \
  packages/application/tests/unit/process/experiments/test_evidence_unit.py \
  packages/application/tests/unit/process/experiments/test_factor_diagnostics_reader_unit.py \
  packages/application/tests/unit/process/experiments/test_candidate_evidence_reader_unit.py \
  packages/application/tests/unit/commands/test_candidate_selection_unit.py \
  packages/application/tests/unit/process/experiments/test_holdout_unit.py \
  packages/application/tests/unit/query/test_experiment_query_review_packet_unit.py \
  packages/apps/tests/unit/api/routes/test_research_catalog_routes_unit.py \
  packages/apps/tests/unit/api/routes/test_research_experiment_routes_unit.py \
  packages/apps/tests/unit/api/routes/test_research_candidate_routes_unit.py \
  packages/apps/tests/integration/api/test_r3_selection_holdout_api_integration.py \
  packages/application/tests/integration/test_r3_evidence_closure_golden.py \
  -q -n0 --no-cov
```

Expected：

- production-path/golden 因 stock contribution、industry/size exposure 为空而 FAIL；
- factor diagnostics/candidate evidence reader tests 因 artifact identity、typed
  page/cursor reader 尚不存在而 FAIL；
- selection command/idempotency tests 因 durable selection event/receipt 尚不存在
  而 FAIL；
- holdout tests 因 persisted selection identity 与 HTTP receipt 尚未接线而 FAIL；
- catalog/experiment/candidate route tests 因 diagnostics、selection、holdout、
  drill-down DTO/routes 尚不存在而 FAIL；
- selection-holdout integration 因 durable replay、one-shot claim 与 evidence
  stale guard 尚未闭环而 FAIL。

**Step 3: 最小实现 factor contribution**

扩展 strategy-owned scoring stage，使 application 只传入编译后的 factor column/weight binding；strategy stage 在同一真实 scoring 路径向 `SelectionEvidenceSink` emit raw/processed/normalized/weight/contribution/final score。

禁止 application 事后根据总分“反推”贡献。

**Step 4: 冻结 artifact/packet 方案与 approval checkpoint**

在写 production artifact 前，先给出 selection exposure value、fold artifact、ReviewPacket input/read DTO 的完整方案，至少绑定：

```text
trade_date
instrument_id
selected_weight
industry_id
size_value or canonical size_bucket
snapshot/column semantics through artifact manifest
```

同时提交 candidate immutable bundle/manifest 提案：

```text
manifest identity:
  experiment_id
  candidate_id
  comparison_payload_hash
  comparison_revision

fold_sources order:
  (validation_fold_ordinal, fold_id)

each fold source:
  comparison-lineage-selected terminal successful committed attempt_id/run_id
  selection artifact id/hash/kind/version
  exclusion artifact id/hash/kind/version
  contribution artifact id/hash/kind/version

bundle identity:
  candidate_bundle_artifact_id
  content_hash
```

不得按 latest/max attempt 猜测 lineage；失败 attempt 与旧 retry attempt 不进入
bundle。三类 items 的 exact stable sort 分别为：

```text
selections:
  (validation_fold_ordinal, fold_id, trade_date, rank, instrument_id)
exclusions:
  (validation_fold_ordinal, fold_id, trade_date, instrument_id, stage, reason_code)
factor_contributions:
  (validation_fold_ordinal, fold_id, trade_date, instrument_id, factor_id)
```

无 cursor 的首请求只解析 current comparison revision 显式引用的 bundle。
successful retry 产生新 comparison revision 与新 immutable bundle，旧 bundle
保留。`next_cursor` 绑定 bundle content hash、resource kind、offset，不得跨
三类 resource 复用；cursor 的旧 hash 不再被 current comparison 引用时返回
`409 EVIDENCE_STALE`。

若方案需要修改 frozen artifact kind/version、manifest schema、reader compatibility 或 architecture allowance，先停止并展示：

1. 新旧 artifact schema 与 version；
2. backward reader/replay 兼容策略；
3. 已有 artifact 的迁移或“不迁移”结论；
4. backup/restore 影响；
5. 新 allowance 的 owner、reason 和最小精确路径。

获得单独批准后再继续；若只复用现有 generic content-addressed artifact envelope，则在证据中记录“schema unchanged”并继续。
该段文字只是 approval proposal，不预先批准 artifact kind/version/manifest，
也不得在此 checkpoint 前写 production artifact。

Task 9 checkpoint 的状态迁移必须独立记录：

- 新 artifact kind/version/manifest 获得单独用户批准：
  `candidate_evidence_bundle_proposal.approval_state=APPROVED`，decision 与
  reference 均记录该次批准；
- 证明完全复用现有 generic content-addressed envelope：
  `approval_state=NOT_REQUIRED`，decision 必须明确 `schema unchanged` 与
  generic envelope，reference 指向 schema/compatibility evidence；
- 两种迁移都要求 classification 已为 `APPROVED`，并在写 production artifact
  前刷新 JSON/Markdown machine summary/canonical hash、运行
  `test_r3_api_surface_contract_unit.py`，并显式更新 Task 4 current-checkpoint test
  的 proposal state/reference expectation。否则保持 `PENDING` 并停止。

**Step 5: 最小实现 exposure evidence**

按已批准方案，以独立 content-addressed fold artifact 存储；generic artifact index 可复用时不改 SQLite schema。聚合器计算 industry weights 和 size-bucket weights，并把 artifact ref/hash 放入 analysis-owned `ReviewPacket`、application `ReviewPacketInput`/query read model 和 selection-evidence API surface。

**Step 6: 验证 integrity/replay**

覆盖：

- serialize/read exact parity；
- empty applicable stock trace fail closed；
- content hash drift 拒绝；
- restart 后读取相同 bytes/hash；
- golden packet 指向非空 trace；
- UI read DTO 不把 absent 与 zero 混淆。

**Step 6b: 暴露 full-scope diagnostics、selection、holdout 与 candidate drill-down**

实现以下 exact surface：

```text
GET  /api/v1/research/factors/{factor_id}/diagnostics
POST /api/v1/research/experiments/{experiment_id}/candidate-selection
POST /api/v1/research/experiments/{experiment_id}/holdout-evaluations
GET  /api/v1/research/candidates/{candidate_id}/selections?experiment_id=...&cursor=...&limit=...
GET  /api/v1/research/candidates/{candidate_id}/exclusions?experiment_id=...&cursor=...&limit=...
GET  /api/v1/research/candidates/{candidate_id}/factor-contributions?experiment_id=...&cursor=...&limit=...
```

DTO/error/revision 以 Task 4 `r3-v1-api-surface.json` 为准。candidate-selection 写
独立 durable preselection event；local pin-max-4 不调用该 command。holdout route
只调用现有 application `HoldoutClaimProcess`/handler，不在 Apps 复制 claim
规则。三个 drill-down reader 从 content-addressed candidate trace artifact 读取并
校验 experiment/candidate/hash，不直接访问文件系统或 analysis store；Apps 只依赖
application DTO/facade。若 durable selection event 无法复用现有 append-only event
envelope而需要 schema 变更，复用 Task 7 schema approval checkpoint，未批准不得建表。
factor diagnostics 同样由 process-layer `FactorDiagnosticsReader` 验证 artifact
identity 后投影；不放入 `queries` 去依赖 experiment process，也不允许 catalog
route 自行解析 artifact。

三个 drill-down 分别返回
`APIResponse[CandidateSelectionPageResponse]`、
`APIResponse[CandidateExclusionPageResponse]` 与
`APIResponse[CandidateFactorContributionPageResponse]`。三个 page 都包含
`candidate_id/experiment_id/artifact_id/content_hash/items/next_cursor`，items
保持各自 typed selection/exclusion/contribution 字段。reader 对 opaque cursor
解码并校验 `candidate bundle content_hash + resource_kind + offset`；page 的
`artifact_id/content_hash` 必须是 `candidate_bundle_artifact_id/content_hash`，
不能是单 fold artifact。非法或 cross-kind cursor 返回
`422 INVALID_CANDIDATE_EVIDENCE_CURSOR`，cursor hash 与当前 artifact 不同返回
`409 EVIDENCE_STALE`，末页返回 `next_cursor=null`。

Task 9 routes 落地的同一变更必须为 6 个新增 surface 写 exact primary
`runtime_method/runtime_path`，确保 route operationId 等于 entry
`operation_id`，再从 `ditto_apps.main.app.openapi()` 重新投影全部
`runtime_contracts` 并刷新 Markdown summary/hash；保持
`implementation_state=PLANNED` 到 Task 16。投影不启动 server、不访问 DB。

**Step 7: 验证 GREEN**

```bash
pixi run -e dev pytest \
  packages/strategy/tests/unit/alpha/test_selection_evidence_unit.py \
  packages/analysis/tests/unit/experiments/test_evidence_unit.py \
  packages/application/tests/unit/builders/test_fold_selection_trace_artifact_adapter_unit.py \
  packages/application/tests/unit/process/experiments/test_evidence_unit.py \
  packages/application/tests/unit/process/experiments/test_factor_diagnostics_reader_unit.py \
  packages/application/tests/unit/process/experiments/test_candidate_evidence_reader_unit.py \
  packages/application/tests/unit/commands/test_candidate_selection_unit.py \
  packages/application/tests/unit/process/experiments/test_holdout_unit.py \
  packages/application/tests/unit/query/test_experiment_query_review_packet_unit.py \
  packages/apps/tests/unit/api/routes/test_research_catalog_routes_unit.py \
  packages/apps/tests/unit/api/routes/test_research_experiment_routes_unit.py \
  packages/apps/tests/unit/api/routes/test_research_candidate_routes_unit.py \
  packages/apps/tests/integration/api/test_r3_selection_holdout_api_integration.py \
  packages/application/tests/integration/test_r3_evidence_closure_golden.py \
  packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py \
  -q -n0 --no-cov
pixi run -e dev arch-check
```

Expected: stock contribution + industry/size exposure 非空，ETF 明确 N/A。

**Step 8: Commit**

```bash
git add packages/strategy packages/analysis packages/application packages/apps \
  docs/contracts/r3-v1-api-surface.json \
  docs/contracts/r3-v1-api-surface.md
git commit -m "feat(research): persist stock contribution and exposure evidence"
```

### Task 10: 补 literal 128-candidate scheduler 压力恢复

**Files:**

- Modify: `packages/application/tests/integration/test_r3_scheduler_capacity.py`
- Modify production only if RED reveals defect:
  - `packages/application/src/ditto_application/processes/experiments/coordinator.py`
  - `packages/application/src/ditto_application/processes/experiments/scheduler_store.py`
  - `packages/application/src/ditto_application/processes/experiments/worker.py`

**Step 1: 写 RED/characterization test**

新增：

```python
def test_128_candidates_survive_restart_without_duplicate_claims(...):
    ...
```

要求实际持久化 128 个轻量 candidate，每个至少一个 fold；2/4 worker 分别运行。中途：

1. claim 一部分；
2. pause；
3. 关闭并重新打开 SQLite/process；
4. lease expiry/reclaim；
5. resume；
6. 完成全部候选。

断言：

- 128 candidate identities 全部出现且唯一；
- simultaneous live claims 不超过 worker_count；
- second experiment 不进入 active slot；
- attempt/fold claim 无重复；
- restart 前后 checkpoint/artifact lineage 连续；
- no orphan lease；
- final durable counts 精确。

**Step 2: 运行测试**

```bash
pixi run -e dev pytest packages/application/tests/integration/test_r3_scheduler_capacity.py -q -n0 --no-cov
```

Expected: 若现有实现已满足则作为 characterization GREEN；若失败，保留最小失败证据后再改 production。

**Step 3: 最小修复（仅在 RED 时）**

不得提高 128 ceiling、放宽 single-slot 或跳过 durable claim；修复 lease/recovery 的实际根因。

**Step 4: 验证 GREEN**

```bash
pixi run -e dev pytest packages/application/tests/integration/test_r3_scheduler_capacity.py -q -n0 --no-cov
pixi run -e dev test --fast
```

Expected: literal 128 压力恢复通过。

**Step 5: Commit**

```bash
git add packages/application
git commit -m "test(research): prove 128-candidate scheduler recovery"
```

### Task 11: 建立可信 R2 live Gate evidence 输入

**Files:**

- Create: `packages/application/src/ditto_application/processes/experiments/r2_live_gate_evidence.py`
- Create test: `packages/application/tests/unit/process/experiments/test_r2_live_gate_evidence_unit.py`
- Modify: `packages/analysis/src/ditto_analysis/experiments/hard_gate_collector.py`
- Modify test: `packages/analysis/tests/unit/experiments/test_hard_gate_collector_unit.py`
- Modify: `packages/application/src/ditto_application/processes/experiments/evidence_collector.py`
- Modify: `packages/application/src/ditto_application/providers_process.py`
- Potential config approval:
  - `packages/application/src/ditto_application/settings.py`
  - `packages/apps/src/ditto_apps/registry/infra/config.py`
- Create integration test: `packages/application/tests/integration/test_r3_live_gate_binding_integration.py`

**Step 1: 写 fail-closed RED 测试**

覆盖：

- no evidence -> NOT_EVALUATED；
- fixture-mode R2 report -> NOT_EVALUATED；
- `configuration_blocked`/missing recovery/idempotency/performance -> FAIL 或 NOT_EVALUATED，绝不能 PASS；
- live ready report + exact content hash + required artifacts -> PASS；
- bytes/hash/path drift -> fail closed；
- hand-constructed `True` 无法进入 collector；
- packet 保存 source report hash、checked_at 和 evidence refs。

**Step 2: 冻结 consumer-owned port**

```python
class R2LiveGateEvidenceReader(Protocol):
    def read_verified_live_gate(self) -> VerifiedR2LiveGateEvidence | None:
        """Return a content-verified live report or None."""
```

`VerifiedR2LiveGateEvidence` 必须包含：

```text
report_hash
checked_at
status
provider/entitlement evidence refs
performance evidence refs
recoverability evidence refs
idempotency evidence refs
```

**Step 3: 环境配置 approval checkpoint**

若 adapter 需要新增 report/manifest path 设置，先展示：

- 字段名和路径解析；
- testing 默认 `None`；
- production 缺失时 fail closed；
- 不自动扫描任意目录；
- 不读 frontend 或用户 home；
- isolated live acceptance 如何显式注入。

获得批准后才修改 settings/config。

**Step 4: 修改 pure hard gate projection**

`HardGateEvidenceView` 接受经过 application 验证后的 `GateFact` 输入；analysis 只投影，不读文件、不解析 R2 report、不依赖 apps/data。

**Step 5: 验证 GREEN**

```bash
pixi run -e dev pytest \
  packages/application/tests/unit/process/experiments/test_r2_live_gate_evidence_unit.py \
  packages/analysis/tests/unit/experiments/test_hard_gate_collector_unit.py \
  packages/application/tests/integration/test_r3_live_gate_binding_integration.py \
  -q -n0 --no-cov
pixi run -e dev arch-check
```

Expected: 只有 content-verified live-ready evidence 能产生 PASS。

**Step 6: Commit**

```bash
git add packages/analysis packages/application packages/apps
git commit -m "feat(research): bind r2 live evidence into r3 hard gates"
```

### RC1 Exit Gate: 滚动冻结 OpenAPI 与 frontend generated DTO

Task 6–9、11 可能改变 request/response/error shape。进入任何 RC2 Task 前，必须先把这些变化滚动到唯一事实源；RC2 组件不得消费旧 generated types 或手写临时 interface。

**Files:**

- Modify: `docs/contracts/r3-v1-api-surface.json`
- Modify: `docs/contracts/r3-v1-api-surface.md`
- Modify: `docs/openapi/v1.json`
- Modify test: `packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py`
- Modify test: `packages/apps/tests/unit/api/test_openapi_snapshot_unit.py`
- ditto-app Modify generated: `src/types/generated/api.d.ts`

backend：

先在同一 Python 进程读取 `ditto_apps.main.app.openapi()`，过滤
`/api/v1/research` 与 `/api/v1/strategies`，按 `(path, method)` canonical
排序，投影 operationId、method/path、request body、全部 response、
path/query/header parameters 与 maturity。不得启动 server、创建 registry 或
访问 DB。随后：

1. route 已落地的 `IMPLEMENT/PLANNED` entry 写 exact
   `runtime_method/runtime_path`，并验证 OpenAPI operationId 等于 entry
   `operation_id`；route 未落地的 entry 保持 null，且 OpenAPI 中不得已有该 path；
2. 用上述投影整体替换 JSON `runtime_contracts`（数量从当前 29 滚动增加），不做
   局部手工追加；
3. 刷新 classification counts、machine-derived summary 与 canonical JSON hash；
4. 保持所有未达到 Task 16 closure 的 entry 为 `implementation_state=PLANNED`。

```bash
pixi run -e dev python scripts/export_openapi.py
pixi run -e dev pytest \
  packages/apps/tests/unit/api/test_openapi_snapshot_unit.py \
  packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py \
  -q -n0 --no-cov
git diff --check
```

ditto-app（使用 Task 4 增加的 file mode，不启动 backend）：

```bash
OPENAPI_FILE=/home/chevy/projects/ditto/docs/openapi/v1.json bun run gen:api
git add src/types/generated/api.d.ts
OPENAPI_FILE=/home/chevy/projects/ditto/docs/openapi/v1.json bun run gen:api
git diff --exit-code -- src/types/generated/api.d.ts
bun run check
```

Expected: runtime/static snapshot 一致；第二次 frontend codegen zero unstaged diff。若 snapshot/generated type 有变化，分别形成小提交：

```bash
git add docs/openapi/v1.json \
  docs/contracts/r3-v1-api-surface.json \
  docs/contracts/r3-v1-api-surface.md \
  packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py \
  packages/apps/tests/unit/api/test_openapi_snapshot_unit.py
git commit -m "chore(api): roll forward r3 backend contract"
```

ditto-app：

```bash
git commit -m "chore(api): regenerate r3 client types"
```

无 diff 时不创建空提交。该 gate 不把 `PLANNED` API 标记为完成；最终无 `PLANNED` closure 仍由 Task 16 证明。

---

## RC2：完成真实前端工作流

### Task 12: 收口 T18 Strategy Studio

**Files (ditto-app):**

- Modify: `src/features/strategy/components/studio-mode-bar.tsx`
- Modify: `src/features/strategy/components/strategy-spec-form.tsx`
- Modify: `src/features/strategy/components/strategy-pipeline-view.tsx`
- Modify: `src/features/strategy/components/strategy-inspector.tsx`
- Modify: `src/features/strategy/components/node-library.tsx`
- Modify: `src/features/strategy/components/strategy-header.tsx`
- Modify: `src/features/strategy/state/strategy-studio-store.ts`
- Modify: `src/features/strategy/api/strategies.ts`
- Modify: `src/features/strategy/api/mappers.ts`
- Create: `src/features/strategy/hooks/use-strategy-version.ts`
- Modify: `src/features/strategy/components/strategy-versions-view.tsx`
- Modify: `src/features/research/hooks/use-factor-detail.ts`
- Create: `src/features/research/api/factor-diagnostics.ts`
- Modify: `src/features/research/components/factor-page.tsx`
- Create test: `src/features/strategy/components/strategy-version-detail.test.tsx`
- Create test: `src/features/research/components/factor-diagnostics.test.tsx`
- Modify/add colocated `*.test.tsx`

**Step 1: 写 UI contract RED 测试**

证明：

- 只有 Form/Pipeline 两种编辑模式，不暴露未治理 Code Editor；
- NodeDescriptor/config schema 是可添加节点与配置字段的唯一事实源；
- add/remove/reorder/configure 后 serialize → backend validate；
- unknown descriptor 只读显示且不能静默删除；
- 固定槽位和 allowed predecessors/successors 受约束；
- header 显示 strategy/version/spec hash、snapshot/start/R2 Gate context；
- 409/422/503、stale validation 和保存冲突有 typed state；
- `<900px` 可完成同等操作，键盘可 reorder。
- historical version 选择后调用
  `GET /v1/strategies/{strategy_id}/versions/{version}`，显示 server canonical
  spec/hash/state；404 不回退 current strategy payload；
- factor detail 调用 `GET /v1/research/factors/{factor_id}/diagnostics`，把
  snapshot/window/registry/artifact hash 明确显示为 provenance；API 失败显示
  typed error/retry，不使用 prototype `/factors/{id}/analysis`。

**Step 2: 运行 RED**

```bash
bunx vitest run \
  src/features/strategy \
  src/features/strategy/components/strategy-version-detail.test.tsx \
  src/features/research/components/factor-diagnostics.test.tsx
```

Expected: 当前 pipeline/inspector/错误/响应式覆盖不完整，version-detail 与
factor-diagnostics generated adapters/typed views 尚不存在。

**Step 3: 最小实现**

保持 view-model 与 generated DTO 隔离；所有 descriptor rule 在 mapper/store action 中集中，不在多个组件复制。
version detail 与 factor diagnostics adapter 只引用 generated operation/schema
types；factor 页面不得从 catalog descriptor 合成 diagnostics。

**Step 4: 验证 GREEN**

```bash
bunx vitest run \
  src/features/strategy \
  src/features/strategy/components/strategy-version-detail.test.tsx \
  src/features/research/components/factor-diagnostics.test.tsx
bun run check
bun run build
```

Expected: all pass。

**Step 5: Commit**

```bash
git add src/features/strategy \
  src/features/research/api/factor-diagnostics.ts \
  src/features/research/hooks/use-factor-detail.ts \
  src/features/research/components/factor-page.tsx \
  src/features/research/components/factor-diagnostics.test.tsx
git commit -m "feat(strategy): complete constrained studio editing"
```

### Task 13: 实现 T19 Experiment create/preflight flow

**Files (ditto-app):**

- Create: `src/routes/research/experiments/new.tsx`
- Modify generated: `src/routeTree.gen.ts`
- Modify: `src/features/research/api/experiments.ts`
- Modify: `src/features/research/api/query-keys.ts`
- Create: `src/features/research/hooks/use-experiment-preflight.ts`
- Create: `src/features/research/hooks/use-experiment-launch.ts`
- Create: `src/features/research/components/experiment-create-page.tsx`
- Create: `src/features/research/components/experiment-config-form.tsx`
- Create: `src/features/research/components/experiment-preflight-panel.tsx`
- Create test: `src/features/research/api/experiments.test.ts`
- Create test: `src/features/research/components/experiment-create-page.test.tsx`

**Step 1: 写 RED 测试**

覆盖：

- 选择固定 strategy version/snapshot/objective/baseline；
- matrix 显示 candidate count/128 ceiling；
- 96 月 validation 和 purge/embargo 可视化；
- worker 只允许 2/4；
- cost/seed/failure policy 完整；
- preflight 无写入；
- plan hash 未确认不能 launch；
- 修改任一字段使旧 confirmation stale；
- launch 使用 `Idempotency-Key`；
- 409/422/503 保留表单与 server truth；
- launch 成功导航到 detail。

**Step 2: 运行 RED**

```bash
bunx vitest run \
  src/features/research/api/experiments.test.ts \
  src/features/research/components/experiment-create-page.test.tsx
```

Expected: API/functions/components 不存在。

**Step 3: 实现 generated DTO adapter**

adapter 只消费 `components["schemas"][...]`，组件只消费 camelCase view-model；canonical planning document 构造集中在单一 mapper。

**Step 4: 实现 task page**

创建 flow 是独立 page，不放 modal。preflight response 是唯一预算/eligibility/plan hash truth。

**Step 5: 验证 GREEN**

```bash
bunx vitest run src/features/research
bun run check
bun run build
```

Expected: tests/check/build pass；route tree 包含 `/research/experiments/new`。

**Step 6: Commit**

```bash
git add src/routes/research/experiments/new.tsx src/routeTree.gen.ts src/features/research
git commit -m "feat(research): add experiment preflight and launch task"
```

### Task 14: 实现 T19 Experiment detail/control/evidence

**Files (ditto-app):**

- Modify: `src/routes/research/experiments.$id.tsx`
- Modify: `src/features/research/api/experiments.ts`
- Create: `src/features/research/api/candidate-evidence.ts`
- Create: `src/features/research/hooks/use-experiment.ts`
- Create: `src/features/research/hooks/use-experiment-mutations.ts`
- Create: `src/features/research/hooks/use-candidate-evidence.ts`
- Create: `src/features/research/hooks/use-candidate-selection.ts`
- Create: `src/features/research/hooks/use-holdout-evaluation.ts`
- Create: `src/features/research/components/experiment-detail-page.tsx`
- Create: `src/features/research/components/experiment-run-controls.tsx`
- Create: `src/features/research/components/candidate-comparison.tsx`
- Create: `src/features/research/components/experiment-validation-view.tsx`
- Create: `src/features/research/components/experiment-evidence-view.tsx`
- Create: `src/features/research/components/candidate-evidence-drilldown.tsx`
- Create: `src/features/research/components/holdout-evaluation-panel.tsx`
- Create test: `src/features/research/components/experiment-detail-page.test.tsx`
- Create test: `src/features/research/components/experiment-run-recovery.test.tsx`
- Create test: `src/features/research/components/candidate-selection-holdout.test.tsx`
- Create test: `src/features/research/components/candidate-evidence-drilldown.test.tsx`

**Step 1: 写 RED 测试**

覆盖：

- detail/candidates/gates/comparison/artifacts/selection-evidence fan-out；
- polling interval 只由 server status 决定；
- pause/cancel/resume/retry 使用 latest revision + idempotency key；
- 最多 pin 4 candidates；
- partial fold failures；
- holdout consumed/blocked 状态；
- 断网时停止伪进度；
- refresh/remount 后恢复 server truth；
- contribution + industry/size exposure 可审查；
- API error 不回退 prototype empty。
- pin 最多 4 个仍是 local comparison state；只有显式“选择为晋级候选”才调用
  candidate-selection mutation，并携带 comparison hash/revision/Idempotency-Key；
- holdout 按钮只对 server 返回的 persisted selection_id 可用，duplicate claim
  显示 `HOLDOUT_ALREADY_CLAIMED` 且刷新 claim truth；
- 选中任意 candidate 时，分别调用 selections/exclusions/factor-contributions
  drill-down（必须同时带 experiment_id），不拿 aggregate selected evidence 冒充。
- `use-candidate-evidence` 只按 server `next_cursor` 请求下一页；把
  `candidate_id/experiment_id/candidate_bundle_artifact_id/content_hash/
  resource_kind` 作为 page identity；不得跨 resource kind 复用 cursor。
  retry 产生新 comparison revision/bundle 后，旧 hash 返回 `EVIDENCE_STALE` 时
  清除旧 page 并 fail closed，不拼接跨 bundle items。测试覆盖 2+ folds 的稳定
  顺序、page boundary 无重复、cross-kind cursor rejection 与 refresh parity。

**Step 2: 运行 RED**

```bash
bunx vitest run \
  src/features/research/components/experiment-detail-page.test.tsx \
  src/features/research/components/experiment-run-recovery.test.tsx \
  src/features/research/components/candidate-selection-holdout.test.tsx \
  src/features/research/components/candidate-evidence-drilldown.test.tsx
```

Expected: 当前 detail 只是“T19 接线中”，candidate selection/holdout hooks、
typed cursor pages、`next_cursor` 追加与 hash-drift fail-closed 均不存在。

**Step 3: 实现 detail query graph**

query keys 必须按 experiment/resource/candidate 分层；selection/holdout mutation
成功后精确 invalidate detail、list、candidates、gates、comparison、
artifacts/evidence、candidate drill-down 和 holdout state，不全局清 cache。

**Step 4: 实现 server-truth controls**

按钮 availability、进度和 retry capability 均来自 API；不在客户端预测 scheduler 状态。

**Step 5: 验证 GREEN**

```bash
bunx vitest run src/features/research
bun run check
bun run build
```

Expected: all pass。

**Step 6: Commit**

```bash
git add src/routes/research/experiments.\$id.tsx src/features/research
git commit -m "feat(research): complete experiment workbench"
```

### Task 15: 收口 T20 Review/Publish/Reactivate

**Files (ditto-app):**

- Modify: `src/features/research/components/review-detail-page.tsx`
- Modify: `src/features/research/components/review-packet-sections.tsx`
- Modify: `src/features/research/components/review-queue-page.tsx`
- Modify: `src/features/strategy/components/review-decision-panel.tsx`
- Modify: `src/features/strategy/components/governance-actions.tsx`
- Modify: `src/features/strategy/hooks/use-strategy-governance.ts`
- Create: `src/features/strategy/hooks/use-strategy-events.ts`
- Create: `src/features/strategy/components/strategy-governance-audit.tsx`
- Modify: `src/features/research/hooks/use-review-packet.ts`
- Modify/add relevant tests
- Create test: `src/features/strategy/components/strategy-governance-audit.test.tsx`

**Step 1: 写 RED 测试**

固定 section 顺序：

```text
Decision Banner
Hard Gates
Statistical Evidence
Spec Diff
Candidate Rationale
Selection/Exposure Evidence
Lineage/Artifacts
R1 Impact
Decision Form
```

同时证明：

- soft stats 不渲染成自动 PASS；
- hard blocked 禁止 submit/approve/publish；
- submit 携带 bundle hash；
- rejected version clone-only；
- publish 与 approve 分步；
- reactivate 显示 current/target/impact/revision；
- 409 stale pointer 保留输入并 refetch；
- narrow viewport 使用 Sheet；
- mutation invalidate versions/active/reviews/review-packet/candidate scopes；
- typed error 不使用 `PrototypeOnlyEmpty`。
- governance audit 调用 `GET /v1/strategies/{strategy_id}/events`，按 server
  event_id/cursor 展示 decision/activation，不从 versions/current pointer
  合成历史；timeline 只显示 event DTO 的现有字段。review detail 可在 timeline
  旁显示当前 packet bundle hash，但必须明确 event row 本身没有持久 bundle
  关联，不能声称某 event 对应该 hash。

**Step 2: 运行 RED**

```bash
bunx vitest run \
  src/features/research/components \
  src/features/strategy/components/review-decision-panel.test.tsx \
  src/features/strategy/components/strategy-governance-audit.test.tsx \
  src/features/strategy/hooks/use-strategy-governance.test.tsx
```

Expected: route/confirmation 修复后仍有统计、R1 impact、responsive、
error/invalidation 缺口，server governance events audit 组件/adapter 尚不存在。

**Step 3: 最小实现**

ReviewPacket mapper 必须从 generated response 显式映射，禁止 UI 从 hash/presence 猜 gate outcome。
governance event mapper 同样只消费 generated event DTO；pagination cursor 来自
最后 event_id，不能用数组 index，也不能把当前 packet bundle hash 注入 event。

**Step 4: 验证 GREEN**

```bash
bunx vitest run src/features/research src/features/strategy
bun run check
bun run build
```

Expected: all pass。

**Step 5: Commit**

```bash
git add src/features/research src/features/strategy
git commit -m "feat(research): close governed review workflow"
```

---

## RC3：契约、deterministic acceptance 与 release evidence

### Task 16: 收口 typed DTO、OpenAPI、codegen、page contracts 与 live mock

**Files:**

- Modify: `packages/apps/src/ditto_apps/models/research.py`
- Modify: `packages/apps/src/ditto_apps/models/strategy.py`
- Modify: `scripts/export_openapi.py`
- Modify: `docs/openapi/v1.json`
- Modify: `docs/contracts/r3-v1-api-surface.json`
- Modify: `docs/contracts/r3-v1-api-surface.md`
- Modify test: `packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py`
- Modify test: `packages/apps/tests/unit/api/test_openapi_snapshot_unit.py`
- ditto-app Modify: `src/types/generated/api.d.ts`
- ditto-app Modify: `src/types/research.ts`
- ditto-app Modify: `src/features/research/api/experiments.ts`
- ditto-app Modify: `src/features/research/api/candidate-evidence.ts`
- ditto-app Modify: `src/features/research/api/factor-diagnostics.ts`
- ditto-app Modify: `src/features/strategy/api/strategies.ts`
- ditto-app Modify: `src/mocks/handlers/research.ts`
- ditto-app Modify: `src/mocks/handlers/strategy.ts`
- ditto-app Modify: `src/features/research/components/research-page.tsx`
- ditto-app Modify: `src/features/research/components/review-detail-page.tsx`
- ditto-app Create:
  - `docs/contracts/pages/experiment-create.contract.json`
  - `docs/contracts/pages/experiment-detail.contract.json`
  - `docs/contracts/pages/review-list.contract.json`
  - `docs/contracts/pages/review-detail.contract.json`
- ditto-app Modify generated: `src/features/shell/page-contracts.generated.ts`
- ditto-app Create test: `src/features/research/live-boundary.test.tsx`

**Step 1: 写 backend snapshot 与 API surface closure RED**

snapshot test 从 `ditto_apps.main.app.openapi()` 生成 canonical bytes，与 `docs/openapi/v1.json` 比较；过滤/排序必须由 exporter 统一，测试本身不“容忍差异”。

同时把 Task 4 surface contract 切换到 closure mode：所有非 `DEFER` entry 必须为 `IMPLEMENTED`，runtime method/path/operationId/request/response/error maturity 均匹配；仍为 `PLANNED` 的 entry 直接 FAIL。

**Step 2: 加固 W5 DTO**

至少替换：

```text
gate observed/policy
candidate parameters
factor resolved_payload
node default_config
artifact/selection/comparison payload
factor diagnostics
strategy version detail/governance events
candidate selection/holdout receipts
candidate selections/exclusions/factor-contributions
```

使用项目的 JSON value type/递归 Pydantic type；禁止继续扩散 `Any`。
Task 8/9 新增的 8 个 IMPLEMENT surface 必须全部由 generated operation/schema
types驱动；closure test 对它们逐项要求 `IMPLEMENTED`、runtime request/response/
status/parameters/maturity exact，任何仍 `PLANNED` 直接失败。

**Step 3: 导出 backend OpenAPI**

```bash
pixi run -e dev python scripts/export_openapi.py
pixi run -e dev pytest \
  packages/apps/tests/unit/api/test_openapi_snapshot_unit.py \
  packages/apps/tests/unit/api/test_r3_api_surface_contract_unit.py \
  -q -n0 --no-cov
```

Expected: static/runtime 124 operations（或当时冻结后的精确数量）一致；所有 R3 operation 有 maturity metadata。

**Step 4: frontend codegen RED/GREEN**

```bash
OPENAPI_FILE=/home/chevy/projects/ditto/docs/openapi/v1.json bun run gen:api
git add src/types/generated/api.d.ts
OPENAPI_FILE=/home/chevy/projects/ditto/docs/openapi/v1.json bun run gen:api
git diff --exit-code -- src/types/generated/api.d.ts
```

使用 Task 4 的 file mode，不启动 backend、不接触任何 DB。第一次允许预期更新并 stage，第二次必须 zero unstaged diff。

**Step 5: 移除 live fallback**

`VITE_USE_MOCK=false`：

- 不注册 MSW；
- 不显示 `PrototypeOnlyEmpty`；
- 无 hardcoded research rows；
- API failure 显示 typed error/retry；
- 测试环境仍可用 MSW 且 `onUnhandledRequest="error"`。

**Step 6: page contracts**

```bash
bun run generate-contracts
bun run audit:routes
bun run prototype:gates
bun run generate-contracts
git diff --exit-code -- src/features/shell/page-contracts.generated.ts
```

Expected: 4 个新页面 contract 生效，两次生成 zero diff。

**Step 7: Commit backend**

```bash
git add packages/apps scripts/export_openapi.py docs/openapi/v1.json \
  docs/contracts/r3-v1-api-surface.json \
  docs/contracts/r3-v1-api-surface.md
git commit -m "feat(api): freeze r3 openapi contract"
```

**Step 8: Commit frontend**

```bash
git add src docs/contracts
git commit -m "feat(research): consume frozen r3 contracts"
```

### Task 17: 生成 deterministic 双黄金 acceptance bundle

**Files:**

- Create: `packages/apps/src/ditto_apps/scripts/r3_research_acceptance.py`
- Create test: `packages/apps/tests/unit/scripts/test_r3_research_acceptance_unit.py`
- Create E2E wrappers:
  - `packages/apps/tests/e2e/test_r3_stock_selection_golden.py`
  - `packages/apps/tests/e2e/test_r3_etf_research_golden.py`
  - `packages/apps/tests/e2e/test_r3_governance_recovery.py`
  - `packages/apps/tests/e2e/test_r3_scheduler_capacity.py`
- Modify: `docs/runbooks/backup-restore.md`
- Create: `docs/evidence/r3/README.md`
- Create: `docs/evidence/r3/manifest.json`
- Runtime: `artifacts/acceptance/r3-report.json`
- ditto-app Create: `scripts/r3-research-acceptance.ts`
- ditto-app Create: `scripts/r3-research-acceptance.test.ts`
- ditto-app Modify: `package.json`
- ditto-app Runtime: `docs/review/r3-research-acceptance/deterministic/`

**Step 1: 写 runner RED 测试**

fixture 模式必须输出：

```json
{
  "mode": "deterministic_fixture",
  "release_status": "RELEASE_ACCEPTANCE_BLOCKED",
  "r2_live_gate": "NOT_EVALUATED",
  "golden_lanes": ["stock", "etf"]
}
```

禁止出现 `live_passed=true`、publish/promotion success 或 production drill wording。

fixture packet 必须带 `r2_live_gate=NOT_EVALUATED`，并实际调用 submit-review 与 publish/promotion 写路径，证明它们均 fail closed、publish 内部的 active-pointer CAS 未发生、append-only event count 不变；不能只检查 report 中的状态字符串，也不能假设存在独立 activate endpoint。

**Step 2: 实现 backend runner**

runner 仿 `scripts/acceptance/rc1_real_data_acceptance.py`，运行并记录：

- backend check；
- stock/ETF golden；
- governance recovery；
- literal 128 scheduler；
- isolated `tmp_path` backup/restore；
- OpenAPI zero-diff。
- fixture gate 下 submit-review/publish-promotion zero-write 且 active pointer 不变；

每个 command 保存 command、returncode、截断 stdout/stderr、artifact hashes。

**Step 3: 运行 deterministic backend acceptance**

```bash
pixi run -e dev python -m ditto_apps.scripts.r3_research_acceptance \
  --fixture \
  --output artifacts/acceptance/r3-report.json
```

Expected: command exit 0 表示 deterministic engineering acceptance 通过，但 report 仍明确 `RELEASE_ACCEPTANCE_BLOCKED`。

**Step 4: 实现 frontend deterministic runner**

使用 isolated backend fixture/MSW 模式，只证明 UI contract，不记录 live evidence。覆盖 Studio → Experiment → Review 页面、刷新恢复和 hard-gate blocked 行为。

**Step 5: 执行 backup/restore**

只使用任务专用临时 data root；验证 metadata、research DB、pinned artifacts、active pointer、review decisions、holdout claim、packet/artifact hashes 和 replay fingerprint。

**Step 6: 生成 manifest**

manifest 对每个 evidence file 记录：

```text
relative_path
sha256
mode
generated_at
source_commit
command
```

**Step 7: 验证**

```bash
pixi run -e dev check
pixi run -e dev pre-commit-run
```

ditto-app：

```bash
bun run check
bun run build
bun run acceptance:r3-research -- --fixture
```

Expected: deterministic suite pass；G2/live 仍 blocked；report 的 `proves` 只列工程闭环，`does_not_prove` 明确列出 provider entitlement、真实 certified data、真实 96 月、真实浏览器与 production recovery。

**Step 8: Commit backend**

```bash
git add packages/apps docs/evidence/r3 docs/runbooks/backup-restore.md artifacts/acceptance/r3-report.json
git commit -m "test(release): record deterministic r3 acceptance"
```

**Step 9: Commit frontend**

```bash
git add scripts package.json docs/review/r3-research-acceptance/deterministic
git commit -m "test(research): record deterministic workbench acceptance"
```

---

## Live G2：真实数据与浏览器验收

### Task 18: 关闭 R2 live Gate 并执行 R3 live acceptance

> **Hard approval checkpoint:** 本 Task 不得自动执行。开始前必须再次获得真实 provider、凭证、隔离 live data root、backup/restore 目标和 browser acceptance 的明确授权。

**Files:**

- Modify as evidence only: `docs/evidence/r2/<timestamp>/`
- Runtime: `artifacts/acceptance/r2-report.json`
- Runtime: `artifacts/acceptance/r3-report.json`
- Create: `docs/evidence/r3/<timestamp>/`
- ditto-app Runtime: `docs/review/r3-research-acceptance/live/`

**Step 1: 先关闭 R2 live Gate**

R2 report 必须同时证明：

- provider entitlement；
- 目标历史覆盖；
- performance benchmarks；
- recoverability；
- consecutive-run idempotency；
- required datasets 已 certified/strategy-eligible。

任何 `configuration_blocked`、`performance_blocked`、missing evidence 或 nonzero exit 都保持 R3 blocked。

**Step 2: 验证 R2 evidence binding**

把 exact R2 report/manifest hash 注入 Task 11 的 reader；重新收集 packet 后，只有该内容验证通过才允许 `r2_live_gate=PASS`。

**Step 3: 运行 R3 live backend**

```bash
DITTO_RUN_REAL_DATA_ACCEPTANCE=1 \
pixi run -e dev python -m ditto_apps.scripts.r3_research_acceptance \
  --real-data \
  --require-certified \
  --require-both-golden-lanes \
  --r2-evidence artifacts/acceptance/r2-report.json \
  --output artifacts/acceptance/r3-report.json
```

Expected:

- 两条 lane 使用真实 certified strategy-eligible data；
- promotable experiment ≥96 完整月；
- stock contribution/exposure 非空；
- one-shot holdout；
- replay；
- submit/review/publish/active/R1/reactivate；
- isolated live backup/restore；
- R2 gate PASS；
- report exit 0。

**Step 4: 运行真实浏览器**

backend + frontend 均使用 live API：

```bash
VITE_USE_MOCK=false bun run acceptance:r3-research -- \
  --real-data \
  --react-base http://127.0.0.1:5173 \
  --api-base http://127.0.0.1:8000
```

覆盖：

- Studio → preflight → launch；
- experiment polling/control/candidate comparison/evidence；
- holdout duplicate 被阻止；
- review/approve/publish；
- R1 active version；
- historical reactivate；
- refresh recovery；
- 0 console/page error；
- screenshots、JSON、trace、network error report。

**Step 5: 生成 live evidence manifest**

所有 evidence 内容寻址并绑定 backend/frontend commit SHA、OpenAPI hash、StrategySpec hash、snapshot hash、registry hash、parameter hash、cost hash、seed、packet bundle hash。

**Step 6: Commit evidence**

```bash
git add docs/evidence/r2 docs/evidence/r3 artifacts/acceptance/r2-report.json artifacts/acceptance/r3-report.json
git commit -m "test(release): certify r3 live g2 evidence"
```

ditto-app：

```bash
git add docs/review/r3-research-acceptance/live
git commit -m "test(research): record live r3 browser acceptance"
```

### Task 19: 最终 DoD 对账、文档校正与集成准备

**Files:**

- Modify: `docs/plans/2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md`
- Modify: `docs/plans/2026-07-27-r3-evidence-collection-closure-plan.md`
- Modify: `docs/plans/2026-07-28-r3-w5-frontend-wiring-design.md`
- Modify: `docs/evidence/r3/README.md`
- Modify: `docs/evidence/r3/manifest.json`
- ditto-app Modify relevant release/review index if present

**Step 1: Fresh final verification**

backend：

```bash
pixi run -e dev arch-check
pixi run -e dev check
pixi run -e dev pre-commit-run
git diff --check
git status --short
```

frontend：

```bash
bun run generate-contracts
bun run audit:routes
bun run prototype:gates
bun run check
bun run build
OPENAPI_FILE=/home/chevy/projects/ditto/docs/openapi/v1.json bun run gen:api
git diff --exit-code -- src/types/generated/api.d.ts
git diff --check
git status --short
```

Expected: all exit 0；两个 worktree clean。

**Step 2: 逐条对账 23 条 G2 DoD**

每条记录：

```text
status
evidence file
sha256
command
backend commit
frontend commit
notes
```

缺任何一项都不能标 PASS。

**Step 3: 校正历史状态文本**

删除/替换“后端 17/17、T18/T20 完成”等已被源码审计推翻的宽泛表述；改为 task/subtask + commit + evidence 的精确状态。不要删除历史设计决策，只追加 superseded/current status。

**Step 4: 请求代码审查**

使用 `ditto-change-review`，分别审查 backend/frontend diff、跨仓 OpenAPI identity 和 release evidence。

**Step 5: Commit documentation reconciliation**

```bash
git add docs
git commit -m "docs(r3): reconcile final g2 completion evidence"
```

**Step 6: 集成选择**

只有所有验证通过后，才使用宿主原生分支/PR 工作流：

1. 保留两个 feature branches；
2. 分别 push；
3. 分别创建/更新 PR；
4. backend 先合并，frontend 在 frozen OpenAPI commit 后合并；
5. 合并后重新验证 `main`/`origin/main`/merge commit 和 clean worktree。

未经用户明确要求，不自动 push、创建 PR、合并或删除分支。

---

## 3. 波次退出门禁

| 波次 | 必须满足 |
|---|---|
| RC0 | backend fast suite 0 fail；research child routes 可达；reactivate 请求体与 server 契约一致 |
| API Surface | 设计 operation 100% 分类；所有 `DEFER`/非等价替代已获批准；machine-readable contract 与 runtime OpenAPI 可对账 |
| RC1 | preflight/create-launch 可用；durable idempotency；submit-review hard-gated；stock contribution/exposure 非空；literal 128 recovery；可信 R2 live evidence port；OpenAPI/frontend generated DTO 已滚动同步 |
| RC2 | T18–T20 真实路由/API 工作流完成；无 prototype fallback；错误/刷新/响应式/键盘测试通过 |
| RC3 | backend OpenAPI = runtime；frontend 双 codegen zero diff；page contracts 完整；deterministic acceptance bundle 完整且明确 live blocked |
| Live G2 | R2 live PASS；真实双 lane ≥96 月；真实 publish/R1/reactivate；live backup/browser artifacts；23/23 DoD 有内容寻址证据 |

里程碑必须使用两个不同状态：

- Task 17 结束只能声明 **R3 ENGINEERING COMPLETE / G2 BLOCKED**；
- 只有 Task 18 live evidence 全部通过且 Task 19 对账完成，才能声明 **R3 G2 PASS**。

## 4. 23 条 G2 DoD Evidence Matrix

“当前”是 2026-07-30 审计快照；关闭状态必须以对应 Task 产生的 fresh command output 和 content-addressed artifact 为准。

| # | G2 DoD 摘要 | 当前 | 关闭 Task | 必需命令 / artifact | 模式 |
|---:|---|---|---|---|---|
| 1 | R2 live data Gate 关闭 | BLOCKED | 11、18 | `artifacts/acceptance/r2-report.json`、其 manifest/hash、Task 11 binding tests、Task 18 live runner | Live |
| 2 | 双黄金路径使用真实 certified、strategy-eligible 数据 | PARTIAL | 18 | `artifacts/acceptance/r3-report.json` 中两条 lane 的 dataset/snapshot/certification refs 与 `docs/evidence/r3/<timestamp>/manifest.json` | Live |
| 3 | 可晋级实验覆盖至少 96 个完整月 | PARTIAL | 6、18 | preflight integration 对 eligibility 的断言；live report 的实际 start/end/month count 和 promotable verdict | Both |
| 4 | StrategySpec 使用完整 canonical hash | PASS（需回归） | 17 | stock/ETF golden command record、StrategySpec bytes/hash、deterministic manifest | Deterministic |
| 5 | typed override 改变 runtime、manifest 和结果 | PASS（需回归） | 17 | 两条 golden 的 override/runtime/result identity assertions 与 artifact hashes | Deterministic |
| 6 | 128 candidate、2/4 worker、单 active 由服务端强制 | PASS（需加 literal 压力） | 6、10、17 | planning API integration；`test_r3_scheduler_capacity.py`；acceptance command record | Deterministic |
| 7 | 相同完整 identity 可确定性重放 | PASS（需回归） | 17 | stock/ETF golden replay assertions、两次 fingerprint/hash 对比 | Deterministic |
| 8 | PIT、split、purge/embargo 无泄漏 | PASS（需回归） | 17 | 双黄金 validation assertions 与 manifest 中 split/purge/embargo identity | Deterministic |
| 9 | holdout 仅预选候选消费一次 | PASS（需回归） | 17 | golden duplicate-holdout rejection、ledger/restart evidence | Deterministic |
| 10 | 个股池、排除、贡献、行业/规模暴露完整 | PARTIAL | 9、14、17、18 | production-path `test_r3_evidence_closure_golden.py`；selection/exposure artifact hashes；live UI/network evidence | Both；Live 终验 |
| 11 | ETF 与 R1 语义一致，可重激活旧版 | PASS（UI/live 待闭） | 3、15、17、18 | governance recovery E2E、R1 active pointer assertions、live publish/reactivate browser trace | Both；Live 终验 |
| 12 | hard gate 失败不能 submit review/publish | PARTIAL | 8、15、17 | API integration；fixture gate 下 submit/publish-promotion zero-write 与 active pointer unchanged；UI disabled/error assertions | Deterministic |
| 13 | UI 不把软统计包装为自动通过 | PARTIAL | 15、18 | Review component tests、`VITE_USE_MOCK=false` live screenshot/trace/network capture | Both；Live 终验 |
| 14 | active pointer 原子切换，R1/EOD 每批锁版 | PASS（需回归） | 3、15、17、18 | governance recovery、R1/EOD version-lock assertions、live reactivate evidence | Both；Live 终验 |
| 15 | 重启后 experiment/checkpoint/decision/holdout 可恢复 | PASS（需加 128） | 10、17 | literal scheduler restart test、governance/holdout recovery E2E、acceptance report | Deterministic |
| 16 | metadata、Research DB、artifacts 完成备份恢复 | PARTIAL | 17、18 | Task 17 `tmp_path` drill；Task 18 isolated live data-root backup/restore manifest 与 hash parity | Both；Live 终验 |
| 17 | `VITE_USE_MOCK=false` 全流程无 mock/hardcode/prototype empty | PARTIAL | 2、12–16、17、18 | `live-boundary.test.tsx`、route/page contract gates、frontend deterministic runner、live browser network trace | Both；Live 终验 |
| 18 | OpenAPI regenerate 零 diff | BLOCKED | 16、19 | `scripts/export_openapi.py` snapshot test；frontend 连续两次 `gen:api`；`git diff --exit-code` | Deterministic |
| 19 | backend `pixi run -e dev check` | BLOCKED | 1、19 | fresh `pixi run -e dev check` 与 `pre-commit-run` output | Deterministic |
| 20 | frontend `bun run check` 与 `bun run build` | BLOCKED | 2、3、12–19 | fresh check/build output、route audit、prototype gates、clean worktree | Deterministic |
| 21 | 真实浏览器 acceptance 有可审计 artifact | BLOCKED | 18、19 | `docs/review/r3-research-acceptance/live/` screenshots、trace、network/error report、manifest/hash | Live |
| 22 | 128 轻量候选通过压力与故障恢复 | PARTIAL | 10、17 | `pytest packages/application/tests/integration/test_r3_scheduler_capacity.py` 的 literal-128 run 与 acceptance command record | Deterministic |
| 23 | 两条黄金路径各有完整 release bundle | PARTIAL | 17、18、19 | deterministic + live manifests；每 lane 的 commits、identity hashes、commands、reports、browser/backup refs | Both；Live 终验 |

Matrix 约束：

- `PASS（需回归）` 只描述当前已有能力，不免除 Task 17 fresh regression；
- `Both；Live 终验` 表示 deterministic 证据可以证明结构与故障语义，但最终 PASS 必须包含真实数据或真实浏览器证据；
- 任一 artifact 缺 `relative_path/sha256/mode/generated_at/source_commit/command`，对应 DoD 维持 PARTIAL/BLOCKED；
- Task 19 必须把本表复制为最终 evidence index，并将“当前”替换成运行后的事实，不允许批量把 23 项改成 PASS。

## 5. 预计工作量

以单人有效开发日估算，不包含 R2 entitlement/provider 等外部等待：

| 范围 | 预计 |
|---|---:|
| RC0 | 1–2 日 |
| API Surface 冻结与批准 | 1–2 日 |
| RC1 | 6–10 日 |
| RC2 | 6–10 日 |
| RC3 | 3–5 日 |
| Live G2 工程执行 | 2–4 日 |
| 合计 | 19–33 日 |

Task 7 durable idempotency、Task 9 exposure evidence 和 Task 11 live evidence binding 是当前最高不确定性；若触发 schema/artifact/config approval，排期从批准后重新计算。Task 18 的 provider/entitlement 等外部等待不计入上述工程日。

## 6. Execution Handoff

按 RC0 → RC1 → RC2 → RC3 → Live G2 的依赖顺序执行。只有互不依赖的
只读探索/审查可使用宿主原生 subagents 并行；主 agent 在 task 间审查并运行
当前波次门禁。

无论选择哪种方式，先从 Task 1 开始；Task 4 的 API classification 获批后才能冻结后续 DTO；Task 18 必须等待新的 live execution 授权。
