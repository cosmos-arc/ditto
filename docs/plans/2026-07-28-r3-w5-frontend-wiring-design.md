# R3 W5 前端接线设计（ditto-app → R3 后端）

> **设计事实源**：[R3 主计划](2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md) Task 18-22 · [Wave 1 接线设计](archive/2026-07-02-wave1-frontend-wiring-design.md) · 2026-07-28 三 agent 调研（前端资产 / 后端 API 契约 / Wave 1 经验）
>
> **跨仓库**：后端 `/home/chevy/projects/ditto`（分支 `docs/r3-research-governance-design` 或继任）；前端 `/home/chevy/projects/ditto-app`（新建分支 `feat/r3-research-wiring`）。
>
> **当前状态（2026-08-01；取代本文内 2026-07-28～30 的阶段性“下一步/剩余”描述）**：
> W5 工程接线、production live boundary、冻结 OpenAPI codegen 与 deterministic UI
> acceptance 已完成。后端 frozen OpenAPI 为 `a6720e8a`（snapshot SHA-256
> `97119bbb1ff6ff9f01c1f7cb8ac6a14522ad5b31417c3816c82c0aa18ac4e221`）；前端契约
> 接线为 `246fc5f`，UI 验收 runner/制品为 `7f4d277`/`6da94e1`，报告 SHA-256 为
> `2aae6a908f5993e11f0125c1ac4732326dc71312293725bed1a99053be7e7f40`。jsdom + MSW
> 结果只能证明确定性 UI 契约，不能证明 `VITE_USE_MOCK=false` 的真实浏览器、真实
> provider 或 production recovery；这些 live 项仍等待 Task 18 单独授权。

## 决策摘要（已对齐）

| 决策 | 选择 | 理由 |
|------|------|------|
| **范围** | 完整 W5（Task 18-22）+ G2 | 完整研究→审查→发布闭环，不裁剪 |
| **后端缺口处理** | 前后端交错 | 每 Task 前补所需后端端点 + 增量 codegen，垂直闭环（Wave 1 纪律） |
| **顺序** | Task 0 spike → T18 → T19 → T20 → T21(滚动) → T22 | T18 依赖最少且建立 studio 模式供后续复用；T20 风险最高放在 Task 0 端点就绪后 |

**关键认知**：W5 不是纯前端工作——Task 17 当初跳过了 7 个 read/create 端点（experiment create、review packet read、candidate comparison、artifacts、selection-evidence、strategy diff/validate、Idempotency-Key）。完整 W5 = 补全 Task 17 遗留 + 前端接线。

## 1. 整体架构：复用 Wave 1 中间层栈（零改动）

调研确认 Wave 1 中间层栈 R3-ready，以下**直接复用**：

| 资产 | 位置 | 作用 |
|------|------|------|
| `apiClient` + `unwrapApiResponse` + `toApiError` | `src/lib/api-client.ts` | 唯一知道 `{data,pagination?}` 信封 + `{status_code,error,detail,error_code,request_id,timestamp}` 错误形态的地方；R3 端点用同一信封，零改动 |
| `withQueryParams` | `src/lib/api-client.ts` | snake_case query 序列化集中点 |
| MSW + `onUnhandledRequest:'error'` | `src/test/setup.ts` | 测试守卫，捕获 adapter/backend 漂移 |
| `gen-api.sh` + committed `api.d.ts` | `scripts/` + `src/types/generated/` | 对 live `/openapi.json` 生成，committed baseline |
| `PrototypeOnlyEmpty` | `src/components/domain/` | 后端喂不了的面的结构化空态 |
| 聚合端点 + TanStack `select` fan-out | `use-daily-decision.ts` 范式 | 一fetch→多派生 view，组件零改动 |
| DTO→view-model `mappers.ts` | `features/trading/api/mappers.ts` 范式 | 唯一翻译缝，组件只认 view-model 不认 DTO |
| query-key factory + scoped invalidation | `features/trading/api/query-keys.ts` 范式 | `DEFAULT_*_ID` + 按 scope 名 invalidate |
| `shouldUsePrototypeMocks()` runtime 双轨 | `api/runtime.ts` | `VITE_USE_MOCK==='true'` 分支 |
| 危险操作确认契约 | Wave 1 dialogs | `data-impact-summary` + `data-confirm-control` + 无快捷键 |

