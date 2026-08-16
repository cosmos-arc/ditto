# R5 当前合同清单

**核对日期：** 2026-08-16
**代码基线：** `69967f97`
**范围：** R5.1 Evidence、R5.2 Author、R5.3 Campaign、R5.4 Decision Briefing 的既有消费面
**结论：** 既有 R3/R4 合同可以作为底层事实源，但不能原样全部注册为 Agent 工具。R5 需要两个 PIT-safe evidence facade、一个 authoring preview facade、Campaign 新领域/编排合同和一个 shadow opinion process。

## 核对方法

从定义符号的叶模块核对类型和签名，不把跨包 re-export 当成事实源：

```bash
rg -n "DailyDecisionV3|Experiment|Holdout|TrialLedger|StrategySpec|FactorEvaluation|RiskGate" \
  packages/application/src packages/analysis/src packages/apps/src
rg -n "^class |^    def |^    async def |^def " \
  packages/application/src/ditto_application/queries \
  packages/application/src/ditto_application/processes/experiments \
  packages/analysis/src/ditto_analysis/experiments
```

设计中提到的 `DailyDecisionV3QueryFacade`、Experiment、Holdout、TrialLedger、StrategySpec、FactorEvaluation 均存在。`ResearchEvidenceQueryFacade`、`DecisionEvidenceQueryFacade`、`AuthoringPreviewFacade`、Campaign/Memory/GeneratedCode、`DecisionOpinionProcess` 不存在，下面给出新增裁决。

## 所有权与依赖裁决

| 能力 | owner / provider | R5 直接 consumer | 跨边界合同 | 裁决 |
|---|---|---|---|---|
| Agent runtime、tools、Agent SQLite、eval | `ditto_agent` | apps API/CLI | Agent-owned contracts、model/store ports | 新增 `packages/agent`；只依赖 application |
| 研究/策略/回测 evidence 聚合 | `ditto_application.queries` | `ditto_agent.tools` | `ResearchEvidenceQueryFacade` 的 typed read models | 新增；隔离 unsafe latest/raw artifact 路径 |
| 组合/风险/DailyDecision evidence 聚合 | `ditto_application.queries` | `ditto_agent.tools` | `DecisionEvidenceQueryFacade` 的 typed read models | 新增；强制显式决策身份和 provenance |
| StrategySpec compile/validate/diff/preview | `ditto_application.queries` | `ditto_agent.tools` | `AuthoringPreviewFacade` | 新增薄 facade；复用 strategy validator/canonical diff |
| Experiment/Holdout/TrialLedger | `ditto_analysis.experiments` + application processes | Campaign coordinator | analysis protocols、application process DTO | 复用，不允许 agent 直连 analysis |
| Campaign/生成代码/研究记忆 | `ditto_analysis.experiments` | application Campaign coordinator | analysis-owned immutable types/protocols | 新增领域对象和研究 SQLite v2 |
| 沙箱执行 | application consumer-owned port；apps adapter | application evaluator | `CandidateSandboxPort` | 新增；物理 OCI 命令仅在 apps registry |
| DecisionOpinion | application process + agent output contract | apps/agent | `DecisionOpinion`、shadow store port | 新增；只消费已完成 V3，不修改 V3 或交易事实 |
| 物理装配 | `ditto_apps.registry.agent` | apps routes/CLI | provider/config factories | 新增；API route 不直连 SQLite |

依赖方向固定为 `apps -> agent -> application -> capabilities`。`ditto_agent` 禁止直接导入 `analysis`、`data`、`features`、`strategy`、`portfolio`、`risk`、`execution`、`backtest` 或 `apps`。

## R5.1 Evidence Copilot

### 研究与 Experiment

