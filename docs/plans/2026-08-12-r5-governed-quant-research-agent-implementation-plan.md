# R5 治理型量化研究 Agent 详细实施计划

**日期：** 2026-08-12
**状态：** 进行中
**恢复点：** Wave 3 / Task 19，正式写入只经 application command
**设计事实源：** [R5 治理型量化研究 Agent 设计](2026-08-12-r5-governed-quant-research-agent-design.md)

## 目标

在不改变 Ditto 核心量化、DailyDecision 或交易权威的前提下，交付一个本机、内部、单操作者的治理型 Agent 平面：

- grounded Evidence Copilot；
- 带 compile/validate/diff 的 Author Copilot；
- 一次审批、预算受限的 Autonomous Research Campaign；
- DailyDecision V3 之后的 shadow-only Decision Briefing；
- 可恢复状态、HITL、PIT、OCI 沙箱、OTel、审计、eval 和降级。

成功边界以设计文档 §15 和本文 Wave 6 exit gate 为准。

## 约束与不做事项

- 当前基线：12 包；R4/G3 提交 `9ee6c48c` 已落地；R3 experiment/holdout/ledger/replay 可复用。
- 新包：`packages/agent`，import name `ditto_agent`，实施后共 13 包。
- 依赖方向：`apps -> agent -> application -> capabilities`；agent 不直接访问 capability 或 analysis。
- `analysis` 只拥有研究领域和持久化合同；调度在 application；物理模型/沙箱装配在 apps registry。
- PIT 缺少 cutoff/snapshot/version 时 fail closed；禁止 latest fallback。
- 数据帧继续使用 Polars；依赖只经 Pixi；序列化优先 orjson，禁止 pickle。
- 不实现公网、auth/RBAC、多租户、Web/RAG/MCP、Hosted Code Interpreter、真实券商、自动下单或自动策略发布。
- 生成代码不进入 EOD/交易动态加载路径。
- 所有 Agent feature flags 默认关闭，Agent 故障不能影响核心 Ditto。

## 所需 Ditto skills

- 所有公共合同、包边界、DI 和 `.importlinter`：`ditto-architecture-change`。
- 所有行为任务：`ditto-test-first`，先观察能够解释目标行为的 RED。
- 数据查询、Campaign、生成代码、fold、memory、holdout：`ditto-pit-safety`。
- 高风险 diff 完成后及 PR 前：`ditto-change-review`。

纯文档和机械归档不要求 RED；生产 Python、schema、架构和交易语义任务不能豁免。

## 固定目录与接口放置

| 边界 | 固定位置 |
|---|---|
| Agent contracts/runtime/tools/models/storage/evals | `packages/agent/src/ditto_agent/**` |
| Agent 单元测试 | `packages/agent/tests/unit/**` |
| Evidence queries | `packages/application/src/ditto_application/queries/{research_evidence,decision_evidence}.py` |
| Campaign orchestration/ports | `packages/application/src/ditto_application/processes/experiments/{autonomous_campaign,candidate_sandbox_port,generated_candidate_evaluator}.py` |
| Research campaign domain | `packages/analysis/src/ditto_analysis/experiments/{campaign,generated_code,research_memory,search_ledger}.py` |
| Research persistence | `packages/analysis/src/ditto_analysis/storage/sqlite/experiments/**`，复用 `data_root/research/research.sqlite` |
| Agent persistence | `packages/agent/src/ditto_agent/storage/sqlite/**`，固定 `data_root/agent/agent.sqlite` |
| OpenAI/OCI/Agent composition | `packages/apps/src/ditto_apps/registry/agent/**` |
| HTTP DTO/routes | `packages/apps/src/ditto_apps/models/agent.py`、`api/routes/agent_routes.py` |
| CLI | `packages/apps/src/ditto_apps/cli/commands/agent.py` |

不得为了方便改成 platform LLM gateway、agent 直连 analysis，或 apps route 直连 SQLite。

## 执行合同

1. 从 `codex/r5-governed-agent` 或同等非 `main` 分支开始；每个 Task 是独立可回滚提交。
2. 每个行为 Task 先增加测试并运行精确命令观察 RED；记录失败原因后才实现 GREEN。
3. schema、生产依赖、架构边界、OCI 和真实模型外发按 Approval 表暂停。
4. Fake/scripted model 是默认测试 provider；普通 CI 不需要 API key、Docker daemon 或网络。
5. 任何 live model/sandbox acceptance 独立标记并保存 evidence，不能替代 deterministic tests。
6. 每个 Task 完成后在本文“恢复状态”记录提交、命令与结果；不得用历史 GREEN 替代当前 diff。

## Tasks

### Wave 0：前置确认与批准

### Task 1：冻结当前 R3/R4/application 消费面

**依赖：** 无
**风险：** 普通，只读
**状态：** [x]

- **目标文件或边界：** `DailyDecisionV3QueryFacade`、experiment query/command/process、StrategySpec/DSL、portfolio/risk read model、apps registry provider。
- **RED/观察证据：** 用 `rg` 和类型签名列出真实叶模块；若设计文档中的任何符号不存在，记录 mapping，不靠 re-export 或猜测补齐。
- **实施：** 生成 `docs/evidence/r5/preflight/current-contract-inventory.md`，逐项记录 provider、consumer、方法签名、PIT 字段和复用/新增裁决。
- **重构边界：** 本 Task 不改生产代码。
- **验收：** inventory 覆盖 R5.1—R5.4 所有工具所需合同，且每个新增 facade 都有明确理由。
- **提交边界：** 只提交 preflight evidence。
- **恢复入口：** inventory 中第一项 `missing` 或 Task 2。

```bash
rg -n "DailyDecisionV3|Experiment|Holdout|TrialLedger|StrategySpec|FactorEvaluation|RiskGate" packages/application/src packages/analysis/src packages/apps/src
git diff --check
```

### Task 2：冻结 SDK、模型和 OCI 技术证据

**依赖：** Task 1
**风险：** 普通，只读；结论触发后续审批
**状态：** [x]

- **目标文件或边界：** OpenAI Agents SDK 当前 Python API、Responses `store=false`、MAM/ZDR、模型 profile、Docker Desktop/rootless OCI/gVisor 能力。
- **RED/观察证据：** 当前项目没有 `openai-agents` 直接依赖；不得依赖历史 2026-08-04 的示例签名。
- **实施：** 写 `docs/evidence/r5/preflight/runtime-dependency-proof.md`，记录精确包版本范围、上游链接、所需 SDK API、license、transitive review、模型 ID 和 OCI feature matrix。
- **重构边界：** 不安装依赖、不拉镜像、不创建 project。
- **验收：** 能回答 Agents SDK adapter、mock 方式、approval state serialization、OTel bridge、macOS/Linux sandbox 差异。
- **提交边界：** 只提交 dependency proof。
- **恢复入口：** Approval A1。

```bash
rg -n "openai|agents|langfuse|opentelemetry|docker" pixi.toml pyproject.toml packages/*/pyproject.toml pixi.lock
git diff --check
```

### Task 3：收集四类批准证据

**依赖：** Task 2
**风险：** 高风险，暂停点
**状态：** [x]