**W5 每个前端 feature** 按 Wave 1 纪律建 5 件套：`api/<resource>.ts`（adapter）+ `api/mappers.ts`（DTO→view-model）+ `api/query-keys.ts` + `hooks/use-*.ts`（聚合+select）+ `state/*.ts`（Zustand 工作副本，如需）。组件层零改动优先，靠 mapper 吸收 DTO 漂移。

## 2. Task 0 启动 spike（两仓库，先于 T18）

### 2.1 ditto 后端补 2 个结构性端点（解决 Wave 1 标记的 CONFIRMED 错配）

**错配 1：`/research/reviews` 顶级集合不存在。** Reviews 是 strategy-version 的 nested actions（`POST /strategies/{id}/versions/{v}/submit-review|approve|reject`），不是顶级 REST 资源。
- **解法**：加 `GET /research/reviews` 聚合端点——跨 strategy 收集 `state=review` 的版本作为 review queue 数据源（application query facade 读 governance store，返回 `StrategyVersionStateInfo` 列表）。**不加 POST 集合**（保留 nested action 模型）。前端 review queue = 此聚合的派生 view。

**错配 2：review-detail 的 11-hard-gate 明细无 read 端点。** `StrategyVersionResponse` 只返回 scalar `review_outcome`，不含 gate 明细/statistical evidence/lineage。
- **解法（2026-07-28 修订：experiment 键）**：加 `GET /research/experiments/{id}/review-packet`——读已持久化的 ReviewPacket。**键修订**：ReviewPacket 按 experiment 持久化（`packet.lineage.experiment_id`），不按 strategy/version——用 experiment 键匹配持久化、避免 version→launch→packet 反向查找；review queue（错配 1 端点）每条携带 `experiment_id` + `strategy_id/version`（从 packet launch binding lineage），前端 review-queue → experiment → review-packet 自然导航。
- **read model 扩展**：`ExperimentReviewPacketReadModel` 当前只有 `gate_outcomes`（rule_id/layer/outcome），需扩展 `build_review_packet_read_model` 暴露 statistical evidence（metric_values / comparison_payload_hash）、lineage（spec/snapshot/registry hashes）、R1 impact 字段，满足决策 4「完整 ReviewPacket」。前端 review-detail 渲染此 read model。

两个端点都是 application query facade + thin route（apps route 只解析 DTO 调 facade，不触 store），每个 1-2 commit。

> **✅ ditto 后端 Task 0 完成**（2026-07-28，commit `4fe17d44` + `be3bca26`，分支 `docs/r3-research-governance-design`）。实际落地决策：review queue 走 **governance MVP**——`GET /research/reviews` 返回跨 strategy `state=REVIEW` 的 `StrategyVersion` 列表（复用 `StrategyVersionResponse` DTO，**不带 experiment_id**：governance 层不持有 experiment identity，跨域 spec_hash 桥接推迟到 T20 前端接线时补，修正上文「每条携带 experiment_id」的初步设想）。`GET /research/experiments/{id}/review-packet` 按 experiment 键读 packet（reader `get_review_packet_for_experiment` 复用 `_load_verified_review_packet` helper），`ExperimentReviewPacketReadModel` 扩展为完整 ReviewPacket（11 gate 明细 + 6 reproduction hashes + comparison/r1 payload hashes + lineage fold/attempt ids + candidate_rationale + selection_trace_artifact_refs）。`pixi check` 全绿（arch 37 contracts + basedpyright 0 + ruff + 11675 test passed）。**下一步 §2.2 ditto-app baseline**（建 `feat/r3-research-wiring` 分支 + gen:api + 路由骨架）。

### 2.2 ditto-app baseline
- 建分支 `feat/r3-research-wiring`（从 main）。
- 起后端（注意：server 启动需 env，Wave 1 教训——`wave1_env.sh` 漏 `TUSHARE_TOKEN` 导致 granarian worker 崩；R3 acceptance env 要补齐），跑 `bun run gen:api` 对 `http://localhost:8000/openapi.json`，验证 research/strategy-governance schema 出现，commit baseline `api.d.ts`。
- 路由骨架：补 `/research/experiments/$id`、`/research/reviews`、`/research/reviews/$id`、`/research/node-descriptors`（TanStack Router 嵌套 + `<Outlet/>`）。
- 确认 wave1 栈零改动可复用（跑 trading 域回归不破）。