| 既有叶合同 | 当前签名/数据 | PIT 与完整性 | R5 裁决 |
|---|---|---|---|
| `ditto_application.queries.experiments.ExperimentQueryFacade` | `list_experiments()`、`get(experiment_id)`、`get_gate(experiment_id, evaluation_id)`、`list_gate_evaluations(experiment_id)`、`list_artifacts(experiment_id)`、`get_review_packet(experiment_id)`、`resolve_experiment_id_by_spec_hash(spec_hash)` | detail 包含 snapshot、fold protocol/hash、candidate/fold/selection；reader 对部分根、跨 experiment gate、并发修订 fail closed | 复用为 `ResearchEvidenceQueryFacade` 的内部 provider；Agent 不直接获得无界 list/raw artifact |
| `ditto_application.queries.evaluation.FactorEvaluationFacade` | `evaluate(factor_id, version: int | None = None, *, options: EvaluationOptions)`；options 含 `dataset_id`、`catalog_snapshot_id`、universe、cost | `version=None` 会解析 offline latest；缺少 Agent temporal context、publication cutoff 和 source snapshot 一致性检查 | 不直接注册工具。新增 facade 必须要求显式 factor version、dataset/snapshot 和 cutoff；禁止走 `None` fallback |
| `ditto_application.queries.backtest.BacktestQueryFacade` | `list_runs(...)`、`get_run(run_id)`、`get_trades(...)`、`get_report(run_id)`、`get_replay_proof(run_id)`、`get_replay_evidence_summary(...)`、NAV/benchmark reads | run summary 有 strategy version；report/proof 是 raw mapping，接口未统一声明 knowledge/publication cutoff、source snapshot | 仅由新 facade 读取已冻结 run/artifact，并校验 run identity、strategy version、snapshot、cutoff、replay hash 完整后才形成 evidence |

新增 `ditto_application.queries.research_evidence.ResearchEvidenceQueryFacade` 的理由：现有三个 facade 分别面向 UI/通用应用读取，存在 `latest`、可选版本、无界列表和 raw mapping。Agent 需要一次 fail-closed 的聚合入口，把显式 `TemporalToolContext` 绑定到 experiment/candidate/fold、factor version、strategy version、dataset/source snapshot、knowledge/publication cutoff 和 artifact hashes。

### Portfolio、Risk 与 DailyDecision V3

| 既有叶合同 | 当前签名/数据 | PIT 与完整性 | R5 裁决 |
|---|---|---|---|
| `ditto_application.queries.daily_decision_v3.DailyDecisionV3QueryFacade` | `get_report_v3(*, strategy_id, trade_date=None, account_id=None)` | 返回 V2、readiness、blocking reasons、portfolio/tail/factor/stress/reconciliation 以及 `ProvenanceSection(decision_time, knowledge_cutoff, publication_cutoff, source_snapshot_ids, generated_at)` | 复用为权威 briefing 输入；Agent 路径要求显式 trade date/account，并核对 provenance 完整性 |
| `DailyDecisionV3ProjectionReader` | `get_latest(*, strategy_id, trade_date, account_id, sleeve_id)` | 注释称 exact identity，但字段允许 `None`；默认 reader 返回无 evidence 并阻塞 readiness | 不直接暴露；由 V3 facade 和新 decision facade 封装 |
| `ditto_application.queries.account.AccountBaselineQuery` | `get_latest(*, account_id, strategy_id, signal_date)` | 只选 `snapshot_date <= signal_date`，带 account/strategy/sleeve identity | 可作为新 decision facade 内部事实源；必须再绑定 source snapshot/cutoff |
| `ditto_application.queries.portfolio_actual.PortfolioActualQueryFacade` | latest positions、date-filtered history/fills、effective fills/adjustments、`compute_pnl(strategy_id, snapshot_date)` | `get_latest_positions` 使用当前最大 snapshot date；history/fills 的时间过滤不等于 knowledge cutoff；无 source snapshot | 禁止直接注册 Agent 工具；仅允许新 facade 的显式 as-of 投影 |
| `ditto_application.processes.risk.daily_projection.DailyRiskProjectionInput` | decision/knowledge/publication 时间、source snapshot ids 以及风险/组合证据；`DailyRiskProjectionProcess.build_and_persist(...)` | 是 V3 shadow projection 的完整 provenance 来源 | 复用已持久化投影，不从 Agent 重新计算或写风险事实 |

新增 `ditto_application.queries.decision_evidence.DecisionEvidenceQueryFacade` 的理由：portfolio/risk 的通用查询允许 latest/可选日期，不能满足 Agent 的 fail-closed temporal contract。新 facade 必须要求 strategy/trade-date/account/sleeve identity，验证 V3 readiness 和 provenance，输出只读 `EvidenceEnvelope` 输入，不允许 Agent 选择或覆盖 temporal context。

### Evidence 工具消费面

R5.1 初始工具只允许下列 typed 读取：