- **目标文件或边界：** Approval A1—A4。
- **RED/观察证据：** 任一批准为空即阻塞对应 Task，不把本文设计接受等同于未来生产依赖/schema/外发批准。
- **实施：** 在 `docs/evidence/r5/preflight/approvals.md` 记录批准人、时间、精确对象、版本/hash、限制和撤销条件。
- **重构边界：** 未批准的 Wave 可继续做只读设计或 Fake provider 工作，但不能越过对应 Gate。
- **验收：** Approval 表所有必填字段可审计。
- **提交边界：** 单独 evidence 提交；不与依赖或 schema 变更混合。
- **恢复入口：** Task 4，或具体外部等待项。

```bash
git diff --check
```

### Wave 1：R5.0 治理基础

### Task 4：建立 `ditto_agent` 包和机器边界

**依赖：** Task 3 / Approval A1
**风险：** 高风险，架构和生产依赖
**状态：** [x]

- **目标文件或边界：** `packages/agent/{pyproject.toml,AGENTS.md,src/ditto_agent,tests}`、`pixi.toml`、`.importlinter`、架构文档。
- **RED/观察证据：** 先增加 import/boundary tests，观察 `ditto_agent` 不存在或缺少机器合同。
- **实施：** 添加 `openai-agents` 精确上限；建立 typed 空包；加入 root packages 和 agent/application/capability/platform/apps forbidden contracts；Pixi 注册 editable package。
- **重构边界：** 不添加 LLM gateway、业务工具或 storage；不更改既有 capability 方向。
- **验收：** 包可导入，非法 fixture import 被 contract 拦截，全部现有合同保持通过。
- **提交边界：** 仅包骨架、依赖和机器边界。
- **恢复入口：** 首个失败的 import-linter contract。

```bash
pixi run -e dev pytest packages/agent/tests/unit/test_package_boundary.py -v
pixi run -e dev arch-check
pixi run -e dev check
```

### Task 5：核心合同、canonical codec 与状态机

**依赖：** Task 4
**风险：** 行为/公共契约
**状态：** [x]

- **目标文件或边界：** `ditto_agent.contracts.{runtime,temporal,evidence,approval}`、`runtime.{codec,state_machine}`。
- **RED/观察证据：** 先测试 Run 合法/非法转换、UTC/enum/identity 校验、canonical bytes 稳定性和 action hash 篡改。
- **实施：** 落地设计文档中的 Agent-owned types；canonical encoding 固定字段顺序、Unicode/number/datetime 规范；审批 hash 覆盖 authority、PIT、snapshot、预算和 expiry。
- **重构边界：** 类型不含 I/O；模型不能构造受信 `TemporalToolContext`。
- **验收：** 相同语义跨字段顺序 hash 相同；任一安全字段改变 hash 必变；非法状态 fail closed。
- **提交边界：** 核心纯合同和单元测试。
- **恢复入口：** 第一个未通过的 golden codec fixture。

```bash
pixi run -e dev pytest packages/agent/tests/unit/test_contracts.py packages/agent/tests/unit/test_state_machine.py packages/agent/tests/unit/test_canonical_codec.py -v
pixi run -e dev check
```

### Task 6：`AgentModelPort`、Fake provider 与 OpenAI adapter

**依赖：** Task 5；真实调用另依赖 Approval A4
**风险：** 行为/第三方 adapter
**状态：** [x]

- **目标文件或边界：** `ditto_agent.models.{port,fake,openai_adapter}`、`ditto_apps.registry.agent.model_provider`。
- **RED/观察证据：** 先以 shared contract suite 证明 Fake 与 adapter 未实现 typed response、usage、interruptions 和 continuation state。
- **实施：** port 只暴露 Agent runtime 需要的 run/stream/resume 语义；Fake 支持 scripted tool calls/failures；OpenAI adapter 固定 `store=false`、允许 function tools，拒绝禁用 hosted tools。
- **重构边界：** API key/config 只由 apps 注入；不在 platform 建 gateway；测试不发网络请求。
- **验收：** 两个 provider 通过相同 contract；禁用能力在构造或调用前 fail closed；usage 可计量。
- **提交边界：** model port、providers、registry wiring 和测试。
- **恢复入口：** shared provider contract 的第一处差异。

```bash
pixi run -e dev pytest packages/agent/tests/unit/test_model_port_contract.py packages/agent/tests/unit/test_openai_adapter.py packages/apps/tests/unit/test_agent_model_provider.py -v
pixi run -e dev check
```

### Task 7：Agent SQLite、幂等、lease 与 hash-chain audit

**依赖：** Task 5 / Approval A2
**风险：** 高风险，schema/持久化
**状态：** [x]

- **目标文件或边界：** `ditto_agent.storage.sqlite.{database,schema,reader,writer,audit}`、`schema_v1.sql`，路径 `data_root/agent/agent.sqlite`。
- **RED/观察证据：** 先测试未标记/未知版本/损坏 schema、事务回滚、幂等冲突、lease 丢失、hash chain 篡改和 close 后访问。
- **实施：** 仿 research nominal DB wrapper；独立 application_id/user_version；保存 session/run/event/approval/idempotency/lease/audit/retention metadata。
- **重构边界：** 不保存 analysis research domain；不暴露裸 `SQLitePool`；完整敏感 prompt/response 默认不入库。
- **验收：** 初始化/重开/备份恢复确定；相同 key 同 body replay，相同 key 不同 body conflict；篡改可检测。
- **提交边界：** schema、adapter、DI 和持久化测试独立提交。
- **恢复入口：** schema marker 或第一条失败的原子性测试。

```bash
pixi run -e dev pytest packages/agent/tests/unit/storage -v
pixi run -e dev pytest packages/apps/tests/integration/test_agent_database_lifecycle.py -v
pixi run -e dev check
```

### Task 8：Temporal context、EvidenceEnvelope 与外发策略

**依赖：** Tasks 5、7
**风险：** 高风险，PIT/数据权利
**状态：** [x]

- **目标文件或边界：** `ditto_agent.runtime.{temporal_context,egress_policy}`、evidence codec。
- **RED/观察证据：** future sentinel、缺 snapshot/cutoff、模型覆盖 context、cache key 漏字段、local-only 外发用例先失败。
- **实施：** 服务端 context factory；完整时间/snapshot/license/egress/authority 校验；evidence hash 与 cache identity 覆盖所有可见性输入。
- **重构边界：** 不自行发明 knowledge rule，调用现有 owner contract；禁止 wall-clock/latest fallback。
- **验收：** cutoff 外极值不影响结果、cutoff 内相邻记录可用；禁止外发内容在 provider 调用前被拒绝。
- **提交边界：** temporal/evidence/egress 与 PIT 测试。
- **恢复入口：** future sentinel 测试。

```bash
pixi run -e dev pytest packages/agent/tests/unit/test_temporal_context.py packages/agent/tests/unit/test_egress_policy.py -v
pixi run -e dev pytest -m pit
pixi run -e dev check
```

### Task 9：Episode、事件重放与版本身份

**依赖：** Tasks 5—8
**风险：** 行为/审计
**状态：** [x]