## 3. Task 18 Strategy Studio

> **✅ T18 后端 diff/validate 端点完成**（2026-07-29，分支 `docs/r3-research-governance-design`）：`POST /strategies/{id}/versions/{v}/validate`（candidate spec_json → `canonical_spec_hash_for_record` 同源 hash + validity + changed；非法 candidate 返 200+`valid=False` 不抛，仅 version 不存在 404）+ `GET /strategies/{id}/versions/{v}/diff`（v vs parent_version，`canonical_spec_payload` 字段级 diff，首版本空 diff）。application：`StrategySpecValidationInfo`/`StrategyVersionDiffInfo`/`SpecChange` read model + `canonical_spec_payload_for_record` 提取（hash/diff 同源）+ `diff_canonical_payloads`（`JsonValue` 递归 diff）+ facade `validate_spec`/`diff_version`/`_find_version`（`list_versions` 过滤，零 Protocol/DI 改动）。apps：4 DTO + 2 mapper + 2 route（thin，不 import capability）。TDD + `pixi check` 全绿（arch 37 contracts + basedpyright 0 + ruff + 127 相关测试）。**simplify**：hash 恢复委托 `canonical_spec_hash`（消除 hashlib/orjson 重复）+ `JsonValue` 复用 `ditto_platform.foundation.json_types` + 异常收敛到 typed `(AppBuilderError, StrategySpecError, ValueError)`。**✅ follow-up 全部完成**（simplify 4-agent review 清完）：① spec-aware keyed diff（`01ae6b11`：`parameter_schema` 按 name / `pipeline.nodes` 按 node_id keyed diff，消除中间插入级联假变更）— altitude STRONG；② `diff_version` 改用一次 `catalog.list_versions` 批量取全部 record（`7be68840`：1 SQL 替代 governance `list_versions` + `get_spec`×2）；③ hash 相等短路（`7be68840`：target/parent 同 `spec_hash` 直接返回空差，避免无谓 deserialize/diff）。diff 端点已 production-ready。

**后端依赖（交错先补）**：`GET /research/node-descriptors`（**已有**，research_catalog_routes）、`GET /research/factors`（已有）、**补 `GET /strategies/{id}/versions/{v}/diff` + `POST /strategies/{id}/versions/{v}/validate`**（plan Task 17 列出但未实现；返回 spec diff + canonical hash 校验结果，供 pre-save validation-panel）。

**前端接线**：
- 路由层级修复：`/research/strategies/index.tsx`（列表）+ `/$id/index.tsx`（详情）+ `/$id/studio.tsx`（Studio，保留）。
- `features/strategy/api/node-descriptors.ts` + `strategies.ts` + `strategy-lifecycle.ts`（adapter，对 generated types）。
- `state/strategy-studio-store.ts`（Zustand）：working copy 与 server version 分离，dirty state 由 server 返回 canonical spec/hash 清除。
- 受约束流水线编辑器：`node-library.tsx`（只读 descriptor）+ `strategy-spec-form.tsx`（配置）+ `strategy-pipeline-view.tsx`（有序节点列表 + 槽位 add/remove/configure/reorder，自动 edge）+ `node-inspector.tsx` + `strategy-validation-panel.tsx`。
- **关键坑（Wave 1）**：biome 300 行 / 200 行组件限制——RED 阶段就拆分上述 5 组件，勿 GREEN 后补拆。`<900px` 用全宽有序节点列表（不依赖图缩放）。拖拽必须有按钮 + 键盘等价路径。Allocator 不展示 R4 optimizer。
- 复用 `useOverlayController` + Drawer（node inspector）。
- `strategy-spec-roundtrip` 测试：表单/流水线切换保持相同 canonical DTO，保存创建新 draft 不覆盖。

**替换**：`experiment-list-page.tsx` + `strategy-list-page.tsx`（硬编码行）→ 真实 adapter 驱动；`hooks/index.ts`（strategy）+ `types/research.ts`（手写 DTO）→ generated + view-model。