| 工具意图 | application provider | 必填身份/PIT 字段 | 缺失行为 |
|---|---|---|---|
| 获取 experiment/candidate/fold/gate/review evidence | `ResearchEvidenceQueryFacade` | experiment id、snapshot、knowledge/publication cutoff；需要时 strategy/factor version | fail closed，不回退 latest |
| 获取冻结 backtest/replay evidence | `ResearchEvidenceQueryFacade` | run id、strategy version、dataset/source snapshot、cutoff | raw artifact、hash 或 lineage 不完整即拒答 |
| 获取 factor evaluation evidence | `ResearchEvidenceQueryFacade` | factor id + exact version、dataset/catalog snapshot、cutoff | version 不可省略 |
| 获取 portfolio/risk/V3 evidence | `DecisionEvidenceQueryFacade` | strategy、trade date、account/sleeve、decision/knowledge/publication、source snapshots | readiness blocked 或 provenance 不完整即拒答 |

工具结果由 `ditto_agent` 包装成 `EvidenceEnvelope`；application 不依赖 Agent 类型。工具不得注册 publish、weights、orders、broker、通用 SQL、文件系统或网络读取。

## R5.2 Author Copilot

| 既有叶合同 | 当前能力 | 缺口与裁决 |
|---|---|---|
| `ditto_application.queries.strategy.StrategyQueryFacade` | `get_spec(strategy_id, version=None)`、`get_version_detail(...)`、versions/events/reviews；`validate_spec(strategy_id, version, spec_json)` 返回 canonical/base hash、changed、valid/errors；`diff_version(strategy_id, version)` 返回 parent diff | validate/diff 可复用，但 get 的可选 version 不能进入 Agent PIT path；现有 diff 是已保存版本相对 parent，不是任意草案 preview |
| StrategySpec canonical builder/validator | canonical payload/hash、typed validation 错误 | 作为 compile/validate 内核复用；不在 Agent 内复制 DSL 语义 |

新增 `ditto_application.queries.authoring_preview.AuthoringPreviewFacade`：输入 exact base strategy/version 和 candidate payload，输出 compile result、canonical hash、validation errors、candidate-vs-base field diff 和无副作用 preview。它不保存草案、不提交 review、不 publish。正式 author write 若后续注册，必须走 application command 且每个 action hash 单独 HITL；R5 永不注册 publish。

## R5.3 Autonomous Research Campaign

### 可复用合同

| 既有叶合同 | 当前能力 | R5 用法 |
|---|---|---|
| `ditto_analysis.experiments.models` | Experiment/Candidate/Fold/Attempt/Snapshot/StrategyVersion/ContentHash typed identities、状态与转换 | 保留为实验事实和运行身份；Campaign 不复制 Experiment aggregate |
| `ditto_analysis.experiments.specs` | `CandidateSpec`、`CandidateExecutionBinding`、`FoldProtocolSpec`、`ExperimentBudget`、`ExperimentLaunchSpec` | Campaign coordinator 将批准 manifest 编译为既有 launch spec；snapshot/fold/budget 明确传播 |
| `ditto_analysis.experiments.trial_ledger.TrialLedger` | immutable statistical trial 与 operational attempt 计数、canonical hashes | `SearchLedger` 必须以其 trial identity 计数；retry/fork 不重置统计 trial/family counter |
| `ditto_analysis.experiments.holdout.HoldoutClaimAuthorityCommand` | 一次性 holdout authority command/receipt | 独立审批后复用；CampaignAuthorization 永不隐含 holdout 权限 |
| `ditto_analysis.experiments.protocols.ExperimentReaderProtocol` / `ExperimentWriterProtocol` | experiment projection、fold claim、attempt、selection、atomic holdout claim、scheduler lease | application coordinator 的持久化边界；Agent 不导入这些 analysis protocols |
| `ditto_application.processes.experiments.coordinator.ExperimentExecutionCoordinator` | `tick(occurred_at)`、holdout claim、checkpoint、lease/dispatch | 复用为底层 experiment 执行，不把模型放入 scheduler authority |
| `ditto_application.processes.experiments.holdout.HoldoutClaimProcess` | typed request/receipt、selection evidence、原子 claim/replay | 作为独立 HITL action，不向模型泄露逐期 holdout 数据 |

### 必须新增的合同