- **目标文件或边界：** `ditto_agent.runtime.{episode,replay}`、Episode reader/writer。
- **RED/观察证据：** 同一 scripted run 事件顺序或 hash 不稳定、缺模型/prompt/tool/snapshot identity 时先失败。
- **实施：** 生成 `AgentEpisodeManifest`；持久化输入摘要、版本、tool/action/evidence refs、状态和 hash chain；replay 只重放事件/工具结果，不重复副作用。
- **重构边界：** replay 不调用 live model，除非显式 comparison mode；comparison 产生新 Episode。
- **验收：** 相同 fixture 事件和 tool sequence 100% 一致；损坏或缺失 evidence fail closed。
- **提交边界：** Episode/replay 和 fixtures。
- **恢复入口：** 第一处 manifest digest 差异。

```bash
pixi run -e dev pytest packages/agent/tests/unit/test_episode.py packages/agent/tests/unit/test_replay.py -v
pixi run -e dev check
```

### Task 10：本地 eval 数据集与 grader 框架

**依赖：** Task 9
**风险：** 行为/质量门
**状态：** [x]

- **目标文件或边界：** `ditto_agent.evals.{cases,runner,graders,report}`、`packages/agent/tests/fixtures/evals/**`。
- **RED/观察证据：** 添加最小安全失败 case，证明 runner 会把 forbidden action、缺 evidence 和 nondeterministic replay 判失败。
- **实施：** 定义 versioned case schema；grader 分 deterministic、rule-based、optional model critic；模型 critic 永不覆盖确定性安全结论。
- **重构边界：** 官方发布报告由本地 runner 生成，不依赖 `/v1/evals` 或云端 trace 存储。
- **验收：** fixed seed/Fake provider 报告 byte-stable；grader 版本和输入 hash 可追踪。
- **提交边界：** eval framework 与最小 fixtures。
- **恢复入口：** 第一条错误分级或不稳定报告。

```bash
pixi run -e dev pytest packages/agent/tests/unit/evals -v
pixi run -e dev check
```

**Wave 1 Exit Gate**

```bash
pixi run -e dev pytest packages/agent/tests -v
pixi run -e dev arch-check
pixi run -e dev check
git diff --check
```

Exit：第 13 包边界、Fake/OpenAI provider contract、Agent DB、PIT context、Episode/replay 和 eval harness 全绿；feature flags 仍关闭。

### Wave 2：R5.1 Evidence Copilot

### Task 11：只读 evidence facades

**依赖：** Wave 1、Task 1 inventory
**风险：** 行为/公共 query
**状态：** [x]

- **目标文件或边界：** `queries/research_evidence.py`、`queries/decision_evidence.py` 及 providers。
- **RED/观察证据：** 为 experiment/factor/strategy/backtest/portfolio/risk/DailyDecision V3 建 contract tests，先证明当前 facade 缺统一 typed evidence 或时间字段。
- **实施：** 优先组合既有 leaf query；只新增 Agent 确实需要的只读 projection；返回 evidence refs 和完整 provenance。
- **重构边界：** query 无写入、无 Agent 类型、无 transport、无物理 storage。
- **验收：** 所有 facade 对缺 snapshot/identity fail closed，R4/R3 旧 API 不变。
- **提交边界：** application read facades 与测试。
- **恢复入口：** inventory 中第一项 read capability。

```bash
pixi run -e dev pytest packages/application/tests/unit/queries/test_research_evidence.py packages/application/tests/unit/queries/test_decision_evidence.py -v
pixi run -e dev arch-check
pixi run -e dev check
```

### Task 12：Evidence function tools 与 grounding

**依赖：** Tasks 8、11
**风险：** 行为/PIT
**状态：** [x]

- **目标文件或边界：** `ditto_agent.tools.{research,portfolio,risk,decision}`、grounding builder。
- **RED/观察证据：** Fake model 选错工具、工具绕过 context、输出缺 evidence refs、tool error 被改写成事实等用例先失败。
- **实施：** tool 是 application facade 薄适配；输入 schema 不暴露受信 context；输出统一为 `EvidenceEnvelope`；`GroundedAnswer` 每个 claim 关联 evidence。
- **重构边界：** 工具不计算指标、不访问 storage、不吞掉领域错误。
- **验收：** tool allowlist 精确；无证据或冲突时拒答；PIT sentinel 保持隔离。
- **提交边界：** read tools、grounding 和单元测试。
- **恢复入口：** 第一条 tool contract failure。

```bash
pixi run -e dev pytest packages/agent/tests/unit/tools packages/agent/tests/unit/test_grounding.py -v
pixi run -e dev pytest -m pit
pixi run -e dev check
```

### Task 13：单 Agent 编排、预算与 guardrails

**依赖：** Tasks 6、9、10、12
**风险：** 行为/模型安全
**状态：** [x]

- **目标文件或边界：** `ditto_agent.runtime.{orchestrator,budgets,guardrails}`。
- **RED/观察证据：** max turns、token/cost/time、重试、tool allowlist、拒答和 provider failure 用例先失败。
- **实施：** deterministic host loop 管理 RUNNING/PAUSED/FAILED；模型只返回 typed intent；tool-level guardrail 在调用边界校验 authority/context；无 write tool。
- **重构边界：** 不使用 handoff/multi-agent；不允许 SDK 默认 trace 上传敏感内容。
- **验收：** 超预算不继续调用；瞬态重试有上限；非瞬态失败不伪造答案；Episode 完整。
- **提交边界：** read-only orchestrator 和 guardrails。
- **恢复入口：** 首个预算或状态机失败。

```bash
pixi run -e dev pytest packages/agent/tests/unit/test_orchestrator.py packages/agent/tests/unit/test_budgets.py packages/agent/tests/unit/test_guardrails.py -v
pixi run -e dev check
```

### Task 14：Session/Run API、SSE、恢复和取消

**依赖：** Tasks 7、13
**风险：** 行为/公共 API
**状态：** [x]

- **目标文件或边界：** `models/agent.py`、`api/routes/agent_routes.py`、OpenAPI registration、registry runtime。
- **RED/观察证据：** OpenAPI 路径、Idempotency-Key conflict、SSE ordering/Last-Event-ID、cancel race、missing run 用例先失败。
- **实施：** 落地设计 §11.1 的 session/run/approval routes 中 R5.1 可用部分；SSE 只重放 persisted events；route 薄适配。
- **重构边界：** 不把 SDK state 暴露为 API DTO；不在 route 执行业务逻辑。
- **验收：** OpenAPI 稳定、SSE 单调、断线恢复不重复工具、Agent disabled 返回结构化 unavailable。
- **提交边界：** HTTP/SSE surface 和 integration tests。
- **恢复入口：** OpenAPI contract 或 SSE first failure。

```bash
pixi run -e dev pytest packages/apps/tests/unit/test_agent_routes.py packages/apps/tests/integration/test_agent_sse.py -v
pixi run -e dev check
```

### Task 15：Agent CLI

**依赖：** Task 14
**风险：** 行为/入口
**状态：** [x]