> **✅ T18 前端 Strategy Studio 完成**（2026-07-29，ditto-app 分支 `feat/r3-research-wiring`）：数据层 5 件套（`types/strategy` view-model + mapper parse/serialize 双向 + adapter node-descriptors/strategies/strategy-lifecycle + query-keys + runtime）+ MSW live-shape（`/api/v1/strategies` + diff/validate + node-descriptors + experiment）+ 6 hooks + `strategy-studio-store`（Zustand working/server/dirty）+ 8 组件迁移（header/meta/inspector/overview/factors/editor/versions/experiment-queue 接 generated DTO→camelCase view-model）+ strategy-list/experiment-list 硬编码→真实 adapter + `node-library`（节点调色板，NodeDescriptor by category）+ `validation-panel`（validate 端点 canonical hash/valid/changed/errors 展示）集成 Studio + `strategy-spec-roundtrip` 测试（parse↔serialize 幂等）。关键认知：**spec_json 存的是 legacy `StrategySpec` asdict**（template/scorer/selector/execution/constraints/params），非 V2 canonical pipeline；前端 view-model 基于 legacy 解析，validate 端点算 canonical hash（后端从 legacy 派生）。`bun run check` 全绿（171 files / 1966 tests + lint + type + design-system 合规）。**后续增量**：完整 pipeline 编辑器（add/remove/reorder/configure）+ spec-form 编辑表单 + node-inspector 节点配置——legacy→V2 spec 编辑深度适配，留作 T18 增量；治理 mutations（submit/approve/publish）UI 留 T20；types/research.ts 手写 strategy 类型 + 旧 prototype mock/handler dead code 清理留 simplify。

## 4. Task 19 Experiment 工作台

**后端依赖（交错先补，本 Task 最多）**：
- **补 `POST /research/experiments`**（launch/create——`LaunchExperimentHandler` 已存在，仅缺 route）。
- **补 `GET /research/experiments/{id}/comparison`**（candidate comparison——`ComparisonQueryFacade.get_comparison` 已存在，wired 到 /trade，补 research 路径）。
- **补 `GET /research/experiments/{id}/artifacts`**（artifact index read——Task 13 已落地，缺 route）。
- **补 `GET /research/experiments/{id}/selection-evidence`**（selection evidence read——artifact 已 emit，缺 route）。
- 已有：`GET /research/experiments`（list）、`GET /{id}`（detail）、`GET /{id}/candidates`、control mutations（pause/cancel/resume/retry）、`GET /{id}/gates`。

> **✅ T19 后端 read 端点 E1-E3 完成**（2026-07-30，分支 `docs/r3-research-governance-design`，3 commits）：调研揭示 4 端点底层多「半现成」但缺 route/新 query/DTO，且 W5 原估「仅缺 route」偏轻。**架构硬约束 r8-queries-no-processes + apps 禁 import analysis 值对象** → read 端点用 **process-layer reader 接收 `str`**（不污染 route）。落地：
> - **E1 `GET .../artifacts`**（`472b05a1`）：`ExperimentReaderProtocol.list_experiment_artifacts`（抽 `_artifacts.py` leaf 守 reader <800 行，索引覆盖查询）+ `ExperimentQueryFacade.list_artifacts`/`ExperimentArtifactReadModel` + `ExperimentArtifactResponse` DTO + route。
> - **E2 `GET .../selection-evidence`**（`3a2c7b5a`）：`ExperimentSelectionEvidenceReader`（process，`get_artifact_by_relative_path` canonical path 解析 → `DurableSelectionEvidenceService.read_selection_evidence` 重建验证 → `SelectionEvidenceView` ledger payload）+ DTO + route + production-analysis allowance。
> - **E3 `GET .../comparison`**（`47bdee7d`）：`ExperimentComparisonReader`（process，精确复用 `evidence_collector.collect:128-136` 读路径但截断在 holdout/publish 前 → `CandidateComparisonProjection.canonical_payload()` → `CandidateComparisonView`）+ DTO + route + allowance。
> - **E4 `POST /preflight` + `POST /`（launch）剩余**：2 端点（launch 内部重算 plan 硬校验 `confirmed_plan_hash` + experiment launch 前不存在 → 单端点不可行）+ `_planning_request_builder.py`（组合 `decode_validation_protocol`/`_matrix_spec`/`_dataset_bindings`/`seal_promotion_objective` 成 JSON→`ExperimentPlanningRequest`，caller 提供预装配 canonical 文档；从 certified 数据装配文档的 assembler 是独立未来能力）+ preflight/launch DTO + 错误映射（PLAN_HASH_MISMATCH→409）。详见 `/home/chevy/.claude/plans/fizzy-rolling-engelbart.md`。
> - 关键坑：**formatter（ruff）每次 edit 后删 unused import**——import 必须与用法在同一 edit 落地（命中 6 次）；长 module 名触发 E501（`experiment_selection_evidence_reader`→`selection_evidence_reader`）。每端点 pixi check 全绿（arch 37 contracts + type 0 + ruff + 24 测试）。