| owner | 合同 | 必需语义 |
|---|---|---|
| analysis | `ResearchCampaignManifest`、`HypothesisSpec`、`ResearchFeedback` | 预注册 objective/metric/snapshot/PIT/single search axis/budgets/stopping rule/lineage；feedback 排除 holdout |
| analysis | `SearchLedger` | operational attempts 与 unique `candidate_hash × validation_protocol_hash` 分离；fork/retry 共享 lineage/family counter |
| analysis | `ResearchCodeArtifact`、`SandboxExecutionManifest` | AST/code/dependency/image/input/output hashes、schemas、seed/resource/exit/attestation；禁止可信绩效字段 |
| analysis | `KnowledgeItem` / research memory | scope、claim、evidence、`outcome_known_at`、snapshot、append-only status/promotion；PIT read fail closed |
| application | `AutonomousCampaignProcess` | 验证 authorization hash/expiry/allowlist/budgets/lease；驱动 hypothesis→candidate→sandbox→trusted evaluation→feedback；模型不决定状态 |
| application | `CandidateSandboxPort` | consumer-owned request/result；只交换冻结输入、code artifact、runtime manifest 和 score artifact |
| application | `GeneratedCandidateEvaluator` | 宿主计算 folds/cost/risk/statistics/evidence；拒绝生成代码自报收益、风险、权重或订单 |

## R5.4 Decision Briefing

`DailyDecisionV3Report` 是唯一权威输入。新增 application `DecisionOpinionProcess` 在 V3 完成后调用 Agent，验证完整 provenance 后持久化 shadow-only `DecisionOpinion`。意见包含解释、异议、逐项 evidence refs、不确定性和 shadow outcome identity；不得改变 V3 readiness、组合/风险投影、权重、订单或执行。失败只记录 unavailable/failed shadow 状态，不能阻塞 DailyDecision。

## apps registry 现状与装配映射

当前 query providers 定义于 application provider 叶模块并由 apps registry 初始化：

| provider | 当前提供 | R5 裁决 |
|---|---|---|
| `ditto_application.providers_strategy.AppStrategyQueryProvider` | Strategy、Experiment、Backtest query facade | 添加 research/authoring evidence 的 application provider wiring；物理 reader 仍由 apps 注入 |
| `ditto_application.providers_market.AppMarketQueryProvider` | FactorEvaluation | 由 research evidence facade 组合，不让 agent 直接 resolve offline latest |
| `ditto_application.providers_portfolio.AppPortfolioQueryProvider` | Account、PortfolioActual、DailyDecision V3 | 添加 decision evidence facade |
| `ditto_apps.registry.infra.risk_persistence.RiskPersistenceProvider` | durable V3 projection reader | 继续作为 fail-closed V3 物理 reader |
| `ditto_apps.registry.infra.init_providers` / container | composition root 初始化 | 新增 `ditto_apps.registry.agent`，装配 model、Agent DB、OTel 和 sandbox；非 registry 代码不得构造物理 adapter |

## 明确 missing 映射与恢复入口

| 顺序 | missing symbol | 固定目标位置 | 首个消费方 | 后续 Task |
|---:|---|---|---|---:|
| 1 | `ditto_agent` 包及机器边界 | `packages/agent/**` | apps registry | 4 |
| 2 | Agent contracts/runtime/model/storage/eval | `packages/agent/src/ditto_agent/**` | apps API/CLI | 5—10 |
| 3 | `ResearchEvidenceQueryFacade` | `ditto_application.queries.research_evidence` | agent evidence tools | 11 |
| 4 | `DecisionEvidenceQueryFacade` | `ditto_application.queries.decision_evidence` | agent decision tools/opinion | 11、27 |
| 5 | `AuthoringPreviewFacade` | `ditto_application.queries.authoring_preview` | agent author tools | 16 |
| 6 | Campaign/search/generated-code/memory domain | `ditto_analysis.experiments.*` | application campaign process | 17—22 |
| 7 | `CandidateSandboxPort` / evaluator / campaign process | `ditto_application.processes.experiments.*` | agent campaign tools | 18—26 |
| 8 | `DecisionOpinionProcess` | `ditto_application.processes.*` | post-V3 apps job | 27 |
| 9 | Agent API/SSE/CLI/registry | `ditto_apps.*` | local operator | 28—31 |

Task 1 不改生产代码。恢复入口是上表第一项 missing（Task 4）；先继续 Task 2 冻结依赖/runtime 证据。