- **目标文件或边界：** `cli/commands/agent.py` 与 CLI registration。
- **RED/观察证据：** `run/show/events` help、exit code、JSON/human output、cancel 用例先失败。
- **实施：** CLI 复用同一 runtime/use case；`--follow` 使用 SSE/repository event reader，不启动旁路 Agent。
- **重构边界：** 不直接构造 facade/model/storage。
- **验收：** help、disabled、success、failure、resume/cancel 输出稳定且无 secret。
- **提交边界：** CLI 和测试。
- **恢复入口：** 首个 CLI golden mismatch。

```bash
pixi run -e dev pytest packages/apps/tests/unit/test_cli_agent.py -v
pixi run -e dev check
```

### Task 16：R5.1 集成与 eval gate

**依赖：** Tasks 11—15；live profile 另依赖 Approval A4
**风险：** 高风险，PIT/模型质量
**状态：** [x]

- **目标文件或边界：** 30 grounded cases、apps E2E、`docs/evidence/r5/r5.1/**`。
- **RED/观察证据：** 先运行未满足门槛的基线并保存 report；不得手改 grader 让结果变绿。
- **实施：** 覆盖 tool choice、事实、证据、冲突、缺失、PIT、provider failure 和 replay；Fake 为硬门，受控 live model 为独立报告。
- **重构边界：** live 模型失败不影响 deterministic gate；不上传禁止外发 fixture。
- **验收：** tool/evidence ≥95%，factual ≥90%，必需拒答/PIT/replay 100%。
- **提交边界：** fixtures、E2E 和 R5.1 evidence。
- **恢复入口：** 失败率最高的 case family。

```bash
pixi run -e dev pytest packages/apps/tests/e2e/test_agent_evidence_copilot.py -v
pixi run -e dev python -m ditto_agent.evals.runner --suite grounded --provider fake
pixi run -e dev pytest -m pit
pixi run -e dev check
```

**Wave 2 Exit Gate：** R5.1 feature flag 可在本机受控打开；read P95/cost、grounding、PIT、SSE resume 和 provider degradation 有 evidence，所有写工具仍未注册。

### Wave 3：R5.2 Author Copilot

### Task 17：草案、compile、validate 与 diff tools

**依赖：** Wave 2
**风险：** 行为/公共契约
**状态：** [x]

- **目标文件或边界：** `ditto_agent.tools.author`，既有 StrategySpec/DSL application facade；必要时新增 `queries/authoring_preview.py`。
- **RED/观察证据：** unknown node、invalid DSL、类型不匹配、canonical diff、模型夹带代码/解释用例先失败。
- **实施：** 结构化输出只形成草案；由 Ditto compiler/validator 生成诊断和 diff；tool 返回 evidence。
- **重构边界：** Agent 不实现 parser/compiler；不写正式 strategy 状态。
- **验收：** invalid 草案 fail closed，canonical preview 可重放，原有 authoring 合同兼容。
- **提交边界：** author read/draft tools 与 tests。
- **恢复入口：** 第一条 compile/validate golden。

```bash
pixi run -e dev pytest packages/agent/tests/unit/tools/test_author_tools.py packages/application/tests/unit/queries/test_authoring_preview.py -v
pixi run -e dev check
```

### Task 18：HITL interruption、过期与恢复

**依赖：** Tasks 7、13、17
**风险：** 高风险，审批
**状态：** [x]

- **目标文件或边界：** approval runtime/store、API decision route、SDK interruption adapter。
- **RED/观察证据：** approve/reject、过期、hash/args/snapshot/budget 篡改、并发双批、restart resume 用例先失败。
- **实施：** 保存 resumable state 的必要脱敏部分；审批时重新计算 action hash/authority；超时或 storage 不可用 fail closed。
- **重构边界：** Agent-level guardrail 不替代 tool boundary；审批不能修改 proposed action。
- **验收：** 只恢复同一 run；变化后必须新审批；决定 append-only 且可审计。
- **提交边界：** approval lifecycle 与 integration tests。
- **恢复入口：** 第一条 bypass 或 restart case。

```bash
pixi run -e dev pytest packages/agent/tests/unit/test_approval_runtime.py packages/apps/tests/integration/test_agent_approval_resume.py -v
pixi run -e dev check
```

### Task 19：正式写入只经 application command

**依赖：** Task 18
**风险：** 高风险，写行为
**状态：** [ ]

- **目标文件或边界：** consumer-owned application commands、Agent author write tools、mutation idempotency。
- **RED/观察证据：** 未审批、审批 hash 不匹配、重复提交、并发提交、agent 直连 store 的架构测试先失败。
- **实施：** 仅注册设计允许的保存草案/提交 review 等命令；复用 application mutation receipts/idempotency；结果写入 evidence。
- **重构边界：** 不注册 publish/deprecate/reactivate/order/broker 工具。
- **验收：** 所有写入有 command receipt、operator approval、run/episode/audit identity；重复请求不重复副作用。
- **提交边界：** application command 适配、write tools 和 tests。
- **恢复入口：** 第一条 mutation receipt mismatch。

```bash
pixi run -e dev pytest packages/application/tests/unit/commands/test_agent_authoring_commands.py packages/agent/tests/unit/tools/test_author_write_tools.py -v
pixi run -e dev arch-check
pixi run -e dev check
```

### Task 20：R5.2 adversarial 与 eval gate

**依赖：** Tasks 17—19
**风险：** 高风险，权限
**状态：** [ ]

- **目标文件或边界：** 20 author + 对应 permission cases、`docs/evidence/r5/r5.2/**`。
- **RED/观察证据：** 保存初始 compile/bypass/篡改失败报告。
- **实施：** 覆盖 prompt injection、参数夹带、unknown node、approval replay、并发、model/provider failure。
- **重构边界：** 不降低 compiler、governance 或 approval hard gate 换取通过率。
- **验收：** author compile/validate ≥90%；approval bypass 100% 阻断；core regression 全绿。
- **提交边界：** cases 和 R5.2 evidence。
- **恢复入口：** 失败 case family。

```bash
pixi run -e dev python -m ditto_agent.evals.runner --suite author --provider fake
pixi run -e dev python -m ditto_agent.evals.runner --suite permission --provider fake
pixi run -e dev check
```

**Wave 3 Exit Gate：** R5.2 flag 独立于 R5.1；草案可生成和验证，任何正式 mutation 都需要不可变审批，发布/交易工具不存在。

### Wave 4：R5.3 Autonomous Research Campaign

### Task 21：Campaign、SearchLedger、代码和记忆领域合同

**依赖：** Wave 1、Task 1 inventory
**风险：** 高风险，研究公共契约
**状态：** [ ]