**前端接线**：

- 路由：`/research/experiments/index.tsx`（catalog）+ `/new`（create flow，分段非 modal）+ `/$id`（detail）。
- `features/research/api/experiments.ts` + `hooks/use-experiments.ts`（list）+ `use-experiment.ts`（detail，**refetchInterval gated on `state==='running'`**，所有进度真理来自 `GET /{id}`，断网停 spinner，无合成动画）+ `use-experiment-mutations.ts`（pause/cancel/resume/retry）。
- 单 active experiment 由**服务端强制**（2/4 worker 单 slot）——UI 只反射 409/conflict `error_code`，不复制 gate。
- candidate-comparison：复用 Wave 1 DataTable + 回测 KPI primitive；pin-max-4 服务端真理。
- experiment-validation-view + experiment-evidence-view：从 `GET /{id}/gates` + `/{id}/artifacts` + `/{id}/selection-evidence` 读。
- 聚合+select：一个 `useExperiment(id)` fan-out 到 candidate-list/evidence/validation hooks（Wave 1 范式）。
- **降级**：若 artifacts/selection-evidence 后端端点未就绪，用 `PrototypeOnlyEmpty`（标 "pending backend read"），勿伪造。

## 5. Task 20 Review / Publish / Reactivate

**后端依赖**：Task 0 的 2 端点（`GET /research/reviews` 聚合 + `GET /research/experiments/{id}/review-packet`）+ 已有 governance mutations（submit-review/approve/reject/deprecate/reactivate/publish）。

> **✅ T20 review-detail + publish + reviews queue 完成**（2026-07-30，ditto `dae9ec54` + ditto-app `feat/r3-research-wiring`）。**跨域桥接**：后端 `list_reviews` 按 spec_hash application 层同层 join 补 `experiment_id`（本地 `ExperimentIdResolver` Protocol，strategy.py 零 analysis import；reader `get_experiment_id_by_spec_hash` EXISTS 过滤优先有 packet 的最新 experiment，抽到 `_review_packet.py` leaf 守 800 行）。**关键认知**：lifecycle 无 APPROVED 状态——APPROVE 决策让版本**留在 REVIEW** 但 `review_outcome=APPROVED`，直到 PUBLISH 才转 PUBLISHED；故 REVIEW 态队列天然含「待审查 + 已批准待发布」，无需改状态过滤。**前端**：review 5 件套（types/review + reviews/review-packet adapter+mapper + reviewKeys + useReviews/useReviewPacket + MSW live-shape）+ review-detail（ReviewDecisionBanner/HardGateList/EvidenceHashes/LineagePanel/CandidateRationale/SpecDiffView 复用 useVersionDiff，绝不伪造 gate）+ review-queue 列表页（experimentId=null 行禁用）+ publish（useStrategyGovernance.publish +reviews scope 失效 + PublishDialog bundle_hash 证据 + type-to-confirm + ReviewDecisionPanel：pending→批准/驳回、approved&!hard_blocked→发布）+ 移除 GovernanceActions 死的 disabled publish 按钮。路由 `/research/reviews/$experimentId` + validateSearch(strategyId,version)。ditto 11711 test + 37 contracts + type 0；ditto-app 185 files/2025 tests + biome 0 + tsc 0；audit:routes(32) + prototype:gates 过。**剩余**：Task 19 experiment 工作台、T22 双黄金/live G2 acceptance。（✅ research 导航入口 2026-07-30 完成，ditto-app `feat/r3-research-wiring`：顶部水平 sub-nav 8 主干入口——总览/因子/策略/实验/审查/回测/Regime/股票池（隐藏 node-descriptors 占位）；复用 DOMAINS/Rail 范式（`RESEARCH_SECTIONS` 常量 + `isSectionActive` + accent 指示条）+ `exact?:boolean` 数据声明（总览精确匹配提为数据层，消除 path 字面量特判）+ `cn` + `aria-current`；改造 `routes/research.tsx` 布局（裸 Outlet → flex-col[sub-nav + flex-1 Outlet]）。4-agent simplify：apply 6（移除冗余 id/aria-label/overflow-hidden、cn、exact、getByRole）/ skip 1（active-match 已 3 份拷贝 rail/use-active-domain/sub-nav，提取 lib `isActivePath` 超本次 scope，留第 2 域 sub-nav 时收敛）。`bun run check` 全绿（186 files/2031 tests）+ audit:routes 32 + playwright 目视（总览/策略页 sub-nav+active+布局确认）。IA_ROUTES 双源纯加 sub-nav 不新增路由无需改。）


**前端接线**：
- 路由：`/research/reviews/index.tsx`（queue，`GET /research/reviews`）+ `/$id`（detail）。
- review-detail 排列（DecisionBanner → hard gates → statistical evidence → spec diff → rationale → lineage → R1 impact → decision form），数据来自 `review-packet` read model。宽屏 persistent detail，窄屏 Sheet（`useOverlayController`）。
- **hard-gate 报告**：从 review-packet 渲染 11 gate 真实状态；**绝不伪造 gate 结果**（不自造通过，治理核心原则）。软统计证据不自动裁决（UI 不把 evidence 包装成自动 PASS）。
- publish/reactivate dialogs（复用 Wave 1 危险操作契约）：显示 current/target version + impact + spec/evidence hash + 必填确认文本；处理 409 stale-pointer（`error_code` → 重读 active pointer + 结构化冲突错误）。HARD GATE fail 时 publish 按钮禁用（服务端 `StrategyPromotionProcess` 强制，UI 反射 `review_outcome`，不自行决定）。
- mutation invalidation：publish/reactivate 同时 invalidate versions + active + review + candidate scopes（reactivate 改 active pointer + 历史 + 下游 review eligibility）。
- reactivate 要求 reason + confirmation + expected pointer revision + impact summary。

## 6. Task 21 OpenAPI codegen 滚动 + 移除 mock

**滚动（非最后）**：每 Task 后端补端点后立即 `gen:api` 重新生成 + `git diff --exit-code` 验证零漂移；adapter 用 generated `components["schemas"][...]`，组件只认 view-model（mapper 隔离）。Task 21 本体收尾：
- `VITE_USE_MOCK=false` 不注册 research/strategy MSW fallback、不显示 `PrototypeOnlyEmpty`（已接通的面）、API 失败进 typed error state（**测试仍用 MSW**——`setup.ts` 不变，`onUnhandledRequest:'error'` 保留；只扩展 `/v1/research/*` + `/v1/strategies/*/versions/*` live-shape handler，**不删**既有 prototype handler）。
- 替换 `types/research.ts` 手写 DTO 为 generated refs，只保留纯 UI view types。
- page contracts：`bun run generate-contracts` + `audit:routes` + `prototype:gates`，新增 routes 符合契约；两次 codegen 零 diff。

## 7. Task 22 双黄金 + G2 acceptance

- `scripts/r3-research-acceptance.ts`（ditto-app）：**严格区分 deterministic-fixture 模式 vs `--real-data` 模式**（仿 `r1-trading-acceptance`）；deterministic 运行**不得**记录为 live evidence。
- 后端 `r3_research_acceptance.py` + 4 e2e golden（stock/ETF/governance recovery/scheduler capacity）deterministic 全绿（r2_live_gate=NOT_EVALUATED 下 promotion `hard_gate_blocked` + active pointer 不变）。
- explicit live G2 acceptance（R2 live gate 关闭后）：`--real-data --require-certified --require-both-golden-lanes`，仅此时断言 publish/activate 成功。
- 浏览器 acceptance：`VITE_USE_MOCK=false` 跑通 Studio→Experiment→Review→Publish→R1→Reactivate；刷新恢复；holdout duplicate 阻止；0 console/page error；保留 evidence JSON + screenshots。
- backup/restore：metadata DB + research DB + pinned artifacts 备份恢复演练（后端已 `710bdde9`，补 acceptance 读侧）。

## 8. 后端端点补充清单（交错汇总，ditto 仓库）