- **目标文件或边界：** analysis 固定目录中的四个新叶模块。
- **RED/观察证据：** budget、单一 search axis、lineage、attempt/trial、known_at、holdout memory 禁止规则先失败。
- **实施：** 落地所有 Analysis-owned types；复用既有 identity/content hash/trial family，避免平行概念。
- **重构边界：** analysis 无调度、无模型、无 sandbox I/O。
- **验收：** 不变式在构造时 fail closed；对象可脱离 Agent 使用；无 capability 依赖。
- **提交边界：** 纯研究领域合同和单元测试。
- **恢复入口：** 第一条 domain invariant。

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_campaign.py packages/analysis/tests/unit/experiments/test_search_ledger.py packages/analysis/tests/unit/experiments/test_research_memory.py -v
pixi run -e dev arch-check
pixi run -e dev check
```

### Task 22：Research SQLite schema 与 migration

**依赖：** Task 21 / Approval A2
**风险：** 高风险，schema/migration
**状态：** [ ]

- **目标文件或边界：** 既有 research schema 新版本、campaign/search/memory/code tables、reader/writer protocols。
- **RED/观察证据：** v1→v2 fixture、rollback、unknown future version、immutable conflict、backup/restore 先失败。
- **实施：** 前向 migration 保留现有 R3 数据；新表使用 FK/check/unique 和 append-only event；更新 application_id/user_version 验证。
- **重构边界：** 不新建第二个 analysis DB；不让 Agent 直接使用 analysis reader/writer。
- **验收：** 空库、现有 v1 fixture、失败回滚、重开、备份恢复全部通过。
- **提交边界：** migration/schema/ports/adapters 与 tests。
- **恢复入口：** v1 fixture migration failure。

```bash
pixi run -e dev pytest packages/analysis/tests/unit/storage/test_campaign_schema_migration.py packages/analysis/tests/integration/test_research_database_restore.py -v
pixi run -e dev check
```

### Task 23：Campaign coordinator、授权、预算和恢复

**依赖：** Tasks 18、21、22
**风险：** 高风险，长流程/权限
**状态：** [ ]

- **目标文件或边界：** `autonomous_campaign.py`、provider wiring、Agent campaign tool。
- **RED/观察证据：** immutable hash、预算、两代无改善、lease lost、retry/fork、cancel/restart 用例先失败。
- **实施：** application coordinator 复用现有 experiment scheduler/lease；Agent 只提出 candidate/feedback；host 决定状态和 stopping。
- **重构边界：** CampaignAuthorization 不覆盖 holdout/publish/trading；运行中不能扩预算或搜索轴。
- **验收：** crash resume 不重复 statistical trial；budget exhausted 进入 `PAUSED_BUDGET`；取消幂等。
- **提交边界：** coordinator、ports、tool 和 tests。
- **恢复入口：** 第一条 lease/budget transition。

```bash
pixi run -e dev pytest packages/application/tests/unit/processes/experiments/test_autonomous_campaign.py packages/agent/tests/unit/tools/test_campaign_tool.py -v
pixi run -e dev check
```

### Task 24：生成代码 host contract 与可信 evaluator

**依赖：** Tasks 21、23
**风险：** 高风险，生成代码/回测
**状态：** [ ]

- **目标文件或边界：** `candidate_sandbox_port.py`、`generated_candidate_evaluator.py`、analysis `generated_code.py`。
- **RED/观察证据：** 非法 signature、mutable state、指标/权重/订单输出、不同 seed、schema/size mismatch 用例先失败。
- **实施：** 固定 `fit`/`score`，Arrow/JSON/NumPy allow_pickle=False；宿主提供 visible window，验证输出后调用现有 experiment/backtest/evaluation。
- **重构边界：** Candidate 不能计算或提交正式 metrics；port 由 application consumer 拥有。
- **验收：** 相同 input/state/digest/seed 输出确定；非法输出在进入回测前被拒绝。
- **提交边界：** contract、trusted evaluator 和 fake sandbox tests。
- **恢复入口：** 第一条 protocol validation failure。

```bash
pixi run -e dev pytest packages/application/tests/unit/processes/experiments/test_generated_candidate_evaluator.py packages/analysis/tests/unit/experiments/test_generated_code.py -v
pixi run -e dev check
```

### Task 25：Hardened OCI sandbox adapter

**依赖：** Task 24 / Approval A3
**风险：** 高风险，执行不可信代码/运行依赖
**状态：** [ ]

- **目标文件或边界：** `ditto_apps.registry.agent.oci_sandbox`、固定 Containerfile/image manifest/SBOM、fake adapter。
- **RED/观察证据：** 网络、socket、Docker socket、host/repo mount、secret、root、write rootfs、fork bomb、OOM、timeout、oversize output 攻击先证明被 harness 捕获。
- **实施：** macOS Docker Desktop VM profile；Linux rootless OCI + 优先 gVisor；无网、non-root、read-only、tmpfs、cap-drop、no-new-privileges、seccomp、resource limits、digest pin。
- **重构边界：** 普通 CI 使用 fake；live sandbox acceptance 显式标记；容器内无 package install。
- **验收：** 10 类攻击全部失败且留下 `SandboxExecutionManifest`；sandbox 不可访问 Docker daemon。
- **提交边界：** adapter、image、attack harness 和 evidence 独立提交。
- **恢复入口：** 第一项未被阻断的攻击。

```bash
pixi run -e dev pytest packages/apps/tests/unit/test_oci_sandbox_adapter.py -v
pixi run -e dev pytest packages/apps/tests/integration/test_oci_sandbox_security.py -v -m sandbox_live
pixi run -e dev check
```

### Task 26：PIT fold、purge/embargo、snapshot 与 future sentinel

**依赖：** Tasks 23—25
**风险：** 高风险，PIT/回测
**状态：** [ ]

- **目标文件或边界：** generated evaluator 的 data feed、现有 validation/walk-forward 合同。
- **RED/观察证据：** cutoff 外极值、late revision、same-close fill、cache key 漏 snapshot、fold boundary 用例先失败。
- **实施：** 复用现有 dynamic purge/embargo；完整传播 decision/knowledge/publication/snapshot/execution eligibility；每 candidate/fold fresh sandbox。
- **重构边界：** 不本地发明 `trade_date + 1`；不允许最新 revision fallback。
- **验收：** sentinel 外不影响、边界内可用；不同 snapshot artifact 不碰撞；同收盘不可成交。
- **提交边界：** PIT implementation、sentinel tests 和 evidence。
- **恢复入口：** future sentinel。

```bash
pixi run -e dev pytest packages/application/tests/unit/processes/experiments/test_generated_candidate_pit.py -v
pixi run -e dev pytest -m pit
pixi run -e dev arch-check
pixi run -e dev check
```

### Task 27：隐藏 holdout 与一次性评价

**依赖：** Tasks 22、23、26
**风险：** 高风险，研究治理
**状态：** [ ]

- **目标文件或边界：** 复用 analysis/application holdout authority，新增 Campaign bridge。
- **RED/观察证据：** Agent context/tool/event/memory 暴露 holdout 日期、逐期值或重复 claim 用例先失败。
- **实施：** holdout 独立审批；只返回签名 aggregate pass/fail 和 threshold evidence；消费 append-only 且原子。
- **重构边界：** CampaignAuthorization 不含 holdout；恢复不能重置 consumption。
- **验收：** 一次性、并发和 crash case 不重复；holdout 信息不进入 search memory 或 prompt。
- **提交边界：** holdout bridge、redaction 和 tests。
- **恢复入口：** 第一条 leakage/reuse case。

```bash
pixi run -e dev pytest packages/application/tests/unit/processes/experiments/test_agent_campaign_holdout.py packages/analysis/tests/unit/experiments/test_holdout_isolation.py -v
pixi run -e dev pytest -m pit
pixi run -e dev check
```

### Task 28：候选新颖性与 multiple-testing ledger

**依赖：** Tasks 21、24、26
**风险：** 高风险，统计治理
**状态：** [ ]

- **目标文件或边界：** SearchLedger bridge、candidate novelty checker、既有 trial family/adjustments。
- **RED/观察证据：** AST 等价代码、输出高相关、retry/fork 重置 counter、protocol 改变未新 trial 用例先失败。
- **实施：** canonical AST hash、output correlation、lineage root；operational attempt 与 statistical trial 分离；复用 multiple-testing/PBO/DSR。
- **重构边界：** 模型 critic 不决定统计接受；不以变量改名制造新候选。
- **验收：** retry 不加 trial，唯一 candidate×protocol 只计一次，fork 共享 family counter。
- **提交边界：** novelty/ledger/统计 bridge 和 tests。
- **恢复入口：** 第一条 trial-count mismatch。

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_agent_search_ledger.py packages/application/tests/unit/processes/experiments/test_candidate_novelty.py -v
pixi run -e dev check
```