| Task | 端点 | 已有实现 | 缺口 |
|------|------|---------|------|
| T0 | `GET /research/reviews`（跨 strategy 聚合 submitted） | governance store 有数据 | route + query facade |
| T0 | `GET /research/experiments/{id}/review-packet` | ReviewPacket 已持久化（experiment 键） | route + read model 扩展（statistical evidence/lineage/R1 impact） |
| T18 | `GET /strategies/{id}/versions/{v}/diff` | — | route + diff facade |
| T18 | `POST /strategies/{id}/versions/{v}/validate` | canonical hash 已有 | route + validate facade |
| T19 | `POST /research/experiments`（create） | `LaunchExperimentHandler` | route wiring |
| T19 | `GET /research/experiments/{id}/comparison` | `ComparisonQueryFacade` | research route |
| T19 | `GET /research/experiments/{id}/artifacts` | Task 13 index | route |
| T19 | `GET /research/experiments/{id}/selection-evidence` | artifact 已 emit | route |
| 全局 | `Idempotency-Key` header on mutations | — | route middleware |
| 全局 | DTO 弱类型加固（gate observed/policy、candidate parameters、factor resolved_payload、node default_config 的 `Any`） | — | typed DTO |

每个端点遵循 Task 17 既有模式：`APIRouter(prefix, tags)` + `@inject` + `FromComponent()` + `run_blocking`（asyncio.to_thread）+ `APIResponse[T]` + `NotFoundError` + `raise_business_error(conflict_keywords=...)`。apps route 不 import capability（application contracts read model 边界）。

## 9. 风险与坑（Wave 1 提炼）

| 坑 | 缓解 |
|----|------|
| biome/ruff 删 unused import（先加 import 后加用法就被删） | 用法与 import 同一 edit 落地 |
| SSH 端口 22 阻断 | `~/.ssh/config` github.com → ssh.github.com:443 |
| MSW 移除边界（Task 21） | 测试仍需 MSW；只扩展 live-shape handler，不删 prototype handler；`main.tsx` gate `VITE_USE_MOCK==='true'` |
| vitest flaky | `retry:2`（measurement/contract/overlay 测试基线） |
| codegen 非确定性漂移 | 两次 `gen:api` + `git diff --exit-code`；修 codegen 确定性而非 snapshot |
| biome 300 行限制（Studio） | RED 阶段拆 5 组件，勿 GREEN 后补拆 |
| dual adapter drift（Wave 1 v1/v2 教训） | 每资源一个 adapter，v2 出现时全量迁移 |
| deterministic ≠ live evidence | acceptance 脚本严格区分模式；MSW 绿 ≠ live smoke |
| selected→overlay coupling | Task 18 早建立 `useOverlayController`，T19/T20 复用 |
| server 启动需 env（TUSHARE_TOKEN 教训） | acceptance env 脚本补齐所有 startup validator 需求 |
| write-path invalidation 不全 | publish/reactivate 同时 invalidate versions+active+review+candidate |

## 10. 已确认决策（2026-07-28）

1. **review queue 范围**：`GET /research/reviews` 跨 strategy 全量 + 分页（MVP 不加 operator 过滤）。
2. **T18 编辑器形态**：有序列表 + 表单优先（覆盖 `<900px` + 键盘等价），图视图作为宽屏增强（非必需，降风险）。
3. **DTO Any 加固范围**：仅 W5 涉及的 4 处（gate observed/policy、candidate parameters、factor resolved_payload、node default_config），不全局加固（避免 scope 膨胀）。
4. **review-packet read model 形状**：完整 ReviewPacket（gate 明细 + statistical evidence + lineage + R1 impact），review-detail 全部 section 都要。
5. **G2 acceptance 与 R2 live gate 解耦**：deterministic G2（r2_live_gate=NOT_EVALUATED）先绿；live G2 等 R2 gate。两条路径分开追踪。

## 实施节奏（建议）

每 Task 一个会话或一组 commit：后端端点（ditto，1-3 commit）→ gen:api → 前端接线（ditto-app，TDD RED→GREEN→REFACTOR，多 commit）→ 该 Task 的 acceptance 切片。Task 间 PR 独立合并。预估 T0(2-3 天) + T18(1-1.5 周) + T19(1-1.5 周) + T20(1 周) + T21(3-5 天) + T22(1 周)，含后端交错约 5-6 周（plan 原 3-5 人周是纯前端估，交错加后端约 +1 周）。