### Task 29：带 `known_at` 的研究记忆

**依赖：** Tasks 8、21、22、27
**风险：** 高风险，PIT/长期知识
**状态：** [ ]

- **目标文件或边界：** research memory domain/storage、application query/command、Agent memory tool。
- **RED/观察证据：** future outcome、holdout result、未验证模型自评、越 scope 检索、未审批 promotion 用例先失败。
- **实施：** local/family/global scope；backward known_at query；promotion/revoke append-only；默认只写 local 的验证反馈。
- **重构边界：** 不做向量库或开放 RAG；检索使用结构化字段与 evidence refs。
- **验收：** `outcome_known_at <= knowledge_cutoff`；holdout 永不可入库；promotion 有审批和 receipt。
- **提交边界：** memory contracts/storage/use cases/tools/tests。
- **恢复入口：** future memory sentinel。

```bash
pixi run -e dev pytest packages/analysis/tests/unit/experiments/test_research_memory_pit.py packages/application/tests/unit/queries/test_research_memory.py packages/agent/tests/unit/tools/test_memory_tool.py -v
pixi run -e dev pytest -m pit
pixi run -e dev check
```

### Task 30：Campaign API、SSE、CLI 与崩溃恢复

**依赖：** Tasks 23—29
**风险：** 高风险，公共 API/长流程
**状态：** [ ]

- **目标文件或边界：** design §11 campaign routes、apps DTO、CLI campaign commands。
- **RED/观察证据：** create/approve/show/cancel、Idempotency-Key、SSE resume、budget pause、crash lease recovery 用例先失败。
- **实施：** routes/CLI 薄适配；审批显示 immutable manifest hash 和预算；事件从 persisted store 重放。
- **重构边界：** API 不允许 patch 运行中 manifest/budget；无 `resume-with-more-budget` 隐式动作。
- **验收：** lifecycle 与设计状态一致；cancel/recovery 幂等；无 double trial/tool。
- **提交边界：** public surface、integration/E2E tests。
- **恢复入口：** 第一条 lifecycle mismatch。

```bash
pixi run -e dev pytest packages/apps/tests/integration/test_agent_campaign_api.py packages/apps/tests/unit/test_cli_agent_campaign.py -v
pixi run -e dev check
```

### Task 31：R5.3 安全、PIT 与 eval gate

**依赖：** Tasks 21—30
**风险：** 高风险，发布前研究安全
**状态：** [ ]

- **目标文件或边界：** 30 campaign/PIT/holdout、10 sandbox attacks、相关 permission cases、`docs/evidence/r5/r5.3/**`。
- **RED/观察证据：** 保存首轮失败报告，按 failure family 修复生产逻辑或 case 事实，不改低门槛。
- **实施：** 跑 deterministic、PIT、sandbox live 和受控 live-model comparison；验证资源/成本/停止规则。
- **重构边界：** optional LLM critic 只读；不得覆盖宿主 verdict。
- **验收：** PIT/holdout/sandbox escape/forbidden action/approval bypass 100%；Campaign replay 和 ledger 确定。
- **提交边界：** eval cases、evidence 和必要修复各自提交。
- **恢复入口：** 最严重的安全/PIT failure。

```bash
pixi run -e dev python -m ditto_agent.evals.runner --suite campaign --provider fake
pixi run -e dev python -m ditto_agent.evals.runner --suite sandbox --provider fake
pixi run -e dev pytest -m pit
pixi run -e dev pytest -m sandbox_live
pixi run -e dev check
```

**Wave 4 Exit Gate：** 自主研究只在不可变授权和预算内运行；生成代码隔离；宿主独占金融评价；holdout、multiple-testing、known_at 和恢复均有证据。

### Wave 5：R5.4 Decision Briefing

### Task 32：DailyDecision V3 后生成 `DecisionOpinion`

**依赖：** Wave 2、R4 current inventory
**风险：** 高风险，决策解释
**状态：** [ ]

- **目标文件或边界：** Agent `DecisionOpinion`、application `decision_evidence.py`、post-V3 shadow process。
- **RED/观察证据：** 缺 V3/provenance、blocked V3、证据冲突、模型失败用例先失败。
- **实施：** 在 V3 持久化成功之后读取不可变报告并生成解释/异议/不确定性；保存独立 shadow identity。
- **重构边界：** 不改变 V3；不写权重、risk status、action 或 order。
- **验收：** 同一 V3 hash 生成可追踪 opinion；V3 缺失/blocked 时只解释阻塞或拒答。
- **提交边界：** shadow process、tool/contract 和 tests。
- **恢复入口：** V3 evidence fixture。

```bash
pixi run -e dev pytest packages/application/tests/unit/processes/risk/test_agent_decision_briefing.py packages/agent/tests/unit/test_decision_opinion.py -v
pixi run -e dev check
```

### Task 33：证明 shadow 隔离

**依赖：** Task 32
**风险：** 高风险，交易/风控边界
**状态：** [ ]

- **目标文件或边界：** EOD/DailyDecision/portfolio/risk/execution regression 与 import/tool registry。
- **RED/观察证据：** 注入恶意 opinion 试图改变权重、状态、订单或 downstream hash，测试先证明 harness 能观察差异。
- **实施：** opinion 使用独立 store/event namespace；下游无 consumer；机器测试断言无 publish/order/broker tools。
- **重构边界：** 不以“暂不调用”代替依赖隔离，需静态和运行时双证据。
- **验收：** 开/关 shadow 后 DailyDecision V3、建议权重、risk gate、orders byte-identical。
- **提交边界：** isolation guards 和 regression tests。
- **恢复入口：** 首个 downstream diff。

```bash
pixi run -e dev pytest packages/apps/tests/integration/test_agent_shadow_isolation.py packages/application/tests/unit/processes/risk/test_daily_projection.py -v
pixi run -e dev arch-check
pixi run -e dev check
```

### Task 34：Outcome feedback 与 shadow eval

**依赖：** Tasks 29、32、33
**风险：** 高风险，PIT/模型监控
**状态：** [ ]

- **目标文件或边界：** opinion outcome linker、10 shadow eval cases、`known_at` feedback。
- **RED/观察证据：** outcome 在可知前被关联、同日收益泄漏、holdout/未来结果进入 prompt 用例先失败。
- **实施：** 只在结果实际可知后关联 outcome；记录 adoption/accuracy/calibration，不自动提升 memory。
- **重构边界：** feedback 不修改历史 opinion 或 V3；promotion 仍需人工。
- **验收：** future sentinel 100%；10 shadow cases 可重放；无 downstream mutation。
- **提交边界：** feedback、PIT tests 和 R5.4 evidence。
- **恢复入口：** outcome known_at sentinel。

```bash
pixi run -e dev python -m ditto_agent.evals.runner --suite shadow --provider fake
pixi run -e dev pytest -m pit
pixi run -e dev check
```

**Wave 5 Exit Gate：** DecisionOpinion 只读、独立持久化、可做 outcome analysis，核心决策和交易输出完全不变。

### Wave 6：R5.5 发布硬化

### Task 35：OTel、审计、成本和运行指标

**依赖：** Waves 1—5
**风险：** 行为/隐私
**状态：** [ ]

- **目标文件或边界：** Agent OTel instrumentation、apps exporter wiring、metrics/audit redaction。
- **RED/观察证据：** secret/敏感 payload 泄漏、缺 run/tool/approval/cost span、exporter failure 影响业务用例先失败。
- **实施：** 复用现有 OTel；Langfuse 仅可选 exporter；记录设计 §12.3 字段；redaction 在 export 前执行。
- **重构边界：** 不改变 SDK 默认行为后直接上线，明确禁用不受控 trace exporter。
- **验收：** exporter 关闭/失败不影响 run；无 secret/raw prohibited content；cost/latency 可聚合。
- **提交边界：** observability、redaction、tests。
- **恢复入口：** trace privacy golden。

```bash
pixi run -e dev pytest packages/agent/tests/unit/test_observability.py packages/apps/tests/integration/test_agent_otel_wiring.py -v
pixi run -e dev check
```

### Task 36：Retention、feature flags 与降级

**依赖：** Tasks 7、35
**风险：** 高风险，删除/运营
**状态：** [ ]

- **目标文件或边界：** apps Agent settings、retention command/job、runbook tests。
- **RED/观察证据：** 29/30/31 天边界、长保留工件误删、provider/DB/sandbox/exporter unavailable、flags 默认值先失败。
- **实施：** 固定 flags：`DITTO_AGENT_ENABLED`、`DITTO_AGENT_AUTHOR_ENABLED`、`DITTO_AGENT_CAMPAIGN_ENABLED`、`DITTO_AGENT_DECISION_SHADOW_ENABLED`、`DITTO_AGENT_MODEL_CALLS_ENABLED`，全部默认 false；30 天 cleanup 只删允许的 raw content。
- **重构边界：** 删除目标由 typed query 精确解析；不递归删除宽目录；审计/approval/formal artifacts 长期保留。
- **验收：** retention boundary 正确、dry-run 清单可审计、核心 Ditto 在所有 Agent 故障下回归通过。
- **提交边界：** settings/cleanup/degradation/tests，执行真实清理前另审批。
- **恢复入口：** retention dry-run diff。

```bash
pixi run -e dev pytest packages/agent/tests/unit/test_retention.py packages/apps/tests/integration/test_agent_degradation.py packages/apps/tests/unit/test_agent_settings.py -v
pixi run -e dev check
```

### Task 37：120 条正式 eval、SLO 与模型对照

**依赖：** Tasks 16、20、31、34—36；live 对照依赖 Approval A4
**风险：** 发布/模型费用/数据外发
**状态：** [ ]

- **目标文件或边界：** 完整 eval dataset、benchmark runner、`docs/evidence/r5/release/eval-report.*`。
- **RED/观察证据：** 先冻结 case/version/hash 和 grader，再运行 baseline；不删除困难 case。
- **实施：** 跑 30 grounded、20 author、30 campaign/PIT/holdout、20 permission、10 sandbox、10 shadow；balanced/quality 分开报告；计算 P50/P95/cost。
- **重构边界：** Fake 安全硬门与 live 质量报告分开；模型升级不继承旧结果。
- **验收：** 达到设计 §13 全部硬门；普通 read/复杂任务满足延迟和成本；零安全/PIT 回退。
- **提交边界：** 冻结 dataset/grader 后提交，再单独提交结果和经 TDD 的修复。
- **恢复入口：** 最严重 failure family 或预算暂停点。

```bash
pixi run -e dev python -m ditto_agent.evals.runner --suite all --provider fake --output docs/evidence/r5/release/eval-report-fake.json
pixi run -e dev python -m ditto_agent.evals.runner --suite all --provider openai --profile balanced --output docs/evidence/r5/release/eval-report-balanced.json
pixi run -e dev python -m ditto_agent.evals.runner --suite all --provider openai --profile quality --output docs/evidence/r5/release/eval-report-quality.json
pixi run -e dev pytest -m pit
pixi run -e dev pytest -m sandbox_live
```

### Task 38：Release evidence、runbook 与最终审查

**依赖：** Task 37
**风险：** 发布
**状态：** [ ]

- **目标文件或边界：** `docs/evidence/r5/release/**`、runbook、安全说明、OpenAPI/CLI 文档、路线图状态。
- **RED/观察证据：** release preflight 应先对缺失的 gate/evidence/approval/backup/restore/SLO 返回 fail closed。
- **实施：** 完成 backup/restore、crash resume、retention dry-run、provider outage、sandbox outage、feature rollback 演练；执行高风险 diff review。
- **重构边界：** 不因功能完整而自动声明 G4/G5 或自动交易能力；flags 仍默认关闭。
- **验收：** release preflight PASS；无未记录失败；设计、源码、OpenAPI、CLI、import contracts 和 evidence 一致。
- **提交边界：** 文档/evidence/状态更新独立提交；PR 前不混入无关变更。
- **恢复入口：** release preflight 第一项 blocker。

```bash
pixi run -e dev arch-check
pixi run -e dev check
pixi run -e dev ci
git diff --check
git status --short
```

## Approval 点

| ID | 时机 | 必须批准的动作 | 获批证据 |
|---|---|---|---|
| A1 | Task 4 前 | 新 `ditto_agent` 包边界、`.importlinter` 规则、精确 `openai-agents` 生产版本范围 | `docs/evidence/r5/preflight/approvals.md`，GRANTED rev2 |
| A2 | Tasks 7、22 前 | Agent SQLite v1、Research SQLite migration、备份/恢复和 retention schema | 同上，scoped GRANTED；最终 DDL hash 待追加 |
| A3 | Task 25 前 | OCI/gVisor runtime、固定 image digest/SBOM、新运行依赖和安全 profile | 同上，PENDING |
| A4 | 任何 live model 调用前 | 专用 OpenAI project、MAM/ZDR、凭证、预算、license/egress class 和允许数据集 | 同上，PENDING |

历史 2026-08-04 对 `openai-agents` 的原则性批准不能替代 A1 的当前版本/API/transitive 证据。Langfuse 不作为生产必需依赖；如后续新增，同样按新生产依赖审批。

## 波次 Exit Gates

| Wave | Exit Gate |
|---|---|
| 0 | 当前合同、SDK/OCI 和 approval 事实可审计，无猜测签名 |
| 1 / R5.0 | 第 13 包、状态/approval、provider、DB、PIT、Episode/replay、eval harness 全绿 |
| 2 / R5.1 | Grounded read 达标，PIT/证据/SSE/degradation 完整，无写工具 |
| 3 / R5.2 | Author compile 达标，正式 mutation 全部 HITL+idempotent，无 publish/trading |
| 4 / R5.3 | Campaign 授权/预算、沙箱、PIT、holdout、ledger、memory 和恢复硬门全过 |
| 5 / R5.4 | DecisionOpinion shadow-only，开关前后核心交易输出完全一致 |
| 6 / R5.5 | 120 eval、SLO、成本、retention、备份恢复、runbook、CI 和 review 全过 |

每个生产 Python Wave 至少运行：

```bash
pixi run -e dev arch-check
pixi run -e dev check
git diff --check
```

涉及 PIT 的 Wave 额外运行：

```bash
pixi run -e dev pytest -m pit
```

PR 前运行：

```bash
pixi run -e dev ci
git diff --check
```

## 发布硬门

- forbidden action、future sentinel、approval bypass、holdout leak、sandbox escape：100%。
- tool choice、evidence coverage：≥95%。
- factual correctness：≥90%。
- required abstention：100%。
- Author compile/validate：≥90%。
- Episode tool/event replay：100%。
- Read P95 ≤30 秒且 ≤0.25 美元；复杂任务 P95 ≤60 秒且 ≤0.75 美元。
- flags 默认关闭；Agent 任意依赖不可用不影响核心 Ditto。
- 多 Agent 不在本计划实施范围；只有设计文档 §13.4 门槛达到后另立 ADR。

## 恢复状态

- **已完成：** Wave 0 / Tasks 1—3。`b5dbb921` 冻结 application/analysis/apps 当前合同；`92cf88ea` 冻结 SDK、模型、数据控制与 OCI 技术证据；`394ca7df` 记录 A1—A4 exact scope。Wave 1 / Task 4 由 `406f8d4e` 建立第 13 个包、`openai-agents==0.20.0` 三平台 lock 和 43 条 import-linter 机器合同；Task 5 由 `e65445bd` 落地冻结 runtime/PIT/evidence/approval 合同、canonical codec、状态机及篡改测试；Task 6 由 `ee1941ae` 落地 shared `AgentModelPort`、scripted Fake、零网络 OpenAI Agents adapter、A4 fail-closed apps registry 和 usage/interruption/continuation 映射；Task 7 由 `be530cb5` 落地 Agent SQLite v1、typed reader/writer、幂等、lease/fence、append-only audit chain、备份恢复及 apps lifecycle；Task 8 由 `a9740d23` 落地 server-only temporal factory、全字段 cache identity、默认 deny-all license/egress gate 和 tamper/context-bound model evidence codec；Task 9 由 `ff15f7fa` 落地 versioned Episode manifest、严格 codec、terminal run/event binding、immutable SQLite seal、100 次稳定性证明和无 live model/无副作用 replay，`8f91dda1` 冻结最终 A2 Agent DDL/hash artifact；Task 10 由 `b31d000c` 落地 versioned local eval case、deterministic/rule-based grader、不可覆盖安全结论的 optional critic、byte-stable report 和 Fake runner，完成 Wave 1 Exit Gate。Wave 2 / Task 11 由 `df9abcd8` 落地 research/decision evidence typed read facades、严格 identity/snapshot/PIT fail-closed、JSON-only immutable payload、deterministic hash 和 provider DI；Task 12 由 `c3642d0e` 落地七个 read-only function tools、host-only temporal injection、精确可收窄 allowlist、sealed `EvidenceEnvelope`、逐 claim grounding/refusal，并以 application pure Protocol 切断 Agent 到 capability 的传递依赖；Task 13 由 `4610e15d` 落地 deterministic 单 Agent host loop、turn/token/cost/time/retry 预算、authority/context/schema/tool guardrails、provider call ID 对账、结构化拒答、失败后完整工具事件链和 terminal Episode；Task 14 由 `8cdd7df0` 落地 session/run/approval HTTP DTO 与薄 route、durable idempotency、revision-fenced cancel、原子 cancel event、persisted-only SSE/Last-Event-ID replay、OpenAPI/maturity registration，以及默认 disabled fail-closed runtime；Task 15 由 `30f1e062` 落地复用 `AgentRuntimePort` 的 `run/show/events/cancel/approve/reject` CLI、稳定 JSON/human 输出与 typed exit codes、revision-fenced cancel、exact action-hash approval，以及只读持久事件的 cursor/follow 恢复；Task 16 由 `c0b07ab5` 落地固定 seed 的 30 例 grounded v2 数据集、不可覆盖的质量/性能阈值、实际 provider observation grading、Fake 主机工具链 E2E、PIT/provider failure/replay 覆盖及 baseline/final/live-status 审计证据，完成 Wave 2 Exit Gate；A4 pending 的 live model 独立报告保持 `not_run`。Wave 3 / Task 17 由 `ac6098c3` 落地 legacy/V2 兼容的 side-effect-free authoring preview facade、Ditto NodeRegistry/ExpressionCompiler 诊断、exact-base canonical validate/diff、四个 sealed no-approval Agent tools、provider DI 与代码/解释夹带及 payload 篡改拦截；Task 18 由 `36fcf49b` 落地本地 continuation 严格 codec、hash-bound action/authority/context/budget 复核、append-only decision/audit、整批审批、单恢复 lease、宿主超时、并发一次恢复、restart retry、API decision 恢复和未装配时 fail-closed。
- **下一步：** Wave 3 / Task 19，先建立未审批、action hash 不匹配、重复/并发提交和 Agent 直连 store 的 RED，再让正式 author 写入只经 consumer-owned application command 与 mutation receipt/idempotency。
- **未解决风险：** A3 因无可用 daemon/runtime/image digest/SBOM 保持 pending；A4 因无专用 OpenAI project、MAM/ZDR、允许数据集和预算保持 pending；A2 的 Agent v1 final artifact 已冻结，Research v2 artifact 仍须在 Task 22 追加，所有真实用户数据库 mutation 仍未授权。
- **最新命令与结果：** Task 18 先观察 approval runtime 缺失、orchestrator 无 suspender、并发 loser 读取已消费 continuation、漂移后错误终态、Fake 拒绝调用仍执行、宿主超时缺失和恢复器未装配仍写决定等 RED；最终目标命令 19 passed，覆盖 approve/reject、expiry、action/continuation/args/authority/snapshot/budget tamper、敏感 continuation、并发整批一次恢复、restart、provider/storage failure 与 API 恢复；最终 `pixi run -e dev check` 为 lint/fmt/type 通过、12,514 passed / 1 个既有 xfail、43 kept / 0 broken、architecture smells 通过、Harness validation 与 16 项 Harness tests 通过；`git diff --check` 通过。
- **外部等待或 approval：** A1 已授权 Task 4；A2 scoped authorization 已授权临时 schema 实现/测试。A3 只阻塞 Task 25 live acceptance，A4 只阻塞任何 live model 调用；Fake provider 工作可继续。
